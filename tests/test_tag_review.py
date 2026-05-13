from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciencemonitor.tag_governance import ensure_tag_governance_files, refresh_pending_tag_files
from sciencemonitor.tag_review import (
    reconcile_deep_read_output_tags_with_review,
    reconcile_all_auto_output_tags_with_review,
    reconcile_auto_output_tags_with_review,
    review_generated_tags,
    run_deep_read_tag_output_review,
    run_tag_output_review,
)
from sciencemonitor.tags import infer_preferred_tags_from_text, normalize_tags


class TagReviewTest(unittest.TestCase):
    def _seed_root(self, root: pathlib.Path) -> None:
        (root / "config").mkdir()
        (root / "config" / "focus_tags.json").write_text(
            (ROOT / "config" / "focus_tags.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        ensure_tag_governance_files(root, refresh_pending=True)

    def test_review_generated_tags_prefers_formal_and_styles_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                ["磁暴", "热层/风", "卫星/MMS", "太阳/日冕"],
                root=root,
                title_text="Solar corona response during geomagnetic storm",
                body_text="MMS observed thermospheric wind changes during a geomagnetic storm.",
                context="article_summary",
            )

            self.assertIn("事件/磁暴", tags)
            self.assertIn("对象/热层/风场", tags)
            self.assertIn("仪器/MMS", tags)
            self.assertIn("对象/太阳/日冕", tags)

    def test_review_generated_tags_uses_context_to_pick_formal_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                ["电子密度"],
                root=root,
                title_text="Ionospheric electron density response to geomagnetic disturbance",
                body_text="The ionosphere TEC and electron density over low latitude stations are analyzed.",
                context="article_summary",
            )

            self.assertEqual(tags, ["对象/电离层/电子密度"])

    def test_review_generated_tags_keeps_tec_adjacent_to_chinese_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                ["对象/电离层/TEC", "仪器/GNSS"],
                root=root,
                title_text="基于智能手机载波相位TEC的电离层时空尺度研究",
                body_text=(
                    "研究针对安卓设备伪距TEC聚合方法的限制，提出主动采集智能手机载波相位TEC的方案，"
                    "并验证其在电离层平静期和日食期间的观测能力。"
                ),
                context="output_review",
            )

            self.assertIn("对象/电离层/TEC", tags)
            self.assertIn("仪器/GNSS", tags)

    def test_review_generated_tags_folds_article_summary_tag_audit_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                [
                    "仪器/TIE-GCM",
                    "事件/SC",
                    "事件/HILDCAA",
                    "对象/热层/水平风",
                    "对象/热层/一氧化氮",
                    "对象/电网",
                    "对象/地磁场",
                    "对象/电离层/F层峰高",
                    "对象/电离层/F2层",
                    "仪器/卫星",
                ],
                root=root,
                title_text="Thermospheric wind, nitric oxide cooling, and sudden commencement effects",
                body_text=(
                    "论文讨论地磁暴急始（SC）和 HILDCAA 期间的热层水平风、一氧化氮冷却、"
                    "地磁场扰动以及电网地磁感应电流风险，并使用 TIE-GCM 模型分析 hmF2/F2 层响应。"
                ),
                context="article_summary",
                max_tags=20,
            )

            for expected in (
                "模型/TIEGCM",
                "事件/磁暴/急始",
                "事件/HILDCAAs",
                "对象/热层/风场",
                "对象/热层/成分",
                "应用/基础设施",
                "对象/地磁",
                "对象/电离层/hmF2",
            ):
                self.assertIn(expected, tags)
            for unexpected in (
                "仪器/TIE-GCM",
                "事件/SC",
                "事件/HILDCAA",
                "对象/热层/水平风",
                "对象/热层/一氧化氮",
                "对象/电网",
                "对象/地磁场",
                "对象/电离层/F层峰高",
                "对象/电离层/F2层",
                "仪器/卫星",
            ):
                self.assertNotIn(unexpected, tags)

    def test_review_generated_tags_rewrites_pending_roots_and_broad_method_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                [
                    "方法/E-CHAIM",
                    "对象/日食",
                    "对象/水星/磁尾",
                    "对象/磁尾/O+",
                    "对象/磁尾/O2+",
                    "方法/趋势拟合",
                    "方法/交叉对比",
                    "方法/MHD模拟",
                    "方法/模式识别",
                ],
                root=root,
                title_text="E-CHAIM, eclipse response, and Mercury magnetosphere examples",
                body_text=(
                    "The paper compares E-CHAIM results during a solar eclipse, discusses Mercury magnetotail context, "
                    "includes O+ and O2+ heavy ions, and uses MHD simulation, "
                    "trend fitting, cross comparison, and pattern recognition."
                ),
                context="article_summary",
                max_tags=20,
            )

            for expected in (
                "模型/E-CHAIM",
                "事件/日食",
                "对象/其他行星/水星",
                "对象/重离子",
                "方法/统计研究",
                "数据/数据对比",
                "方法/数值模拟",
                "方法/建模/机器学习",
            ):
                self.assertIn(expected, tags)
            for unexpected in (
                "方法/E-CHAIM",
                "对象/日食",
                "对象/水星/磁尾",
                "对象/磁尾/O+",
                "对象/磁尾/O2+",
                "方法/趋势拟合",
                "方法/交叉对比",
                "方法/MHD模拟",
                "方法/模式识别",
            ):
                self.assertNotIn(unexpected, tags)

    def test_deep_read_infers_thermosphere_density_from_plural_title(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                ["对象/热层", "仪器/MAVEN"],
                root=root,
                title_text="Solar Rotation Effects in Earth and Mars Thermospheric Densities",
                body_text="The paper analyzes thermospheric density observations at Earth and Mars.",
                context="deep_read",
                max_tags=10,
            )

        self.assertIn("对象/热层/密度", tags)
        self.assertNotIn("对象/热层", tags)

    def test_review_generated_tags_only_keeps_pending_candidates_with_real_output_usage(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            review_generated_tags(
                ["太阳/日冕"],
                root=root,
                title_text="Solar corona structure",
                body_text="The solar corona is discussed.",
                context="article_summary",
                record_candidates=True,
            )
            refresh_pending_tag_files(root)

            payload = json.loads((root / "config" / "pending_tags.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["tags"], {})

    def test_review_generated_tags_drops_unsupported_thermosphere_density_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                ["对象/热层/密度", "对象/太阳风", "对象/高能粒子/电子"],
                root=root,
                title_text="How well can solar wind parameters predict outer radiation belt electron flux?",
                body_text="The study evaluates solar wind parameters and outer radiation belt electron flux prediction skill.",
                extra_text="补充说明：文章重点在辐射带电子通量预报，不涉及热层密度、热层风或卫星阻力的直接分析。",
                context="article_summary",
            )

            self.assertNotIn("对象/热层/密度", tags)
            self.assertIn("对象/太阳风", tags)

    def test_review_generated_tags_drops_density_and_satellite_tags_when_negation_is_trailing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                ["对象/热层/密度", "应用/卫星影响", "事件/磁暴", "仪器/SABER"],
                root=root,
                title_text="Mid- and high-latitude ionospheric responses during a super geomagnetic storm",
                body_text="The paper studies ionospheric disturbance, NO enhancement, temperature structure and gravity-wave signatures using VLF and SABER data.",
                extra_text="按摘要看，论文重点是中高纬电离层和低热层响应；与热层密度、卫星阻力或业务预报的直接联系在摘要中未展开。",
                context="article_summary",
            )

            self.assertNotIn("对象/热层/密度", tags)
            self.assertNotIn("应用/卫星影响", tags)
            self.assertIn("事件/磁暴", tags)
            self.assertIn("仪器/SABER", tags)

    def test_review_generated_tags_drops_density_for_coordinate_system_paper(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                ["对象/热层/密度", "对象/电离层", "对象/磁层", "对象/地磁", "模型/GED", "仪器/CHAMP"],
                root=root,
                title_text="A new orthogonal geomagnetic coordinate system: the generalized eccentric dipole",
                body_text=(
                    "The paper proposes a new orthogonal geomagnetic coordinate system based on IGRF. "
                    "It is intended for magnetosphere-ionosphere-thermosphere coupling studies and has been implemented in IPIM."
                ),
                extra_text=(
                    "摘要级判断：这篇文章更偏基础坐标框架与模型方法，不是直接研究热层密度异常、热层风或卫星应用影响的工作。"
                ),
                context="article_summary",
            )

            self.assertNotIn("对象/热层/密度", tags)
            self.assertIn("模型/GED", tags)
            self.assertIn("对象/磁层", tags)

    def test_review_generated_tags_drops_satellite_impact_for_non_application_paper(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                ["应用/卫星影响", "仪器/MAVEN", "对象/其他行星/火星"],
                root=root,
                title_text="Martian magnetospheric response under quasi-radial IMF and low dynamic pressure",
                body_text="The paper studies the Martian induced magnetosphere and ionosphere response using MAVEN observations.",
                extra_text="当前仅基于摘要生成，不能进一步外推边界位置的定量变化、具体加速效率、卫星或应用影响。",
                context="article_summary",
            )

            self.assertNotIn("应用/卫星影响", tags)
            self.assertIn("仪器/MAVEN", tags)

    def test_review_generated_tags_drops_false_high_speed_flow_and_mars_escape_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                ["对象/太阳风/高速流", "对象/其他行星/火星/逃逸", "对象/太阳射电/III型暴", "事件/太阳耀斑"],
                root=root,
                title_text="Multiwavelength multipoint observations of the October 28, 2021 Type III radio burst",
                body_text=(
                    "The paper identifies the solar source region of a type III radio burst and tracks escaping electron beams "
                    "from a compact flare into the heliosphere."
                ),
                extra_text="当前文本是摘要级概括，未涉及火星大气逃逸或高速流研究对象。",
                context="article_summary",
            )

            self.assertNotIn("对象/太阳风/高速流", tags)
            self.assertNotIn("对象/其他行星/火星/逃逸", tags)
            self.assertIn("对象/太阳射电/III型暴", tags)
            self.assertIn("事件/太阳耀斑", tags)

    def test_review_generated_tags_drops_false_icon_and_euv_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                ["事件/太阳耀斑", "指数/EUV", "仪器/ICON", "仪器/EOS-08"],
                root=root,
                title_text="Solar activity during the peak of Solar Cycle 25 captured by SiC UV dosimeter onboard EOS-08",
                body_text=(
                    "The study uses a three-channel SiC UV dosimeter onboard EOS-08 to track UV-A, UV-B, and UV-C irradiance "
                    "variability and flare-time response."
                ),
                extra_text="来源文本讨论的是UV-A/B/C辐照度，不是EUV，也未使用ICON或MIGHTI。",
                context="article_summary",
            )

            self.assertNotIn("指数/EUV", tags)
            self.assertNotIn("仪器/ICON", tags)
            self.assertIn("事件/太阳耀斑", tags)
            self.assertIn("仪器/EOS-08", tags)

    def test_deep_read_tags_normalize_chen_index_aliases_and_drop_false_instruments(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            body = (
                "The paper analyzes D index st and K index p geomagnetic criteria, including Kp ≥ 7. "
                "The SNMC algorithm (shift neighborhood matching correlation) compares intense geomagnetic storms "
                "with global strong earthquake catalogs. Random sampling, binomial and chi-square tests support "
                "a time-lagged correlation over a 27-28 day window, with probability gain. "
                "The discussion mentions electrokinetic and inverse ofpiezoelectric effects and cites an IconSpace conference paper, "
                "but the observations are geomagnetic index and earthquake catalog data rather than upper-atmosphere instruments."
            )
            tags = review_generated_tags(
                ["对象/地磁暴", "对象/D指数", "对象/K指数", "仪器/FPI", "仪器/ICON"],
                root=root,
                title_text="On solar-terrestrial interactions: correlation between intense geomagnetic storms and global strong earthquakes",
                body_text=body,
                context="deep_read",
                max_tags=14,
            )

        self.assertIn("对象/日地耦合", tags)
        self.assertIn("事件/地震", tags)
        self.assertIn("指数/Dst", tags)
        self.assertIn("指数/Kp", tags)
        self.assertIn("事件/磁暴", tags)
        self.assertIn("方法/SNMC", tags)
        self.assertIn("方法/统计研究", tags)
        self.assertIn("特征/时滞相关", tags)
        self.assertIn("特征/概率增益", tags)
        self.assertIn("特征/电渗流", tags)
        self.assertIn("特征/逆压电效应", tags)
        self.assertNotIn("对象/地磁暴", tags)
        self.assertNotIn("对象/D指数", tags)
        self.assertNotIn("对象/K指数", tags)
        self.assertNotIn("仪器/FPI", tags)
        self.assertNotIn("仪器/ICON", tags)

    def test_deep_read_output_reconcile_adds_missing_evidence_tags_from_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)
            deep_dir = root / "out" / "auto" / "deep_reads"
            deep_dir.mkdir(parents=True, exist_ok=True)
            deep = deep_dir / "Chen 2025 - GRL - 太阳-地球相互作用：强地磁暴与全球强震之间的相关性研究 深度解读.md"
            deep.write_text(
                "\n".join(
                    [
                        "# 深度解读",
                        "- [PDF](<../deep_reads_pdf/chen.pdf>) #事件/磁暴 #指数/Dst #指数/Kp",
                        "",
                        "本文讨论 solar-terrestrial interactions、强地磁暴和全球强震之间的相关性。",
                        "论文使用 D index st / Dst 作为强地磁暴的主要强度刻画。",
                        "数据筛选使用 Kp ≥ 7 的强地磁扰动阈值。",
                        "方法上使用 SNMC algorithm / shift neighborhood matching correlation，并用 random sampling、binomial 和 chi-square tests 做统计检验。",
                        "结果包括 27-28 day time-lagged correlation、probability gain，并讨论 electrokinetic 与 inverse ofpiezoelectric effects。",
                        "后续问题提到 moon tides，但题名和正文主线明确是 solar-terrestrial interactions。",
                        "正文没有使用 FPI、ICON/MIGHTI 或 Ionospheric Connection Explorer 数据。",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = reconcile_deep_read_output_tags_with_review(root)
            rewritten = deep.read_text(encoding="utf-8")

        self.assertEqual(result.scanned_files, 1)
        self.assertEqual(len(result.modified_entries), 1)
        for tag in (
            "#对象/日地耦合",
            "#事件/磁暴",
            "#事件/地震",
            "#指数/Dst",
            "#指数/Kp",
            "#方法/SNMC",
            "#方法/统计研究",
            "#特征/时滞相关",
            "#特征/概率增益",
            "#特征/电渗流",
            "#特征/逆压电效应",
        ):
            self.assertIn(tag, rewritten)
        self.assertNotIn("#仪器/FPI", rewritten)
        self.assertNotIn("#仪器/ICON", rewritten)

    def test_deep_read_streamer_and_secs_tags_use_correct_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                ["对象/SECS技术", "仪器/Streamers", "Streamers", "场向电流"],
                root=root,
                title_text="A Statistical Analysis of the Auroral Streamer Current System",
                body_text=(
                    "Auroral streamers are analyzed using the Spherical Elementary Current System (SECS) "
                    "technique, ground magnetometers, THEMIS ASI images, and field-aligned currents."
                ),
                context="deep_read",
                max_tags=14,
            )

        self.assertIn("对象/极区/极光", tags)
        self.assertNotIn("对象/极区/极光/流光", tags)
        self.assertIn("对象/磁层/电流体系", tags)
        self.assertIn("方法/SECS", tags)
        self.assertNotIn("对象/SECS技术", tags)
        self.assertNotIn("仪器/Streamers", tags)

    def test_streamer_tag_folds_to_aurora_without_global_depth_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            normalized = normalize_tags(["对象/极区/极光/流光", "对象/热层/风场/垂直风"], root=root)
            inferred = infer_preferred_tags_from_text(
                title_text="Auroral streamers during a substorm",
                body_text="The paper analyzes auroral streamers and vertical thermospheric wind.",
                root=root,
                max_tags=10,
            )

        self.assertIn("对象/极区/极光", normalized)
        self.assertIn("对象/热层/风场/垂直风", normalized)
        self.assertNotIn("对象/极区/极光/流光", normalized)
        self.assertIn("对象/极区/极光", inferred)
        self.assertNotIn("对象/极区/极光/流光", inferred)

    def test_deep_read_eta_ada_and_instrument_tags_use_actual_data_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                [
                    "对象/赤道热层异常",
                    "方法/上升-下降加速度分析ADA",
                    "仪器/CHAMP",
                    "仪器/GRACE",
                    "仪器/ICON",
                    "仪器/CHAMPSTAR加速度计",
                ],
                root=root,
                title_text="Distinguishing Density and Wind Perturbations in the Equatorial Thermosphere Anomaly",
                body_text=(
                    "This investigation focuses on in-track accelerometer data from the CHAMP mission. "
                    "The study uses CHAMP STAR accelerometer data from 2003-2004 to separate mass density "
                    "and thermospheric wind perturbations in the ETA, and removes Kp > 5 intervals. "
                    "The introduction lists missions such as GRACE, GRACE-FO, GOLD, TIMED and ICON as background, "
                    "and says the technique can be applied to GRACE in the future, but the analysis here uses CHAMP data."
                ),
                context="deep_read",
                max_tags=14,
            )

        self.assertIn("对象/热层/ETA", tags)
        self.assertIn("对象/热层/密度", tags)
        self.assertIn("对象/热层/风场", tags)
        self.assertIn("方法/ADA", tags)
        self.assertIn("指数/Kp", tags)
        self.assertIn("仪器/CHAMP", tags)
        self.assertNotIn("对象/赤道热层异常", tags)
        self.assertNotIn("方法/上升-下降加速度分析ADA", tags)
        self.assertNotIn("仪器/CHAMPSTAR加速度计", tags)
        self.assertNotIn("仪器/GRACE", tags)
        self.assertNotIn("仪器/ICON", tags)

    def test_text_inference_uses_token_boundaries_for_fpi_and_icon(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = infer_preferred_tags_from_text(
                title_text="Geomagnetic storms and earthquakes",
                body_text=(
                    "The reference list contains measurementofpiezoelectricconstants and IconSpace conference, "
                    "while the actual data are D index st and K index p geomagnetic indices."
                ),
                root=root,
                max_tags=10,
            )

        self.assertIn("指数/Dst", tags)
        self.assertIn("指数/Kp", tags)
        self.assertNotIn("仪器/FPI", tags)
        self.assertNotIn("仪器/ICON", tags)

    def test_deep_read_drops_kp_equation_but_keeps_pinn_xai_method_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                ["方法/物理信息神经网络", "方法/可解释性人工智能", "指数/Kp"],
                root=root,
                title_text="Fundamental flaws of physics-informed neural networks and explainability methods in engineering systems",
                body_text=(
                    "The article critiques physics-informed neural networks (PINNs) and explainable artificial "
                    "intelligence (XAI) in engineering systems. A related-work sentence mentions that ASW-PINN "
                    "was used for a generalized potential KP equation, but this is a mathematical KP equation, "
                    "not a geomagnetic Kp index or space physics study."
                ),
                context="deep_read",
                max_tags=10,
            )

        self.assertIn("方法/建模/机器学习/PINN", tags)
        self.assertIn("方法/可解释模型/XAI", tags)
        self.assertNotIn("指数/Kp", tags)

    def test_deep_read_drops_earthquake_from_late_reference_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                ["事件/地震", "领域/工程计算", "方法/物理信息神经网络", "方法/可解释性人工智能"],
                root=root,
                title_text="Fundamental flaws of physics-informed neural networks and explainability methods in engineering systems",
                body_text=(
                    "This paper critiques PINNs and XAI for engineering systems. "
                    + "Physics-informed models can produce false confidence. " * 80
                    + "A late reference list mentions physics-informed neural network and fault zone acoustic monitoring "
                    "to predict lab earthquakes, but earthquakes are not the paper topic."
                ),
                context="deep_read",
                max_tags=10,
            )

        self.assertIn("方法/建模/机器学习/PINN", tags)
        self.assertIn("方法/可解释模型/XAI", tags)
        self.assertNotIn("事件/地震", tags)
        self.assertNotIn("对象/领域/工程计算", tags)

    def test_deep_read_drops_indices_only_mentioned_in_late_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                ["指数/SYM-H", "指数/Dst", "指数/Kp"],
                root=root,
                title_text="Prediction of the SYM-H Index Using a Bayesian Deep Learning Method",
                body_text=(
                    "### 为什么做\n"
                    "This paper predicts the SYM-H index from solar wind and IMF inputs.\n"
                    "### 怎么做\n"
                    "The model uses SSCDAS data and uncertainty quantification for SYM-H forecasts.\n"
                    "### 局限性\n"
                    "The framework is not extended to Kp or Dst geomagnetic indices."
                ),
                context="deep_read",
                max_tags=10,
            )

        self.assertIn("指数/SYM-H", tags)
        self.assertNotIn("指数/Dst", tags)
        self.assertNotIn("指数/Kp", tags)

    def test_deep_read_tag_review_folds_noisy_pending_aliases_to_canonical_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                [
                    "对象/物理对象/大气重力波",
                    "对象/物理对象/平均分子量",
                    "对象/物理量/等离子体密度",
                    "对象/物理量/等离子体温度",
                    "对象/物理对象/离子漂移",
                    "对象/物理量/磁场扰动",
                    "对象/物理过程/辐射冷却",
                    "对象/数据科学",
                    "对象/统计分析",
                    "对象/低纬度电离层",
                    "对象/全球平均TEC",
                    "对象/行星际磁场",
                    "对象/磁场/IMFBy",
                    "模型/TIE-GCM",
                    "仪器/THEMIS",
                    "仪器/NO",
                    "仪器/地面磁力计",
                    "对象/低地球轨道/卫星",
                    "应用/碰撞风险评估",
                ],
                root=root,
                title_text="Gravity wave deep read tag audit example",
                body_text=(
                    "The paper discusses atmospheric gravity waves and gravity waves, plasma temperature, "
                    "ion drift, IMF By, THEMIS observations, thermospheric nitric oxide cooling, "
                    "low-latitude ionospheric TEC, ground magnetometers, TIE-GCM simulations, "
                    "and satellite conjunction assessment. 该研究还明确讨论重力波驱动和重力波传播。"
                ),
                context="deep_read",
                max_tags=20,
            )

        for expected in (
            "对象/重力波",
            "对象/热层/成分",
            "对象/电离层/电子温度",
            "对象/电离层/离子飘移",
            "对象/地磁",
            "对象/热层/温度",
            "方法/建模/机器学习",
            "方法/统计研究",
            "对象/电离层/低纬",
            "对象/电离层/TEC",
            "指数/IMF/By",
            "模型/TIEGCM",
            "仪器/THEMIS_A-E",
            "仪器/磁强计",
            "应用/卫星轨道",
        ):
            self.assertIn(expected, tags)
        for unexpected in (
            "对象/物理对象/大气重力波",
            "对象/物理对象/平均分子量",
            "对象/物理量/等离子体密度",
            "对象/物理过程/辐射冷却",
            "对象/数据科学",
            "对象/统计分析",
            "对象/低纬度电离层",
            "对象/行星际磁场",
            "模型/TIE-GCM",
            "仪器/THEMIS",
            "仪器/NO",
            "仪器/地面磁力计",
            "应用/碰撞风险评估",
        ):
            self.assertNotIn(unexpected, tags)

    def test_deep_read_output_reconcile_recovers_pinn_xai_from_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)
            deep_dir = root / "out" / "auto" / "deep_reads"
            deep_dir.mkdir(parents=True, exist_ok=True)
            deep = deep_dir / "Naser 2026 - PINN XAI 深度解读.md"
            deep.write_text(
                "\n".join(
                    [
                        "# 论文深度阅读报告",
                        "- [PDF](<../deep_reads_pdf/naser.pdf>) #方法/特征归因 #对象/悬臂梁 #模型/建模误差",
                        "",
                        "本文讨论 physics-informed neural networks (PINNs) and explainable artificial intelligence (XAI)。",
                        "正文参考文献里提到 lab earthquakes，但地震不是论文主题。",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = reconcile_deep_read_output_tags_with_review(root)
            rewritten = deep.read_text(encoding="utf-8")

        self.assertEqual(result.scanned_files, 1)
        self.assertIn("#方法/建模/机器学习/PINN", rewritten)
        self.assertIn("#方法/可解释模型/XAI", rewritten)
        self.assertNotIn("#事件/地震", rewritten)

    def test_instrument_tags_are_kept_with_explicit_source_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            fpi_tags = review_generated_tags(
                ["仪器/FPI"],
                root=root,
                title_text="Thermospheric wind observations",
                body_text="The study uses Fabry-Perot Interferometer (FPI) wind observations.",
                context="deep_read",
            )
            icon_tags = review_generated_tags(
                ["仪器/ICON"],
                root=root,
                title_text="MIGHTI wind observations",
                body_text="The study uses ICON/MIGHTI data from the Ionospheric Connection Explorer mission.",
                context="deep_read",
            )

        self.assertIn("仪器/FPI", fpi_tags)
        self.assertIn("仪器/ICON", icon_tags)

    def test_deep_read_instrument_tags_need_data_source_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            strategic_tags = review_generated_tags(
                ["仪器/SuperDARN", "仪器/MMS", "仪器/GDC", "应用/空间天气"],
                root=root,
                title_text="The Next Decade of Discovery in Solar and Space Physics",
                body_text=(
                    "The report discusses future mission priorities including GDC and mentions SuperDARN and MMS "
                    "as examples in the heliophysics ecosystem. No observational data products are analyzed."
                ),
                context="deep_read",
            )
            observation_tags = review_generated_tags(
                ["仪器/SuperDARN"],
                root=root,
                title_text="Polar convection control of thermospheric wind",
                body_text="The study uses SuperDARN convection maps and radar observations to track the boundary.",
                context="deep_read",
            )

        self.assertNotIn("仪器/SuperDARN", strategic_tags)
        self.assertNotIn("仪器/MMS", strategic_tags)
        self.assertNotIn("仪器/GDC", strategic_tags)
        self.assertIn("应用/空间天气", strategic_tags)
        self.assertIn("仪器/SuperDARN", observation_tags)

    def test_review_generated_tags_repairs_corrupted_deep_read_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                ["对象/热层/风", "对象/极区对all", "事件/日冕物质抛"],
                root=root,
                title_text="CME-driven geomagnetic storm response",
                body_text="The paper studies thermospheric wind, polar convection, and geomagnetic storm response driven by CME impacts.",
                context="deep_read",
            )

        self.assertIn("对象/热层/风场", tags)
        self.assertIn("对象/极区/等离子体对流", tags)
        self.assertIn("事件/磁暴/CME", tags)
        self.assertNotIn("对象/热层/风", tags)
        self.assertNotIn("对象/极区对all", tags)
        self.assertNotIn("事件/日冕物质抛", tags)

    def test_review_generated_tags_drops_storm_tag_when_storm_is_not_main_topic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            li_tags = review_generated_tags(
                ["对象/太阳风", "对象/高能粒子/电子", "事件/磁暴", "仪器/VanAllenProbes", "方法/建模/机器学习", "应用/预测"],
                root=root,
                title_text="How well can solar wind parameters predict outer radiation belt electron flux?",
                body_text=(
                    "The study evaluates forecast skill for outer radiation belt electron flux using solar-wind parameters and geomagnetic indices. "
                    "Performance degrades during extreme geomagnetic storms because such samples are sparse."
                ),
                extra_text="磁暴只作为极端样本条件被提及，不是正文主研究对象。",
                context="article_summary",
            )
            kataoka_tags = review_generated_tags(
                ["方法/多通带滤波", "事件/磁暴", "仪器/极光图像", "仪器/RGB传感器"],
                root=root,
                title_text="Compact all-sky auroral imager using multi band-pass filter and full-color sensor",
                body_text=(
                    "The paper presents the design and performance of a compact all-sky auroral imager and shows an example data set "
                    "obtained during a magnetic storm event."
                ),
                extra_text="磁暴事件只用于示例观测，不是文章主旨。",
                context="article_summary",
            )

            self.assertNotIn("事件/磁暴", li_tags)
            self.assertNotIn("事件/磁暴", kataoka_tags)
            self.assertIn("对象/太阳风", li_tags)
            self.assertIn("仪器/极光图像", kataoka_tags)

    def test_review_generated_tags_drops_gravity_wave_when_it_is_secondary_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                ["对象/重力波", "对象/电离层/高纬", "事件/磁暴", "仪器/SABER"],
                root=root,
                title_text="Mid- and high-latitude ionospheric responses to the Mother's Day super geomagnetic storm",
                body_text=(
                    "The paper studies ionospheric disturbance during the Mother's Day storm using VLF propagation and SABER data. "
                    "Wavelet analysis also identifies gravity-wave signatures."
                ),
                extra_text="重力波只是结果之一，不是标题或正文主研究对象。",
                context="article_summary",
            )

            self.assertNotIn("对象/重力波", tags)
            self.assertIn("事件/磁暴", tags)
            self.assertIn("仪器/SABER", tags)

    def test_review_generated_tags_drops_satellite_impact_for_diffusion_method_paper(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                ["对象/高能粒子/电子", "对象/波粒相互作用/合声波", "对象/波动/EMIC波", "对象/波动/嘶声", "模型/辐射带模型", "应用/卫星影响"],
                root=root,
                title_text="Calculating quasi-linear diffusion rates using different methods to specify the wave spectrum",
                body_text=(
                    "The paper compares diffusion-rate calculations in radiation belt models and argues that uncertainty is more likely due "
                    "to wave-data sampling than to the calculation method itself."
                ),
                extra_text="文章不直接涉及卫星阻力、轨道维持、故障风险或业务化卫星环境评估。",
                context="article_summary",
            )

            self.assertNotIn("应用/卫星影响", tags)
            self.assertIn("模型/辐射带模型", tags)

    def test_review_generated_tags_drops_sun_earth_coupling_for_partial_process_paper(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                ["对象/日地耦合", "对象/太阳风", "对象/磁层/弓激波", "对象/磁鞘/喷流"],
                root=root,
                title_text="Foreshock structures and magnetosheath jets near the terrestrial bow shock",
                body_text="The paper studies how IMF rotation and solar-wind structures relate to bow-shock geometry and magnetosheath jets near Earth.",
                extra_text="本文聚焦弓激波前结构与磁鞘喷流对应关系，不讨论太阳到电离层或热层的跨圈层耦合链条。",
                context="article_summary",
            )

            self.assertNotIn("对象/日地耦合", tags)
            self.assertNotIn("对象/太阳风", tags)
            self.assertIn("对象/磁层/弓激波", tags)

    def test_review_generated_tags_keeps_sun_earth_coupling_for_multi_sphere_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                ["对象/日地耦合", "对象/太阳风", "对象/磁层", "对象/电离层", "对象/热层"],
                root=root,
                title_text="Sun-to-Earth coupling from solar-wind driving to magnetosphere-ionosphere-thermosphere response",
                body_text="The paper analyzes how solar-wind forcing drives coupled magnetosphere, ionosphere, and thermosphere responses across the Sun-to-Earth chain.",
                extra_text="研究强调从太阳风输入到磁层、电离层和热层响应的多圈层耦合传递。",
                context="article_summary",
            )

            self.assertIn("对象/日地耦合", tags)

    def test_review_generated_tags_does_not_treat_existing_doi_tag_line_as_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            body = "\n".join(
                [
                    "- [DOI](https://doi.org/example) #对象/日地耦合 #对象/磁层/太阳风耦合",
                    "- 本文研究太阳风磁场与地面地磁场的谱特征及其非平稳性。",
                    "- 结果说明太阳风中的窄带过程会耦合进入地球局地地磁环境，并与磁层和电离层局地过程区分开来。",
                ]
            )
            tags = review_generated_tags(
                ["对象/日地耦合", "对象/磁层/太阳风耦合", "对象/电离层"],
                root=root,
                title_text="Solar wind and geomagnetic field spectral peaks",
                body_text=body,
                context="output_rewrite",
            )

            self.assertNotIn("对象/日地耦合", tags)
            self.assertIn("对象/磁层/太阳风耦合", tags)

    def test_review_generated_tags_drops_low_value_pending_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                ["对象/区域/阿拉斯加", "对象/极区/极光电流片"],
                root=root,
                title_text="Polar auroral current sheet over Alaska",
                body_text="The paper discusses a polar auroral current sheet structure.",
                context="article_summary",
                record_candidates=True,
            )

            self.assertNotIn("对象/区域/阿拉斯加", tags)
            self.assertIn("对象/极区/极光电流片", tags)

    def test_review_generated_tags_drops_broad_data_analysis_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                ["方法/数据分析", "数据分析", "对象/磁层/弓激波"],
                root=root,
                title_text="Foreshock bubble boundary shocks",
                body_text="The paper studies bow shock related structures with multi-spacecraft observations.",
                context="article_summary",
                record_candidates=True,
            )

            self.assertNotIn("方法/数据分析", tags)
            self.assertNotIn("数据分析", tags)
            self.assertIn("对象/磁层/弓激波", tags)

    def test_review_generated_tags_limits_pending_candidates_per_article(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                [
                    "对象/极区/极光电流片",
                    "对象/太阳活动/高低活动年",
                    "方法/射线追踪",
                    "仪器/天琴",
                    "应用/影响/激光偏折",
                ],
                root=root,
                title_text="Ray-tracing assessment for TianQin pointing error under space plasma conditions",
                body_text="This study uses ray tracing and TianQin payload context to estimate pointing error caused by space plasma.",
                context="article_summary",
                record_candidates=True,
            )

            pending = [tag for tag in tags if tag not in {"应用/空间天气"} and tag.startswith(("对象/", "仪器/", "方法/", "应用/"))]
            self.assertLessEqual(len([tag for tag in pending if tag not in {"方法/建模/机器学习"}]), 2)

    def test_review_generated_tags_rewrites_overlapping_pending_to_formal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                [
                    "对象/太阳活动/耀斑",
                    "方法/深度学习",
                    "对象/电离层/振幅闪烁",
                    "应用/预报/短期预测",
                    "仪器/TIMED-SABER",
                ],
                root=root,
                title_text="Deep-learning prediction of ionospheric amplitude scintillation after solar flare forcing",
                body_text="The study uses a deep-learning model to predict ionospheric amplitude scintillation and compares the result with TIMED/SABER observations after solar flare forcing.",
                context="article_summary",
                record_candidates=True,
            )

            self.assertIn("事件/太阳耀斑", tags)
            self.assertIn("方法/建模/机器学习", tags)
            self.assertIn("对象/电离层/闪烁", tags)
            self.assertIn("应用/预测", tags)
            self.assertIn("仪器/SABER", tags)
            self.assertNotIn("对象/太阳活动/耀斑", tags)
            self.assertNotIn("方法/深度学习", tags)
            self.assertNotIn("对象/电离层/振幅闪烁", tags)
            self.assertNotIn("应用/预报/短期预测", tags)
            self.assertNotIn("仪器/TIMED-SABER", tags)

    def test_review_generated_tags_governs_abstract_and_misrooted_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                [
                    "对象/空间天气/地磁暴",
                    "对象/物理机制/Joule加热",
                    "仪器/磁力计",
                    "应用/空间天气/预报",
                    "应用/业务化预报",
                    "模型/物理模型",
                    "对象/卫星",
                    "应用/卫星再入/轨迹预测",
                ],
                root=root,
                title_text="Satellite reentry predictions during geomagnetic storms and sudden stratospheric warmings",
                body_text=(
                    "The study evaluates satellite re-entry trajectory prediction and orbit decay during SSW. "
                    "It studies geomagnetic storms and Joule heating, using magnetometer data."
                ),
                extra_text="摘要没有说明这是业务化 operational forecast system。",
                context="article_summary",
                max_tags=14,
                record_candidates=True,
            )

            refresh_pending_tag_files(root)
            payload = json.loads((root / "config" / "pending_tags.json").read_text(encoding="utf-8"))

        self.assertIn("事件/磁暴", tags)
        self.assertIn("对象/极区/焦耳加热", tags)
        self.assertIn("仪器/磁强计", tags)
        self.assertIn("应用/预测", tags)
        self.assertIn("应用/卫星轨道衰减", tags)
        self.assertNotIn("应用/业务化预报", tags)
        self.assertNotIn("模型/物理模型", tags)
        self.assertNotIn("对象/卫星", tags)
        for bad_tag in (
            "对象/空间天气/地磁暴",
            "对象/物理机制/Joule加热",
            "仪器/磁力计",
            "应用/空间天气/预报",
            "模型/物理模型",
            "对象/卫星",
        ):
            self.assertNotIn(bad_tag, payload["tags"])

    def test_review_generated_tags_unifies_planetary_environment_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)
            (root / "config" / "tag" / "formal_tags.md").write_text(
                (root / "config" / "tag" / "formal_tags.md")
                .read_text(encoding="utf-8")
                .replace("行星空间环境【AI总结】", "行星际环境")
                .replace("行星空间环境", "行星际环境"),
                encoding="utf-8",
            )

            tags = review_generated_tags(
                [
                    "对象/行星空间环境",
                    "对象/行星空间环境/IMF构型",
                    "对象/行星际环境/IMF构型",
                    "对象/行星际环境/日冕物质抛射CME",
                ],
                root=root,
                title_text="Venus induced magnetosphere under different IMF configurations",
                body_text="The paper studies IMF configurations, CME-related interplanetary conditions, and geomagnetic storm response.",
                context="article_summary",
                max_tags=10,
                record_candidates=True,
            )

            refresh_pending_tag_files(root)
            payload = json.loads((root / "config" / "pending_tags.json").read_text(encoding="utf-8"))

        self.assertIn("对象/行星际环境", tags)
        self.assertIn("指数/IMF", tags)
        self.assertIn("事件/磁暴/CME", tags)
        self.assertNotIn("对象/行星空间环境", tags)
        self.assertNotIn("对象/行星际环境/IMF构型", tags)
        self.assertNotIn("对象/行星际环境/日冕物质抛射CME", tags)
        self.assertEqual(payload["tags"], {})

    def test_reconcile_auto_output_tags_with_review_rewrites_outputs_and_clears_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)
            output_dir = root / "out" / "auto" / "article_summaries"
            output_dir.mkdir(parents=True, exist_ok=True)
            sample = output_dir / "sample.md"
            sample.write_text(
                "\n".join(
                    [
                        "# 示例",
                        "- 标签： #磁暴 #热层/风 #太阳/日冕",
                        "- 正文： 讨论热层风场、太阳日冕结构以及磁暴期间的响应。",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            before = run_tag_output_review(root)
            self.assertFalse(before.passed)

            result = reconcile_auto_output_tags_with_review(root)
            self.assertEqual(result.scanned_files, 1)
            rewritten = sample.read_text(encoding="utf-8")
            self.assertIn("#事件/磁暴", rewritten)
            self.assertIn("#对象/热层/风场", rewritten)
            self.assertIn("#对象/太阳/日冕", rewritten)

            after = run_tag_output_review(root)
            self.assertTrue(after.passed)

            payload = json.loads((root / "config" / "pending_tags.json").read_text(encoding="utf-8"))
            self.assertNotIn("对象/太阳/日冕", payload["tags"])

    def test_reconcile_all_auto_outputs_rewrites_reports_but_pending_ignores_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)
            summary_dir = root / "out" / "auto" / "article_summaries"
            deep_dir = root / "out" / "auto" / "deep_reads"
            report_dir = root / "out" / "research_reports"
            summary_dir.mkdir(parents=True, exist_ok=True)
            deep_dir.mkdir(parents=True, exist_ok=True)
            report_dir.mkdir(parents=True, exist_ok=True)
            (summary_dir / "summary.md").write_text(
                "\n".join(
                    [
                        "# Summary",
                        "- 标签： #对象/空间天气/地磁暴 #对象/物理机制/Joule加热 #仪器/磁力计 #模型/物理模型",
                        "- 正文： 本文研究地磁暴、Joule heating 和 magnetometer data。",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (deep_dir / "deep.md").write_text(
                "# Deep\n- [PDF](<../deep_reads_pdf/a.pdf>) #对象/卫星 #事件/卫星会合 #指数/Kp\n\nSatellite conjunction assessment with Kp.\n",
                encoding="utf-8",
            )
            report = report_dir / "2026-05-06 周报.md"
            report.write_text(
                "\n".join(
                    [
                        "# Report",
                        "- 本周研究地磁暴响应和空间天气预测。",
                        "1. 英文题目：Example",
                        "   - 标签： #对象/空间天气/地磁暴 #应用/空间天气预报 #信息来源/仅摘要",
                        "2. 英文题目：Ionosphere",
                        "   - 标签： #对象/电离层 #信息来源/仅摘要",
                        "3. 英文题目：High-latitude ionosphere",
                        "   - 标签： #对象/电离层/高纬 #信息来源/仅摘要",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = reconcile_all_auto_output_tags_with_review(root)
            rewritten_summary = (summary_dir / "summary.md").read_text(encoding="utf-8")
            rewritten_deep = (deep_dir / "deep.md").read_text(encoding="utf-8")
            rewritten_report = report.read_text(encoding="utf-8")
            review = run_tag_output_review(root)
            refresh_pending_tag_files(root)
            payload = json.loads((root / "config" / "pending_tags.json").read_text(encoding="utf-8"))

        self.assertEqual(result.scanned_files, 3)
        self.assertIn("#事件/磁暴", rewritten_summary)
        self.assertIn("#对象/极区/焦耳加热", rewritten_summary)
        self.assertIn("#仪器/磁强计", rewritten_summary)
        self.assertNotIn("#模型/物理模型", rewritten_summary)
        self.assertNotIn("#对象/卫星", rewritten_deep)
        self.assertIn("#事件/卫星会合", rewritten_deep)
        self.assertIn("   - 标签： #事件/磁暴 #应用/预测 #信息来源/仅摘要", rewritten_report)
        self.assertIn("   - 标签： #对象/电离层 #信息来源/仅摘要", rewritten_report)
        self.assertIn("   - 标签： #对象/电离层/高纬 #信息来源/仅摘要", rewritten_report)
        self.assertTrue(review.passed)
        self.assertEqual(payload["tags"], {})

    def test_tag_output_review_audits_summaries_deep_reads_and_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)
            summary_dir = root / "out" / "auto" / "article_summaries"
            deep_dir = root / "out" / "auto" / "deep_reads"
            report_dir = root / "out" / "research_reports"
            summary_dir.mkdir(parents=True, exist_ok=True)
            deep_dir.mkdir(parents=True, exist_ok=True)
            report_dir.mkdir(parents=True, exist_ok=True)
            summary = summary_dir / "summary.md"
            deep = deep_dir / "deep.md"
            report = report_dir / "report.md"
            summary.write_text(
                "# Summary\n- 标签： #磁暴 #热层/风\n- 正文：讨论磁暴期间的热层风场。\n",
                encoding="utf-8",
            )
            deep.write_text(
                "# Deep\n- [PDF](<../deep_reads_pdf/a.pdf>) #对象/物理机制/电学放电现象 #对象/过程/场向电流 #事件/亚暴\n\n亚暴和场向电流。\n",
                encoding="utf-8",
            )
            report.write_text(
                "# Report\n1. 英文题目：Example\n   - 标签： #对象/空间天气/地磁暴 #应用/空间天气预报 #信息来源/仅摘要\n",
                encoding="utf-8",
            )

            review = run_tag_output_review(root)

        self.assertFalse(review.passed)
        self.assertEqual(review.scanned_files, 3)
        issue_paths = {item.path for item in review.issues}
        self.assertEqual(issue_paths, {summary, deep, report})

    def test_deep_read_context_drops_or_downgrades_virtual_object_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                [
                    "对象/物理机制/电学放电现象",
                    "对象/能量转换/电感电路模型",
                    "对象/过程/场向电流",
                    "对象/物理机制/Joule加热",
                    "事件/亚暴",
                ],
                root=root,
                context="deep_read",
                title_text="Auroral substorms as an electrical discharge phenomenon",
                body_text="The paper discusses field-aligned currents, Joule heating, and auroral substorms.",
                max_tags=10,
            )

        self.assertNotIn("对象/物理机制/电学放电现象", tags)
        self.assertNotIn("对象/能量转换/电感电路模型", tags)
        self.assertNotIn("对象/过程/场向电流", tags)
        self.assertIn("模型/电路模型", tags)
        self.assertIn("对象/磁层/电流体系", tags)
        self.assertIn("对象/极区/焦耳加热", tags)
        self.assertIn("事件/亚暴", tags)

    def test_review_generated_tags_does_not_keep_champ_from_chapman_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                ["仪器/CHAMP", "仪器/磁强计"],
                root=root,
                context="deep_read",
                title_text="Auroral substorms as an electrical discharge phenomenon",
                body_text="The paper cites Chapman and uses six meridian chains of magnetometers.",
                max_tags=10,
            )

        self.assertNotIn("仪器/CHAMP", tags)
        self.assertIn("仪器/磁强计", tags)

    def test_deep_read_batch_tags_rewrite_misrooted_models_and_instruments(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                [
                    "CO2",
                    "仪器/SD-WACCM",
                    "对象/EUV辐射",
                    "对象/IMAGE网络",
                    "对象/全天空相机",
                    "仪器/Swarm-C",
                    "模型/NRLMSISE-00",
                    "事件/卫星会合",
                    "指数/F10．7",
                    "对象/极地亚暴",
                    "对象/极慢太阳风",
                    "对象/西向电喷流",
                    "对象/低地球轨道",
                ],
                root=root,
                title_text="Evidence of the Lower Thermospheric Winter-to-Summer Circulation From SABER CO2 Observations",
                body_text=(
                    "The paper uses TIMED/SABER CO2 observations and SD-WACCM simulations. "
                    "A separate polar substorm case during slow solar wind uses the IMAGE magnetometer network and all-sky camera observations. "
                    "The conjunction paper uses NRLMSISE-00 with F10.7, EUV irradiance, and Kp for satellite conjunction assessment. "
                    "Gasperini et al. use Swarm-C density observations."
                ),
                context="deep_read",
                max_tags=14,
            )

        self.assertIn("对象/热层/成分", tags)
        self.assertIn("模型/WACCM", tags)
        self.assertIn("指数/EUV", tags)
        self.assertIn("仪器/磁强计", tags)
        self.assertIn("仪器/全天空相机", tags)
        self.assertIn("仪器/Swarm", tags)
        self.assertIn("模型/NRLMSISE-00", tags)
        self.assertIn("事件/卫星会合", tags)
        self.assertIn("指数/F107", tags)
        self.assertIn("事件/亚暴", tags)
        self.assertIn("对象/太阳风", tags)
        self.assertIn("对象/极区/PEJ", tags)
        self.assertIn("应用/卫星轨道", tags)
        self.assertNotIn("仪器/CO2", tags)
        self.assertNotIn("仪器/SD-WACCM", tags)
        self.assertNotIn("对象/IMAGE网络", tags)
        self.assertNotIn("对象/全天空相机", tags)
        self.assertNotIn("仪器/Swarm-C", tags)
        self.assertNotIn("指数/F10．7", tags)
        self.assertNotIn("对象/极地亚暴", tags)
        self.assertNotIn("对象/极慢太阳风", tags)
        self.assertNotIn("对象/西向电喷流", tags)
        self.assertNotIn("对象/低地球轨道", tags)

    def test_deep_read_drops_champ_when_only_background_mission_example(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)

            tags = review_generated_tags(
                ["仪器/CHAMP", "模型/NRLMSISE-00", "事件/卫星会合"],
                root=root,
                title_text="Influences of Space Weather Forecasting Uncertainty on Satellite Conjunction Assessment",
                body_text=(
                    "Recent in situ measurements from satellite missions like CHAMP, GRACE, and Swarm "
                    "have provided background observations for atmospheric models. "
                    "This paper uses NRLMSISE-00 to propagate F10.7 and Kp forecast uncertainty into "
                    "satellite conjunction assessment."
                ),
                context="deep_read",
                max_tags=10,
            )

        self.assertNotIn("仪器/CHAMP", tags)
        self.assertIn("模型/NRLMSISE-00", tags)
        self.assertIn("事件/卫星会合", tags)

    def test_deep_read_output_reconcile_does_not_touch_article_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = pathlib.Path(tmpdir)
            self._seed_root(root)
            summary_dir = root / "out" / "auto" / "article_summaries"
            deep_dir = root / "out" / "auto" / "deep_reads"
            summary_dir.mkdir(parents=True, exist_ok=True)
            deep_dir.mkdir(parents=True, exist_ok=True)
            summary = summary_dir / "summary.md"
            deep = deep_dir / "deep.md"
            summary.write_text(
                "# 单篇\n- 标签： #磁暴 #热层/风\n- 正文：讨论热层风和磁暴。\n",
                encoding="utf-8",
            )
            deep.write_text(
                "# 深读\n- [PDF](<../deep_reads_pdf/example.pdf>) #对象/物理机制/电学放电现象 #对象/过程/场向电流 #事件/亚暴\n\n亚暴、极光和场向电流。\n",
                encoding="utf-8",
            )

            result = reconcile_deep_read_output_tags_with_review(root)
            summary_text = summary.read_text(encoding="utf-8")
            deep_text = deep.read_text(encoding="utf-8")
            review = run_deep_read_tag_output_review(root)

        self.assertEqual(result.scanned_files, 1)
        self.assertEqual(len(result.modified_entries), 1)
        self.assertIn("#磁暴 #热层/风", summary_text)
        self.assertNotIn("对象/物理机制", deep_text)
        self.assertIn("#对象/磁层/电流体系", deep_text)
        self.assertIn("#事件/亚暴", deep_text)
        self.assertTrue(review.passed)


if __name__ == "__main__":
    unittest.main()
