from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)

from social_engine.marketing_team import run_marketing_team


def main() -> None:
    site_url = os.environ.get("BRAND_SITE_URL", "https://www.infenergypower.com")
    products_dir = os.environ.get("MARKETING_PRODUCTS_DIR", os.path.join(ROOT, "data", "products"))
    output_dir = os.environ.get("MARKETING_OUTPUT_DIR", os.path.join(ROOT, "data", "marketing"))

    strategy = run_marketing_team(site_url=site_url, products_dir=products_dir, output_dir=output_dir)

    print("Marketing team run complete.")
    print(json.dumps(strategy.get("artifacts", {}), indent=2))


if __name__ == "__main__":
    main()
