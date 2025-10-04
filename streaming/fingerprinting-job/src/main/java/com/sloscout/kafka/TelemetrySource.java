package com.sloscout.kafka;

import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.api.common.serialization.DeserializationSchema;
import org.apache.flink.connector.kafka.source.KafkaSource;
import org.apache.flink.connector.kafka.source.enumerator.initializer.OffsetsInitializer;
import org.apache.avro.generic.GenericRecord;

import java.time.Duration;

/**
 * Kafka source per T060
 * Consume raw-telemetry topic, Avro deserialization, watermark strategy
 */
public class TelemetrySource {

    private static final String TOPIC = "raw-telemetry";
    private static final String CONSUMER_GROUP = "fingerprinting-job";

    /**
     * Create Kafka source for telemetry events
     */
    public static KafkaSource<GenericRecord> createSource(String bootstrapServers) {
        return KafkaSource.<GenericRecord>builder()
            .setBootstrapServers(bootstrapServers)
            .setTopics(TOPIC)
            .setGroupId(CONSUMER_GROUP)
            .setStartingOffsets(OffsetsInitializer.earliest())
            .setValueOnlyDeserializer(new AvroDeserializationSchema())
            .setProperty("enable.auto.commit", "false") // Flink manages offsets
            .setProperty("auto.offset.reset", "earliest")
            .build();
    }

    /**
     * Create watermark strategy with bounded out-of-orderness
     */
    public static WatermarkStrategy<GenericRecord> createWatermarkStrategy() {
        return WatermarkStrategy
            .<GenericRecord>forBoundedOutOfOrderness(Duration.ofMinutes(10))
            .withTimestampAssigner((event, timestamp) -> {
                // Extract timestamp from Avro record
                return (Long) event.get("timestamp");
            });
    }

    /**
     * Avro deserialization schema
     */
    private static class AvroDeserializationSchema implements DeserializationSchema<GenericRecord> {

        @Override
        public GenericRecord deserialize(byte[] message) {
            // TODO: Implement Avro deserialization
            // This will use the TelemetryEvent.avsc schema
            return null;
        }

        @Override
        public boolean isEndOfStream(GenericRecord nextElement) {
            return false;
        }

        @Override
        public org.apache.flink.api.common.typeinfo.TypeInformation<GenericRecord> getProducedType() {
            return org.apache.flink.api.common.typeinfo.TypeInformation.of(GenericRecord.class);
        }
    }
}
