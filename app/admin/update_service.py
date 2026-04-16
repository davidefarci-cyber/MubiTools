"""Servizio aggiornamento: gestione branch, check e apply updates via GitPython."""

import logging
import subprocess
import sys
import threading
from pathlib import Path

import git

from app.config import settings

logger = logging.getLogger(__name__)

REPO_PATH = Path(__file__).resolve().parent.parent.parent
SERVICE_NAME = "mubi-tools"
REQUIREMENTS = REPO_PATH / "requirements.txt"


def _get_repo() -> git.Repo:
    """Apre il repository git locale."""
    return git.Repo(REPO_PATH)


def get_current_branch() -> str:
    """Ritorna il nome del branch corrente."""
    repo = _get_repo()
    try:
        return repo.active_branch.name
    except TypeError:
        return f"detached:{repo.head.commit.hexsha[:8]}"


def get_current_commit() -> str:
    """Ritorna lo SHA corto di HEAD."""
    repo = _get_repo()
    return repo.head.commit.hexsha[:8]


def list_remote_branches() -> list[dict]:
    """Elenca i branch remoti da origin via git ls-remote.

    Ritorna lista di {"name": "main", "sha": "abc1234..."}.
    """
    repo = _get_repo()
    remote_refs = repo.git.ls_remote("--heads", "origin")
    branches = []
    for line in remote_refs.strip().splitlines():
        if not line:
            continue
        sha, ref = line.split("\t")
        branch_name = ref.replace("refs/heads/", "")
        branches.append({"name": branch_name, "sha": sha[:8]})
    return branches


def check_for_updates(branch: str = "main") -> dict:
    """Confronta HEAD locale con il branch remoto.

    Ritorna info su aggiornamenti disponibili, commits behind/ahead.
    """
    repo = _get_repo()
    repo.remotes.origin.fetch()

    try:
        current_branch = repo.active_branch.name
    except TypeError:
        current_branch = f"detached:{repo.head.commit.hexsha[:8]}"

    local_sha = repo.head.commit.hexsha
    remote_ref = f"origin/{branch}"

    try:
        remote_sha = repo.commit(remote_ref).hexsha
    except git.exc.BadName:
        raise ValueError(f"Branch '{branch}' non trovato su origin")

    behind = list(repo.iter_commits(f"HEAD..{remote_ref}"))
    ahead = list(repo.iter_commits(f"{remote_ref}..HEAD"))

    return {
        "branch": branch,
        "current_branch": current_branch,
        "local_sha": local_sha[:8],
        "remote_sha": remote_sha[:8],
        "update_available": len(behind) > 0,
        "commits_behind": len(behind),
        "commits_ahead": len(ahead),
        "version": settings.version,
    }


def _run_command(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    """Esegue un sottoprocesso e ritorna (returncode, output)."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or REPO_PATH,
            capture_output=True,
            text=True,
            timeout=180,
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode, output
    except subprocess.TimeoutExpired:
        return -1, "Timeout (180s)"
    except Exception as exc:
        return -1, str(exc)


def _restart_service_async(delay: float = 4.0) -> None:
    """Riavvia il servizio Windows/Linux in background dopo aver restituito la risposta HTTP."""
    def _do_restart() -> None:
        import time
        time.sleep(delay)
        if sys.platform == "win32":
            _run_command(["net", "stop", SERVICE_NAME])
            _run_command(["net", "start", SERVICE_NAME])
        else:
            _run_command(["systemctl", "restart", SERVICE_NAME])

    threading.Thread(target=_do_restart, daemon=True).start()


def apply_update(branch: str = "main") -> dict:
    """Fetch, checkout del branch target, pull, pip install e riavvio servizio.

    Equivalente a reinstall.bat:
    1. git pull (con checkout al branch selezionato)
    2. pip install -r requirements.txt
    3. riavvio servizio (asincrono, dopo la risposta HTTP)

    Ritorna dettagli e log di ogni step.
    """
    repo = _get_repo()

    if repo.is_dirty():
        raise ValueError(
            "Working tree con modifiche non committate. "
            "Committare o scartare le modifiche prima di aggiornare."
        )

    try:
        old_branch = repo.active_branch.name
    except TypeError:
        old_branch = f"detached:{repo.head.commit.hexsha[:8]}"

    old_sha = repo.head.commit.hexsha[:8]
    log_entries: list[dict] = []

    # Step 1: fetch + checkout + pull
    repo.remotes.origin.fetch()

    local_branches = [ref.name for ref in repo.branches]
    if branch in local_branches:
        repo.git.checkout(branch)
    else:
        repo.git.checkout("-b", branch, f"origin/{branch}")

    try:
        repo.remotes.origin.pull()
        log_entries.append({"step": "git_pull", "success": True, "output": f"Aggiornato a origin/{branch}"})
    except Exception as exc:
        log_entries.append({"step": "git_pull", "success": False, "output": str(exc)})
        raise ValueError(f"git pull fallito: {exc}") from exc

    new_sha = repo.head.commit.hexsha[:8]

    # Step 2: pip install -r requirements.txt
    pip_cmd = [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS), "--quiet"]
    code, output = _run_command(pip_cmd)
    log_entries.append({"step": "pip_install", "success": code == 0, "output": output or "OK"})
    if code != 0:
        logger.warning("pip install warning: %s", output)

    # Step 3: lettura nuova versione dal file aggiornato
    new_version = (
        settings.VERSION_FILE.read_text().strip()
        if settings.VERSION_FILE.exists()
        else settings.version
    )

    # Step 4: riavvio servizio in background (la risposta HTTP viene inviata prima)
    _restart_service_async(delay=4.0)
    log_entries.append({
        "step": "service_restart",
        "success": True,
        "output": "Riavvio servizio avviato — l'applicazione sarà disponibile tra ~15 secondi",
    })

    return {
        "success": True,
        "old_branch": old_branch,
        "new_branch": branch,
        "old_sha": old_sha,
        "new_sha": new_sha,
        "old_version": settings.version,
        "new_version": new_version,
        "restart_required": old_sha != new_sha,
        "log": log_entries,
    }
