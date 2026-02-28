from pathlib import Path

from perf_agent.box_agent import infer_scenario_request, run_box_workflow


def test_infer_scenario_request_basic():
    req = infer_scenario_request('Create login and checkout scenario for 300 users, ramp 180 sec, duration 30 minutes')
    assert req.users == 300
    assert req.ramp_seconds == 180
    assert req.duration_seconds == 1800
    assert 'Login' in req.transactions
    assert 'Checkout' in req.transactions


def test_run_box_workflow_creates_scripts(tmp_path):
    result = run_box_workflow(
        prompt='Build login + search scenario for 120 users for 20 minutes',
        run_full_lifecycle=False,
        base_dir=str(tmp_path),
    )
    assert result['status'] == 'ok'
    assert result['lifecycle'] == 'scripts_created'
    generated_files = [Path(p) for p in result['generated_files']]
    assert any(p.suffix == '.jmx' and p.exists() for p in generated_files)
    assert any(p.name.endswith('_scenario.json') and p.exists() for p in generated_files)
    assert any(p.name.endswith('_performance_plan.md') and p.exists() for p in generated_files)
