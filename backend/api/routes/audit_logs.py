from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import get_db
from api.models.models import AuditLog, Shipment
from api.schemas.schemas import AuditLogOut

router = APIRouter(prefix="/api/audit-logs", tags=["audit-logs"])


@router.get("/{shipment_id}", response_model=list[AuditLogOut])
def get_audit_logs(shipment_id: str, db: Session = Depends(get_db)):
    shipment = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")

    logs = (
        db.query(AuditLog)
        .filter(AuditLog.shipment_id == shipment_id)
        .order_by(AuditLog.timestamp.asc())
        .all()
    )
    return logs
