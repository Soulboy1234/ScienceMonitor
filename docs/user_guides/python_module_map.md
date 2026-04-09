# Python Module Map

这个文件用来说明当前项目里各个 Python 文件的职责。  
定位是“代码地图”，不是设计规范，也不是 source-of-truth 矩阵。

如果你想快速知道：

- 从哪里启动程序
- 某个功能大概在哪个文件
- `doctor`、`config_ui`、`tags` 这些模块分别干什么

先看这份文件。

## 入口层

- [science_monitor.py](../../science_monitor.py)
  项目主入口。优先重启到项目 `.venv/bin/python`，然后转交给 `src/sciencemonitor/cli.py`。

## 核心包：`src/sciencemonitor/`

- [__init__.py](../../src/sciencemonitor/__init__.py)
  包标记文件，没有业务逻辑。

- [cli.py](../../src/sciencemonitor/cli.py)
  命令行薄入口。负责同步 `PROJECT_CONFIG.md`、加载运行默认值、构造 parser 并转交命令分发。

- [cli_support.py](../../src/sciencemonitor/cli_support.py)
  CLI 支撑层。负责子命令定义、参数注册和各命令处理函数，避免 `cli.py` 继续膨胀。

- [pipeline.py](../../src/sciencemonitor/pipeline.py)
  主流程调度器。把抓取、过滤、入库、单篇总结、周报、索引同步串起来。

- [config.py](../../src/sciencemonitor/config.py)
  配置中心。负责路径解析、运行时配置加载，以及作为外部稳定入口对 `PROJECT_CONFIG.md` 同步和研究偏好能力做统一导出。

- [project_config_markdown.py](../../src/sciencemonitor/project_config_markdown.py)
  `PROJECT_CONFIG.md` 控制面工具层。负责同步块扫描、JSON 配置块解析和配置面板 Markdown 正文生成。

- [research_preferences.py](../../src/sciencemonitor/research_preferences.py)
  研究偏好配置层。负责研究偏好 JSON 的标准化、校验、`PROJECT_CONFIG.md` 同步段解析和用户偏好画像构造。

- [config_ui.py](../../src/sciencemonitor/config_ui.py)
  本地网页配置面板入口。负责启动 HTTP 服务、处理请求、解析表单并调度配置保存、周报生成和深度解读动作。

- [config_ui_page.py](../../src/sciencemonitor/config_ui_page.py)
  配置面板渲染层。负责配置 UI 的页面布局、状态条、操作卡片和表单 HTML 片段。

- [config_ui_review.py](../../src/sciencemonitor/config_ui_review.py)
  配置面板结构审查层。负责检查 UI 的关键 HTML 片段、关键 CSS/JS 片段是否存在，避免说明、类名和交互钩子悄悄回退。

- [config_ui_functional_review.py](../../src/sciencemonitor/config_ui_functional_review.py)
  配置面板功能审查层。负责用浏览器模拟导航切换、标题更新、滚动复位和 provider 切换，验证 UI 的核心交互是否真的可用。

- [config_ui_visual_review.py](../../src/sciencemonitor/config_ui_visual_review.py)
  配置面板视觉审查层。负责在固定视口下检查周报页等关键布局是否同排、是否溢出、表单节奏是否均匀，并留存截图。

- [chatgpt_web_manual.py](../../src/sciencemonitor/chatgpt_web_manual.py)
  ChatGPT 网页人工中转层。负责生成请求包、保存 prompt/schema/template、导入人工响应、校验 JSON 结构并维护请求状态。

- [doctor.py](../../src/sciencemonitor/doctor.py)
  环境和运行一致性自检。负责检查 `.venv`、PDF 工具、LLM provider、`PROJECT_CONFIG.md` 同步段、研究偏好落地文件、运行时模板和标签配置。  
  `./scripts/run_science_monitor.sh doctor` 调的就是它。

- [entropy.py](../../src/sciencemonitor/entropy.py)
  代码熵审计层。负责检查模块有效代码行预算、超长函数、import cycle 和 unused import 是否继续恶化。

- [maintenance.py](../../src/sciencemonitor/maintenance.py)
  代码维护循环。负责执行“审核 -> 调整 -> 测试 -> 再审核”，并输出维护报告。

- [golden_eval.py](../../src/sciencemonitor/golden_eval.py)
  Golden eval 回归层。负责生成单篇总结、周报、深度解读的稳定样例输出，和仓库里的基线文件做比对或刷新。

- [real_case_eval.py](../../src/sciencemonitor/real_case_eval.py)
  真实论文集成评测主流程。负责读取真实案例、编排单篇总结/周报/深度解读评测运行，并落地评测产物。

