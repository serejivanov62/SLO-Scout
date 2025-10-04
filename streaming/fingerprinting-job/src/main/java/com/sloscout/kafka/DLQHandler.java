package com.sloscout.kafka;

import org.apache.flink.api.common.functions.FilterFunction;
import org.apache.flink.connector.kafka.sink.KafkaSink;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.datastream.SingleOutputStreamOperator;
import org.apache.flink.util.OutputTag;

/**
 * Dead letter queue handler per T062
 * Send malformed events to raw-telemetry-dlq topic per streaming-capsule.yaml error handling
 */
public class DLQHandler {

    private static final String DLQ_TOPIC = "raw-telemetry-dlq";

    // Output tag for side output (DLQ)
    public static final OutputTag<ErrorEvent> DLQ_TAG = new OutputTag<ErrorEvent>("dlq"){};

    /**
     * Create DLQ sink
     */
    public static KafkaSink<ErrorEvent> createDLQSink(String bootstrapServers) {
        return KafkaSink.<ErrorEvent>builder()
            .setBootstrapServers(bootstrapServers)
            .setRecordSerializer(
                org.apache.flink.connector.kafka.sink.KafkaRecordSerializationSchema.<ErrorEvent>builder()
                    .setTopic(DLQ_TOPIC)
                    .setValueSerializationSchema(new ErrorEventSerializer())
                    .build()
            )
            .build();
    }

    /**
     * Filter for invalid events
     */
    public static class InvalidEventFilter implements FilterFunction<Object> {
        @Override
        public boolean filter(Object value) throws Exception {
            // Check if event is valid
            // Return false for invalid events (they go to DLQ)
            return isValid(value);
        }

        private boolean isValid(Object event) {
            // TODO: Implement validation logic
            // Check Avro schema compliance, required fields, etc.
            return true;
        }
    }

    /**
     * Error event for DLQ
     */
    public static class ErrorEvent {
        public final byte[] originalMessage;
        public final String errorReason;
        public final long timestamp;

        public ErrorEvent(byte[] originalMessage, String errorReason) {
            this.originalMessage = originalMessage;
            this.errorReason = errorReason;
            this.timestamp = System.currentTimeMillis();
        }
    }

    /**
     * Serializer for error events
     */
    private static class ErrorEventSerializer implements org.apache.flink.api.common.serialization.SerializationSchema<ErrorEvent> {
        @Override
        public byte[] serialize(ErrorEvent element) {
            // Serialize error event to JSON or Avro
            String json = String.format(
                "{\"error\":\"%s\",\"timestamp\":%d}",
                element.errorReason,
                element.timestamp
            );
            return json.getBytes();
        }
    }
}
