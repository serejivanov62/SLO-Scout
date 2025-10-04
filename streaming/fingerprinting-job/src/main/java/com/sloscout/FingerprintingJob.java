package com.sloscout;

import com.sloscout.config.CheckpointConfig;
import com.sloscout.config.WindowConfig;
import com.sloscout.kafka.TelemetrySource;
import com.sloscout.kafka.CapsuleSink;
import com.sloscout.kafka.DLQHandler;
import com.sloscout.operators.*;

import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.avro.generic.GenericRecord;

/**
 * Main Flink fingerprinting job
 * Consumes telemetry → fingerprints → aggregates → produces capsules
 */
public class FingerprintingJob {

    public static void main(String[] args) throws Exception {
        // Environment setup
        final StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();

        // Kafka bootstrap servers from environment
        String kafkaBootstrap = System.getenv().getOrDefault("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092");

        // Configure checkpointing per T059
        CheckpointConfig.configureCheckpointing(env);

        // Create Kafka source per T060
        DataStream<GenericRecord> telemetryStream = env
            .fromSource(
                TelemetrySource.createSource(kafkaBootstrap),
                TelemetrySource.createWatermarkStrategy(),
                "Telemetry Source"
            );

        // Fingerprinting and aggregation pipeline
        DataStream<GenericRecord> capsuleStream = telemetryStream
            // Extract message field
            .map(record -> (String) record.get("message"))
            // T054: PII redaction
            .map(new PIIRedactionOperator())
            .filter(msg -> msg.redactionApplied || true) // Allow all, but mark redaction status
            // T053: Fingerprinting
            .map(msg -> new FingerprintOperator().map(msg.message))
            // Key by fingerprint hash
            .keyBy(msg -> msg.fingerprintHash)
            // T058: Windowing (1h tumbling)
            .window(WindowConfig.getTumblingWindows())
            .allowedLateness(WindowConfig.getAllowedLateness())
            // T057: Aggregation
            .process(new CapsuleAggregator())
            // Convert to Avro GenericRecord
            .map(capsule -> convertToAvro(capsule));

        // T061: Write to Kafka capsule-events topic
        capsuleStream.sinkTo(CapsuleSink.createSink(kafkaBootstrap))
            .name("Capsule Sink");

        // T062: DLQ for failed events
        DataStream<DLQHandler.ErrorEvent> dlqStream = telemetryStream
            .process(new org.apache.flink.streaming.api.functions.ProcessFunction<GenericRecord, DLQHandler.ErrorEvent>() {
                @Override
                public void processElement(
                    GenericRecord value,
                    Context ctx,
                    org.apache.flink.util.Collector<DLQHandler.ErrorEvent> out
                ) throws Exception {
                    try {
                        // Validate event
                        if (!isValidEvent(value)) {
                            out.collect(new DLQHandler.ErrorEvent(
                                value.toString().getBytes(),
                                "Invalid schema"
                            ));
                        }
                    } catch (Exception e) {
                        out.collect(new DLQHandler.ErrorEvent(
                            value.toString().getBytes(),
                            e.getMessage()
                        ));
                    }
                }

                private boolean isValidEvent(GenericRecord record) {
                    // Check required fields
                    return record.get("event_id") != null
                        && record.get("service_name") != null
                        && record.get("timestamp") != null;
                }
            });

        dlqStream.sinkTo(DLQHandler.createDLQSink(kafkaBootstrap))
            .name("DLQ Sink");

        // Execute job
        env.execute("SLO-Scout Fingerprinting Job");
    }

    /**
     * Convert CapsuleEvent to Avro GenericRecord
     */
    private static GenericRecord convertToAvro(CapsuleAggregator.CapsuleEvent capsule) {
        // TODO: Implement conversion to Avro GenericRecord using CapsuleEvent.avsc schema
        return null;
    }
}
