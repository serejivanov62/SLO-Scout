"""
Embedding Pipeline Worker - Celery task for generating and storing embeddings in Milvus

This worker processes entities (UserJourneys, SLIs, Artifacts) and:
1. Generates embeddings using sentence-transformers
2. Stores embeddings in Milvus vector database with metadata
3. Enables semantic search and similarity matching

Per research.md Decision 5: Async processing with Celery on Redis backend
Per FR-040: Milvus for vector embeddings with cosine similarity search
"""
import logging
import os
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
from uuid import UUID as PyUUID

from celery import Task
from celery.exceptions import Retry
from sentence_transformers import SentenceTransformer
from pymilvus import (
    connections,
    Collection,
    FieldSchema,
    CollectionSchema,
    DataType,
    utility
)

from src.workers.celery_app import app
from src.storage.timescale_manager import get_timescale_manager
from src.models.user_journey import UserJourney
from src.models.sli import SLI
from src.models.artifact import Artifact

# Configure structured logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Milvus configuration from environment
MILVUS_HOST = os.getenv("MILVUS_HOST", "localhost")
MILVUS_PORT = os.getenv("MILVUS_PORT", "19530")
MILVUS_USER = os.getenv("MILVUS_USER", "")
MILVUS_PASSWORD = os.getenv("MILVUS_PASSWORD", "")

# Embedding model configuration
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # 384-dimensional embeddings, fast inference
EMBEDDING_DIM = 384

# Collection names
JOURNEY_COLLECTION = "user_journeys"
SLI_COLLECTION = "slis"
ARTIFACT_COLLECTION = "artifacts"

# Global model cache (loaded once per worker)
_embedding_model: Optional[SentenceTransformer] = None


class EmbeddingPipelineTask(Task):
    """Base task with error handling and retry logic"""

    autoretry_for = (Exception,)
    retry_kwargs = {'max_retries': 3, 'countdown': 10}
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True


def get_embedding_model() -> SentenceTransformer:
    """Get or initialize the embedding model (singleton per worker)"""
    global _embedding_model
    if _embedding_model is None:
        logger.info(f"Loading embedding model: {EMBEDDING_MODEL}")
        _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("Embedding model loaded successfully")
    return _embedding_model


def connect_milvus() -> None:
    """Establish connection to Milvus"""
    try:
        connections.connect(
            alias="default",
            host=MILVUS_HOST,
            port=MILVUS_PORT,
            user=MILVUS_USER,
            password=MILVUS_PASSWORD
        )
        logger.info(f"Connected to Milvus at {MILVUS_HOST}:{MILVUS_PORT}")
    except Exception as e:
        logger.error(f"Failed to connect to Milvus: {str(e)}")
        raise


def disconnect_milvus() -> None:
    """Disconnect from Milvus"""
    try:
        connections.disconnect(alias="default")
        logger.info("Disconnected from Milvus")
    except Exception as e:
        logger.warning(f"Error disconnecting from Milvus: {str(e)}")


def ensure_collection(collection_name: str, schema: CollectionSchema) -> Collection:
    """Ensure Milvus collection exists with proper schema and index"""
    try:
        if utility.has_collection(collection_name):
            collection = Collection(collection_name)
            logger.info(f"Using existing collection: {collection_name}")
        else:
            collection = Collection(
                name=collection_name,
                schema=schema,
                using='default'
            )
            logger.info(f"Created new collection: {collection_name}")

            # Create IVF_FLAT index for vector similarity search
            index_params = {
                "metric_type": "COSINE",  # Cosine similarity per FR-040
                "index_type": "IVF_FLAT",
                "params": {"nlist": 128}
            }
            collection.create_index(
                field_name="embedding",
                index_params=index_params
            )
            logger.info(f"Created COSINE index on {collection_name}")

        # Load collection into memory for search
        collection.load()
        return collection

    except Exception as e:
        logger.error(f"Failed to ensure collection {collection_name}: {str(e)}")
        raise


