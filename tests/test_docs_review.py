from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.docs_review import render_docs_review_summary, run_docs_review


def _touch(path: pathlib.Path, text: str = "# stub\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _touch_root_docs(root: pathlib.Path, *, readme: str | None = None, project_config: str | None = None) -> None:
    _touch(
        root / "README.md",
        readme
        or (
            "# README\n"
            "openrouter_api\n"
            "manual-llm-import\n"
        ),
    )
    _touch(
        root / "PROJECT_CONFIG.md",
        project_config
        or (
            "# PROJECT_CONFIG\n"
            "openrouter_api\n"
            "chatgpt_web_manual\n"
        ),
    )


class DocsReviewTest(unittest.TestCase):
    def test_docs_review_passes_when_files_are_in_expected_locations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _touch_root_docs(root)
            for filename in (
                "agent_skill_usage.md",
                "chatgpt_web_manual_workflow.md",
                "deep_reading_comparison_and_fusion.md",
                "eval_governance_runbook.md",
                "literature_codex_quick_guide.md",
                "literature_directory_integration_guide.md",
                "llm_analysis_readme.md",
                "maintenance_governance_runbook.md",
                "python_module_map.md",
                "release_checklist.md",
            ):
                _touch(root / "docs" / "user_guides" / filename)
            for filename in (
                "README.md",
                "article_summary_template_guide.md",
                "daily_report_template_guide.md",
                "deep_reading_template_guide.md",
                "hierarchical_tag_reference.md",
                "literature_note_style_guide.md",
                "llm_prompt_contracts.md",
                "report_review_rules.md",
                "rules.md",
                "source_of_truth_matrix.md",
            ):
                _touch(root / "docs" / "workflow_specs" / filename)
            report = run_docs_review(root)

        self.assertTrue(report.passed)
        self.assertIn("overall=ok", render_docs_review_summary(report))

    def test_docs_review_flags_legacy_exec_plan_template_and_missing_docs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _touch_root_docs(root)
            _touch(root / "docs" / "exec_plans" / "TEMPLATE.md")
            report = run_docs_review(root)

        self.assertFalse(report.passed)
        messages = [issue.message for issue in report.issues]
        self.assertTrue(any("TEMPLATE.md" in message for message in messages))
        self.assertTrue(any("缺少应放在" in message for message in messages))

    def test_docs_review_flags_misplaced_known_docs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _touch_root_docs(root)
            _touch(root / "docs" / "workflow_specs" / "python_module_map.md")
            report = run_docs_review(root)

        self.assertFalse(report.passed)
        self.assertTrue(any("应放在 `user_guides/`" in issue.message for issue in report.issues))

    def test_docs_review_flags_legacy_chinese_workflow_spec_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _touch_root_docs(root)
            _touch(root / "docs" / "workflow_specs" / "常用分级标签参考.md")
            report = run_docs_review(root)

        self.assertFalse(report.passed)
        self.assertTrue(any("hierarchical_tag_reference.md" in issue.message for issue in report.issues))

    def test_docs_review_flags_root_doc_provider_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            _touch_root_docs(
                root,
                readme="# README\n支持 `codex_local`、`openai_api`、`chatgpt_web_manual` 三种分析后端\n",
                project_config="# PROJECT_CONFIG\n- `provider`：当前分析后端，可选 `codex_local`、`openai_api`、`openrouter_api`、`chatgpt_web_manual`\n",
            )
            for filename in (
                "agent_skill_usage.md",
                "chatgpt_web_manual_workflow.md",
                "deep_reading_comparison_and_fusion.md",
                "eval_governance_runbook.md",
                "literature_codex_quick_guide.md",
                "literature_directory_integration_guide.md",
                "llm_analysis_readme.md",
                "maintenance_governance_runbook.md",
                "python_module_map.md",
                "release_checklist.md",
            ):
                _touch(root / "docs" / "user_guides" / filename)
            for filename in (
                "README.md",
                "article_summary_template_guide.md",
                "daily_report_template_guide.md",
                "deep_reading_template_guide.md",
                "hierarchical_tag_reference.md",
                "literature_note_style_guide.md",
                "llm_prompt_contracts.md",
                "report_review_rules.md",
                "rules.md",
                "source_of_truth_matrix.md",
            ):
                _touch(root / "docs" / "workflow_specs" / filename)
            report = run_docs_review(root)

        self.assertFalse(report.passed)
        self.assertTrue(any("README.md" in str(issue.path) and "过时表述" in issue.message for issue in report.issues))
        self.assertTrue(any("PROJECT_CONFIG.md" in str(issue.path) and "过时表述" in issue.message for issue in report.issues))


if __name__ == "__main__":
    unittest.main()
