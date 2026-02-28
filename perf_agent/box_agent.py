"""Backend workflow for the web helper box.

This module turns a free-text scenario request into generated artifacts:
- performance plan
- scenario definition (JSON)
- JMX script
- optional local run + report
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from perf_agent import agent


@dataclass
class ScenarioRequest:
    raw: str
    application: str
    domain: str
    users: int
    ramp_seconds: int
    duration_seconds: int
    transactions: List[str]


def infer_scenario_request(raw_text: str) -> ScenarioRequest:
    text = (raw_text or '').strip()
    lower = text.lower()

    users = _read_number_before_unit(lower, ['users', 'vus', 'threads'], default=100)
    ramp_seconds = _read_duration_after_keyword(lower, 'ramp', default_seconds=120)
    duration_seconds = _read_duration_after_keyword(lower, 'duration', default_seconds=None)
    if duration_seconds is None:
        duration_seconds = _read_first_duration(lower, default_seconds=1800)

    application = 'PetStore' if 'petstore' in lower else 'MyApp'
    domain = 'petstore.octoperf.com' if 'petstore' in lower else 'example.com'

    transactions = ['Launch']
    if 'login' in lower:
        transactions.append('Login')
    if 'search' in lower:
        transactions.append('Search')
    if 'checkout' in lower:
        transactions.append('Checkout')
    if 'logout' in lower:
        transactions.append('Logout')
    if len(transactions) == 1:
        transactions.extend(['Login', 'Search'])

    return ScenarioRequest(
        raw=text,
        application=application,
        domain=domain,
        users=max(users, 1),
        ramp_seconds=max(ramp_seconds, 1),
        duration_seconds=max(duration_seconds, 1),
        transactions=transactions,
    )


def scenario_request_from_dict(data: Dict[str, object], raw_text: str = '') -> ScenarioRequest:
    application = str(data.get('application') or 'MyApp').strip() or 'MyApp'
    domain = str(data.get('domain') or 'example.com').strip() or 'example.com'
    users = _safe_int(data.get('users'), 100)
    ramp_seconds = _safe_int(data.get('ramp_seconds'), 120)
    duration_seconds = _safe_int(data.get('duration_seconds'), 1800)

    transactions_raw = data.get('transactions')
    transactions: List[str] = []
    if isinstance(transactions_raw, list):
        for item in transactions_raw:
            item_text = str(item).strip()
            if item_text:
                transactions.append(item_text.title())
    if not transactions:
        transactions = ['Launch', 'Login', 'Search']

    return ScenarioRequest(
        raw=raw_text,
        application=application,
        domain=domain,
        users=max(users, 1),
        ramp_seconds=max(ramp_seconds, 1),
        duration_seconds=max(duration_seconds, 1),
        transactions=transactions,
    )


def run_box_workflow(
    *,
    prompt: str,
    run_full_lifecycle: bool = False,
    base_dir: str = '.',
) -> Dict[str, object]:
    req = infer_scenario_request(prompt)
    return run_box_workflow_for_request(req=req, run_full_lifecycle=run_full_lifecycle, base_dir=base_dir)


def run_box_workflow_for_request(
    *,
    req: ScenarioRequest,
    run_full_lifecycle: bool = False,
    base_dir: str = '.',
) -> Dict[str, object]:
    root = Path(base_dir).resolve()
    out_dir = root / 'generated'
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    slug = _slugify(req.application)

    plan_path = out_dir / f'{slug}_{stamp}_performance_plan.md'
    scenario_path = out_dir / f'{slug}_{stamp}_scenario.json'
    jmx_path = out_dir / f'{slug}_{stamp}.jmx'
    jtl_path = out_dir / f'{slug}_{stamp}.jtl'
    report_path = out_dir / f'{slug}_{stamp}_report.md'
    jmeter_log = out_dir / f'{slug}_{stamp}_jmeter.log'

    agent.create_plan(
        argparse.Namespace(
            application=req.application,
            environment='staging',
            transactions=','.join(req.transactions),
            users=req.users,
            ramp=req.ramp_seconds,
            duration=req.duration_seconds,
            sla_p95_ms=800,
            sla_error_rate=1.0,
            test_types='baseline,load,stress,spike,soak',
            out=str(plan_path),
        )
    )

    scenario_payload = _scenario_payload(req, result_jtl=str(jtl_path))
    scenario_path.write_text(json.dumps(scenario_payload, indent=2) + '\n', encoding='utf-8')

    agent.create_scenario(
        argparse.Namespace(
            scenario=str(scenario_path),
            out=str(jmx_path),
            result_jtl=str(jtl_path),
        )
    )

    lifecycle = 'scripts_created'
    warning = None
    if run_full_lifecycle:
        try:
            agent.run_local(
                argparse.Namespace(
                    jmx=str(jmx_path),
                    jtl=str(jtl_path),
                    jmeter_bin=None,
                    log=str(jmeter_log),
                    prop=[],
                )
            )
            agent.report(
                argparse.Namespace(
                    jtl=str(jtl_path),
                    out=str(report_path),
                    format='markdown',
                    sla_p95_ms=800,
                    sla_error_rate=1.0,
                )
            )
            lifecycle = 'full_completed'
        except Exception as exc:  # pragma: no cover - depends on local JMeter availability
            lifecycle = 'scripts_created'
            warning = f'Full run skipped/failed: {exc}'

    generated_files = [str(plan_path), str(scenario_path), str(jmx_path)]
    if jtl_path.exists():
        generated_files.append(str(jtl_path))
    if report_path.exists():
        generated_files.append(str(report_path))
    if jmeter_log.exists():
        generated_files.append(str(jmeter_log))

    return {
        'status': 'ok',
        'lifecycle': lifecycle,
        'warning': warning,
        'request': {
            'application': req.application,
            'domain': req.domain,
            'users': req.users,
            'ramp_seconds': req.ramp_seconds,
            'duration_seconds': req.duration_seconds,
            'transactions': req.transactions,
        },
        'generated_files': generated_files,
        'next_commands': [
            f'python -m perf_agent.agent create-scenario --scenario "{scenario_path}" --out "{jmx_path}"',
            f'python -m perf_agent.agent run-local --jmx "{jmx_path}" --jtl "{jtl_path}"',
            f'python -m perf_agent.agent report --jtl "{jtl_path}" --out "{report_path}" --sla-p95-ms 800 --sla-error-rate 1',
        ],
    }


def _scenario_payload(req: ScenarioRequest, *, result_jtl: str) -> Dict[str, object]:
    tx_defs = []
    for tx in req.transactions:
        key = tx.lower()
        if key == 'launch':
            tx_defs.append(_tx('Launch', 'GET', '/'))
        elif key == 'login':
            tx_defs.append(
                _tx(
                    'Login',
                    'POST',
                    '/api/login',
                    params={'username': '${user}', 'password': '${pass}'},
                )
            )
        elif key == 'search':
            tx_defs.append(_tx('Search', 'GET', '/api/search', params={'q': 'bike'}))
        elif key == 'checkout':
            tx_defs.append(_tx('Checkout', 'POST', '/api/checkout'))
        elif key == 'logout':
            tx_defs.append(_tx('Logout', 'GET', '/api/logout'))
        else:
            tx_defs.append(_tx(tx.title(), 'GET', '/'))

    return {
        'test_name': f'{req.application} Scenario',
        'defaults': {
            'domain': req.domain,
            'protocol': 'https',
            'headers': {'Accept': 'application/json'},
            'threads': req.users,
            'ramp': req.ramp_seconds,
            'duration': req.duration_seconds,
        },
        'csv': {'path': 'data/users.csv', 'vars': 'user,pass'},
        'timer_ms': 500,
        'thread_groups': [
            {
                'name': 'Primary Users',
                'threads': req.users,
                'ramp': req.ramp_seconds,
                'duration': req.duration_seconds,
                'transactions': tx_defs,
            }
        ],
        'result_jtl': result_jtl,
    }


def _tx(name: str, method: str, path: str, params: Dict[str, str] | None = None) -> Dict[str, object]:
    tx = {
        'name': name,
        'method': method,
        'path': path,
        'assert': {'field': 'ResponseCode', 'pattern': '200'},
    }
    if params:
        tx['params'] = params
    return tx


def _slugify(value: str) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')
    return slug or 'app'


def _read_number_before_unit(text: str, units: List[str], default: int) -> int:
    units_pattern = '|'.join(re.escape(unit) for unit in units)
    match = re.search(rf'\b(\d{{1,5}})\s*(?:{units_pattern})\b', text)
    if match:
        return int(match.group(1))
    return default


def _read_duration_after_keyword(text: str, keyword: str, default_seconds: int | None) -> int | None:
    pattern = rf'{re.escape(keyword)}[^0-9]*(\d{{1,6}})\s*(sec|secs|second|seconds|min|mins|minute|minutes|hr|hrs|hour|hours)?'
    match = re.search(pattern, text)
    if not match:
        return default_seconds
    return _to_seconds(int(match.group(1)), (match.group(2) or 'sec').lower())


def _read_first_duration(text: str, default_seconds: int) -> int:
    match = re.search(r'(\d{1,6})\s*(sec|secs|second|seconds|min|mins|minute|minutes|hr|hrs|hour|hours)\b', text)
    if not match:
        return default_seconds
    return _to_seconds(int(match.group(1)), match.group(2).lower())


def _to_seconds(value: int, unit: str) -> int:
    if unit.startswith('hr') or unit.startswith('hour'):
        return value * 3600
    if unit.startswith('min'):
        return value * 60
    return value


def _safe_int(value: Optional[object], default: int) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (ValueError, TypeError):
        return default
