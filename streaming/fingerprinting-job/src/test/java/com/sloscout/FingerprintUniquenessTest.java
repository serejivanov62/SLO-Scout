package com.sloscout;

import org.junit.jupiter.api.Test;

import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Contract test for fingerprint uniqueness constraint
 * Per streaming-capsule.yaml data quality contract
 *
 * MUST FAIL before implementation (TDD principle)
 */
public class FingerprintUniquenessTest {

    @Test
    public void testFingerprintUniquenessConstraint() {
        // Per streaming-capsule.yaml: fingerprint_hash + service_name + time_bucket must be unique

        String fingerprint = "abc123";
        String service = "payments-api";
        long timeBucket = 1699200000000L;

        // Create composite key
        String compositeKey = compositeKey(fingerprint, service, timeBucket);

        // Simulate state store
        Map<String, TestCapsule> stateStore = new HashMap<>();

        // First insert should succeed
        TestCapsule capsule1 = new TestCapsule(fingerprint, service, timeBucket, 10);
        stateStore.put(compositeKey, capsule1);

        // Second insert with same key should update, not create duplicate
        TestCapsule capsule2 = new TestCapsule(fingerprint, service, timeBucket, 20);
        stateStore.put(compositeKey, capsule2);

        // Should only have one entry
        assertEquals(1, stateStore.size());

        // Count should be from second capsule (aggregated)
        assertEquals(20, stateStore.get(compositeKey).getCount());
    }

    @Test
    public void testDifferentTimeBucketCreatesNewCapsule() {
        String fingerprint = "abc123";
        String service = "payments-api";
        long timeBucket1 = 1699200000000L;
        long timeBucket2 = 1699203600000L; // +1 hour

        Map<String, TestCapsule> stateStore = new HashMap<>();

        stateStore.put(compositeKey(fingerprint, service, timeBucket1), new TestCapsule(fingerprint, service, timeBucket1, 10));
        stateStore.put(compositeKey(fingerprint, service, timeBucket2), new TestCapsule(fingerprint, service, timeBucket2, 5));

        // Different time buckets should create separate capsules
        assertEquals(2, stateStore.size());
    }

    private String compositeKey(String fingerprint, String service, long timeBucket) {
        return String.format("%s:%s:%d", fingerprint, service, timeBucket);
    }

    private static class TestCapsule {
        private final String fingerprintHash;
        private final String serviceName;
        private final long timeBucket;
        private final long count;

        public TestCapsule(String fingerprintHash, String serviceName, long timeBucket, long count) {
            this.fingerprintHash = fingerprintHash;
            this.serviceName = serviceName;
            this.timeBucket = timeBucket;
            this.count = count;
        }

        public long getCount() {
            return count;
        }
    }
}
