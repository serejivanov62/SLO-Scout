.PHONY: all build clean test help
.PHONY: build-backend build-collectors build-streaming
.PHONY: build-go-prometheus build-go-otlp build-go-log
.PHONY: test-backend test-collectors test-streaming
.PHONY: docker-build docker-build-backend docker-build-collectors docker-build-streaming

# Default target
all: help

# Build all components
build: build-collectors build-backend

# Build Go collectors
build-collectors: build-go-prometheus build-go-otlp build-go-log

build-go-prometheus:
	@echo "Building Prometheus collector..."
	cd collectors && CGO_ENABLED=1 go build -o ../bin/prometheus-collector ./prometheus-collector/cmd

build-go-otlp:
	@echo "Building OTLP collector..."
	cd collectors && CGO_ENABLED=1 go build -o ../bin/otlp-collector ./otlp-collector/cmd

build-go-log:
	@echo "Building Log collector..."
	cd collectors && CGO_ENABLED=1 go build -o ../bin/log-collector ./log-collector/cmd

# Build Python backend
build-backend:
	@echo "Building Python backend..."
	@command -v poetry >/dev/null 2>&1 || { echo "Poetry not installed. Installing..."; python3 -m pip install poetry; }
	cd backend && poetry install --no-root

# Build Java streaming jobs (requires network access)
build-streaming:
	@echo "Building Flink streaming jobs..."
	cd streaming && /opt/gradle/bin/gradle jar --no-daemon

# Test targets
test-backend:
	@echo "Running backend tests..."
	cd backend && poetry run pytest tests/unit/ -v

test-collectors:
	@echo "Running collector tests..."
	cd collectors && go test ./... -v

test-streaming:
	@echo "Running streaming tests..."
	cd streaming && /opt/gradle/bin/gradle test --no-daemon

test: test-backend test-collectors test-streaming

# Docker build targets
docker-build: docker-build-backend docker-build-collectors docker-build-streaming

docker-build-backend:
	@echo "Building backend Docker image..."
	docker build -f infrastructure/docker/Dockerfile.python -t slo-scout/backend:dev backend/

docker-build-collectors:
	@echo "Building collectors Docker images..."
	docker build -f infrastructure/docker/Dockerfile.go --build-arg SERVICE=prometheus-collector -t slo-scout/prometheus-collector:dev collectors/
	docker build -f infrastructure/docker/Dockerfile.go --build-arg SERVICE=otlp-collector -t slo-scout/otlp-collector:dev collectors/
	docker build -f infrastructure/docker/Dockerfile.go --build-arg SERVICE=log-collector -t slo-scout/log-collector:dev collectors/

docker-build-streaming:
	@echo "Building streaming Docker image..."
	docker build -f infrastructure/docker/Dockerfile.java -t slo-scout/streaming:dev streaming/

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	rm -rf bin/
	rm -rf backend/.venv/
	rm -rf streaming/build/
	rm -rf streaming/.gradle/
	cd collectors && go clean

# Create bin directory
bin:
	mkdir -p bin

# Help target
help:
	@echo "SLO-Scout Build System"
	@echo "======================"
	@echo ""
	@echo "Available targets:"
	@echo "  make build              - Build all components (Go collectors + Python backend)"
	@echo "  make build-collectors   - Build all Go collectors"
	@echo "  make build-backend      - Build Python backend"
	@echo "  make build-streaming    - Build Flink streaming jobs (requires network)"
	@echo ""
	@echo "  make test               - Run all tests"
	@echo "  make test-backend       - Run backend tests"
	@echo "  make test-collectors    - Run collector tests"
	@echo "  make test-streaming     - Run streaming tests"
	@echo ""
	@echo "  make docker-build       - Build all Docker images"
	@echo "  make docker-build-backend    - Build backend Docker image"
	@echo "  make docker-build-collectors - Build collectors Docker images"
	@echo "  make docker-build-streaming  - Build streaming Docker image"
	@echo ""
	@echo "  make clean              - Clean build artifacts"
	@echo "  make help               - Show this help message"
	@echo ""
	@echo "Note: Building streaming jobs requires network access to Maven Central"
