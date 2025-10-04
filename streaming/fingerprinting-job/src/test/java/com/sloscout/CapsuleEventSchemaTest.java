package com.sloscout;

import org.apache.avro.Schema;
import org.junit.jupiter.api.Test;

import java.io.File;
import java.io.IOException;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Contract test for CapsuleEvent Avro schema
 * Per streaming-capsule.yaml specification
 *
 * MUST FAIL before implementation (TDD principle)
 */
public class CapsuleEventSchemaTest {

    @Test
    public void testCapsuleEventSchemaExists() throws IOException {
        File schemaFile = new File("src/main/avro/CapsuleEvent.avsc");
        assertTrue(schemaFile.exists(), "CapsuleEvent.avsc schema file must exist");

        Schema schema = new Schema.Parser().parse(schemaFile);
        assertEquals("CapsuleEvent", schema.getName());
    }

    @Test
    public void testCapsuleEventHasAllRequiredFields() throws IOException {
        File schemaFile = new File("src/main/avro/CapsuleEvent.avsc");
        Schema schema = new Schema.Parser().parse(schemaFile);

        // Per streaming-capsule.yaml CapsuleEvent fields
        assertNotNull(schema.getField("fingerprint_hash"), "fingerprint_hash field required");
        assertNotNull(schema.getField("template"), "template field required");
        assertNotNull(schema.getField("service_name"), "service_name field required");
        assertNotNull(schema.getField("severity"), "severity field required");
        assertNotNull(schema.getField("count"), "count field required");
        assertNotNull(schema.getField("sample_event_ids"), "sample_event_ids field required");
        assertNotNull(schema.getField("time_bucket"), "time_bucket field required");
        assertNotNull(schema.getField("first_seen_at"), "first_seen_at field required");
        assertNotNull(schema.getField("last_seen_at"), "last_seen_at field required");
    }

    @Test
    public void testFingerprintHashIsString() throws IOException {
        File schemaFile = new File("src/main/avro/CapsuleEvent.avsc");
        Schema schema = new Schema.Parser().parse(schemaFile);

        Schema.Field fingerprintField = schema.getField("fingerprint_hash");
        assertEquals(Schema.Type.STRING, fingerprintField.schema().getType());
    }

    @Test
    public void testCountIsLong() throws IOException {
        File schemaFile = new File("src/main/avro/CapsuleEvent.avsc");
        Schema schema = new Schema.Parser().parse(schemaFile);

        Schema.Field countField = schema.getField("count");
        // Per streaming-capsule.yaml: count is long (bigint)
        assertEquals(Schema.Type.LONG, countField.schema().getType());
    }

    @Test
    public void testSampleEventIdsIsArray() throws IOException {
        File schemaFile = new File("src/main/avro/CapsuleEvent.avsc");
        Schema schema = new Schema.Parser().parse(schemaFile);

        Schema.Field sampleField = schema.getField("sample_event_ids");
        // Per streaming-capsule.yaml: sample_event_ids is array of strings
        assertEquals(Schema.Type.ARRAY, sampleField.schema().getType());
        assertEquals(Schema.Type.STRING, sampleField.schema().getElementType().getType());
    }
}
