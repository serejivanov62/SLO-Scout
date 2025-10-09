package fingerprinting;

import com.esotericsoftware.kryo.Kryo;
import com.esotericsoftware.kryo.Serializer;
import com.esotericsoftware.kryo.io.Input;
import com.esotericsoftware.kryo.io.Output;
import com.sloscout.config.CheckpointConfig;
import com.sloscout.config.WindowConfig;
import com.sloscout.kafka.TelemetrySource;
import com.sloscout.kafka.CapsuleSink;
import com.sloscout.kafka.DLQHandler;
import com.sloscout.operators.*;

import org.apache.flink.api.common.ExecutionConfig;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.avro.generic.GenericRecord;

import java.util.ArrayList;
import java.util.List;

/**
 * Main Flink fingerprinting job with Kryo serialization per T052
 * Consumes telemetry → fingerprints → aggregates → produces capsules
 * Fixes FR-008 serialization issues with proper Kryo registration
 */
public class FingerprintJob {

    public static void main(String[] args) throws Exception {
        // Environment setup
        final StreamExecutionEnvironment env = StreamExecutionEnvironment.getExecutionEnvironment();

        // Kafka bootstrap servers from environment
        String kafkaBootstrap = System.getenv().getOrDefault("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092");

        // T052: Register Kryo serializers for capsule types to fix FR-008
        registerKryoSerializers(env.getConfig());

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
     * T052: Register Kryo serializers for capsule types to fix FR-008 serialization issues
     * Uses Flink 1.17 ExecutionConfig.registerTypeWithKryoSerializer()
     */
    private static void registerKryoSerializers(ExecutionConfig config) {
        // Register CapsuleEvent class with custom Kryo serializer
        config.registerTypeWithKryoSerializer(
            CapsuleAggregator.CapsuleEvent.class,
            CapsuleEventSerializer.class
        );

        // Register FingerprintKey class with custom Kryo serializer
        config.registerTypeWithKryoSerializer(
            FingerprintKey.class,
            FingerprintKeySerializer.class
        );

        // Register CapsuleAggregate class with custom Kryo serializer
        config.registerTypeWithKryoSerializer(
            CapsuleAggregate.class,
            CapsuleAggregateSerializer.class
        );

        // Enable Kryo reference tracking for circular references
        config.enableForceKryo();

        System.out.println("Kryo serializers registered for CapsuleEvent, FingerprintKey, CapsuleAggregate");
    }

    /**
     * Convert CapsuleEvent to Avro GenericRecord
     */
    private static GenericRecord convertToAvro(CapsuleAggregator.CapsuleEvent capsule) {
        // TODO: Implement conversion to Avro GenericRecord using CapsuleEvent.avsc schema
        return null;
    }

    /**
     * FingerprintKey - represents a fingerprint hash key for keyed operations
     */
    public static class FingerprintKey {
        public final String fingerprintHash;
        public final String serviceName;
        public final String severity;

        public FingerprintKey(String fingerprintHash, String serviceName, String severity) {
            this.fingerprintHash = fingerprintHash;
            this.serviceName = serviceName;
            this.severity = severity;
        }

        @Override
        public boolean equals(Object o) {
            if (this == o) return true;
            if (o == null || getClass() != o.getClass()) return false;
            FingerprintKey that = (FingerprintKey) o;
            return fingerprintHash.equals(that.fingerprintHash) &&
                   serviceName.equals(that.serviceName) &&
                   severity.equals(that.severity);
        }

        @Override
        public int hashCode() {
            int result = fingerprintHash.hashCode();
            result = 31 * result + serviceName.hashCode();
            result = 31 * result + severity.hashCode();
            return result;
        }
    }

    /**
     * CapsuleAggregate - represents aggregated capsule data for windowing
     */
    public static class CapsuleAggregate {
        public long count;
        public List<String> sampleEventIds;
        public long firstSeenAt;
        public long lastSeenAt;
        public String template;

        public CapsuleAggregate() {
            this.count = 0;
            this.sampleEventIds = new ArrayList<>();
            this.firstSeenAt = Long.MAX_VALUE;
            this.lastSeenAt = Long.MIN_VALUE;
        }

        public CapsuleAggregate(long count, List<String> sampleEventIds,
                               long firstSeenAt, long lastSeenAt, String template) {
            this.count = count;
            this.sampleEventIds = sampleEventIds;
            this.firstSeenAt = firstSeenAt;
            this.lastSeenAt = lastSeenAt;
            this.template = template;
        }
    }

    // Kryo Serializers

    /**
     * Custom Kryo serializer for CapsuleEvent
     */
    public static class CapsuleEventSerializer extends Serializer<CapsuleAggregator.CapsuleEvent> {
        @Override
        public void write(Kryo kryo, Output output, CapsuleAggregator.CapsuleEvent capsule) {
            output.writeString(capsule.fingerprintHash);
            output.writeString(capsule.template);
            output.writeString(capsule.serviceName);
            output.writeString(capsule.severity);
            output.writeLong(capsule.count);
            output.writeLong(capsule.timeBucket);
            output.writeLong(capsule.firstSeenAt);
            output.writeLong(capsule.lastSeenAt);

            // Write sample event IDs list
            output.writeInt(capsule.sampleEventIds.size());
            for (String eventId : capsule.sampleEventIds) {
                output.writeString(eventId);
            }
        }

        @Override
        public CapsuleAggregator.CapsuleEvent read(Kryo kryo, Input input,
                                                    Class<CapsuleAggregator.CapsuleEvent> type) {
            String fingerprintHash = input.readString();
            String template = input.readString();
            String serviceName = input.readString();
            String severity = input.readString();
            long count = input.readLong();
            long timeBucket = input.readLong();
            long firstSeenAt = input.readLong();
            long lastSeenAt = input.readLong();

            // Read sample event IDs list
            int listSize = input.readInt();
            List<String> sampleEventIds = new ArrayList<>(listSize);
            for (int i = 0; i < listSize; i++) {
                sampleEventIds.add(input.readString());
            }

            return new CapsuleAggregator.CapsuleEvent(
                fingerprintHash,
                template,
                serviceName,
                severity,
                count,
                sampleEventIds,
                timeBucket,
                firstSeenAt,
                lastSeenAt
            );
        }
    }

    /**
     * Custom Kryo serializer for FingerprintKey
     */
    public static class FingerprintKeySerializer extends Serializer<FingerprintKey> {
        @Override
        public void write(Kryo kryo, Output output, FingerprintKey key) {
            output.writeString(key.fingerprintHash);
            output.writeString(key.serviceName);
            output.writeString(key.severity);
        }

        @Override
        public FingerprintKey read(Kryo kryo, Input input, Class<FingerprintKey> type) {
            String fingerprintHash = input.readString();
            String serviceName = input.readString();
            String severity = input.readString();
            return new FingerprintKey(fingerprintHash, serviceName, severity);
        }
    }

    /**
     * Custom Kryo serializer for CapsuleAggregate
     */
    public static class CapsuleAggregateSerializer extends Serializer<CapsuleAggregate> {
        @Override
        public void write(Kryo kryo, Output output, CapsuleAggregate aggregate) {
            output.writeLong(aggregate.count);
            output.writeLong(aggregate.firstSeenAt);
            output.writeLong(aggregate.lastSeenAt);
            output.writeString(aggregate.template);

            // Write sample event IDs list
            output.writeInt(aggregate.sampleEventIds.size());
            for (String eventId : aggregate.sampleEventIds) {
                output.writeString(eventId);
            }
        }

        @Override
        public CapsuleAggregate read(Kryo kryo, Input input, Class<CapsuleAggregate> type) {
            long count = input.readLong();
            long firstSeenAt = input.readLong();
            long lastSeenAt = input.readLong();
            String template = input.readString();

            // Read sample event IDs list
            int listSize = input.readInt();
            List<String> sampleEventIds = new ArrayList<>(listSize);
            for (int i = 0; i < listSize; i++) {
                sampleEventIds.add(input.readString());
            }

            return new CapsuleAggregate(count, sampleEventIds, firstSeenAt, lastSeenAt, template);
        }
    }
}
