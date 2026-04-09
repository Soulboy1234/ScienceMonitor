# v1.3.2 UI 细化计划

## 目标

在上一轮控制台重做基础上，继续把 `config-ui` 调整到更稳定、可读、可操作的状态。

本轮重点：

- 固定左右分栏，不再在窄窗口时把左侧导航压成上下结构
- 允许鼠标拖拽调整左侧导航宽度
- 统一修复文字超出背景框的问题
- 重排总览页信息层级，去掉重复状态展示
- 明确“周报不是自动运行，只是功能已启用”

## 范围

- `config_ui_page.py`
- `config_ui_page_sections.py`
- `ui_assets/config_ui.css`
- `ui_assets/config_ui.js`
- `tests/test_config_ui.py`
- `CHANGELOG.md`

## 非目标

- 不改 HTTP 路由
- 不改周报/深读业务逻辑
- 不引入前端框架

## Progress

- [x] 固定页面为左右分栏，移除会把导航折叠到上方的响应式规则。
- [x] 增加导航栏拖拽宽度能力，并保留合理宽度上下限。
- [x] 统一补 `min-width: 0`、`overflow-wrap` 等约束，修复所有面板的文字溢出。
- [x] 调整总览页结构，去掉重复状态展示，卡片改为纵向信息行。
- [x] 调整交互日志，移除控制面说明并修正环境状态展示。
- [x] 更新测试并跑 gate。

## 验证

- `./.venv/bin/python -m pytest tests/test_config_ui.py -q`
- `./scripts/run_science_monitor.sh entropy-check`
- `./scripts/run_science_monitor.sh harness-check`
- `./scripts/run_science_monitor.sh maintenance-check --auto-repair --max-passes 2`
- `./.venv/bin/python -m pytest -q`

## 结果

- 固定为左右分栏布局，窄窗口下不再把导航栏折叠到页面上方
- 左侧导航新增鼠标拖拽宽度能力
- 统一补充了 `min-width: 0`、`overflow-wrap: anywhere` 等约束，修复文字溢出背景框
- 总览页改为三张主卡片：
  - 运行环境
  - LLM 状态
  - 输出路径
- 卡片内部改为纵向信息行，不再嵌套额外小面板
- 顶部去掉重复的 provider / 模型 / 输出状态展示
- 交互日志移除了控制面说明；总览说明放回标题下方
- 左侧“周报模式”明确写为“手动生成已启用”，避免被理解成自动运行

## 验证结果

- `./.venv/bin/python -m pytest tests/test_config_ui.py -q` -> 通过
- `./scripts/run_science_monitor.sh entropy-check` -> 通过
- `./scripts/run_science_monitor.sh harness-check` -> 通过
- `./scripts/run_science_monitor.sh maintenance-check --auto-repair --max-passes 2` -> 通过
- `./.venv/bin/python -m pytest -q` -> 通过
