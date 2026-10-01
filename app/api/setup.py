from fastapi import APIRouter, Depends
from app.api.dependencies import require_admin_key

from app.config import get_settings
from app.services.meta_client import configured

router = APIRouter(prefix="/setup", tags=["setup"], dependencies=[Depends(require_admin_key)])


@router.get("/status")
def integration_status() -> dict[str, object]:
    """Return non-secret integration metadata and live-readiness requirements."""
    settings = get_settings()
    profile = {
        "meta_ad_account_id": settings.meta_ad_account_id,
        "meta_app_id": settings.meta_app_id,
        "meta_business_manager_id": settings.meta_business_manager_id,
        "facebook_page_url": settings.facebook_page_url,
        "commerce_business_id": settings.commerce_business_id,
        "meta_catalog_id": settings.meta_catalog_id,
        "storefront_url": settings.storefront_url,
        "whatsapp_business_account_id": settings.whatsapp_business_account_id,
    }
    missing = [
        name
        for name, value in {
            "META_ACCESS_TOKEN": settings.meta_access_token,
            "META_AD_ACCOUNT_ID": settings.meta_ad_account_id,
            "FACEBOOK_PAGE_ID": settings.facebook_page_id,
            "CUSTOMER_WHATSAPP_NUMBER": settings.customer_whatsapp_number,
            "META_APP_SECRET": settings.meta_app_secret,
            "META_CATALOG_ID": settings.meta_catalog_id,
            "WHATSAPP_ACCESS_TOKEN": settings.whatsapp_access_token,
            "WHATSAPP_PHONE_NUMBER_ID": settings.whatsapp_phone_number_id,
            "WHATSAPP_VERIFY_TOKEN": settings.whatsapp_verify_token,
            "WHATSAPP_APP_SECRET": settings.whatsapp_app_secret,
            "OWNER_WHATSAPP_NUMBER": settings.owner_whatsapp_number,
            "WHATSAPP_APPROVAL_TEMPLATE": settings.whatsapp_approval_template,
            "PUBLIC_DASHBOARD_URL": settings.public_dashboard_url,
        }.items()
        if not configured(value)
    ]
    return {
        "profile": profile,
        "live_operations_enabled": settings.meta_live_writes_enabled,
        "paused_preparation_enabled": settings.meta_paused_preparation_enabled,
        "meta_read_configured": configured(settings.meta_access_token) and bool(settings.meta_ad_account_id),
        "account_verification": "Run Check Meta connection; configuration alone does not verify access.",
        "scheduler_enabled": settings.scheduler_enabled,
        "whatsapp_notifications_enabled": settings.whatsapp_notifications_enabled,
        "missing_live_configuration": missing,
        "note": "Secrets and access tokens are intentionally never returned by this endpoint.",
    }
