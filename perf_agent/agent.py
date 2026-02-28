"""CLI for the perf_agent utilities."""
import argparse
import json
import shutil
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

from perf_agent.blazemeter import BlazeMeterClient
from perf_agent.jmeter_utils import (
    add_constant_timer,
    add_csv_dataset,
    add_http_sampler_full,
    add_regex_extractor,
    add_response_assertion,
    add_simple_result_collector,
    add_thread_group,
    create_jmx_template,
    find_threadgroup_hashTree_by_name,
    save_jmx,
)
from perf_agent.result_parser import build_performance_report, parse_jtl


def _split_csv_values(raw: str):
    return [item.strip() for item in (raw or '').split(',') if item.strip()]


def _parse_key_value_pairs(pairs):
    data = {}
    for pair in pairs or []:
        if '=' not in pair:
            raise ValueError(f'Expected key=value format but got: {pair}')
        key, value = pair.split('=', 1)
        data[key.strip()] = value.strip()
    return data


def _parse_regex_entries(entries):
    results = []
    for entry in entries or []:
        if ':' not in entry:
            raise ValueError(f'Expected ref:regex format but got: {entry}')
        ref, regex = entry.split(':', 1)
        results.append((ref.strip(), regex))
    return results


def _load_scenario_definition(path: str) -> Dict[str, Any]:
    with open(path, 'r', encoding='utf-8') as fh:
        content = fh.read()

    # JSON is valid YAML subset and works without extra dependencies.
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    try:
        import yaml  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            'YAML scenario parsing requires PyYAML. Install with `pip install pyyaml`, '
            'or provide the same scenario in JSON format.'
        ) from exc

    data = yaml.safe_load(content)  # type: ignore[name-defined]
    if not isinstance(data, dict):
        raise ValueError('Scenario file must contain a top-level object/map.')
    return data


def _build_http_sampler_element(
    *,
    name: str,
    domain: str,
    path: str,
    method: str = 'GET',
    protocol: str = 'https',
    port: Optional[int] = None,
    params: Optional[Dict[str, Any]] = None,
    body: Optional[str] = None,
    post_type: str = 'raw',
) -> ET.Element:
    sampler = ET.Element(
        'HTTPSamplerProxy',
        {'guiclass': 'HttpTestSampleGui', 'testclass': 'HTTPSamplerProxy', 'testname': name},
    )
    ET.SubElement(sampler, 'stringProp', {'name': 'HTTPSampler.domain'}).text = domain
    if port is not None:
        ET.SubElement(sampler, 'stringProp', {'name': 'HTTPSampler.port'}).text = str(port)
    ET.SubElement(sampler, 'stringProp', {'name': 'HTTPSampler.protocol'}).text = protocol
    ET.SubElement(sampler, 'stringProp', {'name': 'HTTPSampler.path'}).text = path
    ET.SubElement(sampler, 'stringProp', {'name': 'HTTPSampler.method'}).text = method.upper()

    args_el = ET.Element('elementProp', {'name': 'HTTPsampler.Arguments', 'elementType': 'Arguments'})
    collection = ET.SubElement(args_el, 'collectionProp', {'name': 'Arguments.arguments'})
    for key, value in (params or {}).items():
        arg = ET.SubElement(collection, 'elementProp', {'name': str(key), 'elementType': 'HTTPArgument'})
        ET.SubElement(arg, 'stringProp', {'name': 'Argument.name'}).text = str(key)
        ET.SubElement(arg, 'stringProp', {'name': 'Argument.value'}).text = str(value)
        ET.SubElement(arg, 'boolProp', {'name': 'HTTPArgument.always_encode'}).text = 'false'
    sampler.append(args_el)

    if body is not None:
        ET.SubElement(sampler, 'stringProp', {'name': 'HTTPSampler.postBodyRaw'}).text = 'true' if post_type == 'raw' else 'false'
        body_el = ET.Element('elementProp', {'name': 'HTTPsampler.PostBody', 'elementType': 'HTTPArgument'})
        ET.SubElement(body_el, 'stringProp', {'name': 'Argument.name'})
        ET.SubElement(body_el, 'stringProp', {'name': 'Argument.value'}).text = body
        ET.SubElement(body_el, 'boolProp', {'name': 'HTTPArgument.always_encode'}).text = 'false'
        sampler.append(body_el)

    return sampler


