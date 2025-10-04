"""
S3 sample writer per T080
Writes reservoir samples to S3 as JSONL.gz
Generates presigned URL for retrieval
"""
from typing import List, Dict
import json
import gzip
from io import BytesIO
from datetime import datetime


class SampleWriter:
    """
    Helper for writing capsule samples to S3/MinIO

    Per data-model.md: samples stored as JSONL.gz in S3
    """

    def __init__(self, blob_storage_client):
        """
        Initialize sample writer

        Args:
            blob_storage_client: BlobStorageClient instance
        """
        self.blob_storage = blob_storage_client

    def write_samples(
        self,
        fingerprint_hash: str,
        time_bucket: int,
        samples: List[Dict],
        compress: bool = True
    ) -> str:
        """
        Write samples to S3

        Args:
            fingerprint_hash: SHA256 hash for organization
            time_bucket: Timestamp for organization
            samples: List of sample events (max 10)
            compress: Whether to gzip compress (default True)

        Returns:
            S3 key of written object

        Per FR-013: Max 10 reservoir samples per capsule
        """
        if len(samples) > 10:
            raise ValueError(f"Too many samples: {len(samples)} (max 10)")

        # Generate S3 key
        # Format: capsules/{fingerprint_hash}/{time_bucket}/samples.jsonl.gz
        timestamp_str = datetime.fromtimestamp(time_bucket / 1000).strftime('%Y%m%d-%H%M%S')
        key = f"capsules/{fingerprint_hash}/{timestamp_str}/samples.jsonl.gz"

        # Convert to JSONL
        jsonl_data = "\n".join(json.dumps(sample) for sample in samples)

        # Compress
        if compress:
            buffer = BytesIO()
            with gzip.GzipFile(fileobj=buffer, mode='wb') as gz_file:
                gz_file.write(jsonl_data.encode('utf-8'))
            data = buffer.getvalue()
        else:
            data = jsonl_data.encode('utf-8')

        # Upload to S3
        self.blob_storage.s3_client.put_object(
            Bucket=self.blob_storage.bucket_name,
            Key=key,
            Body=data,
            ContentType='application/gzip' if compress else 'application/jsonlines',
            Metadata={
                'fingerprint_hash': fingerprint_hash,
                'time_bucket': str(time_bucket),
                'sample_count': str(len(samples))
            }
        )

        return key

    def read_samples(self, s3_key: str) -> List[Dict]:
        """
        Read samples from S3

        Args:
            s3_key: S3 object key

        Returns:
            List of sample events
        """
        return self.blob_storage.download_sample(s3_key)

    def generate_download_url(
        self,
        s3_key: str,
        expiration: int = 3600
    ) -> str:
        """
        Generate presigned URL for sample download

        Args:
            s3_key: S3 object key
            expiration: URL expiration in seconds (default 1 hour)

        Returns:
            Presigned URL
        """
        return self.blob_storage.generate_presigned_url(s3_key, expiration)

    def delete_samples(self, s3_key: str) -> None:
        """Delete samples from S3"""
        self.blob_storage.delete_blob(s3_key)
