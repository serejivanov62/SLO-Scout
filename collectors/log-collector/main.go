package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"sync/atomic"
	"syscall"
	"time"

	"github.com/fsnotify/fsnotify"
	"github.com/linkedin/goavro/v2"
	"github.com/sloscout/collectors/common"
	"gopkg.in/yaml.v3"
)

const (
	configPath         = "/etc/slo-scout/collector/config.yaml"
	reconcileInterval  = 60 * time.Second
	shutdownTimeout    = 30 * time.Second
)

// CollectorConfig represents the ConfigMap configuration structure
type CollectorConfig struct {
	KafkaBootstrap string            `yaml:"kafka_bootstrap_servers"`
	Topic          string            `yaml:"topic"`
	Port           int               `yaml:"port"`
	LogLevel       string            `yaml:"log_level"`
	Labels         map[string]string `yaml:"labels"`
}

// LogCollector receives logs via HTTP per T043 with ConfigMap hot-reload per T051
type LogCollector struct {
	kafkaProducer  atomic.Value // *common.KafkaProducer
	codec          *goavro.Codec
	config         atomic.Value // *CollectorConfig
	configMu       sync.RWMutex
	server         *http.Server
	inFlightReqs   sync.WaitGroup
	shutdownChan   chan struct{}
}

func main() {
	collector, err := NewLogCollector()
	if err != nil {
		log.Fatalf("Failed to create collector: %v", err)
	}
	defer collector.Close()

	// Start ConfigMap watcher with reconciliation loop per T051
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	go collector.WatchConfigMap(ctx)

	// HTTP server for FluentBit
	mux := http.NewServeMux()
	mux.HandleFunc("/ingest/logs", collector.IngestHandler)

	// Health check
	healthChecker := common.NewHealthChecker()
	healthChecker.SetKafkaStatus(true)
	mux.HandleFunc("/health", healthChecker.HealthHandler())

	config := collector.GetConfig()
	collector.server = &http.Server{
		Addr:    fmt.Sprintf(":%d", config.Port),
		Handler: mux,
	}

	// Graceful shutdown handler
	go func() {
		sigChan := make(chan os.Signal, 1)
		signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
		<-sigChan

		log.Println("Shutdown signal received, waiting for in-flight requests...")

		shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), shutdownTimeout)
		defer shutdownCancel()

		// Stop accepting new requests
		if err := collector.server.Shutdown(shutdownCtx); err != nil {
			log.Printf("HTTP server shutdown error: %v", err)
		}

		// Wait for in-flight requests to complete
		done := make(chan struct{})
		go func() {
			collector.inFlightReqs.Wait()
			close(done)
		}()

		select {
		case <-done:
			log.Println("All in-flight requests completed")
		case <-shutdownCtx.Done():
			log.Println("Shutdown timeout reached, forcing exit")
		}

		close(collector.shutdownChan)
		cancel()
	}()

	log.Printf("Log collector listening on :%d", config.Port)
	if err := collector.server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("HTTP server error: %v", err)
	}

	<-collector.shutdownChan
	log.Println("Collector shutdown complete")
}