def _build_header_manager(name: str, headers: Dict[str, Any]) -> ET.Element:
    hm = ET.Element('HeaderManager', {'guiclass': 'HeaderPanel', 'testclass': 'HeaderManager', 'testname': name})
    coll = ET.SubElement(hm, 'collectionProp', {'name': 'HeaderManager.headers'})
    for key, value in headers.items():
        item = ET.SubElement(coll, 'elementProp', {'name': str(key), 'elementType': 'Header'})
        ET.SubElement(item, 'stringProp', {'name': 'Header.name'}).text = str(key)
        ET.SubElement(item, 'stringProp', {'name': 'Header.value'}).text = str(value)
    return hm


def _build_response_assertion_element(field: str, pattern: str, name: str) -> ET.Element:
    assertion = ET.Element(
        'ResponseAssertion',
        {'guiclass': 'AssertionGui', 'testclass': 'ResponseAssertion', 'testname': name},
    )
    ET.SubElement(assertion, 'stringProp', {'name': 'Assertion.test_field'}).text = field
    ET.SubElement(assertion, 'stringProp', {'name': 'ResponseAssertion.pattern'}).text = pattern
    return assertion


def _build_regex_extractor_element(ref_name: str, regex: str, name: str) -> ET.Element:
    reg = ET.Element(
        'RegexExtractor',
        {'guiclass': 'RegexExtractorGui', 'testclass': 'RegexExtractor', 'testname': name},
    )
    ET.SubElement(reg, 'stringProp', {'name': 'RegexExtractor.useHeaders'}).text = 'false'
    ET.SubElement(reg, 'stringProp', {'name': 'RegexExtractor.refname'}).text = ref_name
    ET.SubElement(reg, 'stringProp', {'name': 'RegexExtractor.regex'}).text = regex
    ET.SubElement(reg, 'stringProp', {'name': 'RegexExtractor.template'}).text = '$1$'
    ET.SubElement(reg, 'stringProp', {'name': 'RegexExtractor.match_number'}).text = '1'
    ET.SubElement(reg, 'stringProp', {'name': 'RegexExtractor.default'}).text = ''
    return reg


def _scenario_template_payload(
    *,
    application: str,
    domain: str,
    protocol: str,
    threads: int,
    ramp: int,
    duration: int,
    result_jtl: str,
) -> Dict[str, Any]:
    return {
        'test_name': f'{application} Scenario',
        'defaults': {
            'domain': domain,
            'protocol': protocol,
            'headers': {'Accept': 'application/json'},
            'threads': threads,
            'ramp': ramp,
            'duration': duration,
        },
        'csv': {'path': 'data/users.csv', 'vars': 'user,pass'},
        'timer_ms': 500,
        'thread_groups': [
            {
                'name': 'Primary Users',
                'threads': threads,
                'ramp': ramp,
                'duration': duration,
                'transactions': [
                    {
                        'name': 'Launch',
                        'method': 'GET',
                        'path': '/',
                        'assert': {'field': 'ResponseCode', 'pattern': '200'},
                    },
                    {
                        'name': 'Login',
                        'method': 'POST',
                        'path': '/api/login',
                        'params': {'username': '${user}', 'password': '${pass}'},
                        'assert': {'field': 'ResponseCode', 'pattern': '200'},
                        'extractor': {'ref': 'sessionToken', 'regex': '"token":"(.*?)"'},
                        'think_time_ms': 1000,
                    },
                    {
                        'name': 'Search',
                        'method': 'GET',
                        'path': '/api/search',
                        'params': {'q': 'bike'},
                        'assert': {'field': 'ResponseCode', 'pattern': '200'},
                    },
                ],
            }
        ],
        'result_jtl': result_jtl,
    }


