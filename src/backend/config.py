"""Settings for the diagram API.

Database settings come from the MYSQL_* variables, or the module's .env file (the same values the
CLI uses). Web settings come from WEB_* variables (or .env) and default to a local-only server:

  WEB_HOST          address to listen on (default 127.0.0.1; 0.0.0.0 to serve other machines)
  WEB_PORT          port (default 8765)
  WEB_PUBLIC_URL    address shown to users (default http://<WEB_HOST>:<WEB_PORT>)
  WEB_CORS_ORIGINS  comma-separated extra origins allowed to call the API (e.g. a frontend
                    hosted elsewhere); the bundled frontend is same-origin and needs none
"""

import os
from dataclasses import dataclass
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIST = MODULE_DIR / "src" / "frontend" / "dist"


def _env_file() -> dict[str, str]:
    values: dict[str, str] = {}
    path = MODULE_DIR / ".env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator:
                values[key.strip()] = value.strip().strip("\"'")
    return values


def _setting(file_values: dict[str, str], key: str, default: str) -> str:
    return os.environ.get(key, file_values.get(key, default))


@dataclass(frozen=True)
class Settings:
    db_host: str
    db_port: int
    db_user: str
    db_password: str
    db_name: str
    web_host: str
    web_port: int
    public_url: str
    cors_origins: tuple[str, ...]


def load_settings() -> Settings:
    values = _env_file()
    host = _setting(values, "WEB_HOST", "127.0.0.1")
    port = int(_setting(values, "WEB_PORT", "8765"))
    shown_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    origins = _setting(values, "WEB_CORS_ORIGINS", "")
    return Settings(
        db_host=_setting(values, "MYSQL_HOST", "localhost"),
        db_port=int(_setting(values, "MYSQL_PORT", "3306")),
        db_user=_setting(values, "MYSQL_USER", "stock_app"),
        db_password=_setting(values, "MYSQL_PASSWORD", ""),
        db_name=_setting(values, "MYSQL_DATABASE", "stock_market"),
        web_host=host,
        web_port=port,
        public_url=_setting(values, "WEB_PUBLIC_URL", f"http://{shown_host}:{port}").rstrip("/"),
        cors_origins=tuple(origin.strip() for origin in origins.split(",") if origin.strip()),
    )
