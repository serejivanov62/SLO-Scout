"""
Worker Metrics - Prometheus metrics endpoint for Celery worker monitoring

Exposes Prometheus metrics for:
- Task execution counts (total, success, failure by task name)
- Task execution duration (histogram by task name)
- Worker health and status
- Queue depth and backlog

Per research.md: Prometheus integration for monitoring
Per NFR-050: Worker health monitoring with metrics
"""
import logging
import os
import time
from typing import Dict, Any, Optional
from datetime import datetime

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    Info,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
    push_to_gateway,
)
from celery import Celery
from celery.signals import (
    task_prerun,
    task_postrun,
    task_failure,
    task_retry,
    worker_ready,
    worker_shutdown,
)

from src.workers.celery_app import app

# Configure structured logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Prometheus configuration
PROMETHEUS_PUSHGATEWAY = os.getenv("PROMETHEUS_PUSHGATEWAY", "localhost:9091")
METRICS_JOB_NAME = "slo_scout_workers"

# Create custom registry for worker metrics
registry = CollectorRegistry()

# Task execution metrics
worker_tasks_total = Counter(
    'worker_tasks_total',
    'Total number of tasks processed by workers',
    ['task_name', 'status'],  # status: success, failure, retry
    registry=registry
)

worker_task_duration_seconds = Histogram(
    'worker_task_duration_seconds',
    'Task execution duration in seconds',
    ['task_name'],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
    registry=registry
)

worker_task_retries_total = Counter(
    'worker_task_retries_total',
    'Total number of task retries',
    ['task_name'],
    registry=registry
)

# Worker health metrics
worker_active_tasks = Gauge(
    'worker_active_tasks',
    'Number of currently active tasks',
    ['worker_name'],
    registry=registry
)

worker_queue_depth = Gauge(
    'worker_queue_depth',
    'Number of tasks in queue waiting to be processed',
    ['queue_name'],
    registry=registry
)

worker_status = Gauge(
    'worker_status',
    'Worker status (1=healthy, 0=unhealthy)',
    ['worker_name'],
    registry=registry
)

worker_uptime_seconds = Gauge(
    'worker_uptime_seconds',
    'Worker uptime in seconds',
    ['worker_name'],
    registry=registry
)

# Worker info
worker_info = Info(
    'worker',
    'Worker information',
    registry=registry
)

# Task tracking (in-memory state)
_task_start_times: Dict[str, float] = {}
_worker_start_time: Optional[float] = None
_active_task_counts: Dict[str, int] = {}


@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **extra):
    """
    Handler called before task execution starts.

    Records task start time for duration calculation.
    """
    _task_start_times[task_id] = time.time()

    # Increment active task count
    task_name = task.name if task else 'unknown'
    worker_name = extra.get('hostname', 'unknown')

    if worker_name not in _active_task_counts:
        _active_task_counts[worker_name] = 0
    _active_task_counts[worker_name] += 1

    worker_active_tasks.labels(worker_name=worker_name).set(
        _active_task_counts[worker_name]
    )

    logger.debug(
        f"Task started: {task_name}",
        extra={
            'task_id': task_id,
            'task_name': task_name,
            'worker': worker_name
        }
    )


@task_postrun.connect
def task_postrun_handler(
    sender=None,
    task_id=None,
    task=None,
    args=None,
    kwargs=None,
    retval=None,
    **extra
):
    """
    Handler called after successful task execution.

    Records task success and duration metrics.
    """
    task_name = task.name if task else 'unknown'
    worker_name = extra.get('hostname', 'unknown')

    # Record task completion
    worker_tasks_total.labels(
        task_name=task_name,
        status='success'
    ).inc()

    # Record task duration
    if task_id in _task_start_times:
        duration = time.time() - _task_start_times[task_id]
        worker_task_duration_seconds.labels(task_name=task_name).observe(duration)
        del _task_start_times[task_id]

    # Decrement active task count
    if worker_name in _active_task_counts:
        _active_task_counts[worker_name] = max(0, _active_task_counts[worker_name] - 1)
        worker_active_tasks.labels(worker_name=worker_name).set(
            _active_task_counts[worker_name]
        )

    logger.info(
        f"Task completed successfully: {task_name}",
        extra={
            'task_id': task_id,
            'task_name': task_name,
            'worker': worker_name
        }
    )