def _render_scenario_template_yaml(payload: Dict[str, Any]) -> str:
    # Keep deterministic ordering and formatting to make the starter file readable.
    defaults = payload['defaults']
    tg = payload['thread_groups'][0]
    tx = tg['transactions']
    login_params = tx[1]['params']
    search_params = tx[2]['params']
    return (
        f'test_name: "{payload["test_name"]}"\n'
        'defaults:\n'
        f'  domain: "{defaults["domain"]}"\n'
        f'  protocol: "{defaults["protocol"]}"\n'
        '  headers:\n'
        '    Accept: "application/json"\n'
        f'  threads: {defaults["threads"]}\n'
        f'  ramp: {defaults["ramp"]}\n'
        f'  duration: {defaults["duration"]}\n'
        'csv:\n'
        f'  path: "{payload["csv"]["path"]}"\n'
        f'  vars: "{payload["csv"]["vars"]}"\n'
        f'timer_ms: {payload["timer_ms"]}\n'
        'thread_groups:\n'
        f'  - name: "{tg["name"]}"\n'
        f'    threads: {tg["threads"]}\n'
        f'    ramp: {tg["ramp"]}\n'
        f'    duration: {tg["duration"]}\n'
        '    transactions:\n'
        f'      - name: "{tx[0]["name"]}"\n'
        f'        method: "{tx[0]["method"]}"\n'
        f'        path: "{tx[0]["path"]}"\n'
        '        assert:\n'
        f'          field: "{tx[0]["assert"]["field"]}"\n'
        f'          pattern: "{tx[0]["assert"]["pattern"]}"\n'
        f'      - name: "{tx[1]["name"]}"\n'
        f'        method: "{tx[1]["method"]}"\n'
        f'        path: "{tx[1]["path"]}"\n'
        '        params:\n'
        f'          username: "{login_params["username"]}"\n'
        f'          password: "{login_params["password"]}"\n'
        '        assert:\n'
        f'          field: "{tx[1]["assert"]["field"]}"\n'
        f'          pattern: "{tx[1]["assert"]["pattern"]}"\n'
        '        extractor:\n'
        f'          ref: "{tx[1]["extractor"]["ref"]}"\n'
        f'          regex: "{tx[1]["extractor"]["regex"]}"\n'
        f'        think_time_ms: {tx[1]["think_time_ms"]}\n'
        f'      - name: "{tx[2]["name"]}"\n'
        f'        method: "{tx[2]["method"]}"\n'
        f'        path: "{tx[2]["path"]}"\n'
        '        params:\n'
        f'          q: "{search_params["q"]}"\n'
        '        assert:\n'
        f'          field: "{tx[2]["assert"]["field"]}"\n'
        f'          pattern: "{tx[2]["assert"]["pattern"]}"\n'
        f'result_jtl: "{payload["result_jtl"]}"\n'
    )


def scenario_template(args):
    payload = _scenario_template_payload(
        application=args.application,
        domain=args.domain,
        protocol=args.protocol,
        threads=args.threads,
        ramp=args.ramp,
        duration=args.duration,
        result_jtl=args.result_jtl,
    )

    if args.format == 'json':
        content = json.dumps(payload, indent=2) + '\n'
    else:
        content = _render_scenario_template_yaml(payload)

    with open(args.out, 'w', encoding='utf-8') as fh:
        fh.write(content)

    print(f'Scenario template created: {args.out}')


