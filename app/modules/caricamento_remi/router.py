"""Router API per il modulo Caricamento REMI — Anagrafica DL e caricamento pratiche."""

import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models import DlRegistry, RemiPractice, User, log_audit
from app.modules.caricamento_remi.schemas import (
    DlRegistryCreate,
    DlRegistryOut,
    DlRegistryUpdate,
    RemiConfirmRequest,
    RemiConfirmResponse,
    RemiMatchResult,
    RemiMatchRow,
)
from app.modules.caricamento_remi.service import validate_partita_iva

logger = logging.getLogger(__name__)

router = APIRouter()

MODULE_NAME = "caricamento_remi"

# Regex semplice per validazione formato email/PEC
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _require_module(user: User) -> None:
    """Verifica che l'utente abbia accesso al modulo."""
    if not user.has_module(MODULE_NAME):
        raise HTTPException(status_code=403, detail="Modulo non abilitato")


@router.get("/registry", response_model=list[DlRegistryOut])
def list_registry(
    search: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DlRegistryOut]:
    """Lista distributori locali con filtro testo opzionale."""
    _require_module(current_user)

    query = db.query(DlRegistry)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.filter(
            DlRegistry.company_name.ilike(pattern)
            | DlRegistry.vat_number.ilike(pattern)
            | DlRegistry.pec_address.ilike(pattern)
        )
    query = query.order_by(DlRegistry.company_name)
    return query.all()


