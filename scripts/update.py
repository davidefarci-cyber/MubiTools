"""Script di aggiornamento Grid da GitHub.

Operazioni:
1. Legge VERSION locale
2. Chiama GitHub API per confrontare con ultimo release/tag
3. Se aggiornamento disponibile: git pull origin main
4. pip install -r requirements.txt --quiet
5. Scrive nuova versione in VERSION
6. Riavvia servizio Windows (net stop / net start)
7. Logga l'operazione

Puo' essere eseguito:
- Da linea di comando: python scripts/update.py
- Dall'admin panel via endpoint POST /admin/update
"""

import json
import logging
import subprocess
import sys
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
VERSION_FILE = BASE_DIR / "VERSION"
REQUIREMENTS = BASE_DIR / "requirements.txt"
SERVICE_NAME = "mubi-tools"


def get_local_version() -> str:
    """Legge la versione corrente dal file VERSION."""
    try:
        return VERSION_FILE.read_text().strip()
    except FileNotFoundError:
        return "0.0.0"


def get_remote_version(github_repo: str) -> tuple[str, str]:
    """Interroga GitHub API per l'ultima release.

    Args:
        github_repo: Formato 'owner/repo'.

    Returns:
        Tupla (versione, url_release).
    """
    url = f"https://api.github.com/repos/{github_repo}/releases/latest"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.v3+json"})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            tag = data.get("tag_name", "").lstrip("v")
            html_url = data.get("html_url", "")
            return tag, html_url
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # Nessuna release, prova con i tag
            return _get_latest_tag(github_repo)
        raise
    except Exception:
        # Fallback: prova con i tag
        return _get_latest_tag(github_repo)


def _get_latest_tag(github_repo: str) -> tuple[str, str]:
    """Fallback: prende l'ultimo tag da GitHub."""
    url = f"https://api.github.com/repos/{github_repo}/tags"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.v3+json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data:
                tag = data[0].get("name", "").lstrip("v")
                return tag, ""
    except Exception:
        pass
    return "", ""


def compare_versions(local: str, remote: str) -> bool:
    """Ritorna True se remote > local (confronto semantico semplice)."""
    if not remote:
        return False

    def to_tuple(v: str) -> tuple[int, ...]:
        parts = []
        for p in v.split("."):
            try:
                parts.append(int(p))
            except ValueError:
                parts.append(0)
        return tuple(parts)

    return to_tuple(remote) > to_tuple(local)


def check_for_updates(github_repo: str) -> dict:
    """Controlla se ci sono aggiornamenti disponibili.

    Returns:
        Dict con local_version, remote_version, update_available, release_url.
    """
    local = get_local_version()
    try:
        remote, release_url = get_remote_version(github_repo)
    except Exception as e:
        logger.error("Errore controllo aggiornamenti: %s", e)
        return {
            "local_version": local,
            "remote_version": None,
            "update_available": False,
            "release_url": "",
            "error": str(e),
        }

    return {
        "local_version": local,
        "remote_version": remote or None,
        "update_available": compare_versions(local, remote),
        "release_url": release_url,
    }


def run_command(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    """Esegue un comando e ritorna (returncode, output)."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or BASE_DIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout + result.stderr
        return result.returncode, output.strip()
    except subprocess.TimeoutExpired:
        return -1, "Timeout (120s)"
    except Exception as e:
        return -1, str(e)


def perform_update(github_repo: str) -> dict:
    """Esegue l'aggiornamento completo.

    Steps:
    1. git pull origin main
    2. pip install -r requirements.txt
    3. Aggiorna VERSION
    4. Riavvia servizio Windows

    Returns:
        Dict con log dettagliato di ogni step.
    """
    log_entries: list[dict] = []
    success = True

    # Step 1: git pull
    logger.info("Update: git pull origin main")
    code, output = run_command(["git", "pull", "origin", "main"], cwd=BASE_DIR)
    log_entries.append({"step": "git_pull", "success": code == 0, "output": output})
    if code != 0:
        success = False
        logger.error("git pull fallito: %s", output)

    # Step 2: pip install
    if success:
        logger.info("Update: pip install -r requirements.txt")
        pip_cmd = [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS), "--quiet"]
        code, output = run_command(pip_cmd)
        log_entries.append({"step": "pip_install", "success": code == 0, "output": output})
        if code != 0:
            success = False
            logger.error("pip install fallito: %s", output)

    # Step 3: Aggiorna VERSION
    if success:
        new_version = get_local_version()  # git pull dovrebbe aver aggiornato il file
        try:
            remote, _ = get_remote_version(github_repo)
            if remote:
                new_version = remote
                VERSION_FILE.write_text(f"{new_version}\n")
        except Exception:
            pass
        log_entries.append({"step": "version_update", "success": True, "output": f"v{new_version}"})
        logger.info("Versione aggiornata a %s", new_version)

    # Step 4: Riavvia servizio (solo su Windows)
    if success and sys.platform == "win32":
        logger.info("Update: riavvio servizio %s", SERVICE_NAME)
        code, output = run_command(["net", "stop", SERVICE_NAME])
        log_entries.append({"step": "service_stop", "success": code == 0, "output": output})

        code, output = run_command(["net", "start", SERVICE_NAME])
        log_entries.append({"step": "service_start", "success": code == 0, "output": output})
        if code != 0:
            success = False
    elif success:
        log_entries.append({
            "step": "service_restart",
            "success": True,
            "output": "Non su Windows — riavvio manuale necessario",
        })

    return {
        "success": success,
        "new_version": get_local_version(),
        "log": log_entries,
    }


# ─── CLI ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

    # Leggi repo da .env o usa default
    env_file = BASE_DIR / ".env"
    github_repo = "davidefarci-cyber/MubiTools"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("GITHUB_REPO="):
                github_repo = line.split("=", 1)[1].strip()

    print("Grid — Aggiornamento")
    print(f"Repository: {github_repo}")
    print(f"Versione locale: {get_local_version()}")
    print()

    info = check_for_updates(github_repo)

    if info.get("error"):
        print(f"Errore: {info['error']}")
        sys.exit(1)

    if not info["update_available"]:
        print(f"Versione remota: {info['remote_version'] or 'non disponibile'}")
        print("Nessun aggiornamento disponibile.")
        sys.exit(0)

    print(f"Nuova versione disponibile: {info['remote_version']}")
    print()

    confirm = input("Procedere con l'aggiornamento? [s/N] ").strip().lower()
    if confirm != "s":
        print("Aggiornamento annullato.")
        sys.exit(0)

    print()
    result = perform_update(github_repo)

    for entry in result["log"]:
        status = "OK" if entry["success"] else "ERRORE"
        print(f"  [{status}] {entry['step']}: {entry['output'][:200]}")

    print()
    if result["success"]:
        print(f"Aggiornamento completato. Nuova versione: {result['new_version']}")
    else:
        print("Aggiornamento fallito. Controllare i log sopra.")
        sys.exit(1)
