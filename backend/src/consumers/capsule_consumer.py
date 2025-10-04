"""
Capsule consumer per T079
Kafka consumer for capsule-events topic, calls capsule_service.save
Commits offset after successful write
"""
import json
import logging
from kafka import KafkaConsumer
from kafka.errors import KafkaError

from ..services.capsule_service import CapsuleService
from ..storage.blob_storage import BlobStorageClient
from ..storage.vector_storage import VectorStorageClient

logger = logging.getLogger(__name__)


class CapsuleConsumer:
    """
    Kafka consumer for capsule-events topic

    Consumes CapsuleEvent messages and persists to storage
    """

    def __init__(
        self,
        kafka_bootstrap_servers: str,
        group_id: str = "capsule-consumer",
        blob_storage: BlobStorageClient = None,
        vector_storage: VectorStorageClient = None
    ):
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.group_id = group_id

        # Initialize storage
        self.capsule_service = CapsuleService(
            blob_storage=blob_storage,
            vector_storage=vector_storage
        )

        # Initialize Kafka consumer
        self.consumer = KafkaConsumer(
            'capsule-events',
            bootstrap_servers=kafka_bootstrap_servers,
            group_id=group_id,
            enable_auto_commit=False,  # Manual commit after processing
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            key_deserializer=lambda k: k.decode('utf-8') if k else None,
            auto_offset_reset='earliest'
        )

    def start(self):
        """
        Start consuming messages

        Process messages and commit offsets after successful save
        """
        logger.info(f"Starting capsule consumer, group_id={self.group_id}")

        try:
            for message in self.consumer:
                try:
                    # Parse message
                    capsule_event = message.value

                    # Extract fields per streaming-capsule.yaml CapsuleEvent schema
                    fingerprint_hash = capsule_event['fingerprint_hash']
                    template = capsule_event['template']
                    service_name = capsule_event['service_name']
                    severity = capsule_event.get('severity')
                    count = capsule_event['count']
                    sample_event_ids = capsule_event['sample_event_ids']
                    time_bucket = capsule_event['time_bucket']
                    first_seen_at = capsule_event['first_seen_at']
                    last_seen_at = capsule_event['last_seen_at']

                    # Build severity distribution
                    severity_distribution = {severity: count} if severity else {}

                    # TODO: Lookup service_id from service_name
                    # For now, use placeholder
                    from uuid import uuid4
                    service_id = uuid4()

                    # Build sample array
                    samples = [
                        {'event_id': event_id, 'timestamp': time_bucket}
                        for event_id in sample_event_ids
                    ]

                    # Save capsule (transactional)
                    capsule = self.capsule_service.save_capsule(
                        fingerprint_hash=fingerprint_hash,
                        template=template,
                        count=count,
                        severity_distribution=severity_distribution,
                        samples=samples,
                        service_id=service_id,
                        first_seen_at=first_seen_at,
                        last_seen_at=last_seen_at,
                        time_bucket=time_bucket,
                        redaction_applied=True  # Assumed from Flink pipeline
                    )

                    # Commit offset after successful save
                    self.consumer.commit()

                    logger.info(
                        f"Saved capsule: {capsule.capsule_id}, "
                        f"fingerprint={fingerprint_hash[:8]}..., "
                        f"count={count}"
                    )

                except Exception as e:
                    logger.error(f"Failed to process message: {e}", exc_info=True)
                    # Don't commit offset, will retry on next poll
                    continue

        except KeyboardInterrupt:
            logger.info("Consumer interrupted")
        except KafkaError as e:
            logger.error(f"Kafka error: {e}", exc_info=True)
        finally:
            self.consumer.close()
            logger.info("Consumer closed")

    def stop(self):
        """Stop the consumer"""
        self.consumer.close()
