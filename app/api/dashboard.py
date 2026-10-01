from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin_key
from app.database import get_db
from app.models.campaign import Campaign
from app.models.catalog import CatalogProduct
from app.models.lead import Lead

router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(require_admin_key)])


@router.get("/overview")
def overview(db: Session = Depends(get_db)) -> dict[str, object]:
    """Operational summary for the local dashboard; never includes message contents."""
    campaigns = list(db.scalars(select(Campaign).where(Campaign.status != "ARCHIVED").order_by(Campaign.created_at.desc())))
    leads = list(db.scalars(select(Lead).order_by(Lead.updated_at.desc()).limit(8)))
    return {
        "counts": {
            "campaigns": len(campaigns),
            "ready_campaigns": sum(campaign.status == "READY" for campaign in campaigns),
            "catalog_products": db.scalar(select(func.count()).select_from(CatalogProduct)) or 0,
            "leads": db.scalar(select(func.count()).select_from(Lead)) or 0,
        },
        "recent_leads": [
            {
                "id": lead.id,
                "customer_name": lead.customer_name,
                "product_interest": lead.product_interest,
                "city": lead.city,
                "score": lead.score,
                "status": lead.status,
                "updated_at": lead.updated_at,
            }
            for lead in leads
        ],
    }
