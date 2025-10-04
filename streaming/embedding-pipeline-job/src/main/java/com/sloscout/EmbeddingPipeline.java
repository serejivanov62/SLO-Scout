package com.sloscout;

import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.connector.kafka.source.KafkaSource;
import org.apache.flink.connector.kafka.source.enumerator.initializer.OffsetsInitializer;
import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.avro.generic.GenericRecord;

/**
 * Embedding pipeline job per T071
 * Consumes capsule-events, calls embedding service API, produces to capsule-embeddings
 */
public class EmbeddingPipeline {

    public static void main(String[] args) throws Exception {
        // Environment setup
        final StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();

        // Configuration
        String kafkaBootstrap = System.getenv().getOrDefault("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092");
        String embeddingServiceUrl = System.getenv().getOrDefault("EMBEDDING_SERVICE_URL", "http://slo-scout-api:8000/embeddings");

        // Kafka source for capsule-events
        KafkaSource<GenericRecord> source = KafkaSource.<GenericRecord>builder()
            .setBootstrapServers(kafkaBootstrap)
            .setTopics("capsule-events")
            .setGroupId("embedding-pipeline")
            .setStartingOffsets(OffsetsInitializer.earliest())
            .setValueOnlyDeserializer(new AvroDeserializer())
            .build();

        DataStream<GenericRecord> capsuleStream = env.fromSource(
            source,
            WatermarkStrategy.noWatermarks(),
            "Capsule Source"
        );

        // Batch aggregation per T073 (batch 100 capsules)
        DataStream<CapsuleBatch> batchedStream = capsuleStream
            .countWindowAll(100)
            .process(new BatchAggregator());

        // Call embedding service per T072
        DataStream<EmbeddingResult> embeddingStream = batchedStream
            .flatMap(new EmbeddingServiceClient(embeddingServiceUrl));

        // Write to Vector DB per T074
        embeddingStream
            .addSink(new VectorDBWriter(
                System.getenv().getOrDefault("MILVUS_HOST", "milvus"),
                Integer.parseInt(System.getenv().getOrDefault("MILVUS_PORT", "19530"))
            ))
            .name("Vector DB Sink");

        // Also write to Kafka capsule-embeddings topic
        embeddingStream
            .sinkTo(createKafkaSink(kafkaBootstrap))
            .name("Capsule Embeddings Sink");

        env.execute("SLO-Scout Embedding Pipeline");
    }

    private static org.apache.flink.connector.kafka.sink.KafkaSink<EmbeddingResult> createKafkaSink(String bootstrap) {
        return org.apache.flink.connector.kafka.sink.KafkaSink.<EmbeddingResult>builder()
            .setBootstrapServers(bootstrap)
            .setRecordSerializer(
                org.apache.flink.connector.kafka.sink.KafkaRecordSerializationSchema.<EmbeddingResult>builder()
                    .setTopic("capsule-embeddings")
                    .setValueSerializationSchema(new EmbeddingResultSerializer())
                    .build()
            )
            .build();
    }

    // Placeholder classes (implemented in separate files)
    static class AvroDeserializer implements org.apache.flink.api.common.serialization.DeserializationSchema<GenericRecord> {
        @Override
        public GenericRecord deserialize(byte[] message) { return null; }
        @Override
        public boolean isEndOfStream(GenericRecord nextElement) { return false; }
        @Override
        public org.apache.flink.api.common.typeinfo.TypeInformation<GenericRecord> getProducedType() {
            return org.apache.flink.api.common.typeinfo.TypeInformation.of(GenericRecord.class);
        }
    }

    static class CapsuleBatch {}
    static class EmbeddingResult {}
    static class EmbeddingResultSerializer implements org.apache.flink.api.common.serialization.SerializationSchema<EmbeddingResult> {
        @Override
        public byte[] serialize(EmbeddingResult element) { return new byte[0]; }
    }
}
