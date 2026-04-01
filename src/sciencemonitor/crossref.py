from __future__ import annotations

from datetime import date, datetime

from .http import HTTPClient
from .models import Paper, SourceConfig
from .utils import build_fingerprint, clean_abstract_text, clean_title_text, normalize_journal_title, safe_date


class CrossrefClient:
    API_URL = "https://api.crossref.org/works"

    def __init__(self, http_client: HTTPClient | None = None) -> None:
        self.http = http_client or HTTPClient()

    def fetch_recent_works(
        self,
        source: SourceConfig,
        since_date: date,
        until_date: date,
        max_rows: int = 20,
    ) -> list[Paper]:
        params = self._build_query_params(source, since_date, until_date, max_rows)
        payload = self.http.get_json(self.API_URL, params=params)
        items = payload.get("message", {}).get("items", [])
        return self._parse_items(source, items)

    def _build_query_params(
        self,
        source: SourceConfig,
        since_date: date,
        until_date: date,
        max_rows: int,
    ) -> dict[str, str]:
        params = {
            "rows": str(max_rows),
            "sort": "published",
            "order": "desc",
            "select": ",".join(
                [
                    "DOI",
                    "URL",
                    "title",
                    "container-title",
                    "author",
                    "published",
                    "published-online",
                    "published-print",
                    "issued",
                    "abstract",
                ]
            ),
        }

        if source.crossref_date_field == "online":
            date_filter = (
                f"from-online-pub-date:{since_date.isoformat()},"
                f"until-online-pub-date:{until_date.isoformat()}"
            )
        else:
            date_filter = f"from-pub-date:{since_date.isoformat()},until-pub-date:{until_date.isoformat()}"

        if source.issn:
            params["filter"] = f"issn:{source.issn},{date_filter}"
        else:
            search_title = max([source.journal_title, *source.aliases], key=len)
            params["query.container-title"] = search_title
            params["filter"] = date_filter
        return params

    def _parse_items(self, source: SourceConfig, items: list[dict]) -> list[Paper]:
        results: list[Paper] = []
        allowed = {normalize_journal_title(source.journal_title)}
        allowed.update(normalize_journal_title(alias) for alias in source.aliases)

        for item in items:
            container_titles = item.get("container-title") or []
            container_title = container_titles[0] if container_titles else source.journal_title
            if normalize_journal_title(container_title) not in allowed:
                continue

            title_list = item.get("title") or []
            title = clean_title_text(title_list[0]) if title_list else ""
            if not title:
                continue

            published = self._extract_date(item)
            if not published:
                continue

            doi = item.get("DOI", "") or ""
            url = item.get("URL", "") or ""
            authors = self._parse_authors(item.get("author") or [])
            abstract = clean_abstract_text(item.get("abstract", "") or "")
            fingerprint = build_fingerprint(source.id, title, published, doi)
            results.append(
                Paper(
                    fingerprint=fingerprint,
                    source_id=source.id,
                    source_name=source.journal_title,
                    journal_title=source.journal_title,
                    title=title,
                    abstract=abstract,
                    published_date=published,
                    doi=doi,
                    url=url,
                    authors=authors,
                    tier=source.tier,
                    mode=source.mode,
                    raw_container_title=container_title,
                    fetched_at=datetime.utcnow().isoformat(timespec="seconds"),
                )
            )
        return results

    def _extract_date(self, item: dict) -> date | None:
        for field in ("published-online", "published-print", "published", "issued"):
            candidate = item.get(field, {})
            date_parts = candidate.get("date-parts") or []
            if date_parts:
                parsed = safe_date(date_parts[0])
                if parsed:
                    return parsed
        return None

    def _parse_authors(self, authors: list[dict]) -> list[str]:
        names: list[str] = []
        for item in authors:
            given = item.get("given", "").strip()
            family = item.get("family", "").strip()
            full = " ".join(part for part in [given, family] if part)
            if full:
                names.append(full)
        return names
