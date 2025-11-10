from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Set

from bs4 import BeautifulSoup

def parse_listing_from_html(html: str) -> List[Dict[str, Any]]:
    """
    Very lightweight parser that tries to find listing-like anchors/cards
    on a VRBO search result page. It extracts:
      - property_id (from URL if possible)
      - title (anchor text or aria-label)
      - url (absolute URL)
    NOTE: Real pages are complex; this is a heuristic for demo purposes.
    """
    soup = BeautifulSoup(html, "html.parser")
    results: List[Dict[str, Any]] = []

    # Find anchors that look like property cards
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Heuristic: detail pages often contain "/ha/" paths with alphanumeric ids
        if "/ha/" in href:
            url = href if href.startswith("http") else f"https://www.vrbo.com{href}"
            prop_id = _extract_property_id_from_url(url)
            title = a.get("aria-label") or a.get_text(strip=True) or f"VRBO Listing {prop_id}"
            if prop_id:
                results.append(
                    {
                        "property_id": prop_id,
                        "title": title,
                        "url": url,
                    }
                )

    # Deduplicate by property_id
    unique = {}
    for r in results:
        unique[r["property_id"]] = r
    return list(unique.values())

def _extract_property_id_from_url(url: str) -> Optional[str]:
    # IDs may appear like .../ha/{country}/{id} or .../p{digits}
    m = re.search(r"/ha/[^/]+/([^/?#]+)", url)
    if m:
        return m.group(1)
    m2 = re.search(r"/p(\d+)", url)
    if m2:
        return m2.group(1)
    return None

def enrich_listing_with_details(base: Dict[str, Any], includes: Set[str], html: Optional[str]) -> Dict[str, Any]:
    """
    Enrich a base listing dict (possibly from search) with details.
    If html is provided, we parse extra info. Otherwise, we generate plausible placeholders.
    """
    data = dict(base)
    soup = BeautifulSoup(html or "", "html.parser") if html else None

    # Basic fields (fallbacks)
    data.setdefault("location", _find_text(soup, ["meta[property='og:locale']", "span[itemprop='address']"]) or "Unknown")
    data.setdefault("price", _extract_price(soup) if soup else None)
    data.setdefault("description", _find_text(soup, ["meta[name='description']", "div[id*='description']"]) or "")
    data.setdefault("amenities", _extract_list_items(soup, ["#amenities", ".amenities", "[data-test='amenities']"]) if soup else [])
    data.setdefault("gallery", _extract_images(soup) if soup else [])
    data.setdefault("availability", "Unknown")

    # Optional sections
    if "reviews" in includes:
        data["reviews"] = _extract_reviews(soup) if soup else [
            {"author": "John D.", "rating": 5, "comment": "Amazing stay!"}
        ]
    if "policies" in includes:
        data["policies"] = _find_text(soup, ["#policies", "[data-test='policy-section']"]) or "Policy information not available"
    if "faq" in includes:
        data["faq"] = _extract_faq(soup) if soup else [{"q": "Is WiFi available?", "a": "Yes"}]
    if "offers" in includes:
        data["offers"] = _extract_offers(soup) if soup else [{"label": "Base Rate", "amount": data.get("price")}]
    if "availability" in includes:
        data["availability"] = _extract_availability(soup) if soup else "Available"

    # Nearby points of interest (best-effort)
    data.setdefault("landmarks", _extract_landmarks(soup) if soup else [])

    return data

def _find_text(soup: Optional[BeautifulSoup], selectors: List[str]) -> Optional[str]:
    if not soup:
        return None
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            # meta tag special-case
            if el.name == "meta":
                return el.get("content")
            return el.get_text(strip=True)
    return None

def _extract_price(soup: BeautifulSoup) -> Optional[float]:
    price_candidates = soup.find_all(text=re.compile(r"\$\s?\d[\d,]*"))
    for t in price_candidates:
        m = re.search(r"\$\s?(\d[\d,]*)", t)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                continue
    return None

def _extract_list_items(soup: BeautifulSoup, selectors: List[str]) -> List[str]:
    items: List[str] = []
    for sel in selectors:
        for block in soup.select(sel):
            for li in block.find_all(["li", "span", "div"]):
                text = li.get_text(" ", strip=True)
                if text and len(text) > 2:
                    items.append(text)
    # Deduplicate preserve order
    seen = set()
    uniq = []
    for x in items:
        if x not in seen:
            uniq.append(x)
            seen.add(x)
    return uniq

def _extract_images(soup: BeautifulSoup) -> List[str]:
    urls = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if src and src.startswith("http"):
            urls.append(src)
    # unique
    return list(dict.fromkeys(urls))

def _extract_reviews(soup: Optional[BeautifulSoup]) -> List[Dict[str, Any]]:
    if not soup:
        return []
    reviews = []
    for block in soup.select("[data-test='review'], .review, .review-card"):
        author = block.find(attrs={"data-test": "review-author"}) or block.find(class_=re.compile("author"))
        rating = block.find(attrs={"data-test": "review-rating"}) or block.find(class_=re.compile("rating"))
        text = block.find(attrs={"data-test": "review-text"}) or block.find(class_=re.compile("text"))
        reviews.append(
            {
                "author": (author.get_text(strip=True) if author else "Anonymous"),
                "rating": _extract_first_number(rating.get_text() if rating else None, default=0),
                "comment": (text.get_text(strip=True) if text else ""),
            }
        )
    return reviews

def _extract_offers(soup: Optional[BeautifulSoup]) -> List[Dict[str, Any]]:
    if not soup:
        return []
    offers = []
    for block in soup.select("[data-test='rate'], .rate, .offer"):
        label = block.get_text(" ", strip=True)[:80]
        amt_match = re.search(r"\$\s?(\d[\d,]*)", block.get_text())
        amount = float(amt_match.group(1).replace(",", "")) if amt_match else None
        offers.append({"label": label, "amount": amount})
    return offers

def _extract_availability(soup: Optional[BeautifulSoup]) -> str:
    if not soup:
        return "Unknown"
    # Naive check for availability keywords
    t = soup.get_text(" ", strip=True).lower()
    if "sold out" in t or "not available" in t:
        return "Unavailable"
    if "available" in t:
        return "Available"
    return "Unknown"

def _extract_landmarks(soup: Optional[BeautifulSoup]) -> List[str]:
    if not soup:
        return []
    lm = []
    for block in soup.select("[data-test='poi'], .landmark, .nearby"):
        txt = block.get_text(" ", strip=True)
        if txt and len(txt) > 3:
            lm.append(txt[:120])
    return list(dict.fromkeys(lm))

def _extract_first_number(text: Optional[str], default: float = 0) -> float:
    if not text:
        return default
    m = re.search(r"(\d+(\.\d+)?)", text)
    return float(m.group(1)) if m else default