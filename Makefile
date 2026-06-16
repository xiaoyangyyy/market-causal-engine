# Market Causal Engine — developer Makefile (Step E)
# Windows: use Git Bash / WSL, or run equivalent python scripts directly.

PYTHON ?= python
PIP ?= pip

MARKET_TEST_IGNORE = \
	--ignore=tests/test_phase4.py \
	--ignore=tests/test_phase5_phase6.py \
	--ignore=tests/test_phase7_phase8.py \
	--ignore=tests/test_phase_c.py \
	--ignore=tests/test_compiler.py \
	--ignore=tests/test_evidence.py \
	--ignore=tests/test_experiments.py \
	--ignore=tests/test_reverse.py \
	--ignore=tests/test_mechanisms.py \
	--ignore=tests/test_kernel.py \
	--ignore=tests/test_llm_proposer.py

LINT_PATHS = \
	market_causal_engine/demo \
	market_causal_engine/platform/pit_hardening.py \
	market_causal_engine/platform/pit.py \
	market_causal_engine/counterfactuals/car_ablation.py \
	market_causal_engine/counterfactuals/outcome_layer.py \
	scripts/reproduce_benchmark.py \
	scripts/export_killer_demo.py \
	scripts/audit_pit_compliance.py \
	tests/test_step_d_demo.py \
	tests/test_pit_hardening.py \
	tests/test_car_ablation.py \
	tests/test_outcome_layer.py \
	tests/test_label_quality.py

.PHONY: help install install-dev test test-market test-worldcup lint \
	reproduce-benchmark reproduce-benchmark-smoke audit-pit demo demo-static docker-build

help:
	@echo "Targets:"
	@echo "  make install                  pip install -e '.[dev,platform,api,demo]'"
	@echo "  make test-market              pytest (market product, no World Cup)"
	@echo "  make test-worldcup            pytest World Cup legacy"
	@echo "  make lint                     ruff on Step A-E modules"
	@echo "  make reproduce-benchmark      full headline reproduction (200 events)"
	@echo "  make reproduce-benchmark-smoke CI-sized reproduction (~20 events)"
	@echo "  make audit-pit                PIT compliance audit (case studies)"
	@echo "  make demo-static              export NFLX killer demo HTML"
	@echo "  make docker-build             docker build smoke test"

install install-dev:
	$(PIP) install -e ".[dev,platform,api,demo]"

test-market:
	$(PYTHON) -m pytest tests/ -q $(MARKET_TEST_IGNORE)

test: test-market

test-worldcup:
	$(PYTHON) -m pytest -c pytest-worldcup.ini -q

lint:
	ruff check $(LINT_PATHS)

audit-pit:
	$(PYTHON) scripts/audit_pit_compliance.py

reproduce-benchmark:
	$(PYTHON) scripts/reproduce_benchmark.py

reproduce-benchmark-smoke:
	$(PYTHON) scripts/reproduce_benchmark.py --smoke

demo-static:
	$(PYTHON) scripts/export_killer_demo.py

demo:
	$(PYTHON) scripts/run_killer_demo.py

docker-build:
	docker build -t market-causal-engine:local .
