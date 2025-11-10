from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.modules.parser import parse_listing_from_html, enrich_listing_with_details
from src.modules.helpers import coerce_date, chunked, load_json_file
from src.utils.request_handler import HttpClient
from src.utils.export_manager import normalize_record

class VrboScraper:
    """
    Orchestrates search + detail scraping for VRBO.
    Supports a 'mock' mode that reads from data/input_examples.json for deterministic runs.
    """

    def __init__(self, config: Dict[str, Any], logger):
        self.config = config or {}
        self.logger = logger
        http_cfg = self.config.get("http", {}) or {}
        self.client = HttpClient(
            timeout=http_cfg.get("timeout_seconds", 20),
            retries=http_cfg.get("retries", 2),
            logger=logger,
            headers=self.config.get("headers") or {
                "User-Agent": "Mozilla/5.0 (compatible; VRBO-Extractor/4.0; +https://bitbash.dev)"
            },
            proxy=self.config.get("proxy"),
            rate_limit_per_sec=http_cfg.get("rate_limit_per_sec", 2)
        )
        self.mock = bool(self.config.get("mock"))

    def run(
        self,
        location: Optional[str],
        region_id: Optional[str],
        check_in: Optional[str],
        check_out: Optional[str],
        limit: int,
        includes: Set[str],
    ) -> List[Dict[str, Any]]:
        """
        High-level entry point. Returns list of normalized listing dicts.
        """
        check_in = coerce_date(check_in)
        check_out = coerce_date(check_out)

        if self.mock:
            self.logger.info("Running in MOCK mode using data/input_examples.json")
            return self._run_mock(limit=limit, includes=includes, check_in=check_in, check_out=check_out)

        if not location and not region_id:
            raise ValueError("Provide at least --location or --region-id when not in --mock mode.")

        # NOTE: Real VRBO endpoints are subject to change and may be protected.
        # This example uses a very simple approach: search page -> parse HTML anchors/cards (best-effort).
        # For production, integrate an authenticated/official API or a lawful data source.
        listings = self._search_listings(location=location, region_id=region_id, limit=limit)
        records: List[Dict[str, Any]] = []

        for batch in chunked(listings, 10):
            for lst in batch:
                try:
                    detailed = self._fetch_and_parse_details(lst, includes=includes, check_in=check_in, check_out=check_out)
                    records.append(normalize_record(detailed))
                except Exception as e:
                    self.logger.warning("Failed to enrich listing %s: %s", lst.get("property_id"), e)

        return records

    def _run_mock(self, limit: int, includes: Set[str], check_in: Optional[str], check_out: Optional[str]) -> List[Dict[str, Any]]:
        data_path = Path(__file__).resolve().parents[2] / "data" / "input_examples.json"
        sample = load_json_file(data_path)
        results = []
        for row in sample[: max(1, limit)]:
            row = dict(row)
            if check_in:
                row["check_in"] = check_in
            if check_out:
                row["check_out"] = check_out
            # simulate enrichment
            enriched = enrich_listing_with_details(row, includes=includes, html=None)
            results.append(normalize_record(enriched))
        return results

    def _search_listings(self, location: Optional[str], region_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
        """
        Fetch search results page(s) and parse minimal listing cards.
        This is a best-effort HTML scrape and may not capture all fields.
        """
        query = location or f"region-{region_id}"
        self.logger.info("Searching VRBO for query=%s limit=%d", query, limit)

        # Construct a simple search URL; may not be stable—intended for demonstration.
        # Example base: https://www.vrbo.com/search/keywords:{query}
        url = f"https://www.vrbo.com/search/keywords:{query}"
        html = self.client.get_text(url)
        listings = parse_listing_from_html(html)

        if limit:
            listings = listings[:limit]
        self.logger.info("Parsed %d candidate listings from search", len(listings))
        return listings

    def _fetch_and_parse_details(
        self,
        listing: Dict[str, Any],
        includes: Set[str],
        check_in: Optional[str],
        check_out: Optional[str],
    ) -> Dict[str, Any]:
        """
        Open the property detail page and extract more complete data.
        """
        prop_url = listing.get("url")
        if not prop_url:
            return listing

        html = self.client.get_text(prop_url)
        enriched = enrich_listing_with_details(
            {**listing, "check_in": check_in, "check_out": check_out},
            includes=includes,
            html=html,
        )
        return enriched