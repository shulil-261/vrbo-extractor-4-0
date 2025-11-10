import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Allow running without installing as a package
CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.modules.vrbo_scraper import VrboScraper
from src.modules.helpers import ensure_dir, load_json_file, init_logger

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="VRBO Extractor 4.0 — scrape VRBO listings, reviews, prices, and amenities."
    )
    parser.add_argument("--location", type=str, help="City/region/coordinates (e.g. 'Bali' or '-7.288445,112.676966').")
    parser.add_argument("--region-id", type=str, default=None, help="Internal VRBO region ID (optional).")
    parser.add_argument("--check-in", type=str, default=None, help="Check-in date YYYY-MM-DD (optional).")
    parser.add_argument("--check-out", type=str, default=None, help="Check-out date YYYY-MM-DD (optional).")
    parser.add_argument("--limit", type=int, default=25, help="Max listings to fetch.")
    parser.add_argument("--includes", type=str, default="all",
                        help="Comma-separated include flags (reviews,gallery,availability,policies,faq,offers). Use 'all' or any subset.")
    parser.add_argument("--mock", action="store_true", help="Run in mock mode using data/input_examples.json.")
    parser.add_argument("--out", type=str, default=str(ROOT_DIR / "data" / f"vrbo_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"),
                        help="Output JSON file path.")
    parser.add_argument("--config", type=str, default=str(CURRENT_DIR / "config" / "settings.json"),
                        help="Path to settings.json.")
    return parser.parse_args()

def main():
    args = parse_args()

    # Load config & apply CLI overrides
    settings_path = Path(args.config)
    config = load_json_file(settings_path) if settings_path.exists() else {}
    config.setdefault("mock", False)
    config.setdefault("http", {}).setdefault("timeout_seconds", 20)
    config.setdefault("http", {}).setdefault("retries", 2)
    config.setdefault("logging", {}).setdefault("level", "INFO")
    config.setdefault("logging", {}).setdefault("file", str(ROOT_DIR / "data" / "logs" / "scraper.log"))

    # CLI overrides
    if args.mock:
        config["mock"] = True

    logger = init_logger("vrbo_extractor", config["logging"]["level"], config["logging"]["file"])
    logger.info("Starting VRBO Extractor 4.0")

    # Prepare output dir
    out_path = Path(args.out)
    ensure_dir(out_path.parent)

    # Build include flags
    include_flags = set()
    if args.includes.strip().lower() == "all":
        include_flags = {"reviews", "gallery", "availability", "policies", "faq", "offers"}
    else:
        include_flags = {x.strip().lower() for x in args.includes.split(",") if x.strip()}

    scraper = VrboScraper(config=config, logger=logger)

    try:
        results = scraper.run(
            location=args.location,
            region_id=args.region_id,
            check_in=args.check_in,
            check_out=args.check_out,
            limit=args.limit,
            includes=include_flags
        )
    except Exception as e:
        logger.exception("Fatal error during scraping: %s", e)
        print(json.dumps({"ok": False, "error": str(e)}, indent=2))
        sys.exit(1)

    # Export results
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    logger.info("Completed. Wrote %d records to %s", len(results), out_path)
    print(json.dumps({"ok": True, "count": len(results), "output": str(out_path)}, indent=2))

if __name__ == "__main__":
    main()