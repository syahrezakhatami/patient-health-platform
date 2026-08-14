import pytest
from app.core.errors import AppError
from app.infra.object_storage import InMemoryObjectStorage
from app.modules.audit.domain.events import AuditEvent
from app.modules.audit.infrastructure.memory_sink import InMemoryAuditSink
from app.shared.enums import AuditResult

pytestmark = pytest.mark.unit


async def test_object_storage_uses_random_id_and_checksum() -> None:
    storage = InMemoryObjectStorage()
    stored = await storage.put(b"hello", "text/plain", original_filename="../../etc/passwd")
    assert stored.object_id != "../../etc/passwd"
    assert stored.checksum_sha256
    assert await storage.get(stored.object_id) == b"hello"


async def test_object_storage_rejects_empty_and_invalid_type() -> None:
    storage = InMemoryObjectStorage()
    with pytest.raises(AppError):
        await storage.put(b"", "text/plain")
    with pytest.raises(AppError):
        await storage.put(b"hello", "not-a-type")


async def test_audit_sink_appends_and_does_not_mutate_event() -> None:
    sink = InMemoryAuditSink()
    event = AuditEvent(
        action="auth.context.read",
        resource_type="AuthContext",
        result=AuditResult.SUCCESS,
        metadata={"synthetic": "true"},
    )
    await sink.record(event)
    assert sink.events == [event]
