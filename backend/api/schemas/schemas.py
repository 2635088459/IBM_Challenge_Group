from datetime import datetime
from typing import Any, Optional
import uuid
from pydantic import BaseModel, Field, field_validator


class _UUIDCoerceMixin(BaseModel):
    """
    Coerce uuid.UUID → str for any field whose name ends with '_id' or is 'id'.
    Needed because PostgreSQL returns UUID objects even for Text columns.
    Works for both dict inputs and ORM from_attributes serialization.
    """

    @field_validator("id", mode="before", check_fields=False)
    @classmethod
    def _coerce_id(cls, v: Any) -> Any:
        return str(v) if isinstance(v, uuid.UUID) else v

    @field_validator(
        "shipment_id", "action_id", "task_id",
        mode="before", check_fields=False
    )
    @classmethod
    def _coerce_fk_ids(cls, v: Any) -> Any:
        return str(v) if isinstance(v, uuid.UUID) else v


# ── Shipment ──────────────────────────────────────────────────────────────────

class DocumentOut(_UUIDCoerceMixin):
    id: str
    doc_type: str
    file_hash: Optional[str]
    version: int
    status: str
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class ShipmentOut(_UUIDCoerceMixin):
    id: str
    reference_number: str
    status: str
    created_at: datetime
    documents: list[DocumentOut] = []

    model_config = {"from_attributes": True}


class ShipmentListItem(_UUIDCoerceMixin):
    id: str
    reference_number: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Event ─────────────────────────────────────────────────────────────────────

class EventIn(BaseModel):
    event_id: str = Field(..., description="Unique client-side event identifier")
    event_type: str
    source_verified: bool = False
    shipment_id: Optional[str] = None
    payload: Optional[dict[str, Any]] = None
    occurred_at: Optional[datetime] = None


class EventOut(_UUIDCoerceMixin):
    id: str
    event_id: str
    event_type: str
    source_verified: bool
    shipment_id: Optional[str]
    payload: Optional[dict[str, Any]]
    occurred_at: Optional[datetime]
    processed_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ── Agent Task ────────────────────────────────────────────────────────────────

class AgentTaskIn(BaseModel):
    shipment_id: str
    state: str = "INITIALIZE"


class AgentTaskOut(_UUIDCoerceMixin):
    id: str
    shipment_id: str
    state: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Agent Action ──────────────────────────────────────────────────────────────

class AgentActionIn(BaseModel):
    task_id: str
    action_type: str
    idempotency_key: str
    payload: Optional[dict[str, Any]] = None


class AgentActionOut(_UUIDCoerceMixin):
    id: str
    task_id: str
    action_type: str
    idempotency_key: str
    payload: Optional[dict[str, Any]]
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Approval ──────────────────────────────────────────────────────────────────

class ApprovalIn(BaseModel):
    action_id: Optional[str] = None
    shipment_id: Optional[str] = None
    role: str
    payload_hash: Optional[str] = None


class ApprovalPatch(BaseModel):
    status: str  # APPROVED | REJECTED


class ApprovalOut(_UUIDCoerceMixin):
    id: str
    action_id: Optional[str]
    shipment_id: Optional[str]
    role: str
    status: str
    payload_hash: Optional[str]
    requested_at: datetime
    resolved_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ── Audit Log ─────────────────────────────────────────────────────────────────

class AuditLogOut(_UUIDCoerceMixin):
    id: str
    shipment_id: str
    actor: str
    event: str
    details: Optional[dict[str, Any]]
    timestamp: datetime
    prev_hash: Optional[str] = None
    entry_hash: Optional[str] = None

    model_config = {"from_attributes": True}
