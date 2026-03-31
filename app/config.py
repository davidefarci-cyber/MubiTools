"""Configurazione centrale dell'applicazione MUBI Tools."""

import secrets
from pathlib import Path

from pydantic_settings import BaseSettings


BASE_DIR: Path = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Impostazioni dell'applicazione caricate da .env."""

    # Sicurezza
    SECRET_KEY: str = secrets.token_hex(32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_HOURS: int = 8

    # Admin iniziale
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "changeme"

    # Database
    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'database' / 'app.db'}"

    # GitHub
    GITHUB_REPO: str = "davidefarci-cyber/MubiTools"

    # Server
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # Upload
    MAX_UPLOAD_MB: int = 50

    # Paths
    UPLOAD_DIR: Path = BASE_DIR / "data" / "uploads"
    LOG_DIR: Path = BASE_DIR / "logs"
    VERSION_FILE: Path = BASE_DIR / "VERSION"

    model_config = {"env_file": BASE_DIR / ".env", "env_file_encoding": "utf-8"}

    @property
    def version(self) -> str:
        """Legge la versione corrente dal file VERSION."""
        try:
            return self.VERSION_FILE.read_text().strip()
        except FileNotFoundError:
            return "0.0.0"


settings = Settings()
