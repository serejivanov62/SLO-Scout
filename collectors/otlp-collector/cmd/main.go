package main

import (
	"context"
	"fmt"
	"log"
	"net"
	"os"
	"time"

	"github.com/linkedin/goavro/v2"
	"github.com/sloscout/collectors/common"
	"google.golang.org/grpc"
	tracecollectorv1 "go.opentelemetry.io/proto/otlp/collector/trace/v1"
)

// OTLPCollector receives OTLP traces via gRPC per T042
type OTLPCollector struct {
	kafkaProducer *common.KafkaProducer
	codec         *goavro.Codec
}

func main() {
	kafkaBootstrap := os.Getenv("KAFKA_BOOTSTRAP_SERVERS")
	if kafkaBootstrap == "" {
		kafkaBootstrap = "kafka:9092"
	}

	collector, err := NewOTLPCollector(kafkaBootstrap)
	if err != nil {
		log.Fatalf("Failed to create collector: %v", err)
	}
	defer collector.kafkaProducer.Close()

	// Start gRPC server on port 4317
	lis, err := net.Listen("tcp", ":4317")
	if err != nil {
		log.Fatalf("Failed to listen: %v", err)
	}

	grpcServer := grpc.NewServer()
	tracecollectorv1.RegisterTraceServiceServer(grpcServer, collector)

	log.Printf("OTLP collector listening on :4317")

	// Start health check
	healthChecker := common.NewHealthChecker()
	healthChecker.SetKafkaStatus(true)
	go func() {
		if err := healthChecker.StartHealthServer("8080"); err != nil {
			log.Printf("Health server error: %v", err)
		}
	}()

	if err := grpcServer.Serve(lis); err != nil {
		log.Fatalf("gRPC serve error: %v", err)
	}
}

func NewOTLPCollector(kafkaBootstrap string) (*OTLPCollector, error) {
	producer, err := common.NewKafkaProducer(kafkaBootstrap, "raw-telemetry")
	if err != nil {
		return nil, err
	}

	// Avro schema (same as Prometheus collector)
	schemaJSON := `{"type":"record","name":"TelemetryEvent","namespace":"com.sloscout.schema","fields":[{"name":"event_id","type":"string"},{"name":"service_name","type":"string"},{"name":"environment","type":{"type":"enum","name":"Environment","symbols":["prod","staging","dev"]}},{"name":"event_type","type":{"type":"enum","name":"EventType","symbols":["log","trace","metric"]}},{"name":"timestamp","type":{"type":"long","logicalType":"timestamp-millis"}},{"name":"severity","type":["null",{"type":"enum","name":"Severity","symbols":["DEBUG","INFO","WARN","ERROR","FATAL"]}],"default":null},{"name":"message","type":["null","string"],"default":null},{"name":"trace_id","type":["null","string"],"default":null},{"name":"span_id","type":["null","string"],"default":null},{"name":"attributes","type":{"type":"map","values":"string"},"default":{}},{"name":"raw_blob_s3_key","type":["null","string"],"default":null}]}`

	codec, err := goavro.NewCodec(schemaJSON)
	if err != nil {
		return nil, fmt.Errorf("failed to create Avro codec: %w", err)
	}

	return &OTLPCollector{
		kafkaProducer: producer,
		codec:         codec,
	}, nil
}

// Export implements OTLP TraceService
func (oc *OTLPCollector) Export(ctx context.Context, req *tracecollectorv1.ExportTraceServiceRequest) (*tracecollectorv1.ExportTraceServiceResponse, error) {
	for _, resourceSpan := range req.ResourceSpans {
		serviceName := "unknown"
		if svcAttr := resourceSpan.Resource.GetAttributes(); svcAttr != nil {
			for _, attr := range svcAttr {
				if attr.Key == "service.name" {
					serviceName = attr.Value.GetStringValue()
				}
			}
		}

		for _, scopeSpan := range resourceSpan.ScopeSpans {
			for _, span := range scopeSpan.Spans {
				event := map[string]interface{}{
					"event_id":     fmt.Sprintf("%d", time.Now().UnixNano()),
					"service_name": serviceName,
					"environment":  "prod",
					"event_type":   "trace",
					"timestamp":    span.StartTimeUnixNano / 1e6, // Convert to millis
					"severity":     nil,
					"message":      map[string]interface{}{"string": span.Name},
					"trace_id":     map[string]interface{}{"string": fmt.Sprintf("%x", span.TraceId)},
					"span_id":      map[string]interface{}{"string": fmt.Sprintf("%x", span.SpanId)},
					"attributes": map[string]interface{}{
						"span_kind": span.Kind.String(),
					},
					"raw_blob_s3_key": nil,
				}

				avroData, err := oc.codec.BinaryFromNative(nil, event)
				if err != nil {
					log.Printf("Avro encoding error: %v", err)
					continue
				}

				if err := oc.kafkaProducer.ProduceAsync(serviceName, avroData); err != nil {
					log.Printf("Kafka publish error: %v", err)
				}
			}
		}
	}

	oc.kafkaProducer.Flush(1000)
	return &tracecollectorv1.ExportTraceServiceResponse{}, nil
}
