# World Cup Causal Engine

Trace-First Runtime Causal Engine for World Cup Media-Opinion and Crowd-Risk Simulation.

## Quick start

```bash
pip install -r requirements.txt

# Single scenario
python -m worldcup_causal_engine.main \
  --scenario data/scenarios/S1_controversial_call_high_density.json \
  --world W0 --until 120 --explain

# Text feed mode
python -m worldcup_causal_engine.main \
  --scenario data/scenarios/S1_controversial_call_high_density.json \
  --feed data/atoms/sample_match_feed.jsonl \
  --world W0 --until 120 \
  --ledger-output results/ledger.json

# Calibrated priors (Qatar 2022 post-hoc)
python -m worldcup_causal_engine.main \
  --scenario data/scenarios/S3_heat_crowd_comm_delay.json \
  --priors-profile calibrated --scenario-specific-priors --explain

# LLM proposes intervention; kernel verifies (mock or API)
python -m worldcup_causal_engine.main \
  --scenario data/scenarios/S3_heat_crowd_comm_delay.json --llm-propose-demo

# MDG Mermaid export
python scripts/export_mdg.py

# New scenarios S4–S6
python -m worldcup_causal_engine.main \
  --scenario data/scenarios/S4_misleading_viral_clip.json --world W6 --explain

# Reproduce all experiments (Phase 4)
powershell -File scripts/reproduce_all.ps1

# Real-world calibration pipeline
python scripts/fetch_and_calibrate.py --scenarios S1,S2,S3 --budget 80
```

## Project structure

```
worldcup_causal_engine/   # Kernel, mechanisms, evidence, compiler, reverse
data/                     # Scenarios, priors, interventions, feed, rules
docs/                     # Design docs + experiment report
results/                  # Experiment artifacts
paper/                    # Figures and tables for publication
tests/                    # pytest suite
```

## Experiments

```bash
python -m worldcup_causal_engine.experiments --experiment pressure_test
python -m worldcup_causal_engine.experiments --experiment ablation
python -m worldcup_causal_engine.experiments --experiment sensitivity
# LLM baseline（智算 OpenAI 兼容 API）
python -m worldcup_causal_engine.experiments.llm_baseline \
  --all-scenarios --worlds W0,W1 --runs 3 --use-api \
  --model qwen3.5 --base-url https://ai.azya.top/v1 \
  --output results/experiment_3_zhisuan

# 生成论文图表（含合并雷达图）
python scripts/plot_results.py --all
```

## Tests

```bash
python -m pytest tests/ -v
```

## Scenarios

| ID | Description |
|----|-------------|
| S1 | Controversial call + high density |
| S2 | Team eliminated + transit delay |
| S3 | Heat + crowd + comm channel exhausted |
| S4 | Misleading viral clip spread |
| S5 | Post-match transit delay |
| S6 | Heat + fan zone overflow |

Worlds: W0 (baseline) … W6 (`platform_rumor_throttle`).

## Documentation

- [完整方案](docs/00-完整方案.md)
- [Phase 7–8 架构](docs/phase-07-08-架构.md)
- [校准数据来源](docs/calibration-data-sources.md)
- [实验报告](docs/experiment-report.md)
