"""
Journey Discovery Worker - Celery task for UserJourney discovery from Capsules

This worker processes capsules and generates UserJourney records by:
1. Grouping capsules by fingerprint_hash
2. Analyzing event patterns and sequences
3. Calculating confidence scores based on pattern frequency and consistency
4. Creating UserJourney records with entry points and critical paths

Per research.md Decision 5: Async processing with Celery on Redis backend
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from uuid import UUID as PyUUID, uuid4
from decimal import Decimal
from collections import defaultdict, Counter

from celery import Task
from celery.exceptions import Retry
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from src.workers.celery_app import app
from src.storage.timescale_manager import get_timescale_manager
from src.models.capsule import Capsule
from src.models.user_journey import UserJourney

# Configure structured logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class JourneyDiscoveryTask(Task):
    """Base task with error handling and retry logic"""

    autoretry_for = (Exception,)
    retry_kwargs = {'max_retries': 3, 'countdown': 5}
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True


@app.task(bind=True, base=JourneyDiscoveryTask, name='journey_discovery.discover_journeys')
def discover_journeys(
    self,
    service_id: str,
    lookback_hours: int = 24,
    min_capsule_count: int = 5,
    min_confidence_threshold: float = 0.5
) -> Dict[str, Any]:
    """
    Discover user journeys from capsule data for a given service.

    Args:
        service_id: UUID of the service to analyze
        lookback_hours: Number of hours to look back for capsule data
        min_capsule_count: Minimum number of capsules required to form a journey
        min_confidence_threshold: Minimum confidence score to create a journey

    Returns:
        Dictionary containing:
            - journeys_created: Number of new journeys created
            - journeys_updated: Number of existing journeys updated
            - capsules_processed: Number of capsules analyzed
            - execution_time_seconds: Task execution time

    Raises:
        Retry: If task fails and should be retried
    """
    start_time = datetime.utcnow()
    logger.info(
        "Starting journey discovery",
        extra={
            'service_id': service_id,
            'lookback_hours': lookback_hours,
            'task_id': self.request.id
        }
    )

    try:
        db_manager = get_timescale_manager()

        with db_manager.get_session() as session:
            # Query capsules in the lookback window
            cutoff_time = datetime.utcnow() - timedelta(hours=lookback_hours)
            capsules = session.query(Capsule).filter(
                Capsule.service_id == PyUUID(service_id),
                Capsule.window_start >= cutoff_time,
                Capsule.journey_id.is_(None)  # Only unassigned capsules
            ).order_by(Capsule.window_start).all()

            if not capsules:
                logger.info(f"No unassigned capsules found for service {service_id}")
                return {
                    'journeys_created': 0,
                    'journeys_updated': 0,
                    'capsules_processed': 0,
                    'execution_time_seconds': (datetime.utcnow() - start_time).total_seconds()
                }

            logger.info(f"Processing {len(capsules)} capsules for journey discovery")

            # Group capsules by fingerprint_hash
            fingerprint_groups = _group_capsules_by_fingerprint(capsules)

            # Analyze patterns and create journeys
            journeys_created = 0
            journeys_updated = 0

            for fingerprint_hash, capsule_group in fingerprint_groups.items():
                if len(capsule_group) < min_capsule_count:
                    logger.debug(
                        f"Skipping fingerprint {fingerprint_hash[:8]}: "
                        f"only {len(capsule_group)} capsules (min: {min_capsule_count})"
                    )
                    continue

                # Calculate confidence score
                confidence_score = _calculate_confidence_score(capsule_group)

                if confidence_score < min_confidence_threshold:
                    logger.debug(
                        f"Skipping fingerprint {fingerprint_hash[:8]}: "
                        f"confidence {confidence_score:.3f} below threshold {min_confidence_threshold}"
                    )
                    continue

                # Extract journey metadata
                journey_data = _extract_journey_data(capsule_group, confidence_score)

                # Check if journey already exists with similar pattern
                existing_journey = _find_existing_journey(
                    session,
                    service_id,
                    journey_data['entry_points']
                )

                if existing_journey:
                    # Update existing journey
                    _update_journey(session, existing_journey, journey_data, capsule_group)
                    journeys_updated += 1
                    logger.info(
                        f"Updated journey {existing_journey.journey_id}",
                        extra={'journey_id': str(existing_journey.journey_id)}
                    )
                else:
                    # Create new journey
                    new_journey = _create_journey(
                        session,
                        service_id,
                        journey_data,
                        capsule_group
                    )
                    journeys_created += 1
                    logger.info(
                        f"Created new journey {new_journey.journey_id}",
                        extra={'journey_id': str(new_journey.journey_id)}
                    )

            session.commit()

            execution_time = (datetime.utcnow() - start_time).total_seconds()
            result = {
                'journeys_created': journeys_created,
                'journeys_updated': journeys_updated,
                'capsules_processed': len(capsules),
                'execution_time_seconds': execution_time
            }

            logger.info(
                "Journey discovery completed",
                extra={
                    'service_id': service_id,
                    'result': result,
                    'task_id': self.request.id
                }
            )

            return result

    except Exception as e:
        logger.error(
            f"Journey discovery failed: {str(e)}",
            extra={
                'service_id': service_id,
                'task_id': self.request.id,
                'error': str(e)
            },
            exc_info=True
        )
        # Retry with exponential backoff
        raise self.retry(exc=e)


def _group_capsules_by_fingerprint(capsules: List[Capsule]) -> Dict[str, List[Capsule]]:
    """Group capsules by fingerprint_hash"""
    groups = defaultdict(list)
    for capsule in capsules:
        groups[capsule.fingerprint_hash].append(capsule)
    return dict(groups)


def _calculate_confidence_score(capsules: List[Capsule]) -> float:
    """
    Calculate confidence score for a journey pattern.

    Factors:
    - Frequency: How many times the pattern appears
    - Consistency: How similar the event counts are across capsules
    - Recency: Weight recent patterns higher
    - Completeness: Presence of entry and exit points

    Returns:
        Confidence score between 0.0 and 1.0
    """
    # Frequency score (logarithmic scale, capped at 100 occurrences)
    frequency_score = min(len(capsules) / 100.0, 1.0)

    # Consistency score (based on event count variance)
    event_counts = [c.event_count for c in capsules]
    avg_count = sum(event_counts) / len(event_counts)
    variance = sum((c - avg_count) ** 2 for c in event_counts) / len(event_counts)
    consistency_score = 1.0 / (1.0 + variance / max(avg_count, 1))

    # Recency score (weight last 24 hours higher)
    now = datetime.utcnow()
    recency_weights = []
    for capsule in capsules:
        hours_ago = (now - capsule.window_start).total_seconds() / 3600
        weight = max(0.5, 1.0 - (hours_ago / 168))  # Decay over 7 days, min 0.5
        recency_weights.append(weight)
    recency_score = sum(recency_weights) / len(recency_weights)

    # Weighted combination
    confidence = (
        frequency_score * 0.4 +
        consistency_score * 0.3 +
        recency_score * 0.3
    )

    return min(max(confidence, 0.0), 1.0)


def _extract_journey_data(capsules: List[Capsule], confidence_score: float) -> Dict[str, Any]:
    """
    Extract journey metadata from capsule group.

    Returns:
        Dictionary with journey name, description, entry_points, and critical_path
    """
    # Use the most recent capsule template as representative
    latest_capsule = max(capsules, key=lambda c: c.window_start)
    template = latest_capsule.template

    # Generate journey name from template (simplified)
    journey_name = _generate_journey_name(template)

    # Extract entry points (first operations in the pattern)
    entry_points = _extract_entry_points(capsules)

    # Build critical path from event patterns
    critical_path = _build_critical_path(capsules)

    # Generate description
    description = (
        f"Discovered journey with {len(capsules)} occurrences. "
        f"Pattern: {template[:100]}... "
        f"Confidence: {confidence_score:.3f}"
    )

    return {
        'name': journey_name,
        'description': description,
        'entry_points': entry_points,
        'critical_path': critical_path,
        'confidence_score': Decimal(str(round(confidence_score, 3)))
    }


def _generate_journey_name(template: str) -> str:
    """Generate a human-readable journey name from template"""
    # Extract key operations (simplified - could use NLP in production)
    parts = template.split(' -> ')[:3]  # Take first 3 operations
    if len(parts) > 0:
        return f"Journey: {' -> '.join(parts)}"
    return f"Auto-discovered Journey {uuid4().hex[:8]}"


def _extract_entry_points(capsules: List[Capsule]) -> Dict[str, Any]:
    """Extract common entry points from capsules"""
    # Count first operations across all sample events
    entry_ops = Counter()

    for capsule in capsules:
        if capsule.sample_events:
            # First event is typically the entry point
            entry_ops[capsule.template.split(' -> ')[0]] += 1

    # Return top 3 entry points with their frequencies
    top_entries = entry_ops.most_common(3)
    return {
        'operations': [op for op, _ in top_entries],
        'frequency_distribution': {op: count for op, count in top_entries}
    }


def _build_critical_path(capsules: List[Capsule]) -> Dict[str, Any]:
    """Build critical path sequence from capsule patterns"""
    # Aggregate all templates to find common sequence
    step_sequences = []

    for capsule in capsules:
        steps = capsule.template.split(' -> ')
        step_sequences.append(steps)

    # Find most common sequence (simplified - production would use sequence alignment)
    most_common_seq = max(step_sequences, key=len) if step_sequences else []

    # Build critical path with placeholder latency metrics
    steps = []
    for i, step in enumerate(most_common_seq):
        steps.append({
            'order': i,
            'operation': step,
            'avg_latency_ms': None,  # Would be calculated from actual event data
            'p95_latency_ms': None,
            'p99_latency_ms': None
        })

    return {
        'steps': steps,
        'total_steps': len(steps),
        'estimated_duration_ms': None  # Would sum actual latencies
    }


def _find_existing_journey(
    session: Session,
    service_id: str,
    entry_points: Dict[str, Any]
) -> Optional[UserJourney]:
    """Find existing journey with similar entry points"""
    # Query journeys for this service
    journeys = session.query(UserJourney).filter(
        UserJourney.service_id == PyUUID(service_id)
    ).all()

    # Simple matching on entry point operations (production would use embeddings)
    new_ops = set(entry_points.get('operations', []))

    for journey in journeys:
        existing_ops = set(journey.entry_points.get('operations', []))
        # If >50% overlap in entry points, consider it the same journey
        overlap = len(new_ops & existing_ops) / max(len(new_ops | existing_ops), 1)
        if overlap > 0.5:
            return journey

    return None


def _update_journey(
    session: Session,
    journey: UserJourney,
    journey_data: Dict[str, Any],
    capsules: List[Capsule]
) -> None:
    """Update existing journey with new data"""
    # Update confidence score (weighted average)
    old_confidence = float(journey.confidence_score)
    new_confidence = float(journey_data['confidence_score'])
    journey.confidence_score = Decimal(str(
        round((old_confidence * 0.7 + new_confidence * 0.3), 3)
    ))

    # Update critical path if new data is more comprehensive
    if len(journey_data['critical_path']['steps']) > len(journey.critical_path.get('steps', [])):
        journey.critical_path = journey_data['critical_path']

    # Assign capsules to this journey
    for capsule in capsules:
        capsule.journey_id = journey.journey_id


def _create_journey(
    session: Session,
    service_id: str,
    journey_data: Dict[str, Any],
    capsules: List[Capsule]
) -> UserJourney:
    """Create new UserJourney record"""
    new_journey = UserJourney(
        journey_id=uuid4(),
        service_id=PyUUID(service_id),
        name=journey_data['name'],
        description=journey_data['description'],
        entry_points=journey_data['entry_points'],
        critical_path=journey_data['critical_path'],
        confidence_score=journey_data['confidence_score'],
        discovered_at=datetime.utcnow()
    )

    session.add(new_journey)
    session.flush()  # Get journey_id

    # Assign capsules to this journey
    for capsule in capsules:
        capsule.journey_id = new_journey.journey_id

    return new_journey


@app.task(bind=True, base=JourneyDiscoveryTask, name='journey_discovery.batch_discover')
def batch_discover_journeys(
    self,
    service_ids: List[str],
    lookback_hours: int = 24
) -> Dict[str, Any]:
    """
    Batch discovery task for multiple services.

    Args:
        service_ids: List of service UUIDs to process
        lookback_hours: Hours to look back for capsule data

    Returns:
        Aggregated results from all service discoveries
    """
    logger.info(
        f"Starting batch journey discovery for {len(service_ids)} services",
        extra={'task_id': self.request.id}
    )

    total_created = 0
    total_updated = 0
    total_capsules = 0

    for service_id in service_ids:
        try:
            result = discover_journeys.apply_async(
                args=[service_id, lookback_hours],
                queue='journey_discovery'
            ).get(timeout=300)  # 5 minute timeout per service

            total_created += result['journeys_created']
            total_updated += result['journeys_updated']
            total_capsules += result['capsules_processed']

        except Exception as e:
            logger.error(
                f"Failed to discover journeys for service {service_id}: {str(e)}",
                exc_info=True
            )

    return {
        'services_processed': len(service_ids),
        'total_journeys_created': total_created,
        'total_journeys_updated': total_updated,
        'total_capsules_processed': total_capsules
    }