def create_scenario(args):
    scenario = _load_scenario_definition(args.scenario)
    test_name = scenario.get('test_name', 'Scenario Performance Test')
    defaults = scenario.get('defaults') or {}

    tree = create_jmx_template(test_name)

    csv_config = scenario.get('csv') or {}
    csv_path = csv_config.get('path')
    if csv_path:
        add_csv_dataset(tree, csv_path, _split_csv_values(csv_config.get('vars', '')))

    for regex_entry in scenario.get('regex_extractors') or []:
        if not isinstance(regex_entry, dict):
            continue
        ref = str(regex_entry.get('ref', '')).strip()
        regex = str(regex_entry.get('regex', '')).strip()
        if ref and regex:
            add_regex_extractor(tree, ref, regex)

    timer_ms = scenario.get('timer_ms')
    if timer_ms is not None:
        add_constant_timer(tree, int(timer_ms))

    for tg in scenario.get('thread_groups') or []:
        if not isinstance(tg, dict):
            continue
        tg_name = tg.get('name', 'Scenario Users')
        threads = int(tg.get('threads', defaults.get('threads', 1)))
        ramp = int(tg.get('ramp', defaults.get('ramp', 1)))
        duration = tg.get('duration', defaults.get('duration'))
        add_thread_group(
            tree,
            num_threads=threads,
            ramp_time=ramp,
            duration=int(duration) if duration is not None else None,
            name=tg_name,
        )

        tg_ht = find_threadgroup_hashTree_by_name(tree.getroot(), tg_name)
        if tg_ht is None:
            raise RuntimeError(f'Could not find hashTree for thread group: {tg_name}')

        for tx in tg.get('transactions') or []:
            if not isinstance(tx, dict):
                continue
            tx_name = tx.get('name', 'HTTP Transaction')
            domain = tx.get('domain', defaults.get('domain'))
            if not domain:
                raise ValueError(f'Missing domain for transaction "{tx_name}"')

            sampler = _build_http_sampler_element(
                name=tx_name,
                domain=domain,
                path=tx.get('path', '/'),
                method=tx.get('method', 'GET'),
                protocol=tx.get('protocol', defaults.get('protocol', 'https')),
                port=tx.get('port', defaults.get('port')),
                params=tx.get('params') if isinstance(tx.get('params'), dict) else {},
                body=tx.get('body'),
                post_type=tx.get('post_type', 'raw'),
            )
            tg_ht.append(sampler)
            sampler_ht = ET.Element('hashTree')
            tg_ht.append(sampler_ht)

            combined_headers: Dict[str, Any] = {}
            if isinstance(defaults.get('headers'), dict):
                combined_headers.update(defaults['headers'])
            if isinstance(tx.get('headers'), dict):
                combined_headers.update(tx['headers'])
            if combined_headers:
                hm = _build_header_manager(f'Headers for {tx_name}', combined_headers)
                sampler_ht.append(hm)
                sampler_ht.append(ET.Element('hashTree'))

            assertion_cfg = tx.get('assert')
            if isinstance(assertion_cfg, dict):
                field = str(assertion_cfg.get('field', 'ResponseCode'))
                pattern = str(assertion_cfg.get('pattern', '')).strip()
                if pattern:
                    assertion = _build_response_assertion_element(field, pattern, f'Assert {tx_name}')
                    sampler_ht.append(assertion)
                    sampler_ht.append(ET.Element('hashTree'))

            extractor_cfg = tx.get('extractor')
            if isinstance(extractor_cfg, dict):
                ref_name = str(extractor_cfg.get('ref', '')).strip()
                regex = str(extractor_cfg.get('regex', '')).strip()
                if ref_name and regex:
                    extractor = _build_regex_extractor_element(ref_name, regex, f'Extractor {tx_name}')
                    sampler_ht.append(extractor)
                    sampler_ht.append(ET.Element('hashTree'))

            think_time_ms = tx.get('think_time_ms')
            if think_time_ms is not None:
                timer = ET.Element(
                    'ConstantTimer',
                    {'guiclass': 'ConstantTimerGui', 'testclass': 'ConstantTimer', 'testname': f'Think Time {tx_name}'},
                )
                ET.SubElement(timer, 'stringProp', {'name': 'ConstantTimer.delay'}).text = str(int(think_time_ms))
                sampler_ht.append(timer)
                sampler_ht.append(ET.Element('hashTree'))

    result_path = args.result_jtl or scenario.get('result_jtl')
    if result_path:
        add_simple_result_collector(tree, filename=result_path, name='Scenario Results')

    save_jmx(tree, args.out)
    print(f'Scenario JMX generated: {args.out}')


