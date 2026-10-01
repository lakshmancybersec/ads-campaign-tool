from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin_key
from app.database import get_db
from app.models.catalog import CatalogProduct

router = APIRouter(prefix="/catalog", tags=["catalog"], dependencies=[Depends(require_admin_key)])


class CatalogProductCreate(BaseModel):
    product_code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=120)
    description: str | None = None
    image_url: HttpUrl
    price_inr: int = Field(gt=0)
    available: bool = True


class CatalogProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    product_code: str
    name: str
    category: str
    description: str | None
    image_url: str
    price_inr: int
    available: bool
    owner_approved: bool
    created_at: datetime


@router.get("", response_model=list[CatalogProductRead])
def list_catalog(available_only: bool = False, db: Session = Depends(get_db)) -> list[CatalogProduct]:
    statement = select(CatalogProduct).order_by(CatalogProduct.created_at.desc())
    if available_only:
        statement = statement.where(CatalogProduct.available.is_(True))
    return list(db.scalars(statement))


@router.post("", response_model=CatalogProductRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_admin_key)])
def create_catalog_product(payload: CatalogProductCreate, db: Session = Depends(get_db)) -> CatalogProduct:
    if db.scalar(select(CatalogProduct).where(CatalogProduct.product_code == payload.product_code)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Product code already exists.")
    product = CatalogProduct(**payload.model_dump(mode="json"))
    db.add(product)
    db.commit()
    db.refresh(product)
    return product
