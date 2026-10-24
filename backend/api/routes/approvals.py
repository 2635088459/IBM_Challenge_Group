import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from db.database import get_db
from api.models.models import Approval, AuditLog
from api.schemas.schemas import ApprovalIn, ApprovalOut, ApprovalPatch
from api.agent_store import resume_if_ready

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/approvals", tags=["approvals"])

VALID_STATUSES = {"APPROVED", "REJECTED"}


@router.post("", response_model=ApprovalOut, status_code=status.HTTP_201_CREATED)
def create_approval(body: ApprovalIn, db: Session = Depends(get_db)):
    approval = Approval(
        action_id=body.action_id,
        shipment_id=body.shipment_id,
        role=body.role,
        status="PENDING",
        payload_hash=body.payload_hash,
    )
    db.add(approval)
    if body.shipment_id:
        db.add(AuditLog(
            shipment_id=body.shipment_id,
            actor="system",
            event="APPROVAL_REQUESTED",
            details={"role": body.role, "payload_hash": body.payload_hash},
        ))
    db.commit()
    db.refresh(approval)
    return approval


@router.get("", response_model=list[ApprovalOut])
def list_approvals(
    shipment_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(Approval)
    if shipment_id:
        query = query.filter(Approval.shipment_id == shipment_id)
    if status:
        query = query.filter(Approval.status == status)
    return query.order_by(Approval.requested_at.desc()).all()


@router.patch("/{approval_id}", response_model=ApprovalOut)
def update_approval(approval_id: str, body: ApprovalPatch, db: Session = Depends(get_db)):
    approval = db.query(Approval).filter(Approval.id == approval_id).first()
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")

    if approval.status != "PENDING":
        raise HTTPException(
            status_code=409,
            detail=f"Approval is already {approval.status}",
        )

    if body.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{body.status}'. Must be one of {VALID_STATUSES}",
        )

    # Check expiry: approvals older than 30 minutes are expired
    age_minutes = (datetime.now(timezone.utc).replace(tzinfo=None) - approval.requested_at).total_seconds() / 60
    if age_minutes > 30:
        approval.status = "EXPIRED"
        db.commit()
        db.refresh(approval)
        raise HTTPException(status_code=409, detail="approval_expired")

    approval.status = body.status
    approval.resolved_at = datetime.now(timezone.utc).replace(tzinfo=None)

    if approval.shipment_id:
        db.add(AuditLog(
            shipment_id=approval.shipment_id,
            actor="human",
            event=f"APPROVAL_{body.status}",
            details={"approval_id": approval_id, "role": approval.role},
        ))

    db.commit()

    # Wake the agent if this was the last open approval for its plan.  The
    # decision above is already committed, so a failed resume must not undo it.
    try:
        resume_if_ready(db, approval)
    except Exception:
        logger.exception("Agent resume failed after approval %s", approval_id)
        db.rollback()

    db.refresh(approval)
    return approval
