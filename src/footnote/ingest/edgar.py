"""
Discover 10-k filings on SEC Edgar.

Notes:
1. Every request needs a User-Agent with real contect
2. Max 10 requests/second
"""
import os
import time
from datetime import date
from functools import cached_property
from typing import Self

import httpx
from dotenv import load_dotenv

from footnote.constants import DEFAULT_RATE_LIMIT, SUBMISSIONS_URL, TICKERS_URL
from footnote.models.edgar.edgar_models import EdgarConfigError, EdgarError, FilingRef

load_dotenv()

def _require_user_agent() -> str:
    ua = os.getenv("SEC_USER_AGENT", "").strip()
    if not ua:
        raise EdgarConfigError(
            "SEC_USER_AGENT is not set — EDGAR returns 403 without a contact address. "
            'Add to .env:  SEC_USER_AGENT="Your Name you@example.com"'
        )

    return ua

class EdgarClient:
    def __init__(self, user_agent: str | None = None, requests_per_second: float = DEFAULT_RATE_LIMIT, timeout: float = 30.0):
        self._min_interval = 1.0 / requests_per_second
        self._last_request = 0.0
        self._client = httpx.Client(
            headers={"User-Agent": user_agent or _require_user_agent()},
            timeout=timeout,
            follow_redirects=True,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self._client.close()

    def _get(self, url: str) -> httpx.Response:
        # Edgar blocks IPs for sustained bursts instead of 429ing. Space out requests
        wait = self._min_interval - (time.monotonic() - self._last_request)

        if wait > 0:
            time.sleep(wait)

        self._last_request = time.monotonic()

        response = self._client.get(url)
        if response.status_code == 403:
            raise EdgarConfigError(
                f"403 from {url} — SEC_USER_AGENT is missing or malformed. "
                "Every request will fail until it's fixed."
            )

        response.raise_for_status()
        return response

    @cached_property
    def _ticker_map(self) -> dict[str, tuple[str, str]]:
        payload = self._get(TICKERS_URL).json()
        return {
            entry["ticker"].upper(): (f"{entry['cik_str']:010d}", entry["title"])
            for entry in payload.values()
        }

    def cik_for_ticker(self, ticker: str) -> tuple[str, str]:
        try:
            return self._ticker_map[ticker.upper()]
        except KeyError:
            raise EdgarError(f"No CIK on EDGAR for ticker {ticker!r}") from None

    def filings(self, cik: str, form_type: str = "10-K", limit: int = 1) -> list[FilingRef]:
        payload = self._get(SUBMISSIONS_URL.format(cik=cik)).json()
        company_name = payload.get("name", "")
        recent = payload["filings"]["recent"]

        refs: list[FilingRef] = []

        for i, form in enumerate(recent["form"]):
            if form != form_type: continue # exclude 10-K/A and 10-K/KT for now
            period = recent["reportDate"][i]
            refs.append(
                FilingRef(
                    cik=cik,
                    company_name=company_name,
                    accession_no=recent["accessionNumber"][i],
                    form_type=form,
                    filing_date=date.fromisoformat(recent["filingDate"][i]),
                    period_of_report=date.fromisoformat(period) if period else None,
                    primary_document=recent["primaryDocument"][i],
                )
            )

            if len(refs) == limit:
                break

        if not refs:
            raise EdgarError(
                f"No {form_type} filings for CIK {cik} in recent history. If this "
                "company reorganized, its ticker may now point to a successor entity "
                "that has no filing history of its own."
            )
        # `filings.recent` holds the last 1,000 filings or one year, whichever is more.
        # Heavy filers blow through that in months, leaving older 10-Ks in the
        # paginated archives under payload["filings"]["files"], which we don't read yet.
        if len(refs) < limit and payload["filings"].get("files"):
            raise EdgarError(
                f"Only {len(refs)} of {limit} requested {form_type} filings for CIK "
                f"{cik} are in recent history; older ones live in paginated archives "
                "(not yet supported)."
            )
        return refs