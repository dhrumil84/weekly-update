"""Zero-dependency .env loader. Reads KEY=VALUE lines into os.environ.

Existing env vars take precedence (so CI secrets aren't overridden).
"""
from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: str | Path = ".env") -> int:
    """Load a .env file into os.environ. Returns count of vars loaded."""
    p = Path(path)
    if not p.exists():
        return 0
    n = 0
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        # Strip surrounding quotes if present, but otherwise keep value as-is
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or \
           (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        # Don't override existing env vars
        if key and key not in os.environ:
            os.environ[key] = value
            n += 1
    return n
