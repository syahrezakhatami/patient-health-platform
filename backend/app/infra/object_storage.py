import hashlib
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse
from uuid import uuid4

import boto3
from botocore.config import Config

from app.core.config import Settings
from app.core.errors import AppError


@dataclass(frozen=True, slots=True)
class StoredObject:
    object_id: str
    bucket: str
    content_type: str
    size_bytes: int
    checksum_sha256: str


class ObjectStorage(Protocol):
    async def put(
        self,
        data: bytes,
        content_type: str,
        *,
        original_filename: str | None = None,
    ) -> StoredObject: ...

    async def get(self, object_id: str) -> bytes: ...

    async def delete(self, object_id: str) -> None: ...

    async def exists_bucket(self) -> bool: ...


def _validate_upload(data: bytes, content_type: str, max_bytes: int) -> None:
    if not data:
        raise AppError("empty_object", "Uploaded object is empty", 400)
    if len(data) > max_bytes:
        raise AppError("object_too_large", "Uploaded object exceeds the size limit", 413)
    if not content_type or "/" not in content_type:
        raise AppError("invalid_content_type", "Content type is required", 400)
    if ".." in content_type or "\x00" in content_type:
        raise AppError("invalid_content_type", "Content type is invalid", 400)


def new_object_id() -> str:
    return str(uuid4())


class InMemoryObjectStorage:
    def __init__(self, bucket: str = "test-private", max_bytes: int = 1_048_576) -> None:
        self.bucket = bucket
        self.max_bytes = max_bytes
        self._objects: dict[str, tuple[bytes, str]] = {}

    async def put(
        self,
        data: bytes,
        content_type: str,
        *,
        original_filename: str | None = None,
    ) -> StoredObject:
        del original_filename
        _validate_upload(data, content_type, self.max_bytes)
        object_id = new_object_id()
        self._objects[object_id] = (data, content_type)
        return StoredObject(
            object_id=object_id,
            bucket=self.bucket,
            content_type=content_type,
            size_bytes=len(data),
            checksum_sha256=hashlib.sha256(data).hexdigest(),
        )

    async def get(self, object_id: str) -> bytes:
        try:
            return self._objects[object_id][0]
        except KeyError as exc:
            raise AppError("object_not_found", "Object not found", 404) from exc

    async def delete(self, object_id: str) -> None:
        self._objects.pop(object_id, None)

    async def exists_bucket(self) -> bool:
        return True


class S3ObjectStorage:
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self._settings = settings
        parsed = urlparse(settings.object_storage_endpoint)
        if parsed.scheme not in {"http", "https"}:
            raise AppError("invalid_storage_endpoint", "Object storage endpoint is invalid", 500)
        self._client: Any = client or boto3.client(
            "s3",
            endpoint_url=settings.object_storage_endpoint,
            aws_access_key_id=settings.object_storage_access_key.get_secret_value(),
            aws_secret_access_key=settings.object_storage_secret_key.get_secret_value(),
            region_name=settings.object_storage_region,
            use_ssl=settings.object_storage_use_ssl,
            config=Config(s3={"addressing_style": "path"}),
        )

    async def put(
        self,
        data: bytes,
        content_type: str,
        *,
        original_filename: str | None = None,
    ) -> StoredObject:
        del original_filename
        _validate_upload(data, content_type, self._settings.object_storage_max_bytes)
        object_id = new_object_id()
        checksum = hashlib.sha256(data).hexdigest()
        self._client.put_object(
            Bucket=self._settings.object_storage_bucket,
            Key=object_id,
            Body=data,
            ContentType=content_type,
            ACL="private",
            Metadata={"checksum-sha256": checksum},
        )
        return StoredObject(
            object_id=object_id,
            bucket=self._settings.object_storage_bucket,
            content_type=content_type,
            size_bytes=len(data),
            checksum_sha256=checksum,
        )

    async def get(self, object_id: str) -> bytes:
        response = self._client.get_object(
            Bucket=self._settings.object_storage_bucket,
            Key=object_id,
        )
        return bytes(response["Body"].read())

    async def delete(self, object_id: str) -> None:
        self._client.delete_object(
            Bucket=self._settings.object_storage_bucket,
            Key=object_id,
        )

    async def exists_bucket(self) -> bool:
        self._client.head_bucket(Bucket=self._settings.object_storage_bucket)
        return True
