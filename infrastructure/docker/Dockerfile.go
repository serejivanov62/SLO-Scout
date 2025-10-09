FROM golang:1.21-bullseye AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y git gcc make && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy go mod files
COPY go.mod ./

# Copy source code
COPY . .

# Download dependencies and tidy
RUN go mod tidy && go mod download

# Build the binary
ARG SERVICE=prometheus-collector
RUN CGO_ENABLED=1 GOOS=linux go build -a \
    -ldflags="-w -s" -o /collector ./${SERVICE}/cmd

# Runtime image
FROM debian:bullseye-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates wget librdkafka1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the binary
COPY --from=builder /collector ./collector

# Create non-root user
RUN useradd -r -u 1000 -s /bin/false collector
USER collector

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:8080/health || exit 1

# Run the collector
ENTRYPOINT ["./collector"]