func NewLogCollector() (*LogCollector, error) {
	// Load initial configuration
	config, err := loadConfig(configPath)
	if err != nil {
		// Fallback to environment variables if ConfigMap not available
		config = &CollectorConfig{
			KafkaBootstrap: getEnvOrDefault("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
			Topic:          getEnvOrDefault("KAFKA_TOPIC", "raw-telemetry"),
			Port:           9090,
			LogLevel:       "INFO",
			Labels:         make(map[string]string),
		}
		log.Printf("Using default config (ConfigMap not found): %v", err)
	}

	producer, err := common.NewKafkaProducer(config.KafkaBootstrap, config.Topic)
	if err != nil {
		return nil, err
	}

	schemaJSON := `{"type":"record","name":"TelemetryEvent","namespace":"com.sloscout.schema","fields":[{"name":"event_id","type":"string"},{"name":"service_name","type":"string"},{"name":"environment","type":{"type":"enum","name":"Environment","symbols":["prod","staging","dev"]}},{"name":"event_type","type":{"type":"enum","name":"EventType","symbols":["log","trace","metric"]}},{"name":"timestamp","type":{"type":"long","logicalType":"timestamp-millis"}},{"name":"severity","type":["null",{"type":"enum","name":"Severity","symbols":["DEBUG","INFO","WARN","ERROR","FATAL"]}],"default":null},{"name":"message","type":["null","string"],"default":null},{"name":"trace_id","type":["null","string"],"default":null},{"name":"span_id","type":["null","string"],"default":null},{"name":"attributes","type":{"type":"map","values":"string"},"default":{}},{"name":"raw_blob_s3_key","type":["null","string"],"default":null}]}`

	codec, err := goavro.NewCodec(schemaJSON)
	if err != nil {
		return nil, fmt.Errorf("failed to create Avro codec: %w", err)
	}

	collector := &LogCollector{
		codec:        codec,
		shutdownChan: make(chan struct{}),
	}
	collector.kafkaProducer.Store(producer)
	collector.config.Store(config)

	return collector, nil
}

// WatchConfigMap implements T051: fsnotify-based ConfigMap watch with 60s reconciliation loop
func (lc *LogCollector) WatchConfigMap(ctx context.Context) {
	watcher, err := fsnotify.NewWatcher()
	if err != nil {
		log.Printf("Failed to create fsnotify watcher: %v, using reconciliation loop only", err)
		lc.reconciliationLoop(ctx)
		return
	}
	defer watcher.Close()

	// Watch the ConfigMap file
	if err := watcher.Add(configPath); err != nil {
		log.Printf("Failed to watch ConfigMap at %s: %v, using reconciliation loop only", configPath, err)
		lc.reconciliationLoop(ctx)
		return
	}

	log.Printf("ConfigMap watcher started for %s", configPath)

	ticker := time.NewTicker(reconcileInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			log.Println("ConfigMap watcher stopped")
			return

		case event, ok := <-watcher.Events:
			if !ok {
				return
			}

			// ConfigMaps in Kubernetes are updated via symlink changes
			// We need to handle Write, Create, and Remove events
			if event.Op&(fsnotify.Write|fsnotify.Create|fsnotify.Remove) != 0 {
				log.Printf("ConfigMap change detected: %s", event.Op)

				// Small delay to ensure file write is complete
				time.Sleep(100 * time.Millisecond)

				if err := lc.reloadConfig(); err != nil {
					log.Printf("Failed to reload config: %v", err)
				} else {
					log.Println("ConfigMap reloaded successfully")
				}

				// Re-watch the file after symlink update
				watcher.Remove(configPath)
				if err := watcher.Add(configPath); err != nil {
					log.Printf("Failed to re-watch ConfigMap: %v", err)
				}
			}

		case err, ok := <-watcher.Errors:
			if !ok {
				return
			}
			log.Printf("ConfigMap watcher error: %v", err)

		case <-ticker.C:
			// Reconciliation loop fallback per T051 Decision 6
			if err := lc.reloadConfig(); err != nil {
				log.Printf("Reconciliation reload failed: %v", err)
			}
		}
	}
}

// reconciliationLoop is a fallback when fsnotify is not available
func (lc *LogCollector) reconciliationLoop(ctx context.Context) {
	ticker := time.NewTicker(reconcileInterval)
	defer ticker.Stop()

	log.Printf("Running reconciliation-only mode (60s interval)")

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if err := lc.reloadConfig(); err != nil {
				log.Printf("Reconciliation reload failed: %v", err)
			}
		}
	}
}

