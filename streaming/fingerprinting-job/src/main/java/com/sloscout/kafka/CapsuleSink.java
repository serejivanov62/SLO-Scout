package com.sloscout.kafka;

import org.apache.flink.api.common.serialization.SerializationSchema;
import org.apache.flink.connector.base.DeliveryGuarantee;
import org.apache.flink.connector.kafka.sink.KafkaRecordSerializationSchema;
import org.apache.flink.connector.kafka.sink.KafkaSink;
import org.apache.avro.generic.GenericRecord;

/**
 * Kafka sink per T061
 * Produce to capsule-events topic, Avro serialization, transactional writes for exactly-once
 */
public class CapsuleSink {

    private static final String TOPIC = "capsule-events";
    private static final String TRANSACTION_ID_PREFIX = "fingerprinting-job";

    /**
     * Create Kafka sink for capsule events
     */
    public static KafkaSink<GenericRecord> createSink(String bootstrapServers) {
        return KafkaSink.<GenericRecord>builder()
            .setBootstrapServers(bootstrapServers)
            .setRecordSerializer(
                KafkaRecordSerializationSchema.builder()
                    .setTopic(TOPIC)
                    .setValueSerializationSchema(new AvroSerializationSchema())
                    .build()
            )
            .setDeliveryGuarantee(DeliveryGuarantee.EXACTLY_ONCE)
            .setTransactionalIdPrefix(TRANSACTION_ID_PREFIX)
            .setProperty("transaction.timeout.ms", "900000") // 15 minutes
            .build();
    }

    /**
     * Avro serialization schema
     */
    private static class AvroSerializationSchema implements SerializationSchema<GenericRecord> {

        @Override
        public byte[] serialize(GenericRecord record) {
            // TODO: Implement Avro serialization
            // This will use the CapsuleEvent.avsc schema
            return new byte[0];
        }
    }
}
