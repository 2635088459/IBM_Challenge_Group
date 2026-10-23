from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from db.database import get_db
from api.models.models import Event, Shipment, AuditLog
from api.schemas.schemas import EventIn, EventOut

router = APIRouter(prefix="/api/events", tags=["events"])


@router.post("", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def ingest_event(body: EventIn, db: Session = Depends(get_db)):
    # Validate event_id presence (Pydantic already enforces non-null, but be explicit)
    if not body.event_id or not body.event_id.strip():
        raise HTTPException(status_code=400, detail="event_id is required")

    # Deduplication: reject if event_id already processed
    existing = db.query(Event).filter(Event.event_id == body.event_id).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Event '{body.event_id}' already processed",
        )

    # Validate shipment reference if provided
    if body.shipment_id:
        shipment = db.query(Shipment).filter(Shipment.id == body.shipment_id).first()
        if not shipment:
            raise HTTPException(status_code=404, detail="Shipment not found")

    event = Event(
        event_id=body.event_id,
        event_type=body.event_type,
        source_verified=body.source_verified,
        shipment_id=body.shipment_id,
        payload=body.payload,
        occurred_at=body.occurred_at,
        processed_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )

    try:
        db.add(event)
        # Write audit log entry
        if body.shipment_id:
            db.add(AuditLog(
                shipment_id=body.shipment_id,
                actor="system",
                event=body.event_type,
                details=body.payload,
            ))
        db.commit()
        db.refresh(event)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Event '{body.event_id}' already processed (concurrent insert)",
        )

    return event
