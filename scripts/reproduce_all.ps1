# Reproduce all Phase 4 experiments
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Write-Host "=== Experiment 1: Pressure test ==="
python -m worldcup_causal_engine.experiments --experiment pressure_test --scenarios S1,S2,S3 --worlds W0,W1,W2,W3,W4,W5 --output results/experiment_1

Write-Host "=== Experiment 2: Ablation ==="
python -m worldcup_causal_engine.experiments --experiment ablation --scenarios S1,S2,S3 --output results/experiment_2

Write-Host "=== Experiment 3: LLM baseline ==="
python -m worldcup_causal_engine.experiments.llm_baseline --scenario S1 --worlds W0,W1 --runs 5 --output results/experiment_3
python -m worldcup_causal_engine.experiments.llm_baseline --scenario S3 --worlds W0,W1 --runs 5 --output results/experiment_3

Write-Host "=== Sensitivity analysis ==="
python -m worldcup_causal_engine.experiments --experiment sensitivity --scenarios S1 --output results/experiment_sensitivity

Write-Host "=== Generate figures ==="
python scripts/plot_results.py --all --output paper/figures

Write-Host "=== Build reproducibility manifest ==="
python scripts/build_manifest.py

Write-Host "=== Final demo ==="
python -m worldcup_causal_engine.main --scenario data/scenarios/S1_controversial_call_high_density.json --feed data/atoms/sample_match_feed.jsonl --world W1 --until 120 --explain --output results/final_demo.json

Write-Host "Done."
