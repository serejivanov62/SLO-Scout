package common

import (
	"fmt"
	"github.com/confluentinc/confluent-kafka-go/v2/kafka"
	"time"
)

// KafkaProducer wraps Kafka producer with compression, batching, and error handling per T044
type KafkaProducer struct {
	producer *kafka.Producer
	topic    string
}

// NewKafkaProducer creates a new Kafka producer
func NewKafkaProducer(bootstrapServers string, topic string) (*KafkaProducer, error) {
	config := &kafka.ConfigMap{
		"bootstrap.servers": bootstrapServers,
		"compression.type":  "snappy", // Per research.md
		"linger.ms":         10,       // Batch for 10ms
		"batch.size":        16384,    // 16KB batches
		"acks":              "all",    // Wait for all replicas
		"max.in.flight":     5,
		"enable.idempotence": true, // Exactly-once semantics
	}

	producer, err := kafka.NewProducer(config)
	if err != nil {
		return nil, fmt.Errorf("failed to create Kafka producer: %w", err)
	}

	return &KafkaProducer{
		producer: producer,
		topic:    topic,
	}, nil
}

// Produce sends a message to Kafka with idempotency key
func (kp *KafkaProducer) Produce(key string, value []byte) error {
	deliveryChan := make(chan kafka.Event, 1)

	err := kp.producer.Produce(&kafka.Message{
		TopicPartition: kafka.TopicPartition{
			Topic:     &kp.topic,
			Partition: kafka.PartitionAny,
		},
		Key:   []byte(key),
		Value: value,
		Headers: []kafka.Header{
			{Key: "timestamp", Value: []byte(fmt.Sprintf("%d", time.Now().UnixMilli()))},
		},
	}, deliveryChan)

	if err != nil {
		return fmt.Errorf("failed to produce message: %w", err)
	}

	// Wait for delivery report
	e := <-deliveryChan
	m := e.(*kafka.Message)

	if m.TopicPartition.Error != nil {
		return fmt.Errorf("delivery failed: %w", m.TopicPartition.Error)
	}

	close(deliveryChan)
	return nil
}

// ProduceAsync sends message without waiting for delivery
func (kp *KafkaProducer) ProduceAsync(key string, value []byte) error {
	return kp.producer.Produce(&kafka.Message{
		TopicPartition: kafka.TopicPartition{
			Topic:     &kp.topic,
			Partition: kafka.PartitionAny,
		},
		Key:   []byte(key),
		Value: value,
	}, nil)
}

// Flush waits for all messages to be delivered
func (kp *KafkaProducer) Flush(timeoutMs int) int {
	return kp.producer.Flush(timeoutMs)
}

// Close shuts down the producer
func (kp *KafkaProducer) Close() {
	kp.producer.Close()
}
