from footnote.ingest.edgar import EdgarClient

with EdgarClient() as c:
    cik, name = c.cik_for_ticker("AAPL")
    print(cik, name)
    for ref in c.filings(cik, limit=3):
        print(ref.accession_no, ref.fiscal_year, ref.filing_date)
        print(" ", ref.source_url)