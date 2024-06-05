SCENARIO ?= network-anomaly
VENV := .venv
PY := $(VENV)/bin/python

.PHONY: help install test smoke-local demo up down smoke roi scenarios

help:  ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/'

$(VENV)/.stamp: requirements-dev.txt
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -q -r requirements-dev.txt
	touch $@

install: $(VENV)/.stamp  ## create venv and install dependencies

test: install  ## unit tests
	$(PY) -m pytest -q

smoke-local: install  ## end-to-end pipeline check in one process (no Docker needed)
	$(PY) -m ttv.cli smoke --local --scenario $(SCENARIO)

demo: install  ## run pipeline + dashboard locally on :8090 (no Docker needed)
	$(PY) -m ttv.cli demo --scenario $(SCENARIO)

up: install  ## deploy to local kind cluster and record time-to-first-insight (SCENARIO=...)
	$(PY) -m ttv.cli up --scenario $(SCENARIO)

down: install  ## delete the kind cluster
	$(PY) -m ttv.cli down

smoke: install  ## end-to-end smoke test against the running cluster
	$(PY) -m ttv.cli smoke

roi: install  ## ROI estimate from the last `make up` run
	$(PY) -m ttv.cli roi --scenario $(SCENARIO)

scenarios: install  ## list scenario packs
	$(PY) -m ttv.cli scenarios
