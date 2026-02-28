import argparse
import json
from xml.etree import ElementTree as ET

from perf_agent import agent


def test_create_scenario_generates_multi_transaction_jmx(tmp_path):
    scenario = {
        'test_name': 'Checkout Journey',
        'defaults': {
            'domain': 'example.com',
            'protocol': 'https',
            'headers': {'Accept': 'application/json'},
        },
        'csv': {'path': 'data/users.csv', 'vars': 'user,pass'},
        'thread_groups': [
            {
                'name': 'Web Users',
                'threads': 10,
                'ramp': 20,
                'duration': 120,
                'transactions': [
                    {'name': 'Launch', 'method': 'GET', 'path': '/'},
                    {
                        'name': 'Login',
                        'method': 'POST',
                        'path': '/api/login',
                        'body': '{"user":"${user}","pass":"${pass}"}',
                        'assert': {'field': 'ResponseCode', 'pattern': '200'},
                    },
                ],
            }
        ],
        'result_jtl': 'results.jtl',
    }

    scenario_file = tmp_path / 'scenario.json'
    scenario_file.write_text(json.dumps(scenario), encoding='utf-8')
    out_file = tmp_path / 'scenario.jmx'

    args = argparse.Namespace(
        scenario=str(scenario_file),
        out=str(out_file),
        result_jtl=None,
    )
    agent.create_scenario(args)

    assert out_file.exists()

    root = ET.parse(str(out_file)).getroot()
    assert root.findall('.//ThreadGroup')
    assert root.findall('.//HTTPSamplerProxy')
    assert root.findall('.//HeaderManager')
    assert root.findall('.//ResponseAssertion')
    assert root.findall('.//ResultCollector')


def test_scenario_template_json_round_trip(tmp_path):
    template_file = tmp_path / 'scenario_template.json'
    args = argparse.Namespace(
        out=str(template_file),
        format='json',
        application='DemoApp',
        domain='example.org',
        protocol='https',
        threads=25,
        ramp=60,
        duration=900,
        result_jtl='demo_results.jtl',
    )
    agent.scenario_template(args)

    assert template_file.exists()
    payload = json.loads(template_file.read_text(encoding='utf-8'))
    assert payload['test_name'] == 'DemoApp Scenario'
    assert payload['defaults']['domain'] == 'example.org'
    assert payload['thread_groups']

    out_jmx = tmp_path / 'roundtrip.jmx'
    scenario_args = argparse.Namespace(
        scenario=str(template_file),
        out=str(out_jmx),
        result_jtl=None,
    )
    agent.create_scenario(scenario_args)
    assert out_jmx.exists()
