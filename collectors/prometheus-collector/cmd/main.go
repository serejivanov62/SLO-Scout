package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"time"

	"github.com/linkedin/goavro/v2"
	"github.com/prometheus/client_golang/api"
	v1 "github.com/prometheus/client_golang/api/prometheus/v1"
	"github.com/prometheus/common/model"
	"github.com/sloscout/collectors/common"
)

// PrometheusCollector collects metrics via remote_read per T041
type PrometheusCollector struct {
	prometheusURL string
	kafkaProducer *common.KafkaProducer
	codec         *goavro.Codec
}

func main() {
	prometheusURL := os.Getenv("PROMETHEUS_URL")
	if prometheusURL == "" {
		prometheusURL = "http://prometheus:9090"
	}

	kafkaBootstrap := os.Getenv("KAFKA_BOOTSTRAP_SERVERS")
	if kafkaBootstrap == "" {
		kafkaBootstrap = "kafka:9092"
	}

	collector, err := NewPrometheusCollector(prometheusURL, kafkaBootstrap)
	if err != nil {
		log.Fatalf("Failed to create collector: %v", err)
	}
	defer collector.kafkaProducer.Close()

	log.Printf("Starting Prometheus collector: %s -> Kafka %s", prometheusURL, kafkaBootstrap)

	// Start health check server
	healthChecker := common.NewHealthChecker()
	go func() {
		if err := healthChecker.StartHealthServer("8080"); err != nil {
			log.Printf("Health server error: %v", err)
		}
	}()

	// Collect metrics every 30 seconds
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for range ticker.C {
		if err := collector.CollectAndPublish(); err != nil {
			log.Printf("Collection error: %v", err)
			healthChecker.SetKafkaStatus(false)
		} else {
			healthChecker.SetKafkaStatus(true)
		}
	}
}

func NewPrometheusCollector(prometheusURL, kafkaBootstrap string) (*PrometheusCollector, error) {
	// Create Kafka producer
	producer, err := common.NewKafkaProducer(kafkaBootstrap, "raw-telemetry")
	if err != nil {
		return nil, err
	}

	// Load Avro schema
	schemaJSON := `{
		"type": "record",
		"name": "TelemetryEvent",
		"namespace": "com.sloscout.schema",
		"fields": [
			{"name": "event_id", "type": "string"},
			{"name": "service_name", "type": "string"},
			{"name": "environment", "type": {"type": "enum", "name": "Environment", "symbols": ["prod", "staging", "dev"]}},
			{"name": "event_type", "type": {"type": "enum", "name": "EventType", "symbols": ["log", "trace", "metric"]}},
			{"name": "timestamp", "type": {"type": "long", "logicalType": "timestamp-millis"}},
			{"name": "severity", "type": ["null", {"type": "enum", "name": "Severity", "symbols": ["DEBUG", "INFO", "WARN", "ERROR", "FATAL"]}], "default": null},
			{"name": "message", "type": ["null", "string"], "default": null},
			{"name": "trace_id", "type": ["null", "string"], "default": null},
			{"name": "span_id", "type": ["null", "string"], "default": null},
			{"name": "attributes", "type": {"type": "map", "values": "string"}, "default": {}},
			{"name": "raw_blob_s3_key", "type": ["null", "string"], "default": null}
		]
	}`

	codec, err := goavro.NewCodec(schemaJSON)
	if err != nil {
		return nil, fmt.Errorf("failed to create Avro codec: %w", err)
	}

	return &PrometheusCollector{
		prometheusURL: prometheusURL,
		kafkaProducer: producer,
		codec:         codec,
	}, nil
}

func (pc *PrometheusCollector) CollectAndPublish() error {
	// Create Prometheus API client
	client, err := api.NewClient(api.Config{Address: pc.prometheusURL})
	if err != nil {
		return fmt.Errorf("failed to create Prometheus client: %w", err)
	}

	v1api := v1.NewAPI(client)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	// Query recent metrics (last 1 minute)
	query := `{__name__=~".+"}`
	result, warnings, err := v1api.Query(ctx, query, time.Now())
	if err != nil {
		return fmt.Errorf("query failed: %w", err)
	}

	if len(warnings) > 0 {
		log.Printf("Warnings: %v", warnings)
	}

	// Convert to TelemetryEvent and publish
	vector, ok := result.(model.Vector)
	if !ok {
		return fmt.Errorf("unexpected result type: %T", result)
	}

	for _, sample := range vector {
		event := map[string]interface{}{
			"event_id":     fmt.Sprintf("%d", time.Now().UnixNano()),
			"service_name": string(sample.Metric["job"]),
			"environment":  "prod", // Extract from labels if available
			"event_type":   "metric",
			"timestamp":    sample.Timestamp.Time().UnixMilli(),
			"severity":     map[string]interface{}{"string": "INFO"},
			"message":      map[string]interface{}{"string": fmt.Sprintf("%s=%f", sample.Metric["__name__"], sample.Value)},
			"trace_id":     nil,
			"span_id":      nil,
			"attributes": map[string]interface{}{
				"metric_name":  string(sample.Metric["__name__"]),
				"metric_value": fmt.Sprintf("%f", sample.Value),
			},
			"raw_blob_s3_key": nil,
		}

		// Encode to Avro
		avroData, err := pc.codec.BinaryFromNative(nil, event)
		if err != nil {
			log.Printf("Avro encoding error: %v", err)
			continue
		}

		// Publish to Kafka
		key := string(sample.Metric["job"])
		if err := pc.kafkaProducer.ProduceAsync(key, avroData); err != nil {
			log.Printf("Kafka publish error: %v", err)
		}
	}

	pc.kafkaProducer.Flush(5000)
	log.Printf("Published %d metric samples", len(vector))
	return nil
}