- [real_case_outputs.py](../../src/sciencemonitor/real_case_outputs.py)
  真实案例结果治理层。负责 fixture 比较、漂移 diff、结果汇总文本和评测输出标准化。

- [harness.py](../../src/sciencemonitor/harness.py)
  统一 harness gate。负责把 `doctor`、`golden eval` 和可选的 `real eval fixture` 检查收成一个 `harness-check` 入口。

- [harness_audit.py](../../src/sciencemonitor/harness_audit.py)
  Harness 自监督层。负责评估当前 harness 是否还覆盖了当前工作流的关键风险点，并输出审计报告。

- [harness_optimize.py](../../src/sciencemonitor/harness_optimize.py)
  Harness 优化层。负责按 harness 审计结论做低风险、确定性的治理修补，并生成前后对比报告。

- [crossref.py](../../src/sciencemonitor/crossref.py)
  Crossref 抓取客户端。负责按期刊源、时间窗口获取论文元数据，也负责按 DOI/标题查询单篇论文元数据。

- [article_fetch.py](../../src/sciencemonitor/article_fetch.py)
  文章来源获取层。负责拼接 DOI/落地页候选 URL、提取网页标题/摘要/全文/PDF 链接、落本地 PDF 文本，并生成单篇总结/深读可复用的来源材料与缓存。

- [article_source_text.py](../../src/sciencemonitor/article_source_text.py)
  科学正文整理层。负责把 PDF/网页全文清洗成“科学文本”，并从全文中抽取摘要、方法、结果、结论证据包，供单篇总结和深度解读复用。

- [http.py](../../src/sciencemonitor/http.py)
  底层 HTTP 包装。提供文本、字节、JSON 请求和超时控制。

- [html_extract.py](../../src/sciencemonitor/html_extract.py)
  HTML 页面抽取器。负责从 DOI 落地页抽标题、摘要、PDF 链接和可能的全文文本。

- [topics.py](../../src/sciencemonitor/topics.py)
  主题分类器。负责基于 `config/topics.json` 做关键词匹配、相关性打分和“是否保留该论文”的判断。

- [models.py](../../src/sciencemonitor/models.py)
  数据模型定义。主要放 `SourceConfig`、`TopicProfile`、`Paper`、`ArticleSummaryResult` 这些 dataclass。

- [storage.py](../../src/sciencemonitor/storage.py)
  SQLite 持久化层。负责论文记录和周报记录的读写。

- [article_summaries.py](../../src/sciencemonitor/article_summaries.py)
  单篇总结主流程。负责来源获取、分析调用、输出路径分配、渲染编排和审核闭环。

- [article_summary_markdown.py](../../src/sciencemonitor/article_summary_markdown.py)
  单篇总结 Markdown 工具层。负责模板契约、Markdown 解析、关联报告链接修补和 Obsidian 链接生成。

- [article_summary_text.py](../../src/sciencemonitor/article_summary_text.py)
  单篇总结文本生成层。负责标题、标签、正文、补充信息、推荐语和安全降级文本生成。

- [article_summary_meta.py](../../src/sciencemonitor/article_summary_meta.py)
  单篇总结元数据层。负责作者格式化、DOI 链接、文件命名、期刊缩写和特殊论文 override。

- [reporting.py](../../src/sciencemonitor/reporting.py)
  周报主流程。负责重点论文选择、主题与期刊汇总，以及周报渲染编排。

- [reporting_template.py](../../src/sciencemonitor/reporting_template.py)
  周报模板工具层。负责周报模板契约、模板渲染、Markdown 校验和审核修复闭环。

- [deep_reads.py](../../src/sciencemonitor/deep_reads.py)
  深度解读主流程。负责解析输入论文、获取 PDF/全文、调用 LLM 分析，以及编排深读输出写入与索引同步。

- [deep_read_markdown.py](../../src/sciencemonitor/deep_read_markdown.py)
  深度解读 Markdown 工具层。负责深读模板契约、文本规范化、结构化后处理和“生成后审核-自动修正-再审核”闭环。

- [llm.py](../../src/sciencemonitor/llm.py)
  LLM 分析主流程。负责 provider 选择、缓存、结构化执行和 LLM 返回结果标准化。现在也负责把 `chatgpt_web_manual` 接到现有分析链路。

- [llm_contracts.py](../../src/sciencemonitor/llm_contracts.py)
  LLM 合同层。负责单篇总结、周报、深度解读的 prompt 约束、schema 构造和输入文本整理工具。

- [tags.py](../../src/sciencemonitor/tags.py)
  标签执行层。负责 canonical 标签归一化、排序、父子压制、开放词表控制和候选标签记录。

- [tag_candidates.py](../../src/sciencemonitor/tag_candidates.py)
  候选标签审阅层。负责读取运行中积累的新标签候选，并输出审阅报告。

