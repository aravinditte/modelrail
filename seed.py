"""Convenience entrypoint to seed demo data from repository root."""

from __future__ import annotations

import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent
gateway_dir = repo_root / "apps" / "gateway"
if str(gateway_dir) not in sys.path:
    sys.path.insert(0, str(gateway_dir))

from app.seed import main  # noqa: E402

if __name__ == "__main__":
    main()
