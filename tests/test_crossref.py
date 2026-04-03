from __future__ import annotations

import pathlib
import sys
import unittest
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.crossref import CrossrefClient
from sciencemonitor.models import SourceConfig


class FakeHTTPClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.last_params: dict | None = None

    def get_json(self, url: str, params: dict | None = None) -> dict:
        self.last_params = params
        return self.payload


class CrossrefClientTest(unittest.TestCase):
    def test_filters_by_exact_container_title_alias(self) -> None:
        source = SourceConfig(
            id="jgr_space_physics",
            journal_title="JGR: Space Physics",
            aliases=["JGR: Space Physics", "Journal of Geophysical Research: Space Physics"],
            tier="core",
            mode="full",
            priority=1,
            description="",
        )
        payload = {
            "message": {
                "items": [
                    {
                        "DOI": "10.1000/keep",
                        "URL": "https://example.org/keep",
                        "title": ["Storm-time Electrodynamics"],
                        "container-title": ["Journal of Geophysical Research: Space Physics"],
                        "author": [{"given": "A", "family": "Author"}],
                        "issued": {"date-parts": [[2026, 3, 14]]},
                        "abstract": "<jats:p>Test abstract.</jats:p>",
                    },
                    {
                        "DOI": "10.1000/drop",
                        "URL": "https://example.org/drop",
                        "title": ["Unrelated"],
                        "container-title": ["Journal of Geophysical Research: Oceans"],
                        "author": [],
                        "issued": {"date-parts": [[2026, 3, 14]]},
                        "abstract": "",
                    },
                ]
            }
        }
        client = CrossrefClient(http_client=FakeHTTPClient(payload))
        papers = client.fetch_recent_works(source, date(2026, 3, 13), date(2026, 3, 14))

        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0].doi, "10.1000/keep")
        self.assertEqual(papers[0].published_date.isoformat(), "2026-03-14")

    def test_uses_issn_and_online_date_filter_when_configured(self) -> None:
        http = FakeHTTPClient({"message": {"items": []}})
        source = SourceConfig(
            id="jgr_space_physics",
            journal_title="JGR: Space Physics",
            aliases=["JGR: Space Physics", "Journal of Geophysical Research: Space Physics"],
            tier="core",
            mode="full",
            priority=1,
            description="",
            issn="2169-9402",
            crossref_date_field="online",
        )
        client = CrossrefClient(http_client=http)
        client.fetch_recent_works(source, date(2026, 3, 13), date(2026, 3, 14), max_rows=15)

        assert http.last_params is not None
        self.assertEqual(http.last_params["filter"], "issn:2169-9402,from-online-pub-date:2026-03-13,until-online-pub-date:2026-03-14")
        self.assertNotIn("query.container-title", http.last_params)
        self.assertEqual(http.last_params["rows"], "15")

    def test_lookup_work_by_doi_prefers_primary_resource_url_and_links(self) -> None:
        payload = {
            "message": {
                "DOI": "10.1000/example",
                "URL": "https://doi.org/10.1000/example",
                "resource": {"primary": {"URL": "https://publisher.example.org/article"}},
                "link": [{"URL": "https://publisher.example.org/article.pdf"}],
                "title": ["Storm-time Electrodynamics"],
                "container-title": ["Journal of Geophysical Research: Space Physics"],
                "author": [{"given": "A", "family": "Author"}],
                "issued": {"date-parts": [[2026, 3, 14]]},
                "abstract": "<jats:p>Test abstract.</jats:p>",
            }
        }
        client = CrossrefClient(http_client=FakeHTTPClient(payload))

        result = client.lookup_work_by_doi("10.1000/example")

        self.assertIsNotNone(result)
        self.assertEqual(result["url"], "https://publisher.example.org/article")
        self.assertEqual(result["pdf_urls"], ["https://publisher.example.org/article.pdf"])
        self.assertEqual(result["published_date"], "2026-03-14")
        self.assertEqual(result["abstract"], "Test abstract.")


if __name__ == "__main__":
    unittest.main()