- [article_index.py](../../src/sciencemonitor/article_index.py)
  输出索引与链接修复主流程。负责维护 Obsidian 输出目录下的 `article_index/`、同步子索引、目录页和链接修复编排。

- [article_index_rules.py](../../src/sciencemonitor/article_index_rules.py)
  输出索引规则层。负责目录树常量、行星判定、页面映射、标签页规则和显示名规范化。

- [article_index_paths.py](../../src/sciencemonitor/article_index_paths.py)
  输出索引路径工具层。负责索引遍历、Obsidian 路径目标、wikilink 拼接和手工笔记路径判定。

- [source_audit.py](../../src/sciencemonitor/source_audit.py)
  来源审计模块。负责把程序抓取结果和 Crossref 精确计数做对照，辅助判断是否漏抓。

- [utils.py](../../src/sciencemonitor/utils.py)
  通用工具函数。主要是文本清洗、日期处理、指纹生成等底层小工具。

## 脚本层：`scripts/*.py`

- [launch_config_ui.py](../../scripts/launch_config_ui.py)
  本地配置面板启动器。负责选端口、复用已启动 UI、拉起 `science_monitor.py config-ui`。

- [pdfinfo_wrapper.py](../../scripts/pdfinfo_wrapper.py)
  `pdfinfo` 的 Python 包装器，用于缺少系统命令时兜底。

- [pdftoppm_wrapper.py](../../scripts/pdftoppm_wrapper.py)
  `pdftoppm` 的 Python 包装器，用于缺少系统命令时兜底。

- [pdftotext_wrapper.py](../../scripts/pdftotext_wrapper.py)
  `pdftotext` 的 Python 包装器，用于缺少系统命令时兜底。

## 测试层：`tests/*.py`

- [test_article_index.py](../../tests/test_article_index.py)
  测试输出索引和链接修复。

- [test_article_summaries.py](../../tests/test_article_summaries.py)
  测试单篇总结生成、模板契约、标签和兼容逻辑。

- [test_config.py](../../tests/test_config.py)
  测试配置加载、`PROJECT_CONFIG.md` 同步和研究偏好同步。

- [test_config_ui.py](../../tests/test_config_ui.py)
  测试本地配置面板的渲染和主要动作。

- [test_crossref.py](../../tests/test_crossref.py)
  测试 Crossref 抓取与解析逻辑。

- [test_chatgpt_web_manual.py](../../tests/test_chatgpt_web_manual.py)
  测试人工中转请求包生成、响应导入和状态流转。

- [test_deep_reads.py](../../tests/test_deep_reads.py)
  测试深度解读模板、渲染和校验逻辑。

- [test_doctor.py](../../tests/test_doctor.py)
  测试 `doctor` 的环境和一致性检查。

- [test_article_fetch.py](../../tests/test_article_fetch.py)
  测试网页摘要/全文提取和 Crossref 摘要回退。

- [test_llm.py](../../tests/test_llm.py)
  测试 LLM 层的标准化、schema 和标签处理逻辑。

- [test_pipeline.py](../../tests/test_pipeline.py)
  测试主流程串联。

- [test_real_case_eval.py](../../tests/test_real_case_eval.py)
  测试真实论文集成评测命令的基本输出。

- [test_reporting.py](../../tests/test_reporting.py)
  测试周报生成、模板契约和输出结构。

- [test_tag_candidates.py](../../tests/test_tag_candidates.py)
  测试候选标签统计和审阅报告输出。

- [test_topics.py](../../tests/test_topics.py)
  测试主题分类和保留逻辑。

- [__init__.py](../../tests/__init__.py)
  测试包标记文件，没有业务逻辑。

## 使用建议

- 想知道“命令从哪里进”：先看 [science_monitor.py](../../science_monitor.py)、[cli.py](../../src/sciencemonitor/cli.py) 和 [cli_support.py](../../src/sciencemonitor/cli_support.py)
- 想知道“主流程怎么串”：看 [pipeline.py](../../src/sciencemonitor/pipeline.py)
- 想知道“输出为什么长这样”：看 [article_summaries.py](../../src/sciencemonitor/article_summaries.py)、[reporting.py](../../src/sciencemonitor/reporting.py)、[deep_reads.py](../../src/sciencemonitor/deep_reads.py)
- 想知道“配置为什么这么生效”：看 [config.py](../../src/sciencemonitor/config.py) 和 [doctor.py](../../src/sciencemonitor/doctor.py)
- 想知道“标签为什么被打成这样”：看 [tags.py](../../src/sciencemonitor/tags.py) 和 [tag_candidates.py](../../src/sciencemonitor/tag_candidates.py)
