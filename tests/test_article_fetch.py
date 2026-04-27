from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.article_fetch import (
    _compact_pdf_text_for_summary,
    build_candidate_article_urls,
    fetch_article_page_snapshot,
    load_article_source_cache,
    resolve_summary_source_material,
)


class FakeHTTPClient:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages

    def get_text(self, url: str) -> str:
        if url not in self.pages:
            raise RuntimeError("missing page")
        return self.pages[url]


class FakeCrossrefClient:
    def __init__(self, by_doi: dict | None = None, by_title: dict | None = None) -> None:
        self.by_doi = by_doi
        self.by_title = by_title

    def lookup_work_by_doi(self, doi: str) -> dict | None:
        return self.by_doi

    def lookup_work_by_title(self, title: str) -> dict | None:
        return self.by_title


class ArticleFetchTest(unittest.TestCase):
    def test_build_candidate_article_urls_deduplicates_and_prefers_primary_url(self) -> None:
        urls = build_candidate_article_urls(
            "10.1029/2023JA032141",
            "https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2023JA032141",
            extra_urls=[
                "https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2023JA032141",
                "https://example.org/alt",
            ],
        )
        self.assertEqual(
            urls,
            [
                "https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2023JA032141",
                "https://example.org/alt",
                "https://doi.org/10.1029/2023JA032141",
            ],
        )

    def test_fetch_article_page_snapshot_detects_html_full_text(self) -> None:
        html = """
        <html>
          <head>
            <title>Example Full Text</title>
            <meta name="citation_title" content="Example Full Text" />
            <meta name="citation_abstract" content="Short abstract." />
            <meta name="citation_pdf_url" content="/paper.pdf" />
          </head>
          <body>
            <h1>Introduction</h1>
            <p>Methods Results Discussion Conclusion References</p>
            <p>{body}</p>
          </body>
        </html>
        """.format(body="storm coupling " * 700)
        snapshot = fetch_article_page_snapshot(FakeHTTPClient({"https://example.org/paper": html}), ["https://example.org/paper"])
        self.assertTrue(snapshot.is_full_text)
        self.assertEqual(snapshot.page_title, "Example Full Text")
        self.assertTrue(snapshot.pdf_urls)
        self.assertIn("Introduction", snapshot.full_text)

    def test_resolve_summary_source_material_falls_back_to_crossref_abstract(self) -> None:
        material = resolve_summary_source_material(
            doi="10.1000/example",
            url="https://example.org/blocked",
            title="Example Paper",
            journal="JGR: Space Physics",
            abstract="",
            authors=[],
            published_date="2026-03-14",
            http=FakeHTTPClient({}),
            crossref=FakeCrossrefClient(
                by_doi={
                    "doi": "10.1000/example",
                    "title": "Example Paper",
                    "journal": "JGR: Space Physics",
                    "url": "https://example.org/landing",
                    "authors": ["A Author"],
                    "published_date": "2026-03-14",
                    "abstract": "This paper studies thermosphere density during a storm.",
                    "pdf_urls": [],
                }
            ),
        )
        self.assertEqual(material.source_kind, "crossref_abstract")
        self.assertTrue(material.abstract_only)
        self.assertEqual(material.title, "Example Paper")
        self.assertIn("thermosphere density", material.summary_text)

    def test_resolve_summary_source_material_prefers_local_pdf_full_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = pathlib.Path(tmpdir)
            (project_root / "data").mkdir(parents=True, exist_ok=True)
            with mock.patch(
                "sciencemonitor.article_fetch._extract_local_pdf_text",
                return_value=("Full text from local PDF with methods and results.", "Summary packet from local PDF."),
            ):
                material = resolve_summary_source_material(
                    doi="10.1000/example",
                    url="https://example.org/blocked",
                    title="Example Paper",
                    journal="JGR: Space Physics",
                    abstract="Short abstract",
                    authors=[],
                    published_date="2026-03-14",
                    http=FakeHTTPClient({}),
                    crossref=FakeCrossrefClient(
                        by_doi={
                            "doi": "10.1000/example",
                            "title": "Example Paper",
                            "journal": "JGR: Space Physics",
                            "url": "https://example.org/landing",
                            "authors": ["A Author"],
                            "published_date": "2026-03-14",
                            "abstract": "Crossref abstract.",
                            "pdf_urls": [],
                        }
                    ),
                    local_pdf_path=pathlib.Path("/tmp/example.pdf"),
                    project_root=project_root,
                )
            self.assertEqual(material.source_kind, "local_pdf_full_text")
            self.assertFalse(material.abstract_only)
            self.assertIn("Crossref abstract.", material.summary_text)
            self.assertEqual(material.scientific_text, "Full text from local PDF with methods and results.")
            self.assertTrue(material.cache_path)
            cached = load_article_source_cache(project_root, doi="10.1000/example", title="Example Paper")
            self.assertIsNotNone(cached)
            self.assertEqual(cached["scientific_text"], "Full text from local PDF with methods and results.")

    def test_resolve_summary_source_material_ignores_redirect_page_title(self) -> None:
        html = """
        <html>
          <head>
            <title>Redirecting</title>
          </head>
          <body></body>
        </html>
        """
        material = resolve_summary_source_material(
            doi="10.1000/example",
            url="https://doi.org/10.1000/example",
            title="Stored Title",
            journal="JGR: Space Physics",
            abstract="",
            authors=[],
            published_date="2026-03-14",
            http=FakeHTTPClient({"https://doi.org/10.1000/example": html}),
            crossref=FakeCrossrefClient(
                by_doi={
                    "doi": "10.1000/example",
                    "title": "Crossref Title",
                    "journal": "JGR: Space Physics",
                    "url": "https://example.org/landing",
                    "authors": ["A Author"],
                    "published_date": "2026-03-14",
                    "abstract": "",
                    "pdf_urls": [],
                }
            ),
        )
        self.assertEqual(material.title, "Crossref Title")

    def test_compact_pdf_text_for_summary_prefers_abstract_and_plain_language_summary(self) -> None:
        raw_text = """
        Cover page and author block.
        Abstract This paper studies thermospheric mass density during storms and compares ResNet with a shallow network.
        Plain Language Summary The model keeps generalization while better extracting multi-scale features from observations.
        1. Introduction Many additional paragraphs follow here.
        2. Data and Methods More details.
        """
        compact = _compact_pdf_text_for_summary(raw_text, max_chars=500)
        self.assertIn("Abstract:", compact)
        self.assertIn("Plain Language Summary:", compact)
        self.assertNotIn("Cover page and author block", compact)
        self.assertNotIn("Author Contributions", compact)

    def test_compact_pdf_text_for_summary_keeps_results_and_conclusions_sections(self) -> None:
        raw_text = """
        RESEARCH ARTICLE
        Abstract This paper studies thermospheric density changes during storms.
        Plain Language Summary The deep network extracts multi-scale density features.
        1. Introduction
        Background paragraph.
        2. Data Description
        CHAMP and GRACE are used, with HASDM and NRLMSISE-00 for comparison.
        3. Deep Learning Model
        A residual network is trained with solar and geomagnetic indices.
        4. Estimation Results and Discussions
        The ResNet reproduces density variability better than the shallow network and captures storm-time responses.
        5. Conclusions
        The deep model improves feature extraction while keeping generalization.
        References
        """
        compact = _compact_pdf_text_for_summary(raw_text, max_chars=2000)
        self.assertIn("Methods/Data:", compact)
        self.assertIn("Results:", compact)
        self.assertIn("Discussion/Conclusion:", compact)
        self.assertIn("Estimation Results and Discussions", compact)
        self.assertIn("The deep model improves feature extraction while keeping generalization.", compact)

    def test_compact_pdf_text_for_summary_selects_late_high_value_result_sentence(self) -> None:
        filler = "General discussion without quantitative findings. " * 80
        raw_text = f"""
        RESEARCH ARTICLE
        Abstract This paper studies thermospheric density during storms.
        1. Introduction
        Background paragraph.
        2. Data and Methods
        CHAMP and GRACE observations are used to train a ResNet model.
        4. Estimation Results and Discussions
        {filler}
        During the April 2023 geomagnetic storm, the ResNet reduced RMSE by 22% relative to the shallow network and better reproduced the storm-time density response.
        5. Conclusions
        The network preserves generalization while improving multi-scale feature extraction.
        References
        """
        compact = _compact_pdf_text_for_summary(raw_text, max_chars=2400)
        self.assertIn("reduced RMSE by 22%", compact)
        self.assertIn("storm-time density response", compact)


if __name__ == "__main__":
    unittest.main()
