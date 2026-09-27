"""Where Home Knowledge comes from, and what it must never come from.

Deliberately NOT a raw filesystem crawl of every drive: this project's drives hold terabytes of media, node_modules,
build artifacts and other people's unrelated code (see HomeLab documentation/anvaya/ARCHITECTURE.md). "Full
visibility" here means every authoritative, already-catalogued source: HomeLab's own documentation, the live
container/page catalog (homelab-hub), the Ecosystem Atlas, and the scheduled-task inventory - the same sources a
human would open to answer "what do we have and where is it".
"""

from __future__ import annotations

import os
from pathlib import Path

# Path segments that must NEVER be read for ingestion, anywhere under DOCS_DIR. Matched case-insensitively against
# the relative path. This is a second, independent layer on top of "we only mount documentation/, not compose/.env
# or config/docs/htpasswd at all" (see compose/infrastructure/compose.yml - only documentation/ is bind-mounted).
DENY_SUBSTRINGS = ("creds.html", "htpasswd", "secrets.yaml", ".env", ".storage", "vault.yml", "sca-token")

# File types worth ingesting as text. HTML is stripped of tags first (see ingest.py::html_to_text).
TEXT_SUFFIXES = {".md", ".html"}

DOCS_DIR = Path(os.environ.get("HOMELAB_DOCS_DIR", "/sources/homelab-docs"))
ATLAS_GRAPH_PATH = Path(os.environ.get("ATLAS_GRAPH_PATH", "/sources/atlas-graph.json"))
HUB_CATALOG_URL = os.environ.get("HUB_CATALOG_URL", "http://homelab-hub:8114/api/catalog")
TASKS_URL = os.environ.get("TASKS_URL", "http://host.docker.internal:8112/api/tasks")


def is_denied(rel_path: str) -> bool:
    low = rel_path.lower()
    return any(d in low for d in DENY_SUBSTRINGS)
