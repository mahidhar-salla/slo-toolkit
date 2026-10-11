# slo-toolkit. `make demo` is the one command to try: it needs only Python 3.11+.
PYTHON ?= python3
VENV   ?= .venv
BIN    := $(VENV)/bin
SPEC   ?= examples/http-api/checkout-api.slo.yaml
OUT    ?= out
PROMTOOL ?= $(shell command -v promtool 2>/dev/null)
HELM     ?= $(shell command -v helm 2>/dev/null)

.DEFAULT_GOAL := help
.PHONY: help install demo test lint fmt examples check-examples check-rules helm ci stack-up stack-down chaos clean

help: ## Show targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

$(BIN)/slo-toolkit: pyproject.toml
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install -q --upgrade pip
	$(BIN)/pip install -q -e ".[dev]"
	@touch $@

install: $(BIN)/slo-toolkit ## Create .venv and install with dev tools

demo: install ## End-to-end demo on synthetic data (no Docker needed)
	@echo "\n\033[1m1) What does a 99.9% / 30d objective allow?\033[0m"
	@$(BIN)/slo-toolkit calc --objective 99.9 --window 30d
	@echo "\n\033[1m2) Validate the spec\033[0m"
	@$(BIN)/slo-toolkit validate $(SPEC)
	@echo "\n\033[1m3) Generate Prometheus rules, Grafana dashboard and Helm values\033[0m"
	@$(BIN)/slo-toolkit generate $(SPEC) -o $(OUT) --helm-values
	@echo "\n\033[1m4) 30 days of synthetic traffic: a 4-min blip, a 40-min outage, a 2-day slow burn\033[0m"
	@$(BIN)/slo-toolkit simulate $(SPEC) -o $(OUT)/samples.csv
	@echo "\n\033[1m5) Budget report + replay of which alerts would have fired\033[0m"
	@$(BIN)/slo-toolkit report $(SPEC) --data $(OUT)/samples.csv
	@if [ -n "$(PROMTOOL)" ]; then \
	  echo "\033[1m6) promtool: lint and unit-test the generated rules\033[0m"; \
	  $(PROMTOOL) check rules $(OUT)/*.rules.yaml && $(PROMTOOL) test rules tests/promtool/*.test.yaml; \
	else echo "(promtool not installed; skipping rule lint. CI runs it.)"; fi

test: install ## Unit tests
	$(BIN)/pytest

lint: install ## ruff + format check + mypy
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .
	$(BIN)/mypy

fmt: install ## Auto-format
	$(BIN)/ruff format .
	$(BIN)/ruff check --fix .

examples: install ## Regenerate committed outputs under examples/*/out
	@for spec in examples/*/*.slo.yaml; do $(BIN)/slo-toolkit generate $$spec -o $$(dirname $$spec)/out; done

check-examples: examples ## Fail if committed example outputs are stale
	git diff --exit-code -- examples

check-rules: ## promtool check + unit tests for generated rules
	@test -n "$(PROMTOOL)" || { echo "promtool not found"; exit 1; }
	$(PROMTOOL) check rules examples/*/out/*.rules.yaml
	$(PROMTOOL) test rules tests/promtool/*.test.yaml

helm: install ## helm lint + template the chart with generated values
	@test -n "$(HELM)" || { echo "helm not found"; exit 1; }
	$(BIN)/slo-toolkit generate $(SPEC) -o $(OUT) --helm-values > /dev/null
	$(HELM) lint charts/slo-rules -f $(OUT)/checkout-api.values.yaml
	$(HELM) template slo charts/slo-rules -f $(OUT)/checkout-api.values.yaml > $(OUT)/rendered.yaml
	@echo "rendered: $(OUT)/rendered.yaml"

ci: lint test check-rules helm ## Everything CI runs

stack-up: ## Docker: synthetic service + Prometheus + Grafana (http://localhost:3000)
	docker compose up -d
	@echo "Grafana http://localhost:3000   Prometheus http://localhost:9090/alerts   then: make chaos"

stack-down: ## Docker: stop the stack
	docker compose down -v

chaos: ## Inject 20% errors for 10 minutes into the demo service
	curl -fsS -XPOST 'http://localhost:8080/chaos?error_rate=0.2&latency_ms=400&seconds=600'; echo

clean: ## Remove build output
	rm -rf $(OUT) .pytest_cache .ruff_cache .mypy_cache .local-stack
