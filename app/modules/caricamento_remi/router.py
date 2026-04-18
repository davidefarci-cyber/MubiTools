"""Router API per il modulo Caricamento REMI — caricamento pratiche e dashboard."""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import require_module
from app.database import get_db
from app.models import User, log_audit
from app.modules.caricamento_remi import service
from app.modules.caricamento_remi.schemas import (
    RemiChangeStatusRequest,
    RemiChangeStatusResponse,
    RemiConfirmRequest,
    RemiConfirmResponse,
    RemiHistoryResponse,
    RemiMatchResult,
    RemiMatchRow,
    RemiResendRequest,
    RemiResendResponse,
    RemiStatsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

MODULE_NAME = "caricamento_remi"


# --- Caricamento pratiche REMI ---


@router.post("/match", response_model=list[RemiMatchResult])
def match_practices(
    rows: list[RemiMatchRow],
    current_user: User = Depends(require_module(MODULE_NAME)),
    db: Session = Depends(get_db),
) -> list[RemiMatchResult]:
    """Esegue il match delle P.IVA contro l'anagrafica distributori attivi."""
    results = service.match_vat_numbers(rows, db)
    logger.info(
        "Match pratiche: %d righe, %d trovate — utente %s",
        len(rows),
        sum(1 for r in results if r.matched),
        current_user.username,
    )
    return results


@router.post("/confirm", response_model=RemiConfirmResponse)
def confirm_practices(
    data: RemiConfirmRequest,
    current_user: User = Depends(require_module(MODULE_NAME)),
    db: Session = Depends(get_db),
) -> RemiConfirmResponse:
    """Conferma e inserisce le pratiche REMI nel database."""
    batch_id, inserted, skipped = service.create_practices_batch(data, db)

    log_audit(
        db,
        "remi_practices_loaded",
        user_id=current_user.id,
        detail={
            "batch_id": batch_id,
            "inserted": inserted,
            "skipped": skipped,
            "effective_date": str(data.effective_date),
        },
    )
    logger.info(
        "Pratiche REMI caricate: batch=%s, inserite=%d, saltate=%d — utente %s",
        batch_id,
        inserted,
        skipped,
        current_user.username,
    )
    return RemiConfirmResponse(batch_id=batch_id, inserted=inserted, skipped=skipped)


# --- Dashboard ---


@router.get("/history", response_model=RemiHistoryResponse)
def get_history(
    status: str | None = None,
    vat_number: str | None = None,
    search: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 50,
    current_user: User = Depends(require_module(MODULE_NAME)),
    db: Session = Depends(get_db),
) -> RemiHistoryResponse:
    """Storico pratiche REMI aggregato per DL + batch di invio, con filtri e paginazione."""
    items, total = service.list_practice_history(
        db,
        status=status,
        vat_number=vat_number,
        search=search,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
    return RemiHistoryResponse(total=total, page=page, items=items)


@router.get("/history/stats", response_model=RemiStatsResponse)
def get_stats(
    current_user: User = Depends(require_module(MODULE_NAME)),
    db: Session = Depends(get_db),
) -> RemiStatsResponse:
    """Statistiche riepilogative delle pratiche REMI."""
    return service.get_practices_stats(db)


@router.post("/history/resend", response_model=RemiResendResponse)
def resend_practices(
    data: RemiResendRequest,
    current_user: User = Depends(require_module(MODULE_NAME)),
    db: Session = Depends(get_db),
) -> RemiResendResponse:
    """Reimposta le pratiche in errore a stato pending per il reinvio."""
    updated_ids = service.reset_practices_to_pending(data.practice_ids, db)

    log_audit(
        db,
        "remi_practices_resend",
        user_id=current_user.id,
        detail={
            "practice_ids": updated_ids,
            "count": len(updated_ids),
        },
    )
    logger.info(
        "Pratiche REMI reimpostate: %d pratiche — utente %s",
        len(updated_ids),
        current_user.username,
    )
    return RemiResendResponse(updated=len(updated_ids))


@router.post("/history/change-status", response_model=RemiChangeStatusResponse)
def change_practice_status(
    data: RemiChangeStatusRequest,
    current_user: User = Depends(require_module(MODULE_NAME)),
    db: Session = Depends(get_db),
) -> RemiChangeStatusResponse:
    """Cambia lo stato di un gruppo di pratiche REMI (transizioni validate)."""
    try:
        updated_ids = service.transition_practices_status(
            data.practice_ids, data.new_status, db
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    log_audit(
        db,
        "remi_change_status",
        user_id=current_user.id,
        detail={
            "practice_ids": updated_ids,
            "new_status": data.new_status,
            "count": len(updated_ids),
        },
    )
    logger.info(
        "Cambio stato REMI: %d pratiche → %s — utente %s",
        len(updated_ids),
        data.new_status,
        current_user.username,
    )
    return RemiChangeStatusResponse(updated=len(updated_ids))
