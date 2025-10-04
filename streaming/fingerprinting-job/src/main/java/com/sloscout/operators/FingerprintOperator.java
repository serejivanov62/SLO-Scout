package com.sloscout.operators;

import org.apache.flink.api.common.functions.MapFunction;
import java.util.regex.Pattern;
import java.util.regex.Matcher;
import java.security.MessageDigest;
import java.nio.charset.StandardCharsets;

/**
 * Fingerprinting operator per T053
 * Normalizes log templates and masks variable tokens
 */
public class FingerprintOperator implements MapFunction<String, FingerprintedMessage> {

    // Regex patterns for variable token masking per research.md
    private static final Pattern USER_ID_PATTERN = Pattern.compile("\\b(user[_-]?id|uid)[:\\s=]\\s*[a-zA-Z0-9-]+", Pattern.CASE_INSENSITIVE);
    private static final Pattern IP_PATTERN = Pattern.compile("\\b(?:[0-9]{1,3}\\.){3}[0-9]{1,3}\\b");
    private static final Pattern TIMESTAMP_PATTERN = Pattern.compile("\\d{4}-\\d{2}-\\d{2}[T\\s]\\d{2}:\\d{2}:\\d{2}");
    private static final Pattern UUID_PATTERN = Pattern.compile("\\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\\b");
    private static final Pattern NUMBER_PATTERN = Pattern.compile("\\b\\d{4,}\\b"); // Numbers with 4+ digits
    private static final Pattern EMAIL_PATTERN = Pattern.compile("\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}\\b");

    @Override
    public FingerprintedMessage map(String message) throws Exception {
        String template = normalizeMessage(message);
        String fingerprintHash = generateFingerprint(template);

        return new FingerprintedMessage(
            fingerprintHash,
            template,
            message // Original message
        );
    }

    /**
     * Normalize message by masking variable tokens
     */
    private String normalizeMessage(String message) {
        String normalized = message;

        // Mask email addresses (PII)
        normalized = EMAIL_PATTERN.matcher(normalized).replaceAll("{EMAIL}");

        // Mask IP addresses (PII)
        normalized = IP_PATTERN.matcher(normalized).replaceAll("{IP}");

        // Mask user IDs
        normalized = USER_ID_PATTERN.matcher(normalized).replaceAll("user_id={USER_ID}");

        // Mask UUIDs
        normalized = UUID_PATTERN.matcher(normalized).replaceAll("{UUID}");

        // Mask timestamps
        normalized = TIMESTAMP_PATTERN.matcher(normalized).replaceAll("{TIMESTAMP}");

        // Mask large numbers
        normalized = NUMBER_PATTERN.matcher(normalized).replaceAll("{NUMBER}");

        return normalized;
    }

    /**
     * Generate SHA256 fingerprint hash per T055
     */
    private String generateFingerprint(String template) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] hash = digest.digest(template.getBytes(StandardCharsets.UTF_8));

        // Convert to hex string
        StringBuilder hexString = new StringBuilder();
        for (byte b : hash) {
            String hex = Integer.toHexString(0xff & b);
            if (hex.length() == 1) hexString.append('0');
            hexString.append(hex);
        }

        return hexString.toString();
    }

    /**
     * Data class for fingerprinted message
     */
    public static class FingerprintedMessage {
        public final String fingerprintHash;
        public final String template;
        public final String originalMessage;

        public FingerprintedMessage(String fingerprintHash, String template, String originalMessage) {
            this.fingerprintHash = fingerprintHash;
            this.template = template;
            this.originalMessage = originalMessage;
        }
    }
}