@task_failure.connect
def task_failure_handler(
    sender=None,
    task_id=None,
    exception=None,
    args=None,
    kwargs=None,
    traceback=None,
    einfo=None,
    **extra
):
    """
    Handler called when task execution fails.

    Records task failure metrics.
    """
    task_name = sender.name if sender else 'unknown'
    worker_name = extra.get('hostname', 'unknown')

    # Record task failure
    worker_tasks_total.labels(
        task_name=task_name,
        status='failure'
    ).inc()

    # Record duration if available
    if task_id in _task_start_times:
        duration = time.time() - _task_start_times[task_id]
        worker_task_duration_seconds.labels(task_name=task_name).observe(duration)
        del _task_start_times[task_id]

    # Decrement active task count
    if worker_name in _active_task_counts:
        _active_task_counts[worker_name] = max(0, _active_task_counts[worker_name] - 1)
        worker_active_tasks.labels(worker_name=worker_name).set(
            _active_task_counts[worker_name]
        )

    logger.error(
        f"Task failed: {task_name} - {str(exception)}",
        extra={
            'task_id': task_id,
            'task_name': task_name,
            'worker': worker_name,
            'exception': str(exception)
        }
    )


@task_retry.connect
def task_retry_handler(
    sender=None,
    task_id=None,
    reason=None,
    einfo=None,
    **extra
):
    """
    Handler called when task is retried.

    Records task retry metrics.
    """
    task_name = sender.name if sender else 'unknown'

    # Record task retry
    worker_task_retries_total.labels(task_name=task_name).inc()

    logger.warning(
        f"Task retry: {task_name} - {str(reason)}",
        extra={
            'task_id': task_id,
            'task_name': task_name,
            'reason': str(reason)
        }
    )


@worker_ready.connect
def worker_ready_handler(sender=None, **kwargs):
    """
    Handler called when worker is ready to accept tasks.

    Initializes worker health metrics.
    """
    global _worker_start_time
    _worker_start_time = time.time()

    worker_name = sender.hostname if sender else 'unknown'

    # Set worker status to healthy
    worker_status.labels(worker_name=worker_name).set(1)

    # Record worker info
    worker_info.info({
        'hostname': worker_name,
        'version': '1.0.0',
        'started_at': datetime.utcnow().isoformat()
    })

    logger.info(
        f"Worker ready: {worker_name}",
        extra={'worker': worker_name}
    )


@worker_shutdown.connect
def worker_shutdown_handler(sender=None, **kwargs):
    """
    Handler called when worker is shutting down.

    Updates worker health metrics.
    """
    worker_name = sender.hostname if sender else 'unknown'

    # Set worker status to unhealthy
    worker_status.labels(worker_name=worker_name).set(0)

    logger.info(
        f"Worker shutting down: {worker_name}",
        extra={'worker': worker_name}
    )


def update_queue_metrics(celery_app: Celery) -> None:
    """
    Update queue depth metrics by inspecting Celery queues.

    Args:
        celery_app: Celery application instance
    """
    try:
        # Get active queue stats from Celery
        inspect = celery_app.control.inspect()

        # Get active, scheduled, and reserved tasks
        active = inspect.active() or {}
        scheduled = inspect.scheduled() or {}
        reserved = inspect.reserved() or {}

        # Calculate queue depths
        queue_depths = {}

        for worker_name, tasks in active.items():
            for task in tasks:
                queue = task.get('delivery_info', {}).get('routing_key', 'default')
                queue_depths[queue] = queue_depths.get(queue, 0) + 1

        for worker_name, tasks in scheduled.items():
            for task in tasks:
                queue = task.get('delivery_info', {}).get('routing_key', 'default')
                queue_depths[queue] = queue_depths.get(queue, 0) + 1

        for worker_name, tasks in reserved.items():
            for task in tasks:
                queue = task.get('delivery_info', {}).get('routing_key', 'default')
                queue_depths[queue] = queue_depths.get(queue, 0) + 1

        # Update metrics
        for queue_name, depth in queue_depths.items():
            worker_queue_depth.labels(queue_name=queue_name).set(depth)

        logger.debug(f"Updated queue metrics: {queue_depths}")

    except Exception as e:
        logger.error(f"Failed to update queue metrics: {str(e)}")