def get_journey_schema() -> CollectionSchema:
    """Define schema for UserJourney embeddings"""
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="journey_id", dtype=DataType.VARCHAR, max_length=36),
        FieldSchema(name="service_id", dtype=DataType.VARCHAR, max_length=36),
        FieldSchema(name="name", dtype=DataType.VARCHAR, max_length=255),
        FieldSchema(name="confidence_score", dtype=DataType.FLOAT),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM),
        FieldSchema(name="created_at", dtype=DataType.INT64)  # Unix timestamp
    ]
    return CollectionSchema(
        fields=fields,
        description="UserJourney embeddings for semantic search"
    )


def get_sli_schema() -> CollectionSchema:
    """Define schema for SLI embeddings"""
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="sli_id", dtype=DataType.VARCHAR, max_length=36),
        FieldSchema(name="journey_id", dtype=DataType.VARCHAR, max_length=36),
        FieldSchema(name="metric_name", dtype=DataType.VARCHAR, max_length=255),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM),
        FieldSchema(name="created_at", dtype=DataType.INT64)
    ]
    return CollectionSchema(
        fields=fields,
        description="SLI embeddings for semantic search"
    )


def get_artifact_schema() -> CollectionSchema:
    """Define schema for Artifact embeddings"""
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="artifact_id", dtype=DataType.VARCHAR, max_length=36),
        FieldSchema(name="artifact_type", dtype=DataType.VARCHAR, max_length=50),
        FieldSchema(name="entity_id", dtype=DataType.VARCHAR, max_length=36),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM),
        FieldSchema(name="created_at", dtype=DataType.INT64)
    ]
    return CollectionSchema(
        fields=fields,
        description="Artifact embeddings for semantic search"
    )


@app.task(bind=True, base=EmbeddingPipelineTask, name='embedding_pipeline.embed_journey')
def embed_journey(self, journey_id: str) -> Dict[str, Any]:
    """
    Generate and store embedding for a UserJourney.

    Args:
        journey_id: UUID of the journey to embed

    Returns:
        Dictionary containing:
            - journey_id: ID of embedded journey
            - embedding_dim: Dimension of embedding vector
            - execution_time_seconds: Task execution time

    Raises:
        Retry: If task fails and should be retried
    """
    start_time = datetime.utcnow()
    logger.info(
        f"Generating embedding for journey {journey_id}",
        extra={'journey_id': journey_id, 'task_id': self.request.id}
    )

    try:
        # Get journey from database
        db_manager = get_timescale_manager()
        with db_manager.get_session() as session:
            journey = session.query(UserJourney).filter(
                UserJourney.journey_id == PyUUID(journey_id)
            ).first()

            if not journey:
                raise ValueError(f"Journey {journey_id} not found")

            # Create text representation for embedding
            text_repr = _journey_to_text(journey)

            # Generate embedding
            model = get_embedding_model()
            embedding = model.encode(text_repr, normalize_embeddings=True)

            # Connect to Milvus and store embedding
            connect_milvus()
            try:
                collection = ensure_collection(
                    JOURNEY_COLLECTION,
                    get_journey_schema()
                )

                # Prepare data for insertion
                entities = [
                    [str(journey.journey_id)],
                    [str(journey.service_id)],
                    [journey.name],
                    [float(journey.confidence_score)],
                    [embedding.tolist()],
                    [int(datetime.utcnow().timestamp())]
                ]

                # Insert into Milvus
                collection.insert(entities)
                collection.flush()

                logger.info(
                    f"Stored embedding for journey {journey_id}",
                    extra={
                        'journey_id': journey_id,
                        'embedding_dim': len(embedding)
                    }
                )

            finally:
                disconnect_milvus()

            execution_time = (datetime.utcnow() - start_time).total_seconds()
            return {
                'journey_id': journey_id,
                'embedding_dim': len(embedding),
                'execution_time_seconds': execution_time
            }

    except Exception as e:
        logger.error(
            f"Failed to embed journey {journey_id}: {str(e)}",
            extra={'journey_id': journey_id, 'task_id': self.request.id},
            exc_info=True
        )
        raise self.retry(exc=e)


