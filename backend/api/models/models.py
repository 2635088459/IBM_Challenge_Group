import uuid
from datetime import datetime, timezone

def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)
from sqlalchemy import Column, Text, DateTime, ForeignKey, Integer, Boolean, JSON
from sqlalchemy.orm import relationship
from db.database import Base

# Use JSONB on PostgreSQL, plain JSON for SQLite (checked via DATABASE_URL env var)
import os as _os
_db_url = _os.environ.get("DATABASE_URL", "")
if _db_url.startswith("postgresql"):
    from sqlalchemy.dialects.postgresql import JSONB as _JSON  # type: ignore[assignment]
else:
    _JSON = JSON

# UUID columns are stored as TEXT strings (as_uuid=False equivalent) — works on both PG and SQLite
_UUID = Text


def _uuid():
    return str(uuid.uuid4())


class Shipment(Base):
    __tablename__ = "shipments"

    id = Column(_UUID, primary_key=True, default=_uuid)
    reference_number = Column(Text, nullable=False, unique=True)
    status = Column(Text, nullable=False, default="OBSERVE")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    documents = relationship("Document", back_populates="shipment", cascade="all, delete-orphan")
    agent_tasks = relationship("AgentTask", back_populates="shipment", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="shipment", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"

    id = Column(_UUID, primary_key=True, default=_uuid)
    shipment_id = Column(_UUID, ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False)
    doc_type = Column(Text, nullable=False)   # INVOICE | PACKING_LIST | BILL_OF_LADING
    file_hash = Column(Text, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    status = Column(Text, nullable=False, default="raw")  # raw | extracted | verified
    uploaded_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    shipment = relationship("Shipment", back_populates="documents")


class Event(Base):
    __tablename__ = "events"

    id = Column(_UUID, primary_key=True, default=_uuid)
    event_id = Column(Text, nullable=False, unique=True)   # deduplication key
    event_type = Column(Text, nullable=False)
    source_verified = Column(Boolean, nullable=False, default=False)
    shipment_id = Column(_UUID, ForeignKey("shipments.id", ondelete="SET NULL"), nullable=True)
    payload = Column(_JSON, nullable=True)
    occurred_at = Column(DateTime, nullable=True)
    processed_at = Column(DateTime, nullable=True)


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id = Column(_UUID, primary_key=True, default=_uuid)
    shipment_id = Column(_UUID, ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False)
    state = Column(Text, nullable=False, default="INITIALIZE")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    shipment = relationship("Shipment", back_populates="agent_tasks")
    actions = relationship("AgentAction", back_populates="task", cascade="all, delete-orphan")


class AgentAction(Base):
    __tablename__ = "agent_actions"

    id = Column(_UUID, primary_key=True, default=_uuid)
    task_id = Column(_UUID, ForeignKey("agent_tasks.id", ondelete="CASCADE"), nullable=False)
    action_type = Column(Text, nullable=False)
    idempotency_key = Column(Text, nullable=False, unique=True)
    payload = Column(_JSON, nullable=True)
    status = Column(Text, nullable=False, default="PENDING")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    task = relationship("AgentTask", back_populates="actions")
    approvals = relationship("Approval", back_populates="action", cascade="all, delete-orphan")
    outbox_entries = relationship("OutboxEntry", back_populates="action", cascade="all, delete-orphan")


class Approval(Base):
    __tablename__ = "approvals"

    id = Column(_UUID, primary_key=True, default=_uuid)
    action_id = Column(_UUID, ForeignKey("agent_actions.id", ondelete="CASCADE"), nullable=True)
    shipment_id = Column(_UUID, ForeignKey("shipments.id", ondelete="CASCADE"), nullable=True)
    role = Column(Text, nullable=False)   # R2 | R3 | R4 | R5
    status = Column(Text, nullable=False, default="PENDING")  # PENDING | APPROVED | REJECTED | EXPIRED
    payload_hash = Column(Text, nullable=True)
    requested_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    action = relationship("AgentAction", back_populates="approvals")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(_UUID, primary_key=True, default=_uuid)
    shipment_id = Column(_UUID, ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False)
    actor = Column(Text, nullable=False)
    event = Column(Text, nullable=False)
    details = Column(_JSON, nullable=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)

    shipment = relationship("Shipment", back_populates="audit_logs")


class OutboxEntry(Base):
    __tablename__ = "outbox"

    id = Column(_UUID, primary_key=True, default=_uuid)
    action_id = Column(_UUID, ForeignKey("agent_actions.id", ondelete="CASCADE"), nullable=True)
    payload = Column(_JSON, nullable=False)
    status = Column(Text, nullable=False, default="PENDING")  # PENDING | DISPATCHED | FAILED
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    action = relationship("AgentAction", back_populates="outbox_entries")
