from __future__ import annotations

import pathlib
import sys
import unittest
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.models import Paper, SourceConfig, TopicProfile
from sciencemonitor.topics import TopicClassifier


class TopicClassifierTest(unittest.TestCase):
    def test_classifies_multiple_topics(self) -> None:
        source = SourceConfig(
            id="jgr_space_physics",
            journal_title="JGR: Space Physics",
            aliases=["JGR: Space Physics", "Journal of Geophysical Research: Space Physics"],
            tier="core",
            mode="full",
            priority=1,
            description="",
        )
        topics = [
            TopicProfile(id="ionosphere", label="电离层", keywords=["ionosphere", "tec"]),
            TopicProfile(id="thermosphere", label="热层", keywords=["thermosphere"]),
        ]
        paper = Paper(
            fingerprint="x",
            source_id=source.id,
            source_name=source.journal_title,
            journal_title=source.journal_title,
            title="Ionosphere and Thermosphere Response During a Storm",
            abstract="We analyze TEC changes and thermosphere density variations.",
            published_date=date(2026, 3, 14),
            doi="10.1234/example",
            url="https://example.org",
        )
        classifier = TopicClassifier(topics)
        result = classifier.classify(paper, source)

        self.assertEqual(result.topics, ["ionosphere", "thermosphere"])
        self.assertTrue(result.relevance_score > 5.0)

    def test_short_acronym_uses_word_boundaries(self) -> None:
        source = SourceConfig(
            id="grl",
            journal_title="Geophysical Research Letters",
            aliases=["Geophysical Research Letters"],
            tier="related",
            mode="topic_filter",
            priority=1,
            description="",
        )
        topics = [TopicProfile(id="ionosphere", label="电离层", keywords=["tec"])]
        paper = Paper(
            fingerprint="y",
            source_id=source.id,
            source_name=source.journal_title,
            journal_title=source.journal_title,
            title="A detection method for wind extremes",
            abstract="This detection framework focuses on surface climate extremes.",
            published_date=date(2026, 3, 14),
            doi="10.1234/example-2",
            url="https://example.org/2",
        )
        classifier = TopicClassifier(topics)
        result = classifier.classify(paper, source)

        self.assertEqual(result.topics, [])

    def test_multiword_keyword_uses_phrase_boundaries(self) -> None:
        source = SourceConfig(
            id="eps",
            journal_title="Earth, Planets and Space",
            aliases=["Earth, Planets and Space"],
            tier="related",
            mode="topic_filter",
            priority=2,
            description="",
        )
        topics = [TopicProfile(id="ionosphere", label="电离层", keywords=["e region"])]
        paper = Paper(
            fingerprint="m",
            source_id=source.id,
            source_name=source.journal_title,
            journal_title=source.journal_title,
            title="Seismic velocity structure beneath the source region",
            abstract="This study constrains physical properties beneath the region using tomography.",
            published_date=date(2026, 3, 14),
            doi="10.1234/example-5",
            url="https://example.org/5",
        )
        classifier = TopicClassifier(topics)
        result = classifier.classify(paper, source)

        self.assertEqual(result.topics, [])

    def test_watchlist_drops_methods_only_matches(self) -> None:
        source = SourceConfig(
            id="nature_communications",
            journal_title="Nature Communications",
            aliases=["Nature Communications"],
            tier="watchlist",
            mode="watchlist",
            priority=3,
            description="",
        )
        topics = [
            TopicProfile(id="methods_models", label="观测/反演/同化/模型", keywords=["machine learning", "observations"]),
            TopicProfile(id="ionosphere", label="电离层", keywords=["ionosphere", "tec"]),
        ]
        paper = Paper(
            fingerprint="z",
            source_id=source.id,
            source_name=source.journal_title,
            journal_title=source.journal_title,
            title="Experimental mechanician for metamaterial discovery",
            abstract="We use machine learning and observations to explore structure-property relationships.",
            published_date=date(2026, 3, 14),
            doi="10.1234/example-3",
            url="https://example.org/3",
        )
        classifier = TopicClassifier(topics)
        result = classifier.classify(paper, source)

        self.assertEqual(result.topics, ["methods_models"])
        self.assertFalse(classifier.should_keep(result, source))

    def test_topic_filter_requires_space_domain_anchor(self) -> None:
        source = SourceConfig(
            id="acp",
            journal_title="Atmospheric Chemistry and Physics",
            aliases=["Atmospheric Chemistry and Physics"],
            tier="related",
            mode="topic_filter",
            priority=3,
            description="",
        )
        topics = [
            TopicProfile(id="space_weather", label="空间天气", keywords=["forecast", "forecasting"]),
        ]
        paper = Paper(
            fingerprint="k",
            source_id=source.id,
            source_name=source.journal_title,
            journal_title=source.journal_title,
            title="Improved seasonal forecasting of rainfall extremes",
            abstract="This study improves forecasting skill for precipitation extremes using observations and simulations.",
            published_date=date(2026, 3, 14),
            doi="10.1234/example-4",
            url="https://example.org/4",
        )
        classifier = TopicClassifier(topics)
        result = classifier.classify(paper, source)

        self.assertEqual(result.topics, ["space_weather"])
        self.assertFalse(result.has_domain_anchor)
        self.assertFalse(classifier.should_keep(result, source))

    def test_watchlist_drops_astrophysics_noise_without_strong_space_anchor(self) -> None:
        source = SourceConfig(
            id="a_and_a",
            journal_title="Astronomy & Astrophysics",
            aliases=["Astronomy & Astrophysics"],
            tier="watchlist",
            mode="watchlist",
            priority=4,
            description="",
        )
        topics = [
            TopicProfile(id="ionosphere", label="电离层", keywords=["electron density"]),
        ]
        paper = Paper(
            fingerprint="astro",
            source_id=source.id,
            source_name=source.journal_title,
            journal_title=source.journal_title,
            title="Electron density diagnostics in an ultraluminous X-ray source outflow",
            abstract="We study electron density in an ultraluminous X-ray source and black hole accretion flow.",
            published_date=date(2026, 3, 14),
            doi="10.1234/example-astro",
            url="https://example.org/astro",
        )
        classifier = TopicClassifier(topics)
        result = classifier.classify(paper, source)

        self.assertEqual(result.topics, ["ionosphere"])
        self.assertTrue(result.has_noise_conflict)
        self.assertFalse(result.has_strong_domain_anchor)
        self.assertFalse(classifier.should_keep(result, source))


if __name__ == "__main__":
    unittest.main()
