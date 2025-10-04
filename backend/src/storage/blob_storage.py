"""
S3/MinIO blob storage client per T038
"""
import boto3
from botocore.exceptions import ClientError
from typing import Optional, List
import json
import gzip
from io import BytesIO


class BlobStorageClient:
    """S3/MinIO client for capsule samples and telemetry blobs"""

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket_name: str = "capsule-samples"
    ):
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key
        )
        self.bucket_name = bucket_name

    def upload_sample(
        self,
        key: str,
        samples: List[dict],
        compress: bool = True
    ) -> str:
        """
        Upload capsule samples to S3

        Args:
            key: S3 object key (e.g., "capsules/abc123/samples.jsonl.gz")
            samples: List of sample events (max 10 per FR requirement)
            compress: Whether to gzip compress (default True)

        Returns:
            S3 key of uploaded object
        """
        # Convert samples to JSONL
        jsonl_data = "\n".join(json.dumps(sample) for sample in samples)

        if compress:
            # Gzip compress
            buffer = BytesIO()
            with gzip.GzipFile(fileobj=buffer, mode="wb") as gz_file:
                gz_file.write(jsonl_data.encode("utf-8"))
            data = buffer.getvalue()
            content_type = "application/gzip"
        else:
            data = jsonl_data.encode("utf-8")
            content_type = "application/jsonlines"

        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=data,
                ContentType=content_type
            )
            return key
        except ClientError as e:
            raise Exception(f"Failed to upload samples to S3: {e}")

    def download_sample(self, key: str) -> List[dict]:
        """
        Download and decompress capsule samples

        Args:
            key: S3 object key

        Returns:
            List of sample events
        """
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=key
            )

            data = response["Body"].read()

            # Check if gzipped
            if key.endswith(".gz"):
                data = gzip.decompress(data)

            # Parse JSONL
            samples = []
            for line in data.decode("utf-8").strip().split("\n"):
                if line:
                    samples.append(json.loads(line))

            return samples
        except ClientError as e:
            raise Exception(f"Failed to download samples from S3: {e}")

    def list_blobs(self, prefix: str, max_keys: int = 1000) -> List[str]:
        """
        List blobs with given prefix

        Args:
            prefix: S3 key prefix
            max_keys: Maximum number of keys to return

        Returns:
            List of S3 keys
        """
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix,
                MaxKeys=max_keys
            )

            return [obj["Key"] for obj in response.get("Contents", [])]
        except ClientError as e:
            raise Exception(f"Failed to list blobs from S3: {e}")

    def delete_blob(self, key: str) -> None:
        """Delete a blob from S3"""
        try:
            self.s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=key
            )
        except ClientError as e:
            raise Exception(f"Failed to delete blob from S3: {e}")

    def generate_presigned_url(self, key: str, expiration: int = 3600) -> str:
        """
        Generate presigned URL for download

        Args:
            key: S3 object key
            expiration: URL expiration in seconds (default 1 hour)

        Returns:
            Presigned URL
        """
        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": key},
                ExpiresIn=expiration
            )
            return url
        except ClientError as e:
            raise Exception(f"Failed to generate presigned URL: {e}")
