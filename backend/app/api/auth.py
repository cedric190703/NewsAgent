"""Admin authentication: verify admin key."""

from fastapi import APIRouter, Header, HTTPException

from app.core.config import settings

router = APIRouter()


@router.post("/auth/verify")
async def verify_admin(x_admin_key: str | None = Header(default=None)) -> dict[str, bool]:
    if x_admin_key != settings.admin_password:
        raise HTTPException(status_code=403, detail="Invalid admin key")
    return {"valid": True}