@app.task(bind=True, base=EmbeddingPipelineTask, name='embedding_pipeline.embed_sli')
def embed_sli(self, sli_id: str) -> Dict[str, Any]:
    """
    Generate and store embedding for an SLI.

    Args:
        sli_id: UUID of the SLI to embed

    Returns:
        Dictionary with embedding results
    """
    start_time = datetime.utcnow()
    logger.info(
        f"Generating embedding for SLI {sli_id}",
        extra={'sli_id': sli_id, 'task_id': self.request.id}
    )

    try:
        db_manager = get_timescale_manager()
        with db_manager.get_session() as session:
            sli = session.query(SLI).filter(
                SLI.sli_id == PyUUID(sli_id)
            ).first()

            if not sli:
                raise ValueError(f"SLI {sli_id} not found")

            # Create text representation
            text_repr = _sli_to_text(sli)

            # Generate embedding
            model = get_embedding_model()
            embedding = model.encode(text_repr, normalize_embeddings=True)

            # Store in Milvus
            connect_milvus()
            try:
                collection = ensure_collection(
                    SLI_COLLECTION,
                    get_sli_schema()
                )

                entities = [
                    [str(sli.sli_id)],
                    [str(sli.journey_id) if sli.journey_id else ""],
                    [sli.metric_name],
                    [embedding.tolist()],
                    [int(datetime.utcnow().timestamp())]
                ]

                collection.insert(entities)
                collection.flush()

                logger.info(f"Stored embedding for SLI {sli_id}")

            finally:
                disconnect_milvus()

            execution_time = (datetime.utcnow() - start_time).total_seconds()
            return {
                'sli_id': sli_id,
                'embedding_dim': len(embedding),
                'execution_time_seconds': execution_time
            }

    except Exception as e:
        logger.error(
            f"Failed to embed SLI {sli_id}: {str(e)}",
            exc_info=True
        )
        raise self.retry(exc=e)


@app.task(bind=True, base=EmbeddingPipelineTask, name='embedding_pipeline.embed_artifact')
def embed_artifact(self, artifact_id: str) -> Dict[str, Any]:
    """
    Generate and store embedding for an Artifact.

    Args:
        artifact_id: UUID of the artifact to embed

    Returns:
        Dictionary with embedding results
    """
    start_time = datetime.utcnow()
    logger.info(
        f"Generating embedding for artifact {artifact_id}",
        extra={'artifact_id': artifact_id, 'task_id': self.request.id}
    )

    try:
        db_manager = get_timescale_manager()
        with db_manager.get_session() as session:
            artifact = session.query(Artifact).filter(
                Artifact.artifact_id == PyUUID(artifact_id)
            ).first()

            if not artifact:
                raise ValueError(f"Artifact {artifact_id} not found")

            # Create text representation
            text_repr = _artifact_to_text(artifact)

            # Generate embedding
            model = get_embedding_model()
            embedding = model.encode(text_repr, normalize_embeddings=True)

            # Store in Milvus
            connect_milvus()
            try:
                collection = ensure_collection(
                    ARTIFACT_COLLECTION,
                    get_artifact_schema()
                )

                entities = [
                    [str(artifact.artifact_id)],
                    [artifact.artifact_type],
                    [str(artifact.entity_id)],
                    [embedding.tolist()],
                    [int(datetime.utcnow().timestamp())]
                ]

                collection.insert(entities)
                collection.flush()

                logger.info(f"Stored embedding for artifact {artifact_id}")

            finally:
                disconnect_milvus()

            execution_time = (datetime.utcnow() - start_time).total_seconds()
            return {
                'artifact_id': artifact_id,
                'embedding_dim': len(embedding),
                'execution_time_seconds': execution_time
            }

    except Exception as e:
        logger.error(
            f"Failed to embed artifact {artifact_id}: {str(e)}",
            exc_info=True
        )
        raise self.retry(exc=e)


