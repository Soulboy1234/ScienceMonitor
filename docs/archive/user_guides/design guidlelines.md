# Design Guidlelines

## 核心设计原则

- 输出优先服务科研阅读，而不是服务爬虫展示
- 标签要简洁、稳定、可统计
- 规则层必须可解释，LLM 层必须可替换
- 目录结构要长期可维护，输出、日志、文档分开

## 输出设计

- 周报强调概览、重点论文、主题聚焦、期刊汇总
- 单篇卡片强调中文概括、标签、APA 引用、正文摘要
- 单篇卡片的具体写法以 [literature_note_style_guide.md](../workflow_specs/literature_note_style_guide.md) 为准
- 新增单篇笔记时，默认还要遵守 [literature_directory_integration_guide.md](literature_directory_integration_guide.md) 的目录整合规则
- 标签适配 Obsidian，统一以 `#标签` 形式出现
- 输出侧索引统一维护在输出根目录下的 `article_index/`，新生成的单篇总结和深读应能从 `sub_index` 找回

## 系统设计

- `config/` 放配置
- `src/` 放逻辑
- 输出根目录由 [../config/paths.json](../config/paths.json) 指定，负责存放用户最终阅读输出
- `log/` 放审计和运行中间文件
- `docs/` 放说明、模板和设计文档

## 扩展原则

- 新加期刊尽量先做 ISSN 精确抓取
- 新增标签先看是否可复用已有标签
- 新增 LLM 后端必须通过统一配置接入
- 不要把核心业务逻辑写死在单一外部平台上
