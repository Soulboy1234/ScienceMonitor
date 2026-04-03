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
  命令行入口。负责解析 `daily`、`update`、`report`、`summaries`、`deep-read`、`doctor`、`config-ui`、`golden-eval`、`real-eval`、`entropy-check`、`maintenance-check` 等命令。

- [pipeline.py](../../src/sciencemonitor/pipeline.py)
  主流程调度器。把抓取、过滤、入库、单篇总结、周报、索引同步串起来。

- [config.py](../../src/sciencemonitor/config.py)
  配置中心。负责路径解析、`PROJECT_CONFIG.md` 同步、运行时配置加载、研究偏好加载和相关校验。

- [config_ui.py](../../src/sciencemonitor/config_ui.py)
  本地网页配置面板。负责启动 HTTP 服务、展示当前配置、自检状态，并触发保存、周报生成和深度解读操作。

- [doctor.py](../../src/sciencemonitor/doctor.py)
  环境和运行一致性自检。负责检查 `.venv`、PDF 工具、LLM provider、`PROJECT_CONFIG.md` 同步段、研究偏好落地文件、运行时模板和标签配置。  
  `./scripts/run_science_monitor.sh doctor` 调的就是它。

- [entropy.py](../../src/sciencemonitor/entropy.py)
  代码熵审计层。负责检查模块行数预算、超长函数和 import cycle 是否继续恶化。

- [maintenance.py](../../src/sciencemonitor/maintenance.py)
  代码维护循环。负责执行“审核 -> 调整 -> 测试 -> 再审核”，并输出维护报告。

- [golden_eval.py](../../src/sciencemonitor/golden_eval.py)
  Golden eval 回归层。负责生成单篇总结、周报、深度解读的稳定样例输出，和仓库里的基线文件做比对或刷新。

- [real_case_eval.py](../../src/sciencemonitor/real_case_eval.py)
  真实论文集成评测层。负责使用 `evals/real_cases/cases.json` 里的 DOI/文章页或本地 PDF，生成真实案例输出，并和 `evals/real_cases/fixtures/` 下的已认可基线比较或刷新。

- [harness.py](../../src/sciencemonitor/harness.py)
  统一 harness gate。负责把 `doctor`、`golden eval` 和可选的 `real eval fixture` 检查收成一个 `harness-check` 入口。

- [crossref.py](../../src/sciencemonitor/crossref.py)
  Crossref 抓取客户端。负责按期刊源、时间窗口获取论文元数据，也负责按 DOI/标题查询单篇论文元数据。

- [article_fetch.py](../../src/sciencemonitor/article_fetch.py)
  网页内容抓取层。负责拼接 DOI/落地页候选 URL、提取网页标题/摘要/全文/PDF 链接，并为单篇总结生成“网页全文优先、摘要回退”的输入材料。

- [http.py](../../src/sciencemonitor/http.py)
  底层 HTTP 包装。提供文本、字节、JSON 请求和超时控制。

- [html_extract.py](../../src/sciencemonitor/html_extract.py)
  HTML 页面抽取器。负责从 DOI 落地页抽标题、摘要、PDF 链接和可能的全文文本。

- [topics.py](../../src/sciencemonitor/topics.py)
  主题分类器。负责基于 `config/topics.json` 做关键词匹配、相关性打分和“是否保留该论文”的判断。

- [models.py](../../src/sciencemonitor/models.py)
  数据模型定义。主要放 `SourceConfig`、`TopicProfile`、`Paper` 这些 dataclass。

- [storage.py](../../src/sciencemonitor/storage.py)
  SQLite 持久化层。负责论文记录和周报记录的读写。

- [article_summaries.py](../../src/sciencemonitor/article_summaries.py)
  单篇总结模块。负责单篇卡片的字段生成、标签归一化、模板渲染、兼容修复和输出写入。

- [reporting.py](../../src/sciencemonitor/reporting.py)
  周报模块。负责重点论文选择、主题与期刊汇总、周报模板渲染和输出校验。

- [deep_reads.py](../../src/sciencemonitor/deep_reads.py)
  深度解读模块。负责解析输入论文、获取 PDF/全文、调用 LLM 分析、模板渲染和深读输出校验。

- [llm.py](../../src/sciencemonitor/llm.py)
  LLM 分析层。负责 provider 选择、prompt 构建、schema 约束、缓存和 LLM 返回结构的标准化。

- [tags.py](../../src/sciencemonitor/tags.py)
  标签执行层。负责 canonical 标签归一化、排序、父子压制、开放词表控制和候选标签记录。

- [tag_candidates.py](../../src/sciencemonitor/tag_candidates.py)
  候选标签审阅层。负责读取运行中积累的新标签候选，并输出审阅报告。

- [article_index.py](../../src/sciencemonitor/article_index.py)
  输出索引与链接修复。负责维护 Obsidian 输出目录下的 `article_index/` 和相关回链。

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

- 想知道“命令从哪里进”：先看 [science_monitor.py](../../science_monitor.py) 和 [cli.py](../../src/sciencemonitor/cli.py)
- 想知道“主流程怎么串”：看 [pipeline.py](../../src/sciencemonitor/pipeline.py)
- 想知道“输出为什么长这样”：看 [article_summaries.py](../../src/sciencemonitor/article_summaries.py)、[reporting.py](../../src/sciencemonitor/reporting.py)、[deep_reads.py](../../src/sciencemonitor/deep_reads.py)
- 想知道“配置为什么这么生效”：看 [config.py](../../src/sciencemonitor/config.py) 和 [doctor.py](../../src/sciencemonitor/doctor.py)
- 想知道“标签为什么被打成这样”：看 [tags.py](../../src/sciencemonitor/tags.py) 和 [tag_candidates.py](../../src/sciencemonitor/tag_candidates.py)
