"""Runtime settings, read once from the environment (never from files that could hold secrets)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

# The ONLY provider Anvaya may ever use (owner decision D-04: AbstractAI + local LLM only, no cloud).
LOCAL_PROVIDER = "ollama"


@dataclass(frozen=True)
class Settings:
    gateway_url: str = "http://abstractai-gateway:8000"
    username: str = ""
    password: str = ""
    project_id: str = "anvaya"
    primary_model: str = "llama3.1:8b"
    data_dir: Path = Path("/data")
    request_timeout_s: float = 240.0  # a cold local-model load can take minutes (docs/anvaya/LOCAL-LLM.md)

    # Live-facts providers (live_facts.py) - each is optional; an empty api_key/token means that
    # provider silently contributes nothing (never an error shown to the user). See docs/DECISIONS.md
    # "live facts" entry. URLs default to how these are actually reachable from anvaya-api's own
    # networks today (verified live 2026-09-27): HA shares abstractai-shared, Radarr/Sonarr are reached
    # via host.docker.internal (not on anvaya-api's networks), finance-api shares infrastructure.
    ha_url: str = "http://homeassistant:8123"
    ha_token: str = ""
    radarr_url: str = "http://host.docker.internal:7878"
    radarr_api_key: str = ""
    sonarr_url: str = "http://host.docker.internal:8989"
    sonarr_api_key: str = ""
    finance_api_url: str = "http://finance-api:8200"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        e = os.environ if env is None else env
        return cls(
            gateway_url=e.get("ANVAYA_ABSTRACTAI_URL", cls.gateway_url).rstrip("/"),
            username=e.get("ANVAYA_ABSTRACTAI_USER", ""),
            password=e.get("ANVAYA_ABSTRACTAI_PASSWORD", ""),
            project_id=e.get("ANVAYA_PROJECT_ID", cls.project_id),
            primary_model=e.get("ANVAYA_PRIMARY_MODEL", cls.primary_model),
            data_dir=Path(e.get("ANVAYA_DATA_DIR", str(cls.data_dir))),
            request_timeout_s=float(e.get("ANVAYA_REQUEST_TIMEOUT_S", cls.request_timeout_s)),
            ha_url=e.get("ANVAYA_HA_URL", cls.ha_url).rstrip("/"),
            ha_token=e.get("ANVAYA_HA_TOKEN", ""),
            radarr_url=e.get("ANVAYA_RADARR_URL", cls.radarr_url).rstrip("/"),
            radarr_api_key=e.get("ANVAYA_RADARR_API_KEY", ""),
            sonarr_url=e.get("ANVAYA_SONARR_URL", cls.sonarr_url).rstrip("/"),
            sonarr_api_key=e.get("ANVAYA_SONARR_API_KEY", ""),
            finance_api_url=e.get("ANVAYA_FINANCE_API_URL", cls.finance_api_url).rstrip("/"),
        )

    @property
    def has_credentials(self) -> bool:
        return bool(self.username and self.password)
