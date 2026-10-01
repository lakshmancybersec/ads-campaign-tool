import hmac

from fastapi import Header, HTTPException, status

from app.config import get_settings


def require_admin_key(x_admin_key: str | None = Header(default=None)) -> None:
    """Protect write endpoints when an admin key has been configured."""
    expected_key = get_settings().api_admin_key
    if not expected_key:
        raise HTTPException(status_code=503, detail="Configure API_ADMIN_KEY before using protected operations.")
    if not x_admin_key or not hmac.compare_digest(x_admin_key.encode("utf-8"), expected_key.encode("utf-8")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin API key.")
