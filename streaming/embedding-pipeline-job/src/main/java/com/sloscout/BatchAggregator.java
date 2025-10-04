package com.sloscout;

import org.apache.flink.streaming.api.functions.windowing.ProcessAllWindowFunction;
import org.apache.flink.streaming.api.windowing.windows.GlobalWindow;
import org.apache.flink.util.Collector;
import org.apache.avro.generic.GenericRecord;

import java.util.ArrayList;
import java.util.List;

/**
 * Batch aggregation per T073
 * Batch 100 capsules before calling embedding service for efficiency
 */
public class BatchAggregator extends ProcessAllWindowFunction<
    GenericRecord,
    CapsuleBatch,
    GlobalWindow
> {

    @Override
    public void process(
        Context context,
        Iterable<GenericRecord> elements,
        Collector<CapsuleBatch> out
    ) throws Exception {

        List<CapsuleRecord> capsules = new ArrayList<>();

        // Collect capsules in batch
        for (GenericRecord record : elements) {
            CapsuleRecord capsule = new CapsuleRecord(
                (String) record.get("capsule_id"),
                (String) record.get("fingerprint_hash"),
                (String) record.get("template"),
                (String) record.get("service_name"),
                (String) record.get("environment"),
                (String) record.get("severity"),
                (Long) record.get("time_bucket")
            );
            capsules.add(capsule);

            // Emit batch when reaching 100 capsules
            if (capsules.size() >= 100) {
                out.collect(new CapsuleBatch(capsules));
                capsules.clear();
            }
        }

        // Emit remaining capsules
        if (!capsules.isEmpty()) {
            out.collect(new CapsuleBatch(capsules));
        }
    }

    /**
     * Data class for capsule record
     */
    public static class CapsuleRecord {
        public final String capsuleId;
        public final String fingerprintHash;
        public final String template;
        public final String serviceName;
        public final String environment;
        public final String severity;
        public final long timeBucket;

        public CapsuleRecord(
            String capsuleId,
            String fingerprintHash,
            String template,
            String serviceName,
            String environment,
            String severity,
            long timeBucket
        ) {
            this.capsuleId = capsuleId;
            this.fingerprintHash = fingerprintHash;
            this.template = template;
            this.serviceName = serviceName;
            this.environment = environment;
            this.severity = severity;
            this.timeBucket = timeBucket;
        }
    }

    /**
     * Batch of capsules
     */
    public static class CapsuleBatch {
        public final List<CapsuleRecord> capsules;

        public CapsuleBatch(List<CapsuleRecord> capsules) {
            this.capsules = new ArrayList<>(capsules);
        }

        public int size() {
            return capsules.size();
        }
    }
}
