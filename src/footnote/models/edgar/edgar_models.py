from dataclasses import dataclass
from datetime import date

from footnote.constants import ARCHIVE_URL


class EdgarError(RuntimeError):
    """Something went wrong talking to EDGAR. Usually safe to skip this ticker."""


class EdgarConfigError(EdgarError):
    """Bad local setup — missing or malformed SEC_USER_AGENT.

    Every subsequent request fails the same way, so callers should let this
    propagate and kill the run rather than skipping to the next ticker.
    """

@dataclass(frozen=True)
class FilingRef:
    cik: str
    company_name: str
    accession_no: str
    form_type: str
    filing_date: date
    period_of_report: date | None
    primary_document: str

    @property
    def fiscal_year(self) -> int | None:
        return self.period_of_report.year if self.period_of_report else None

    @property
    def source_url(self) -> str:
        return ARCHIVE_URL.format(cik_int=int(self.cik), accession=self.accession_no.replace("-", ""), document=self.primary_document)
