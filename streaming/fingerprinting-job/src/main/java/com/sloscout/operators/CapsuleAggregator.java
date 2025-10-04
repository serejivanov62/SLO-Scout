package com.sloscout.operators;

import org.apache.flink.api.common.state.ValueState;
import org.apache.flink.api.common.state.ValueStateDescriptor;
import org.apache.flink.configuration.Configuration;
import org.apache.flink.streaming.api.functions.windowing.ProcessWindowFunction;
import org.apache.flink.streaming.api.windowing.windows.TimeWindow;
import org.apache.flink.util.Collector;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Capsule aggregation operator per T057
 * RocksDB state backend, keyed by fingerprint_hash, tumbling window 1h
 * Counts events and collects severity distribution
 */
public class CapsuleAggregator extends ProcessWindowFunction<
    TelemetryEvent,
    CapsuleEvent,
    String,  // Key: fingerprint_hash
    TimeWindow
> {

    private transient ValueState<CapsuleState> state;

    @Override
    public void open(Configuration parameters) throws Exception {
        super.open(parameters);

        ValueStateDescriptor<CapsuleState> descriptor = new ValueStateDescriptor<>(
            "capsule-state",
            CapsuleState.class
        );

        state = getRuntimeContext().getState(descriptor);
    }

    @Override
    public void process(
        String fingerprintHash,
        Context context,
        Iterable<TelemetryEvent> events,
        Collector<CapsuleEvent> out
    ) throws Exception {

        long count = 0;
        Map<String, Integer> severityDistribution = new HashMap<>();
        List<String> sampleEventIds = new ArrayList<>();
        String template = null;
        String serviceName = null;
        String severity = null;
        long firstSeenAt = Long.MAX_VALUE;
        long lastSeenAt = Long.MIN_VALUE;

        // Aggregate events in window
        for (TelemetryEvent event : events) {
            count++;

            if (template == null) {
                template = event.template;
                serviceName = event.serviceName;
            }

            // Update severity distribution
            if (event.severity != null) {
                severity = event.severity;
                severityDistribution.put(
                    event.severity,
                    severityDistribution.getOrDefault(event.severity, 0) + 1
                );
            }

            // Track time range
            if (event.timestamp < firstSeenAt) {
                firstSeenAt = event.timestamp;
            }
            if (event.timestamp > lastSeenAt) {
                lastSeenAt = event.timestamp;
            }

            // Reservoir sampling for event IDs (max 10)
            if (sampleEventIds.size() < 10) {
                sampleEventIds.add(event.eventId);
            } else {
                // Replace randomly
                int randomIndex = (int) (Math.random() * count);
                if (randomIndex < 10) {
                    sampleEventIds.set(randomIndex, event.eventId);
                }
            }
        }

        // Create capsule event per streaming-capsule.yaml
        CapsuleEvent capsule = new CapsuleEvent(
            fingerprintHash,
            template,
            serviceName,
            severity,
            count,
            sampleEventIds,
            context.window().getStart(), // time_bucket
            firstSeenAt,
            lastSeenAt
        );

        out.collect(capsule);
    }

    /**
     * Internal state for capsule aggregation
     */
    public static class CapsuleState {
        public long count;
        public Map<String, Integer> severityDistribution;
        public List<String> samples;

        public CapsuleState() {
            this.count = 0;
            this.severityDistribution = new HashMap<>();
            this.samples = new ArrayList<>();
        }
    }

    /**
     * Input telemetry event
     */
    public static class TelemetryEvent {
        public String eventId;
        public String serviceName;
        public String severity;
        public String template;
        public long timestamp;

        public TelemetryEvent(String eventId, String serviceName, String severity, String template, long timestamp) {
            this.eventId = eventId;
            this.serviceName = serviceName;
            this.severity = severity;
            this.template = template;
            this.timestamp = timestamp;
        }
    }

    /**
     * Output capsule event per streaming-capsule.yaml
     */
    public static class CapsuleEvent {
        public String fingerprintHash;
        public String template;
        public String serviceName;
        public String severity;
        public long count;
        public List<String> sampleEventIds;
        public long timeBucket;
        public long firstSeenAt;
        public long lastSeenAt;

        public CapsuleEvent(
            String fingerprintHash,
            String template,
            String serviceName,
            String severity,
            long count,
            List<String> sampleEventIds,
            long timeBucket,
            long firstSeenAt,
            long lastSeenAt
        ) {
            this.fingerprintHash = fingerprintHash;
            this.template = template;
            this.serviceName = serviceName;
            this.severity = severity;
            this.count = count;
            this.sampleEventIds = sampleEventIds;
            this.timeBucket = timeBucket;
            this.firstSeenAt = firstSeenAt;
            this.lastSeenAt = lastSeenAt;
        }
    }
}
