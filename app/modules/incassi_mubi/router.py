"""Router API per il modulo Incassi Mubi."""

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.models import User

router = APIRouter()


@router.get("/status")
def module_status(current_user: User = Depends(get_current_user)) -> dict:
    """Stato del modulo incassi."""
    return {"module": "incassi_mubi", "status": "active"}