@app.task(bind=True, base=EmbeddingPipelineTask, name='embedding_pipeline.batch_embed')
def batch_embed(
    self,
    entity_type: str,
    entity_ids: List[str]
) -> Dict[str, Any]:
    """
    Batch embedding generation for multiple entities.

    Args:
        entity_type: Type of entity ('journey', 'sli', 'artifact')
        entity_ids: List of entity UUIDs to embed

    Returns:
        Aggregated results from all embedding tasks
    """
    logger.info(
        f"Starting batch embedding for {len(entity_ids)} {entity_type} entities",
        extra={'task_id': self.request.id}
    )

    # Select appropriate task
    task_map = {
        'journey': embed_journey,
        'sli': embed_sli,
        'artifact': embed_artifact
    }

    if entity_type not in task_map:
        raise ValueError(f"Invalid entity_type: {entity_type}")

    embed_task = task_map[entity_type]
    success_count = 0
    failure_count = 0

    for entity_id in entity_ids:
        try:
            embed_task.apply_async(
                args=[entity_id],
                queue='embeddings'
            ).get(timeout=120)  # 2 minute timeout per entity
            success_count += 1
        except Exception as e:
            logger.error(
                f"Failed to embed {entity_type} {entity_id}: {str(e)}",
                exc_info=True
            )
            failure_count += 1

    return {
        'entity_type': entity_type,
        'total_processed': len(entity_ids),
        'success_count': success_count,
        'failure_count': failure_count
    }


def _journey_to_text(journey: UserJourney) -> str:
    """Convert UserJourney to text representation for embedding"""
    parts = [
        f"Journey: {journey.name}",
        f"Description: {journey.description or 'N/A'}",
        f"Entry points: {', '.join(journey.entry_points.get('operations', []))}",
        f"Steps: {journey.critical_path.get('total_steps', 0)}",
        f"Confidence: {journey.confidence_score}"
    ]
    return " | ".join(parts)


def _sli_to_text(sli: SLI) -> str:
    """Convert SLI to text representation for embedding"""
    parts = [
        f"Metric: {sli.metric_name}",
        f"Query: {sli.query_template}",
        f"Threshold: {sli.threshold_value} {sli.comparison_operator}"
    ]
    return " | ".join(parts)


def _artifact_to_text(artifact: Artifact) -> str:
    """Convert Artifact to text representation for embedding"""
    parts = [
        f"Type: {artifact.artifact_type}",
        f"Format: {artifact.format}",
        f"Content: {str(artifact.content)[:500]}"  # First 500 chars
    ]
    return " | ".join(parts)


@app.task(bind=True, base=EmbeddingPipelineTask, name='embedding_pipeline.search_similar')
def search_similar(
    self,
    entity_type: str,
    query_text: str,
    top_k: int = 10
) -> Dict[str, Any]:
    """
    Search for similar entities using semantic similarity.

    Args:
        entity_type: Type of entity to search ('journey', 'sli', 'artifact')
        query_text: Text query for similarity search
        top_k: Number of results to return

    Returns:
        List of similar entities with similarity scores
    """
    logger.info(
        f"Searching for similar {entity_type} entities",
        extra={'query': query_text[:100], 'task_id': self.request.id}
    )

    try:
        # Generate query embedding
        model = get_embedding_model()
        query_embedding = model.encode(query_text, normalize_embeddings=True)

        # Select collection
        collection_map = {
            'journey': JOURNEY_COLLECTION,
            'sli': SLI_COLLECTION,
            'artifact': ARTIFACT_COLLECTION
        }

        if entity_type not in collection_map:
            raise ValueError(f"Invalid entity_type: {entity_type}")

        connect_milvus()
        try:
            collection = Collection(collection_map[entity_type])
            collection.load()

            # Search for similar vectors
            search_params = {
                "metric_type": "COSINE",
                "params": {"nprobe": 10}
            }

            results = collection.search(
                data=[query_embedding.tolist()],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                output_fields=["*"]
            )

            # Format results
            similar_entities = []
            for hits in results:
                for hit in hits:
                    similar_entities.append({
                        'id': hit.entity.get(f'{entity_type}_id'),
                        'similarity_score': float(hit.score),
                        'metadata': {
                            k: v for k, v in hit.entity.to_dict().items()
                            if k not in ['id', 'embedding']
                        }
                    })

            logger.info(f"Found {len(similar_entities)} similar {entity_type} entities")

            return {
                'entity_type': entity_type,
                'query': query_text,
                'results': similar_entities
            }

        finally:
            disconnect_milvus()

    except Exception as e:
        logger.error(f"Similarity search failed: {str(e)}", exc_info=True)
        raise self.retry(exc=e)