// reloadConfig performs graceful config reload without dropping telemetry events
func (lc *LogCollector) reloadConfig() error {
	newConfig, err := loadConfig(configPath)
	if err != nil {
		return fmt.Errorf("failed to load config: %w", err)
	}

	oldConfig := lc.GetConfig()

	// Check if Kafka config changed
	if newConfig.KafkaBootstrap != oldConfig.KafkaBootstrap || newConfig.Topic != oldConfig.Topic {
		log.Printf("Kafka configuration changed, creating new producer...")

		newProducer, err := common.NewKafkaProducer(newConfig.KafkaBootstrap, newConfig.Topic)
		if err != nil {
			return fmt.Errorf("failed to create new Kafka producer: %w", err)
		}

		// Wait for in-flight requests to complete before swapping
		// This ensures no telemetry events are dropped
		lc.inFlightReqs.Wait()

		oldProducer := lc.kafkaProducer.Swap(newProducer).(*common.KafkaProducer)

		// Flush old producer before closing
		oldProducer.Flush(5000)
		oldProducer.Close()

		log.Printf("Kafka producer updated: %s -> %s", oldConfig.KafkaBootstrap, newConfig.KafkaBootstrap)
	}

	// Update config atomically
	lc.config.Store(newConfig)

	log.Printf("Configuration reloaded: port=%d, topic=%s", newConfig.Port, newConfig.Topic)
	return nil
}

func (lc *LogCollector) GetConfig() *CollectorConfig {
	return lc.config.Load().(*CollectorConfig)
}

func (lc *LogCollector) IngestHandler(w http.ResponseWriter, r *http.Request) {
	// Track in-flight request to ensure graceful shutdown
	lc.inFlightReqs.Add(1)
	defer lc.inFlightReqs.Done()

	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "Failed to read body", http.StatusBadRequest)
		return
	}
	defer r.Body.Close()

	// Parse JSON logs (FluentBit format)
	var logs []map[string]interface{}
	if err := json.Unmarshal(body, &logs); err != nil {
		http.Error(w, "Invalid JSON", http.StatusBadRequest)
		return
	}

	producer := lc.kafkaProducer.Load().(*common.KafkaProducer)
	count := 0

	for _, logEntry := range logs {
		serviceName := "unknown"
		if svc, ok := logEntry["service"].(string); ok {
			serviceName = svc
		}

		message := ""
		if msg, ok := logEntry["message"].(string); ok {
			message = msg
		}

		severity := "INFO"
		if sev, ok := logEntry["severity"].(string); ok {
			severity = sev
		}

		event := map[string]interface{}{
			"event_id":     fmt.Sprintf("%d", time.Now().UnixNano()),
			"service_name": serviceName,
			"environment":  "prod",
			"event_type":   "log",
			"timestamp":    time.Now().UnixMilli(),
			"severity":     map[string]interface{}{"string": severity},
			"message":      map[string]interface{}{"string": message},
			"trace_id":     nil,
			"span_id":      nil,
			"attributes":   logEntry,
			"raw_blob_s3_key": nil,
		}

		avroData, err := lc.codec.BinaryFromNative(nil, event)
		if err != nil {
			log.Printf("Avro encoding error: %v", err)
			continue
		}

		if err := producer.ProduceAsync(serviceName, avroData); err != nil {
			log.Printf("Kafka publish error: %v", err)
			continue
		}
		count++
	}

	producer.Flush(1000)

	w.WriteHeader(http.StatusOK)
	fmt.Fprintf(w, `{"ingested": %d}`, count)
	log.Printf("Ingested %d log entries", count)
}

func (lc *LogCollector) Close() {
	if producer := lc.kafkaProducer.Load(); producer != nil {
		producer.(*common.KafkaProducer).Close()
	}
}

func loadConfig(path string) (*CollectorConfig, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}

	var config CollectorConfig
	if err := yaml.Unmarshal(data, &config); err != nil {
		return nil, fmt.Errorf("failed to parse config: %w", err)
	}

	// Apply defaults
	if config.Port == 0 {
		config.Port = 9090
	}
	if config.Topic == "" {
		config.Topic = "raw-telemetry"
	}
	if config.LogLevel == "" {
		config.LogLevel = "INFO"
	}

	return &config, nil
}

func getEnvOrDefault(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}