def _add_common_jmx_elements(tree, args):
    if args.csv:
        add_csv_dataset(tree, args.csv, _split_csv_values(args.vars))

    if args.timer is not None:
        add_constant_timer(tree, int(args.timer))

    for ref, regex in _parse_regex_entries(args.regex):
        add_regex_extractor(tree, ref, regex)

    if args.threads is not None:
        add_thread_group(
            tree,
            num_threads=int(args.threads),
            ramp_time=int(args.ramp),
            duration=int(args.duration) if args.duration is not None else None,
            name=args.thread_group_name,
        )

    if args.domain:
        add_http_sampler_full(
            tree,
            name=args.sampler_name,
            domain=args.domain,
            port=args.port,
            path=args.path,
            method=args.method,
            protocol=args.protocol,
            headers=_parse_key_value_pairs(args.header),
            params=_parse_key_value_pairs(args.param),
            body=args.body,
            post_type=args.post_type,
        )

    if args.assert_pattern:
        add_response_assertion(tree, test_field=args.assert_field, pattern=args.assert_pattern)

    if args.result_jtl:
        add_simple_result_collector(tree, filename=args.result_jtl, name='Results')


def generate_jmx(args):
    tree = create_jmx_template(args.name)
    _add_common_jmx_elements(tree, args)
    save_jmx(tree, args.out)
    print(f'Generated JMX: {args.out}')


def enhance_jmx(args):
    tree = ET.parse(args.input)
    _add_common_jmx_elements(tree, args)
    save_jmx(tree, args.out)
    print(f'Enhanced JMX saved: {args.out}')


def create_plan(args):
    transactions = _split_csv_values(args.transactions)
    test_types = _split_csv_values(args.test_types)

    lines = [
        f'# Performance Engineering Plan - {args.application}',
        '',
        f'- Generated on: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")} UTC',
        f'- Environment: {args.environment}',
        f'- Peak users target: {args.users}',
        f'- Ramp-up (seconds): {args.ramp}',
        f'- Duration (seconds): {args.duration}',
        '',
        '## NFR / SLA Targets',
        f'- p95 response time <= {args.sla_p95_ms} ms',
        f'- Error rate <= {args.sla_error_rate}%'
    ]

    if transactions:
        lines.extend(['', '## Business Transactions', ''])
        for tx in transactions:
            lines.append(f'- {tx}')

    lines.extend(['', '## Performance Lifecycle Checklist', ''])
    lifecycle_steps = [
        'Capture workload model, user mix, and critical business flows.',
        'Prepare test data and parameterization strategy (CSV/user pools).',
        'Create base JMeter scripts for all key transactions.',
        'Enhance scripts with timers, correlation, assertions, and listeners.',
        'Run shake-down test to validate script stability and data handling.',
        'Execute baseline test to establish current performance benchmark.',
        'Run planned load profiles (load, stress, spike, soak as applicable).',
        'Analyze bottlenecks (application, database, infra, external dependencies).',
        'Produce final report with SLA pass/fail and tuning recommendations.',
        'Track fixes and run re-tests until performance criteria are met.',
    ]
    for step in lifecycle_steps:
        lines.append(f'- [ ] {step}')

    lines.extend(['', '## Planned Test Types', ''])
    for test_type in test_types:
        lines.append(f'- {test_type}')

    lines.extend([
        '',
        '## Execution Commands',
        '',
        '```bash',
        '# 1) Generate base script',
        'python -m perf_agent.agent generate-jmx --name "Perf Test" --out generated.jmx',
        '',
        '# 2) Enhance existing script',
        'python -m perf_agent.agent enhance-jmx --input generated.jmx --out enhanced.jmx --timer 500',
        '',
        '# 3) Run local load test',
        'python -m perf_agent.agent run-local --jmx enhanced.jmx --jtl results.jtl',
        '',
        '# 4) Build report',
        'python -m perf_agent.agent report --jtl results.jtl --out perf_report.md',
        '```',
    ])

    with open(args.out, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines) + '\n')
    print(f'Performance plan created: {args.out}')


