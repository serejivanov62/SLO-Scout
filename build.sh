#!/bin/bash

# SLO-Scout Build Script
# This script builds all components of the SLO-Scout platform

set -e  # Exit on error

echo "======================================"
echo "SLO-Scout Build Script"
echo "======================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print success message
success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Function to print error message
error() {
    echo -e "${RED}✗ $1${NC}"
}

# Function to print warning message
warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Create bin directory
echo "Creating bin directory..."
mkdir -p bin
success "Bin directory created"
echo ""

# Build Go Collectors
echo "======================================"
echo "Building Go Collectors"
echo "======================================"
echo ""

echo "1. Building Prometheus Collector..."
if cd collectors && CGO_ENABLED=1 go build -o ../bin/prometheus-collector ./prometheus-collector/cmd 2>&1; then
    cd ..
    success "Prometheus collector built successfully"
else
    cd ..
    error "Failed to build Prometheus collector (network required for dependencies)"
fi
echo ""

echo "2. Building OTLP Collector..."
if cd collectors && CGO_ENABLED=1 go build -o ../bin/otlp-collector ./otlp-collector/cmd 2>&1; then
    cd ..
    success "OTLP collector built successfully"
else
    cd ..
    error "Failed to build OTLP collector (network required for dependencies)"
fi
echo ""

echo "3. Building Log Collector..."
if cd collectors && CGO_ENABLED=1 go build -o ../bin/log-collector ./log-collector/cmd 2>&1; then
    cd ..
    success "Log collector built successfully"
else
    cd ..
    error "Failed to build Log collector (network required for dependencies)"
fi
echo ""

# Build Python Backend
echo "======================================"
echo "Building Python Backend"
echo "======================================"
echo ""

if command -v poetry >/dev/null 2>&1; then
    echo "Poetry is installed"
else
    warning "Poetry not found. Installing..."
    python3 -m pip install poetry
fi

echo "Installing backend dependencies..."
if cd backend && poetry install --no-root 2>&1; then
    cd ..
    success "Backend dependencies installed"
else
    cd ..
    error "Failed to install backend dependencies"
fi
echo ""

# Build Flink Streaming Jobs
echo "======================================"
echo "Building Flink Streaming Jobs"
echo "======================================"
echo ""

warning "Note: Building streaming jobs requires network access to Maven Central"
echo "Attempting to build..."
if cd streaming && /opt/gradle/bin/gradle jar --no-daemon 2>&1 | tail -20; then
    cd ..
    success "Streaming jobs built successfully"
else
    cd ..
    error "Failed to build streaming jobs (network access required)"
fi
echo ""

# Summary
echo "======================================"
echo "Build Summary"
echo "======================================"
echo ""

if [ -f "bin/prometheus-collector" ]; then
    success "Prometheus Collector: bin/prometheus-collector"
else
    error "Prometheus Collector: FAILED"
fi

if [ -f "bin/otlp-collector" ]; then
    success "OTLP Collector: bin/otlp-collector"
else
    error "OTLP Collector: FAILED"
fi

if [ -f "bin/log-collector" ]; then
    success "Log Collector: bin/log-collector"
else
    error "Log Collector: FAILED"
fi

if [ -d "backend/.venv" ] || [ -f "backend/poetry.lock" ]; then
    success "Python Backend: Dependencies installed"
else
    error "Python Backend: FAILED"
fi

if [ -f "streaming/build/libs/slo-scout-streaming-1.0.0.jar" ]; then
    success "Flink Streaming Jobs: streaming/build/libs/"
else
    error "Flink Streaming Jobs: FAILED (may require network access)"
fi

echo ""
echo "======================================"
echo "Build complete!"
echo "======================================"
echo ""
echo "To run components:"
echo "  Backend:    cd backend && poetry run uvicorn src.main:app --reload"
echo "  Collectors: ./bin/prometheus-collector (or otlp-collector, log-collector)"
echo ""
