from __future__ import annotations

import time
from typing import Optional

import requests

class HttpClient:
    """
    Minimal HTTP client with retries, backoff, timeout, and optional proxy.
    """

    def __init__(
        self,
        timeout: int = 20,
        retries: int = 2,
        logger=None,
        headers: Optional[dict] = None,
        proxy: Optional[str] = None,
        rate_limit_per_sec: Optional[float] = None,
    ):
        self.timeout = timeout
        self.retries = retries
        self.logger = logger
        self.headers = headers or {}
        self.proxies = {"http": proxy, "https": proxy} if proxy else None
        self.rate_limit_per_sec = rate_limit_per_sec or 0.0
        self._last_request_ts = 0.0

    def _respect_rate_limit(self):
        if self.rate_limit_per_sec <= 0:
            return
        min_interval = 1.0 / float(self.rate_limit_per_sec)
        now = time.time()
        elapsed = now - self._last_request_ts
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_ts = time.time()

    def get_text(self, url: str) -> str:
        last_err = None
        for attempt in range(self.retries + 1):
            try:
                self._respect_rate_limit()
                resp = requests.get(url, headers=self.headers, timeout=self.timeout, proxies=self.proxies)
                if 200 <= resp.status_code < 300:
                    return resp.text
                if self.logger:
                    self.logger.warning("GET %s -> %s", url, resp.status_code)
                last_err = Exception(f"HTTP {resp.status_code}")
            except Exception as e:
                last_err = e
                if self.logger:
                    self.logger.warning("GET error (attempt %d/%d) %s: %s", attempt + 1, self.retries + 1, url, e)
            # backoff
            time.sleep(min(2 ** attempt, 5))
        raise last_err or Exception("GET failed with unknown error")