def run_local(args):
    jmeter_bin = args.jmeter_bin or shutil.which('jmeter') or shutil.which('jmeter.bat')
    if not jmeter_bin:
        raise RuntimeError('JMeter executable not found. Pass --jmeter-bin or add jmeter to PATH.')

    cmd = [jmeter_bin, '-n', '-t', args.jmx, '-l', args.jtl]
    if args.log:
        cmd += ['-j', args.log]
    for prop in args.prop or []:
        cmd.append(f'-J{prop}')

    print('Running:', ' '.join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())
    if result.returncode != 0:
        raise RuntimeError(f'JMeter run failed with exit code {result.returncode}')
    print(f'Load test completed. Results: {args.jtl}')


def _fmt(value, digits=2):
    if value is None:
        return 'n/a'
    if isinstance(value, float):
        return f'{value:.{digits}f}'
    return str(value)


def _render_markdown_report(report_payload, source_jtl):
    overall = report_payload['overall']
    by_label = report_payload['by_label']
    sla = report_payload['sla']

    lines = [
        '# Performance Test Report',
        '',
        f'- Generated on: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")} UTC',
        f'- Source JTL: {source_jtl}',
        '',
        '## Overall Summary',
        '',
        f"- Samples: {_fmt(overall.get('count'), 0)}",
        f"- Avg Response Time (ms): {_fmt(overall.get('avg'))}",
        f"- Min Response Time (ms): {_fmt(overall.get('min'))}",
        f"- Max Response Time (ms): {_fmt(overall.get('max'))}",
        f"- p90 (ms): {_fmt(overall.get('p90'))}",
        f"- p95 (ms): {_fmt(overall.get('p95'))}",
        f"- p99 (ms): {_fmt(overall.get('p99'))}",
        f"- Error Rate (%): {_fmt(overall.get('error_rate'))}",
        f"- Throughput (req/sec): {_fmt(overall.get('throughput'))}",
    ]

    if sla:
        lines.extend(['', '## SLA Evaluation', ''])
        if 'p95' in sla:
            p95 = sla['p95']
            lines.append(
                f"- p95 <= {p95['target_ms']} ms: {'PASS' if p95.get('pass') else 'FAIL'} "
                f"(actual: {_fmt(p95.get('actual_ms'))} ms)"
            )
        if 'error_rate' in sla:
            err = sla['error_rate']
            lines.append(
                f"- Error Rate <= {err['target_pct']}%: {'PASS' if err.get('pass') else 'FAIL'} "
                f"(actual: {_fmt(err.get('actual_pct'))}%)"
            )
        lines.append(f"- Overall SLA: {'PASS' if sla.get('overall_pass') else 'FAIL'}")

    lines.extend(['', '## Endpoint Breakdown', ''])
    for label, summary in sorted(by_label.items()):
        lines.extend([
            '',
            f'### {label}',
            f"- Samples: {_fmt(summary.get('count'), 0)}",
            f"- Avg (ms): {_fmt(summary.get('avg'))}",
            f"- p95 (ms): {_fmt(summary.get('p95'))}",
            f"- Error Rate (%): {_fmt(summary.get('error_rate'))}",
            f"- Throughput (req/sec): {_fmt(summary.get('throughput'))}",
        ])
    return '\n'.join(lines) + '\n'


