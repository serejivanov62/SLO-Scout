package com.sloscout;

import org.apache.avro.Schema;
import org.apache.avro.SchemaBuilder;
import org.junit.jupiter.api.Test;

import java.io.File;
import java.io.IOException;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Contract test for TelemetryEvent Avro schema
 * Per streaming-capsule.yaml specification
 *
 * MUST FAIL before implementation (TDD principle)
 */
public class TelemetryEventSchemaTest {

    @Test
    public void testTelemetryEventSchemaExists() throws IOException {
        // Schema file should exist at streaming/src/main/avro/TelemetryEvent.avsc
        File schemaFile = new File("src/main/avro/TelemetryEvent.avsc");
        assertTrue(schemaFile.exists(), "TelemetryEvent.avsc schema file must exist");

        // Should be valid Avro schema
        Schema schema = new Schema.Parser().parse(schemaFile);
        assertEquals("TelemetryEvent", schema.getName());
    }

    @Test
    public void testTelemetryEventHasAllRequiredFields() throws IOException {
        File schemaFile = new File("src/main/avro/TelemetryEvent.avsc");
        Schema schema = new Schema.Parser().parse(schemaFile);

        // Per streaming-capsule.yaml: all required fields
        assertNotNull(schema.getField("event_id"), "event_id field required");
        assertNotNull(schema.getField("service_name"), "service_name field required");
        assertNotNull(schema.getField("environment"), "environment field required");
        assertNotNull(schema.getField("event_type"), "event_type field required");
        assertNotNull(schema.getField("timestamp"), "timestamp field required");
        assertNotNull(schema.getField("severity"), "severity field required");
        assertNotNull(schema.getField("message"), "message field required");
        assertNotNull(schema.getField("trace_id"), "trace_id field required");
        assertNotNull(schema.getField("span_id"), "span_id field required");
        assertNotNull(schema.getField("attributes"), "attributes field required");
        assertNotNull(schema.getField("raw_blob_s3_key"), "raw_blob_s3_key field required");
    }

    @Test
    public void testEnvironmentEnumHasCorrectSymbols() throws IOException {
        File schemaFile = new File("src/main/avro/TelemetryEvent.avsc");
        Schema schema = new Schema.Parser().parse(schemaFile);

        Schema.Field envField = schema.getField("environment");
        Schema envSchema = envField.schema();

        // Per streaming-capsule.yaml: environment enum [prod, staging, dev]
        assertEquals(Schema.Type.ENUM, envSchema.getType());
        assertTrue(envSchema.getEnumSymbols().contains("prod"));
        assertTrue(envSchema.getEnumSymbols().contains("staging"));
        assertTrue(envSchema.getEnumSymbols().contains("dev"));
    }

    @Test
    public void testEventTypeEnumHasCorrectSymbols() throws IOException {
        File schemaFile = new File("src/main/avro/TelemetryEvent.avsc");
        Schema schema = new Schema.Parser().parse(schemaFile);

        Schema.Field eventTypeField = schema.getField("event_type");
        Schema eventTypeSchema = eventTypeField.schema();

        // Per streaming-capsule.yaml: event_type enum [log, trace, metric]
        assertEquals(Schema.Type.ENUM, eventTypeSchema.getType());
        assertTrue(eventTypeSchema.getEnumSymbols().contains("log"));
        assertTrue(eventTypeSchema.getEnumSymbols().contains("trace"));
        assertTrue(eventTypeSchema.getEnumSymbols().contains("metric"));
    }

    @Test
    public void testTimestampHasLogicalType() throws IOException {
        File schemaFile = new File("src/main/avro/TelemetryEvent.avsc");
        Schema schema = new Schema.Parser().parse(schemaFile);

        Schema.Field timestampField = schema.getField("timestamp");
        Schema timestampSchema = timestampField.schema();

        // Per streaming-capsule.yaml: timestamp with logicalType timestamp-millis
        assertEquals(Schema.Type.LONG, timestampSchema.getType());
        assertEquals("timestamp-millis", timestampSchema.getLogicalType().getName());
    }
}
