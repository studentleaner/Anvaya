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
    primary_model: str = "qwen2.5:7b"
    data_dir: Path = Path("/data")
    request_timeout_s: float = 240.0  # a cold local-model load can take minutes (docs/anvaya/LOCAL-LLM.md)

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
        )

    @property
    def has_credentials(self) -> bool:
        return bool(self.username and self.password)
