FROM golang:1.21-bullseye AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y git gcc make && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy go mod files
COPY go.mod go.sum ./

# Download dependencies
RUN go mod download

# Copy source code
COPY . .

# Build the binary
ARG SERVICE=prometheus-collector
RUN CGO_ENABLED=1 GOOS=linux go build -a -installsuffix cgo \
    -o /collector ./${SERVICE}/cmd

# Runtime image
FROM alpine:latest

RUN apk --no-cache add ca-certificates

WORKDIR /app

# Copy the binary
COPY --from=builder /collector ./collector

# Create non-root user
RUN adduser -D -u 1000 collector
USER collector

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget --no-verbose --tries=1 --spider http://localhost:8080/health || exit 1

# Run the collector
ENTRYPOINT ["./collector"]
