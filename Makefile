.PHONY: validate-native test run run-worker diagnostics docker-up docker-down clean

PYTHON ?= python3

# Run one-command full native scientific validation harness
validate-native:
	$(PYTHON) validate_native_runtime.py --mode AUTO

# Run unified multi-tier test suite
test:
	$(PYTHON) run_tests.py

# Run system capability diagnostics
diagnostics:
	$(PYTHON) -m aidd_worker.diagnostics

# Start the worker service locally
run-worker:
	./aidd_worker/run_worker.sh

# Start the main web application
run-app:
	./run.sh

# Start complete multi-container scientific environment with Docker Compose
docker-up:
	docker compose up --build

# Stop Docker Compose services
docker-down:
	docker compose down

# Clean temporary runtime data
clean:
	rm -rf data/jobs/* data/artifacts/*
	rm -f native_validation_report.json native_validation_report.html
