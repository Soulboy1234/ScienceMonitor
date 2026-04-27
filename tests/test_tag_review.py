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
    reconcile_auto_output_tags_with_review,
    review_generated_tags,
    run_tag_output_review,
)


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


if __name__ == "__main__":
    unittest.main()
