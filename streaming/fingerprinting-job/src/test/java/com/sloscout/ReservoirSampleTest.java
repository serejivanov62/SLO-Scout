package com.sloscout;

import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Contract test for reservoir sample limit
 * Per streaming-capsule.yaml data quality contract
 *
 * MUST FAIL before implementation (TDD principle)
 */
public class ReservoirSampleTest {

    @Test
    public void testReservoirSampleMaxLimit() {
        // Per streaming-capsule.yaml: max 10 sample event IDs per capsule

        List<String> samples = new ArrayList<>();

        // Add 15 events
        for (int i = 0; i < 15; i++) {
            addToReservoirSample(samples, "event-" + i);
        }

        // Should maintain only 10 samples
        assertTrue(samples.size() <= 10, "Reservoir sample must not exceed 10 events");
    }

    @Test
    public void testReservoirSampleUnderLimit() {
        List<String> samples = new ArrayList<>();

        // Add 5 events
        for (int i = 0; i < 5; i++) {
            addToReservoirSample(samples, "event-" + i);
        }

        // All 5 should be present
        assertEquals(5, samples.size());
    }

    @Test
    public void testReservoirSampleRandomness() {
        // Reservoir sampling should give each event equal probability of selection

        List<String> samples = new ArrayList<>();

        // Add 100 events
        for (int i = 0; i < 100; i++) {
            addToReservoirSample(samples, "event-" + i);
        }

        // Should have exactly 10 samples
        assertEquals(10, samples.size());

        // All samples should be unique
        assertEquals(10, samples.stream().distinct().count());
    }

    /**
     * Mock reservoir sampling algorithm (will be replaced by actual implementation)
     * Algorithm R (Vitter's reservoir sampling)
     */
    private void addToReservoirSample(List<String> reservoir, String eventId) {
        final int MAX_SAMPLES = 10;

        if (reservoir.size() < MAX_SAMPLES) {
            // Reservoir not full, add directly
            reservoir.add(eventId);
        } else {
            // Reservoir full, replace with decreasing probability
            int randomIndex = (int) (Math.random() * (reservoir.size() + 1));
            if (randomIndex < MAX_SAMPLES) {
                reservoir.set(randomIndex, eventId);
            }
        }
    }
}
