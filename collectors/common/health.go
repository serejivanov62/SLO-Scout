package common

import (
	"encoding/json"
	"net/http"
	"sync"
)

// HealthChecker provides HTTP health check endpoint per T045
type HealthChecker struct {
	mu              sync.RWMutex
	kafkaConnected  bool
	diskSpoolStatus string
}

// NewHealthChecker creates health checker
func NewHealthChecker() *HealthChecker {
	return &HealthChecker{
		kafkaConnected:  false,
		diskSpoolStatus: "ok",
	}
}

// SetKafkaStatus updates Kafka connectivity status
func (hc *HealthChecker) SetKafkaStatus(connected bool) {
	hc.mu.Lock()
	defer hc.mu.Unlock()
	hc.kafkaConnected = connected
}

// SetDiskSpoolStatus updates disk spool status
func (hc *HealthChecker) SetDiskSpoolStatus(status string) {
	hc.mu.Lock()
	defer hc.mu.Unlock()
	hc.diskSpoolStatus = status
}

// HealthResponse represents health check response
type HealthResponse struct {
	Status          string `json:"status"`
	KafkaConnected  bool   `json:"kafka_connected"`
	DiskSpoolStatus string `json:"disk_spool_status"`
}

// HealthHandler returns HTTP handler for /health endpoint
func (hc *HealthChecker) HealthHandler() http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		hc.mu.RLock()
		defer hc.mu.RUnlock()

		status := "healthy"
		statusCode := http.StatusOK

		if !hc.kafkaConnected {
			status = "degraded"
			statusCode = http.StatusServiceUnavailable
		}

		if hc.diskSpoolStatus != "ok" {
			status = "degraded"
			statusCode = http.StatusServiceUnavailable
		}

		response := HealthResponse{
			Status:          status,
			KafkaConnected:  hc.kafkaConnected,
			DiskSpoolStatus: hc.diskSpoolStatus,
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(statusCode)
		json.NewEncoder(w).Encode(response)
	}
}

// StartHealthServer starts HTTP server for health checks
func (hc *HealthChecker) StartHealthServer(port string) error {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", hc.HealthHandler())

	server := &http.Server{
		Addr:    ":" + port,
		Handler: mux,
	}

	return server.ListenAndServe()
}
