from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.property_reso_baseline import validate_reso_property_baseline
from core.property_source_map import validate_source_map
from core.services.reso_property_baseline_loader import ResoPropertyBaselineLoader
from db import init_db


def main() -> int:
    if not init_db():
        print("Database initialization failed.", file=sys.stderr)
        return 1

    validate_source_map()
    validate_reso_property_baseline()

    result = ResoPropertyBaselineLoader().load()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
