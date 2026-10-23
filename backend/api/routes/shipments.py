from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import get_db
from api.models.models import Shipment
from api.schemas.schemas import ShipmentListItem, ShipmentOut

router = APIRouter(prefix="/api/shipments", tags=["shipments"])


@router.get("", response_model=list[ShipmentListItem])
def list_shipments(db: Session = Depends(get_db)):
    return db.query(Shipment).order_by(Shipment.created_at.desc()).all()


@router.get("/{shipment_id}", response_model=ShipmentOut)
def get_shipment(shipment_id: str, db: Session = Depends(get_db)):
    shipment = db.query(Shipment).filter(Shipment.id == shipment_id).first()
    if not shipment:
        raise HTTPException(status_code=404, detail="Shipment not found")
    return shipment
