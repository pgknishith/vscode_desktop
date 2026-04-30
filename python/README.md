# perf_agent

Performance-engineering agent scaffold for the complete lifecycle:

- create a performance plan/checklist
- generate, scenario-build, and enhance JMeter scripts (`.jmx`)
- run local load tests in JMeter non-GUI mode
- produce performance reports from JTL results with SLA checks

## Requirements

- Python 3.8+
- JMeter installed separately if you want to run `run-local`

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## CLI commands

### 1. Create a lifecycle plan

```powershell
python -m perf_agent.agent create-plan `
  --application "PetStore" `
  --environment "staging" `
  --transactions "Launch,Login,Search,Checkout" `
  --users 300 `
  --ramp 180 `
  --duration 3600 `
  --sla-p95-ms 800 `
  --sla-error-rate 1 `
  --out performance_test_plan.md
```

### 2. Generate a base JMX

```powershell
python -m perf_agent.agent generate-jmx `
  --name "PetStore Load Test" `
  --out petstore.jmx `
  --threads 100 `
  --ramp 120 `
  --duration 1800 `
  --csv data/users.csv `
  --vars user,pass `
  --domain petstore.octoperf.com `
  --path /actions/Catalog.action `
  --method GET `
  --timer 500 `
  --result-jtl results.jtl
```

### 2b. Auto-generate JMX from scenario YAML

Create `scenario.yaml`:

```yaml
test_name: "PetStore Scenario"
defaults:
  domain: "petstore.octoperf.com"
  protocol: "https"
  headers:
    Accept: "text/html"
csv:
  path: "data/users.csv"
  vars: "user,pass"
thread_groups:
  - name: "PetStore Users"
    threads: 50
    ramp: 120
    duration: 1800
    transactions:
      - name: "Launch"
        method: "GET"
        path: "/actions/Catalog.action"
      - name: "Login"
        method: "POST"
        path: "/actions/Account.action"
        params:
          username: "${user}"
          password: "${pass}"
        assert:
          field: "ResponseCode"
          pattern: "200"
result_jtl: "petstore_results.jtl"
```

Generate JMX:

```powershell
python -m perf_agent.agent create-scenario `
  --scenario scenario.yaml `
  --out petstore_scenario.jmx
```

You can scaffold starter scenario YAML automatically:

```powershell
python -m perf_agent.agent scenario-template `
  --out scenario.yaml `
  --application "PetStore" `
  --domain "petstore.octoperf.com"
```

### 3. Enhance an existing JMX

```powershell
python -m perf_agent.agent enhance-jmx `
  --input petstore.jmx `
  --out petstore_enhanced.jmx `
  --regex "sessionToken:name=\".*?token.*?\" value=\"(.*?)\"" `
  --assert-field ResponseCode `
  --assert-pattern 200 `
  --header "Content-Type=application/json"
```

### 4. Run local JMeter load test

```powershell
python -m perf_agent.agent run-local `
  --jmx petstore_enhanced.jmx `
  --jtl petstore_results.jtl `
  --prop "threads=100" `
  --prop "ramp=120"
```

If JMeter is not in `PATH`, pass `--jmeter-bin "C:\path\to\jmeter.bat"`.

### 5. Generate report

```powershell
python -m perf_agent.agent report `
  --jtl petstore_results.jtl `
  --out perf_report.md `
  --sla-p95-ms 800 `
  --sla-error-rate 1
```

For JSON output:

```powershell
python -m perf_agent.agent report --jtl petstore_results.jtl --format json --out perf_report.json
```

## Web helper box (executes from UI)

Start backend server:

```powershell
python agent_box_server.py --port 8010
```

Open:

```text
http://localhost:8010/agent_visual.html
```

From the top-right helper box:
- `Create Scripts` generates plan + scenario JSON + JMX under `generated/`
- `Run Full Lifecycle` also attempts local JMeter run and report generation
- `ChatGPT Reply` calls OpenAI for scenario guidance
- `ChatGPT Execute` uses OpenAI-structured scenario and executes generation

To enable ChatGPT in the box, set:

```powershell
$env:OPENAI_API_KEY="your_api_key_here"
```

Optional:

```powershell
$env:OPENAI_MODEL="gpt-4.1-mini"
$env:OPENAI_BASE_URL="https://api.openai.com/v1"
```