def report(args):
    samples = parse_jtl(args.jtl)
    payload = build_performance_report(
        samples,
        sla_p95_ms=args.sla_p95_ms,
        sla_error_rate_pct=args.sla_error_rate,
    )

    if args.format == 'json':
        with open(args.out, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, indent=2)
    else:
        text = _render_markdown_report(payload, args.jtl)
        with open(args.out, 'w', encoding='utf-8') as fh:
            fh.write(text)
    print(f'Report generated: {args.out}')


def upload_jmx(args):
    client = BlazeMeterClient(api_key=args.apikey)
    res = client.upload_jmx(args.jmx, name=args.name)
    print('Upload result:', res)


def start_test(args):
    client = BlazeMeterClient(api_key=args.apikey)
    res = client.start_test(args.jmx_id, location=args.location)
    print('Start result:', res)


def main():
    parser = argparse.ArgumentParser(
        prog='perf-agent',
        description='Performance lifecycle assistant: plan, script, run, and report.',
    )
    sub = parser.add_subparsers(dest='cmd')

    # Lifecycle planning
    plan = sub.add_parser('create-plan', help='Create a performance lifecycle plan/checklist')
    plan.add_argument('--application', required=True, help='Application or service name')
    plan.add_argument('--environment', default='staging', help='Target environment')
    plan.add_argument('--transactions', default='', help='Comma-separated business transactions')
    plan.add_argument('--users', type=int, default=100, help='Target virtual users')
    plan.add_argument('--ramp', type=int, default=120, help='Ramp-up in seconds')
    plan.add_argument('--duration', type=int, default=1800, help='Test duration in seconds')
    plan.add_argument('--sla-p95-ms', type=float, default=1000, help='SLA target for p95 latency')
    plan.add_argument('--sla-error-rate', type=float, default=1.0, help='SLA target for error rate (%)')
    plan.add_argument('--test-types', default='baseline,load,stress,spike,soak', help='Comma-separated test types')
    plan.add_argument('--out', default='performance_test_plan.md', help='Output markdown file')
    plan.set_defaults(func=create_plan)

    # Scenario-based JMX generation
    tmpl = sub.add_parser('scenario-template', help='Create a starter scenario YAML/JSON template')
    tmpl.add_argument('--out', default='scenario.yaml', help='Output template file')
    tmpl.add_argument('--format', choices=['yaml', 'json'], default='yaml', help='Template format')
    tmpl.add_argument('--application', default='MyApp', help='Application/service name for template')
    tmpl.add_argument('--domain', default='example.com', help='Default domain')
    tmpl.add_argument('--protocol', default='https', help='Default protocol')
    tmpl.add_argument('--threads', type=int, default=50, help='Default users/thread count')
    tmpl.add_argument('--ramp', type=int, default=120, help='Default ramp-up in seconds')
    tmpl.add_argument('--duration', type=int, default=1800, help='Default duration in seconds')
    tmpl.add_argument('--result-jtl', default='results.jtl', help='Default JTL output path')
    tmpl.set_defaults(func=scenario_template)

    # Scenario-based JMX generation
    scn = sub.add_parser('create-scenario', help='Generate multi-transaction JMX from scenario YAML/JSON')
    scn.add_argument('--scenario', required=True, help='Scenario definition file (.yaml/.yml/.json)')
    scn.add_argument('--out', default='scenario_generated.jmx', help='Output JMX file')
    scn.add_argument('--result-jtl', help='Override result JTL path from scenario')
    scn.set_defaults(func=create_scenario)

    # Build new JMX
    gen = sub.add_parser('generate-jmx', help='Generate a base JMX and optional test elements')
    gen.add_argument('--name', default='Perf Test')
    gen.add_argument('--out', default='generated.jmx')
    _add_jmx_common_args(gen, include_input=False)
    gen.set_defaults(func=generate_jmx)

    # Enhance existing JMX
    enh = sub.add_parser('enhance-jmx', help='Enhance an existing JMX file with new elements')
    enh.add_argument('--input', required=True, help='Input JMX file')
    enh.add_argument('--out', default='enhanced.jmx', help='Output JMX file')
    _add_jmx_common_args(enh, include_input=True)
    enh.set_defaults(func=enhance_jmx)

    # Run local JMeter
    run = sub.add_parser('run-local', help='Run JMeter in non-GUI mode')
    run.add_argument('--jmx', required=True, help='JMX file to execute')
    run.add_argument('--jtl', required=True, help='Output JTL/CSV result file')
    run.add_argument('--jmeter-bin', help='Path to jmeter executable')
    run.add_argument('--log', help='JMeter log file')
    run.add_argument('--prop', action='append', default=[], help='JMeter property as key=value (repeatable)')
    run.set_defaults(func=run_local)

    # Reporting
    rep = sub.add_parser('report', help='Generate performance report from JTL')
    rep.add_argument('--jtl', required=True, help='JTL/CSV result file')
    rep.add_argument('--out', default='performance_report.md', help='Output report file')
    rep.add_argument('--format', choices=['markdown', 'json'], default='markdown')
    rep.add_argument('--sla-p95-ms', type=float, help='SLA threshold for p95 response time (ms)')
    rep.add_argument('--sla-error-rate', type=float, help='SLA threshold for error rate (%)')
    rep.set_defaults(func=report)

    # BlazeMeter stubs
    up = sub.add_parser('upload')
    up.add_argument('jmx')
    up.add_argument('--apikey', help='BlazeMeter API key')
    up.add_argument('--name', help='Test name')
    up.set_defaults(func=upload_jmx)

    st = sub.add_parser('start')
    st.add_argument('jmx_id')
    st.add_argument('--apikey', help='BlazeMeter API key')
    st.add_argument('--location', help='Load location')
    st.set_defaults(func=start_test)

    args = parser.parse_args()
    if not hasattr(args, 'func'):
        parser.print_help()
        return
    args.func(args)


