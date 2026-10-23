from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from db.database import get_db
from api.models.models import AgentTask, Shipment
from api.schemas.schemas import AgentTaskIn, AgentTaskOut

router = APIRouter(prefix="/api/agent-tasks", tags=["agent-tasks"])


@router.post("", response_model=AgentTaskOut, status_code=status.HTTP_201_CREATED)
def create_agent_task(body: AgentTaskIn, db: Session = Depends(get_db)):
    shipment = db.query(Shipment).filter(Shipment.id == body.shipment_id).first()
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")

    task = AgentTask(
        shipment_id=body.shipment_id,
        state=body.state,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task
