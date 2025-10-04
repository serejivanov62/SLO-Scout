package com.sloscout.operators;

import org.apache.flink.api.common.functions.RichMapFunction;
import org.apache.flink.configuration.Configuration;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/**
 * Reservoir sampling operator per T056
 * Maintains max 10 samples per fingerprint using Algorithm R (Vitter's reservoir sampling)
 */
public class ReservoirSamplingOperator extends RichMapFunction<EventWithSamples, EventWithSamples> {

    private static final int MAX_SAMPLES = 10;
    private Random random;

    @Override
    public void open(Configuration parameters) throws Exception {
        super.open(parameters);
        this.random = new Random();
    }

    @Override
    public EventWithSamples map(EventWithSamples event) throws Exception {
        List<String> reservoir = event.samples;
        long currentCount = event.totalCount;

        // Add new event ID to reservoir
        String newEventId = event.eventId;

        if (reservoir.size() < MAX_SAMPLES) {
            // Reservoir not full, add directly
            reservoir.add(newEventId);
        } else {
            // Reservoir full, replace with probability k/currentCount
            // where k = MAX_SAMPLES
            long randomIndex = Math.abs(random.nextLong()) % currentCount;
            if (randomIndex < MAX_SAMPLES) {
                reservoir.set((int) randomIndex, newEventId);
            }
        }

        return new EventWithSamples(
            event.fingerprintHash,
            event.eventId,
            reservoir,
            currentCount
        );
    }

    /**
     * Data class for event with samples
     */
    public static class EventWithSamples {
        public final String fingerprintHash;
        public final String eventId;
        public final List<String> samples;
        public final long totalCount;

        public EventWithSamples(String fingerprintHash, String eventId, List<String> samples, long totalCount) {
            this.fingerprintHash = fingerprintHash;
            this.eventId = eventId;
            this.samples = new ArrayList<>(samples);
            this.totalCount = totalCount;
        }

        public EventWithSamples(String fingerprintHash, String eventId) {
            this.fingerprintHash = fingerprintHash;
            this.eventId = eventId;
            this.samples = new ArrayList<>();
            this.totalCount = 1;
        }
    }
}
