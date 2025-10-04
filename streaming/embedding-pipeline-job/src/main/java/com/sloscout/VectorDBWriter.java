package com.sloscout;

import org.apache.flink.streaming.api.functions.sink.RichSinkFunction;
import org.apache.flink.configuration.Configuration;

/**
 * Vector DB writer per T074
 * Writes CapsuleEmbedding to Milvus via gRPC, handles write failures
 */
public class VectorDBWriter extends RichSinkFunction<EmbeddingResult> {

    private final String milvusHost;
    private final int milvusPort;

    private transient MilvusClient milvusClient;

    public VectorDBWriter(String milvusHost, int milvusPort) {
        this.milvusHost = milvusHost;
        this.milvusPort = milvusPort;
    }

    @Override
    public void open(Configuration parameters) throws Exception {
        super.open(parameters);

        // Initialize Milvus client
        this.milvusClient = new MilvusClient(milvusHost, milvusPort);
    }

    @Override
    public void invoke(EmbeddingResult result, Context context) throws Exception {
        try {
            // Write to Milvus
            milvusClient.insert(
                result.capsuleId,
                result.fingerprintHash,
                result.serviceName,
                result.environment,
                result.severity,
                result.timeBucket,
                result.embedding
            );

        } catch (Exception e) {
            // Per streaming-capsule.yaml error handling:
            // Fallback to TimescaleDB-only storage, alert on-call
            logWriteFailure(result, e);

            // Store in fallback storage (TimescaleDB)
            storeFallback(result);

            // Alert (would integrate with alerting system)
            alertOnCall("Vector DB write failed", e);
        }
    }

    @Override
    public void close() throws Exception {
        if (milvusClient != null) {
            milvusClient.close();
        }
        super.close();
    }

    private void logWriteFailure(EmbeddingResult result, Exception e) {
        System.err.println("Failed to write to Milvus: capsule_id=" + result.capsuleId + ", error=" + e.getMessage());
    }

    private void storeFallback(EmbeddingResult result) {
        // TODO: Write to TimescaleDB as fallback
    }

    private void alertOnCall(String message, Exception e) {
        // TODO: Send alert to on-call via PagerDuty/Slack
    }

    /**
     * Milvus client wrapper
     */
    static class MilvusClient {
        private final String host;
        private final int port;

        public MilvusClient(String host, int port) {
            this.host = host;
            this.port = port;
            // TODO: Initialize actual Milvus gRPC client
        }

        public void insert(
            String capsuleId,
            String fingerprintHash,
            String serviceName,
            String environment,
            String severity,
            long timeBucket,
            float[] embedding
        ) throws Exception {
            // TODO: Insert into Milvus collection
        }

        public void close() {
            // TODO: Close Milvus connection
        }
    }

    /**
     * Embedding result data class
     */
    static class EmbeddingResult {
        public String capsuleId;
        public String fingerprintHash;
        public String serviceName;
        public String environment;
        public String severity;
        public long timeBucket;
        public float[] embedding;
    }
}
