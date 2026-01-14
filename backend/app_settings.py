from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


_BACKEND_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _BACKEND_DIR.parent
_ENV_CANDIDATES = [str(_REPO_ROOT / ".env"), str(_BACKEND_DIR / ".env")]


class Settings(BaseSettings):
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_bucket: str = "project-documents"
    signed_url_expires_seconds: int = 3600

    model_config = SettingsConfigDict(env_file=_ENV_CANDIDATES, extra="ignore")


settings = Settings()


def _raise_missing(missing: list[str]) -> None:
    if not missing:
        return
    env_hint = " or ".join(_ENV_CANDIDATES)
    raise RuntimeError(f"Missing env: {', '.join(missing)}. Define them in {env_hint}")


def require_supabase_url() -> None:
    _raise_missing(["SUPABASE_URL"] if not settings.supabase_url else [])


def require_supabase_anon() -> None:
    missing: list[str] = []
    if not settings.supabase_url:
        missing.append("SUPABASE_URL")
    if not settings.supabase_anon_key:
        missing.append("SUPABASE_ANON_KEY")
    _raise_missing(missing)


def require_supabase_service() -> None:
    missing: list[str] = []
    if not settings.supabase_url:
        missing.append("SUPABASE_URL")
    if not settings.supabase_service_role_key:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    _raise_missing(missing)