def update_worker_uptime() -> None:
    """Update worker uptime metric"""
    if _worker_start_time is not None:
        uptime = time.time() - _worker_start_time
        # Use a generic label since we don't have hostname here
        worker_uptime_seconds.labels(worker_name='worker').set(uptime)


def get_metrics() -> bytes:
    """
    Generate Prometheus metrics in text format.

    Returns:
        Metrics data in Prometheus exposition format
    """
    # Update dynamic metrics
    update_queue_metrics(app)
    update_worker_uptime()

    # Generate metrics
    return generate_latest(registry)


def push_metrics_to_gateway() -> None:
    """
    Push metrics to Prometheus Pushgateway.

    Used for workers that don't have persistent HTTP endpoints.
    """
    try:
        from prometheus_client import push_to_gateway as push

        # Update metrics before pushing
        update_queue_metrics(app)
        update_worker_uptime()

        # Push to gateway
        push(
            gateway=PROMETHEUS_PUSHGATEWAY,
            job=METRICS_JOB_NAME,
            registry=registry
        )

        logger.debug(f"Pushed metrics to {PROMETHEUS_PUSHGATEWAY}")

    except Exception as e:
        logger.error(f"Failed to push metrics to gateway: {str(e)}")


def start_metrics_server(port: int = 9090) -> None:
    """
    Start HTTP server to expose metrics endpoint.

    Args:
        port: Port to listen on (default: 9090)

    Note:
        This is an alternative to pushing metrics. Workers can expose
        a /metrics endpoint that Prometheus can scrape.
    """
    from prometheus_client import start_http_server

    try:
        start_http_server(port, registry=registry)
        logger.info(f"Metrics server started on port {port}")

        # Register periodic metric updates
        from celery.schedules import crontab

        @app.on_after_configure.connect
        def setup_periodic_tasks(sender, **kwargs):
            # Update queue metrics every 30 seconds
            sender.add_periodic_task(
                30.0,
                update_queue_metrics.s(app),
                name='update_queue_metrics'
            )

    except Exception as e:
        logger.error(f"Failed to start metrics server: {str(e)}")
        raise


# Periodic task to push metrics (if using Pushgateway)
@app.task(name='metrics.push_metrics')
def push_metrics_task():
    """Celery task to periodically push metrics to Pushgateway"""
    push_metrics_to_gateway()


# Health check endpoint data
def get_health_status() -> Dict[str, Any]:
    """
    Get worker health status.

    Returns:
        Dictionary containing:
            - status: 'healthy' or 'unhealthy'
            - uptime_seconds: Worker uptime
            - active_tasks: Number of active tasks
            - total_tasks_processed: Total tasks processed
    """
    uptime = 0
    if _worker_start_time is not None:
        uptime = time.time() - _worker_start_time

    total_tasks = sum(_active_task_counts.values())

    # Get total processed from metrics
    # Note: This is a simplified version - production would query actual metric values

    return {
        'status': 'healthy' if uptime > 0 else 'unhealthy',
        'uptime_seconds': uptime,
        'active_tasks': total_tasks,
        'worker_start_time': datetime.fromtimestamp(_worker_start_time).isoformat() if _worker_start_time else None,
        'timestamp': datetime.utcnow().isoformat()
    }


# Flask/FastAPI integration for /metrics endpoint
def create_metrics_app():
    """
    Create a simple WSGI app for serving metrics.

    Returns:
        WSGI application that serves Prometheus metrics at /metrics

    Usage:
        Can be run with Gunicorn or uWSGI alongside Celery workers:
        gunicorn "src.workers.metrics:create_metrics_app()" --bind 0.0.0.0:9090
    """
    from flask import Flask, Response

    app = Flask(__name__)

    @app.route('/metrics')
    def metrics():
        """Prometheus metrics endpoint"""
        return Response(
            get_metrics(),
            mimetype=CONTENT_TYPE_LATEST
        )

    @app.route('/health')
    def health():
        """Health check endpoint"""
        import json
        status = get_health_status()
        return Response(
            json.dumps(status, indent=2),
            mimetype='application/json'
        )

    return app


if __name__ == '__main__':
    # For testing: Start metrics server
    logger.info("Starting metrics server...")
    start_metrics_server(port=9090)

    # Keep the process running
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down metrics server...")
