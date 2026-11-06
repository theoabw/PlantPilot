"""Write the OpenAPI schema the API serves to docs/openapi.json.

    make openapi

The schema comes from `app.openapi()`, so it cannot describe a different API
than the one that runs. `app/server/tests/test_openapi.py` compares the
committed file with the app, so it is either current or the suite is red.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "server" / "src"))

from plantpilot.main import app  # noqa: E402

OUT = ROOT / "docs" / "openapi.json"


def main() -> int:
    OUT.write_text(
        json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