def _add_jmx_common_args(parser, include_input):
    del include_input  # kept for signature clarity in case of future divergence
    parser.add_argument('--csv', help='Path to CSV file for parameterization')
    parser.add_argument('--vars', default='', help='Comma-separated variable names for CSV')
    parser.add_argument('--timer', type=int, help='Constant timer delay in ms')
    parser.add_argument('--regex', action='append', default=[], help='Add regex extractor as ref:regex; repeatable')
    parser.add_argument('--threads', type=int, help='Add Thread Group with thread count')
    parser.add_argument('--ramp', type=int, default=1, help='Thread Group ramp-up seconds')
    parser.add_argument('--duration', type=int, help='Thread Group duration in seconds')
    parser.add_argument('--thread-group-name', default='Workload Users', help='Thread Group name')
    parser.add_argument('--domain', help='HTTP sampler domain (example.com)')
    parser.add_argument('--port', type=int, help='HTTP sampler port')
    parser.add_argument('--protocol', default='https', help='HTTP sampler protocol')
    parser.add_argument('--path', default='/', help='HTTP sampler path')
    parser.add_argument('--method', default='GET', help='HTTP sampler method')
    parser.add_argument('--sampler-name', default='HTTP Request', help='HTTP sampler name')
    parser.add_argument('--header', action='append', default=[], help='Header as key=value; repeatable')
    parser.add_argument('--param', action='append', default=[], help='Request param as key=value; repeatable')
    parser.add_argument('--body', help='Request body for POST/PUT')
    parser.add_argument('--post-type', choices=['raw', 'form'], default='raw', help='Body mode')
    parser.add_argument('--assert-field', default='ResponseCode', help='Assertion test field')
    parser.add_argument('--assert-pattern', help='Assertion pattern (for response assertion)')
    parser.add_argument('--result-jtl', help='Add Result Collector with this JTL output path')


if __name__ == '__main__':
    main()
