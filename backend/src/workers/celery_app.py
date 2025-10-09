"""
Celery application configuration for SLO-Scout async workers

Configuration per research.md Decision 5:
- 4 workers with prefork pool
- 5 concurrent tasks per worker = 20 total slots
- Redis backend for broker and result storage
- Isolated job failures (process boundaries)
"""
import os
from celery import Celery
from kombu import Exchange, Queue

# Redis connection from environment
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create Celery app
app = Celery(
    "slo_scout_workers",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "src.workers.journey_discovery",
        "src.workers.embedding_pipeline",
    ]
)

# Celery configuration
app.conf.update(
    # Worker configuration (per research.md)
    worker_pool="prefork",  # Process pool for isolation
    worker_concurrency=5,   # 5 tasks per worker
    worker_prefetch_multiplier=1,  # Fair task distribution
    worker_max_tasks_per_child=1000,  # Restart workers after 1000 tasks (prevent memory leaks)

    # Task configuration
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,

    # Task routing
    task_routes={
        "src.workers.journey_discovery.*": {"queue": "journey_discovery"},
        "src.workers.embedding_pipeline.*": {"queue": "embeddings"},
    },

    # Queue configuration
    task_queues=(
        Queue("journey_discovery", Exchange("journey_discovery"), routing_key="journey_discovery"),
        Queue("embeddings", Exchange("embeddings"), routing_key="embeddings"),
        Queue("default", Exchange("default"), routing_key="default"),
    ),

    # Result backend configuration
    result_backend_transport_options={
        "master_name": "mymaster",  # For Redis Sentinel support
    },
    result_expires=3600,  # Results expire after 1 hour

    # Task execution
    task_acks_late=True,  # Acknowledge task after completion (at-least-once delivery)
    task_reject_on_worker_lost=True,  # Requeue tasks if worker crashes
    task_track_started=True,  # Track task start time

    # Monitoring
    worker_send_task_events=True,  # Send task events for monitoring
    task_send_sent_event=True,  # Send task-sent events

    # Rate limiting (prevent overwhelming downstream systems)
    task_default_rate_limit="100/m",  # 100 tasks per minute default

    # Timeouts
    task_soft_time_limit=1800,  # 30 minutes soft limit (sends SIGTERM)
    task_time_limit=1900,  # 31.67 minutes hard limit (sends SIGKILL)
    broker_connection_retry_on_startup=True,
)

# Beat schedule for periodic tasks (if needed in future)
app.conf.beat_schedule = {
    # Example: Periodic cleanup task
    # "cleanup-old-capsules": {
    #     "task": "src.workers.maintenance.cleanup_old_capsules",
    #     "schedule": 3600.0,  # Every hour
    # },
}

if __name__ == "__main__":
    app.start()