@router.post("/registry", response_model=DlRegistryOut, status_code=201)
def create_registry(
    data: DlRegistryCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DlRegistryOut:
    """Crea un nuovo distributore locale."""
    _require_module(current_user)

    # Validazione P.IVA
    if not validate_partita_iva(data.vat_number):
        raise HTTPException(status_code=400, detail="Partita IVA non valida")

    # Validazione formato PEC
    if not _EMAIL_RE.match(data.pec_address):
        raise HTTPException(status_code=400, detail="Formato PEC non valido")

    # Unicità P.IVA
    existing = db.query(DlRegistry).filter(DlRegistry.vat_number == data.vat_number).first()
    if existing:
        raise HTTPException(status_code=409, detail="Partita IVA già registrata")

    dl = DlRegistry(
        company_name=data.company_name.strip(),
        vat_number=data.vat_number.strip(),
        pec_address=data.pec_address.strip(),
        is_active=True,
    )
    db.add(dl)
    db.commit()
    db.refresh(dl)

    log_audit(
        db,
        "dl_registry_created",
        user_id=current_user.id,
        detail={
            "dl_id": dl.id,
            "company_name": dl.company_name,
            "vat_number": dl.vat_number,
        },
    )

    logger.info("DL creato: %s (P.IVA %s) da %s", dl.company_name, dl.vat_number, current_user.username)
    return dl


@router.put("/registry/{dl_id}", response_model=DlRegistryOut)
def update_registry(
    dl_id: int,
    data: DlRegistryUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DlRegistryOut:
    """Modifica un distributore locale esistente."""
    _require_module(current_user)

    dl = db.query(DlRegistry).filter(DlRegistry.id == dl_id).first()
    if not dl:
        raise HTTPException(status_code=404, detail="Distributore non trovato")

    if data.vat_number is not None:
        if not validate_partita_iva(data.vat_number):
            raise HTTPException(status_code=400, detail="Partita IVA non valida")
        # Unicità P.IVA (escluso il record corrente)
        existing = (
            db.query(DlRegistry)
            .filter(DlRegistry.vat_number == data.vat_number, DlRegistry.id != dl_id)
            .first()
        )
        if existing:
            raise HTTPException(status_code=409, detail="Partita IVA già registrata")
        dl.vat_number = data.vat_number.strip()

    if data.pec_address is not None:
        if not _EMAIL_RE.match(data.pec_address):
            raise HTTPException(status_code=400, detail="Formato PEC non valido")
        dl.pec_address = data.pec_address.strip()

    if data.company_name is not None:
        dl.company_name = data.company_name.strip()

    dl.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(dl)

    log_audit(
        db,
        "dl_registry_updated",
        user_id=current_user.id,
        detail={"dl_id": dl.id, "company_name": dl.company_name, "vat_number": dl.vat_number},
    )

    logger.info("DL aggiornato: id=%d da %s", dl.id, current_user.username)
    return dl


@router.delete("/registry/{dl_id}")
def deactivate_registry(
    dl_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Disattiva un distributore locale (soft delete).

    Blocca se ci sono pratiche REMI pending associate alla P.IVA.
    """
    _require_module(current_user)

    dl = db.query(DlRegistry).filter(DlRegistry.id == dl_id).first()
    if not dl:
        raise HTTPException(status_code=404, detail="Distributore non trovato")

    if not dl.is_active:
        raise HTTPException(status_code=400, detail="Distributore già disattivato")

    # Controlla pratiche pending associate
    pending_count = (
        db.query(RemiPractice)
        .filter(RemiPractice.vat_number == dl.vat_number, RemiPractice.status == "pending")
        .count()
    )
    if pending_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Impossibile disattivare: {pending_count} pratiche in stato pending associate a questa P.IVA",
        )

    dl.is_active = False
    dl.updated_at = datetime.now(timezone.utc)
    db.commit()

    log_audit(
        db,
        "dl_registry_deactivated",
        user_id=current_user.id,
        detail={"dl_id": dl.id, "company_name": dl.company_name, "vat_number": dl.vat_number},
    )

    logger.info("DL disattivato: id=%d da %s", dl.id, current_user.username)
    return {"detail": "Distributore disattivato"}


@router.put("/registry/{dl_id}/reactivate", response_model=DlRegistryOut)
def reactivate_registry(
    dl_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DlRegistryOut:
    """Riattiva un distributore locale precedentemente disattivato."""
    _require_module(current_user)

    dl = db.query(DlRegistry).filter(DlRegistry.id == dl_id).first()
    if not dl:
        raise HTTPException(status_code=404, detail="Distributore non trovato")

    if dl.is_active:
        raise HTTPException(status_code=400, detail="Distributore già attivo")

    dl.is_active = True
    dl.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(dl)

    log_audit(
        db,
        "dl_registry_reactivated",
        user_id=current_user.id,
        detail={"dl_id": dl.id, "company_name": dl.company_name, "vat_number": dl.vat_number},
    )

    logger.info("DL riattivato: id=%d da %s", dl.id, current_user.username)
    return dl


# --- Caricamento pratiche REMI ---


@router.post("/match", response_model=list[RemiMatchResult])
def match_practices(
    rows: list[RemiMatchRow],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RemiMatchResult]:
    """Esegue il match delle P.IVA contro l'anagrafica distributori attivi."""
    _require_module(current_user)

    results: list[RemiMatchResult] = []
    for row in rows:
        vat = row.vat_number.strip()
        dl = (
            db.query(DlRegistry)
            .filter(DlRegistry.vat_number == vat, DlRegistry.is_active.is_(True))
            .first()
        )
        if dl:
            results.append(
                RemiMatchResult(
                    vat_number=vat,
                    remi_code=row.remi_code.strip(),
                    matched=True,
                    company_name=dl.company_name,
                    pec_address=dl.pec_address,
                )
            )
        else:
            results.append(
                RemiMatchResult(
                    vat_number=vat,
                    remi_code=row.remi_code.strip(),
                    matched=False,
                    company_name=None,
                    pec_address=None,
                )
            )

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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RemiConfirmResponse:
    """Conferma e inserisce le pratiche REMI nel database."""
    _require_module(current_user)

    batch_id = str(uuid.uuid4())
    inserted = 0
    skipped = 0

    for row in data.rows:
        # Ignora righe senza company_name (non matched)
        if not row.company_name:
            skipped += 1
            continue

        practice = RemiPractice(
            vat_number=row.vat_number.strip(),
            company_name=row.company_name.strip(),
            pec_address=row.pec_address.strip(),
            remi_code=row.remi_code.strip(),
            effective_date=data.effective_date,
            status="pending",
            batch_id=batch_id,
        )
        db.add(practice)
        inserted += 1

    db.commit()

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
