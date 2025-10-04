package com.sloscout;

import org.apache.flink.api.common.functions.RichFlatMapFunction;
import org.apache.flink.configuration.Configuration;
import org.apache.flink.util.Collector;

import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.URI;
import java.time.Duration;

/**
 * Embedding service client per T072
 * HTTP client for backend embedding API, retry with exponential backoff
 */
public class EmbeddingServiceClient extends RichFlatMapFunction<CapsuleBatch, EmbeddingResult> {

    private final String serviceUrl;
    private transient HttpClient httpClient;

    private static final int MAX_RETRIES = 5;
    private static final long INITIAL_BACKOFF_MS = 1000;

    public EmbeddingServiceClient(String serviceUrl) {
        this.serviceUrl = serviceUrl;
    }

    @Override
    public void open(Configuration parameters) throws Exception {
        super.open(parameters);

        // Initialize HTTP client
        this.httpClient = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_2)
            .connectTimeout(Duration.ofSeconds(30))
            .build();
    }

    @Override
    public void flatMap(CapsuleBatch batch, Collector<EmbeddingResult> out) throws Exception {
        int attempt = 0;
        Exception lastException = null;

        while (attempt < MAX_RETRIES) {
            try {
                // Call embedding service
                EmbeddingResult result = callEmbeddingService(batch);
                out.collect(result);
                return; // Success

            } catch (Exception e) {
                lastException = e;
                attempt++;

                if (attempt < MAX_RETRIES) {
                    // Exponential backoff per streaming-capsule.yaml error handling
                    long backoffMs = INITIAL_BACKOFF_MS * (1L << (attempt - 1));
                    Thread.sleep(backoffMs);
                }
            }
        }

        // Max retries exceeded, send to DLQ
        throw new RuntimeException(
            "Failed to get embeddings after " + MAX_RETRIES + " attempts",
            lastException
        );
    }

    /**
     * Call embedding service API
     */
    private EmbeddingResult callEmbeddingService(CapsuleBatch batch) throws Exception {
        // Build request
        String requestBody = buildRequestJson(batch);

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(serviceUrl + "/embed_batch"))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(requestBody))
            .timeout(Duration.ofSeconds(60))
            .build();

        // Send request
        HttpResponse<String> response = httpClient.send(
            request,
            HttpResponse.BodyHandlers.ofString()
        );

        if (response.statusCode() != 200) {
            throw new RuntimeException("Embedding service error: " + response.statusCode());
        }

        // Parse response
        return parseResponse(response.body());
    }

    private String buildRequestJson(CapsuleBatch batch) {
        // TODO: Serialize batch to JSON
        return "{}";
    }

    private EmbeddingResult parseResponse(String json) {
        // TODO: Parse JSON response
        return new EmbeddingResult();
    }

    static class CapsuleBatch {}
    static class EmbeddingResult {}
}
