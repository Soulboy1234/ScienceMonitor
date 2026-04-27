from __future__ import annotations

# Compatibility re-export for the old tag_candidates module.
from .tag_governance import (
    PendingTagEntry as TagCandidate,
    candidate_log_path,
    candidate_review_report_path,
    filter_tag_candidates,
    load_pending_tags as load_tag_candidates,
    render_tag_candidates_report,
    write_tag_candidates_report,
)

__all__ = [
    "TagCandidate",
    "candidate_log_path",
    "candidate_review_report_path",
    "load_tag_candidates",
    "filter_tag_candidates",
    "render_tag_candidates_report",
    "write_tag_candidates_report",
]
