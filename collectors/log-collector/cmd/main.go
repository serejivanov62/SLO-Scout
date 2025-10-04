package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/linkedin/goavro/v2"
	"github.com/sloscout/collectors/common"
)

// LogCollector receives logs via HTTP per T043
type LogCollector struct {
	kafkaProducer *common.KafkaProducer
	codec         *goavro.Codec
}

func main() {
	kafkaBootstrap := os.Getenv("KAFKA_BOOTSTRAP_SERVERS")
	if kafkaBootstrap == "" {
		kafkaBootstrap = "kafka:9092"
	}

	collector, err := NewLogCollector(kafkaBootstrap)
	if err != nil {
		log.Fatalf("Failed to create collector: %v", err)
	}
	defer collector.kafkaProducer.Close()

	// HTTP server for FluentBit
	http.HandleFunc("/ingest/logs", collector.IngestHandler)

	// Health check
	healthChecker := common.NewHealthChecker()
	healthChecker.SetKafkaStatus(true)
	http.HandleFunc("/health", healthChecker.HealthHandler())

	log.Printf("Log collector listening on :9090")
	if err := http.ListenAndServe(":9090", nil); err != nil {
		log.Fatalf("HTTP server error: %v", err)
	}
}

func NewLogCollector(kafkaBootstrap string) (*LogCollector, error) {
	producer, err := common.NewKafkaProducer(kafkaBootstrap, "raw-telemetry")
	if err != nil {
		return nil, err
	}

	schemaJSON := `{"type":"record","name":"TelemetryEvent","namespace":"com.sloscout.schema","fields":[{"name":"event_id","type":"string"},{"name":"service_name","type":"string"},{"name":"environment","type":{"type":"enum","name":"Environment","symbols":["prod","staging","dev"]}},{"name":"event_type","type":{"type":"enum","name":"EventType","symbols":["log","trace","metric"]}},{"name":"timestamp","type":{"type":"long","logicalType":"timestamp-millis"}},{"name":"severity","type":["null",{"type":"enum","name":"Severity","symbols":["DEBUG","INFO","WARN","ERROR","FATAL"]}],"default":null},{"name":"message","type":["null","string"],"default":null},{"name":"trace_id","type":["null","string"],"default":null},{"name":"span_id","type":["null","string"],"default":null},{"name":"attributes","type":{"type":"map","values":"string"},"default":{}},{"name":"raw_blob_s3_key","type":["null","string"],"default":null}]}`

	codec, err := goavro.NewCodec(schemaJSON)
	if err != nil {
		return nil, fmt.Errorf("failed to create Avro codec: %w", err)
	}

	return &LogCollector{
		kafkaProducer: producer,
		codec:         codec,
	}, nil
}

func (lc *LogCollector) IngestHandler(w http.ResponseWriter, r *http.Request) {
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

		if err := lc.kafkaProducer.ProduceAsync(serviceName, avroData); err != nil {
			log.Printf("Kafka publish error: %v", err)
			continue
		}
		count++
	}

	lc.kafkaProducer.Flush(1000)

	w.WriteHeader(http.StatusOK)
	fmt.Fprintf(w, `{"ingested": %d}`, count)
	log.Printf("Ingested %d log entries", count)
}
