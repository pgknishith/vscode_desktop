# Performance Engineering Plan - MyApp

- Generated on: 2026-02-28 22:01:24 UTC
- Environment: staging
- Peak users target: 100
- Ramp-up (seconds): 120
- Duration (seconds): 1800

## NFR / SLA Targets
- p95 response time <= 800 ms
- Error rate <= 1.0%

## Business Transactions

- Launch
- Login
- Logout

## Performance Lifecycle Checklist

- [ ] Capture workload model, user mix, and critical business flows.
- [ ] Prepare test data and parameterization strategy (CSV/user pools).
- [ ] Create base JMeter scripts for all key transactions.
- [ ] Enhance scripts with timers, correlation, assertions, and listeners.
- [ ] Run shake-down test to validate script stability and data handling.
- [ ] Execute baseline test to establish current performance benchmark.
- [ ] Run planned load profiles (load, stress, spike, soak as applicable).
- [ ] Analyze bottlenecks (application, database, infra, external dependencies).
- [ ] Produce final report with SLA pass/fail and tuning recommendations.
- [ ] Track fixes and run re-tests until performance criteria are met.

## Planned Test Types

- baseline
- load
- stress
- spike
- soak

## Execution Commands

```bash
# 1) Generate base script
python -m perf_agent.agent generate-jmx --name "Perf Test" --out generated.jmx

# 2) Enhance existing script
python -m perf_agent.agent enhance-jmx --input generated.jmx --out enhanced.jmx --timer 500

# 3) Run local load test
python -m perf_agent.agent run-local --jmx enhanced.jmx --jtl results.jtl

# 4) Build report
python -m perf_agent.agent report --jtl results.jtl --out perf_report.md
```
