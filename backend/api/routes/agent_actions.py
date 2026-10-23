from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from db.database import get_db
from api.models.models import AgentAction, AgentTask, OutboxEntry
from api.schemas.schemas import AgentActionIn, AgentActionOut

router = APIRouter(prefix="/api/agent-actions", tags=["agent-actions"])


@router.post("", response_model=AgentActionOut)
def create_agent_action(body: AgentActionIn, db: Session = Depends(get_db)):
    # Idempotency: return existing record if key already exists
    existing = db.query(AgentAction).filter(
        AgentAction.idempotency_key == body.idempotency_key
    ).first()
    if existing:
        return existing  # 200 OK with original record

    task = db.query(AgentTask).filter(AgentTask.id == body.task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="AgentTask not found")

    action = AgentAction(
        task_id=body.task_id,
        action_type=body.action_type,
        idempotency_key=body.idempotency_key,
        payload=body.payload,
        status="PENDING",
    )

    try:
        db.add(action)
        db.flush()  # get action.id before outbox insert

        # Outbox: write action to dispatch queue
        outbox = OutboxEntry(
            action_id=action.id,
            payload={
                "action_id": action.id,
                "action_type": action.action_type,
                "task_id": action.task_id,
                "payload": action.payload,
            },
            status="PENDING",
        )
        db.add(outbox)
        db.commit()
        db.refresh(action)
    except IntegrityError:
        db.rollback()
        # Race condition on concurrent insert with same idempotency_key
        existing = db.query(AgentAction).filter(
            AgentAction.idempotency_key == body.idempotency_key
        ).first()
        if existing:
            return existing
        raise HTTPException(status_code=409, detail="Concurrent duplicate idempotency_key")

    return action
