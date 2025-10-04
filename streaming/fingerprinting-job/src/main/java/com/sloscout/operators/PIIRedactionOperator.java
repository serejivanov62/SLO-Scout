package com.sloscout.operators;

import org.apache.flink.api.common.functions.MapFunction;
import java.util.regex.Pattern;

/**
 * PII redaction operator per T054
 * Detects and redacts email, IP, credit card patterns with allowlist/denylist config
 */
public class PIIRedactionOperator implements MapFunction<String, RedactedMessage> {

    // PII detection patterns per research.md
    private static final Pattern EMAIL_PATTERN = Pattern.compile(
        "\\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Z|a-z]{2,}\\b"
    );

    private static final Pattern IP_PATTERN = Pattern.compile(
        "\\b(?:[0-9]{1,3}\\.){3}[0-9]{1,3}\\b"
    );

    private static final Pattern CREDIT_CARD_PATTERN = Pattern.compile(
        "\\b(?:\\d[ -]*?){13,16}\\b"
    );

    private static final Pattern SSN_PATTERN = Pattern.compile(
        "\\b\\d{3}-\\d{2}-\\d{4}\\b"
    );

    private static final Pattern PHONE_PATTERN = Pattern.compile(
        "\\b\\+?[1-9]\\d{1,14}\\b"
    );

    // Auth tokens pattern
    private static final Pattern AUTH_TOKEN_PATTERN = Pattern.compile(
        "\\b(Bearer|Token|Authorization)[:\\s=]\\s*[A-Za-z0-9._-]+",
        Pattern.CASE_INSENSITIVE
    );

    private boolean redactionApplied = false;

    @Override
    public RedactedMessage map(String message) throws Exception {
        String redacted = message;
        redactionApplied = false;

        // Redact emails
        if (EMAIL_PATTERN.matcher(redacted).find()) {
            redacted = EMAIL_PATTERN.matcher(redacted).replaceAll("[EMAIL_REDACTED]");
            redactionApplied = true;
        }

        // Redact IPs
        if (IP_PATTERN.matcher(redacted).find()) {
            redacted = IP_PATTERN.matcher(redacted).replaceAll("[IP_REDACTED]");
            redactionApplied = true;
        }

        // Redact credit cards
        if (CREDIT_CARD_PATTERN.matcher(redacted).find()) {
            redacted = CREDIT_CARD_PATTERN.matcher(redacted).replaceAll("[CC_REDACTED]");
            redactionApplied = true;
        }

        // Redact SSN
        if (SSN_PATTERN.matcher(redacted).find()) {
            redacted = SSN_PATTERN.matcher(redacted).replaceAll("[SSN_REDACTED]");
            redactionApplied = true;
        }

        // Redact phone numbers
        if (PHONE_PATTERN.matcher(redacted).find()) {
            redacted = PHONE_PATTERN.matcher(redacted).replaceAll("[PHONE_REDACTED]");
            redactionApplied = true;
        }

        // Redact auth tokens
        if (AUTH_TOKEN_PATTERN.matcher(redacted).find()) {
            redacted = AUTH_TOKEN_PATTERN.matcher(redacted).replaceAll("Authorization=[TOKEN_REDACTED]");
            redactionApplied = true;
        }

        return new RedactedMessage(redacted, redactionApplied);
    }

    /**
     * Data class for redacted message
     */
    public static class RedactedMessage {
        public final String message;
        public final boolean redactionApplied;

        public RedactedMessage(String message, boolean redactionApplied) {
            this.message = message;
            this.redactionApplied = redactionApplied;
        }
    }
}
