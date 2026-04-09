# v1.3.1 UI 重做计划

## 目标

把当前 `config-ui` 从“配置表单堆叠页”重做成更接近 Codex 的控制台：

- 左侧导航负责模块切换
- 右侧主体同时承载交互日志和操作界面
- 周报、深度解读作为主导航模块显式前置
- 继续保留 provider、路径、本机私有配置、人工中转导入等核心控制能力

## 范围

- 重做 `config_ui_page.py` 的页面结构、样式和导航交互
- 必要时微调 `config_ui.py` 传入页面的数据结构
- 更新 `tests/test_config_ui.py`
- 更新 `CHANGELOG.md`

## 非目标

- 不改运行时业务逻辑
- 不改 `config-ui` 的 HTTP 接口路径
- 不在这一轮引入新的前端框架
- 不处理 GitHub 提交和发布

## 设计原则

1. 页面结构优先清晰，不追求花哨。
2. 左侧导航至少包含：
   - 周报
   - 深度解读
3. 右侧上半区显示交互日志/状态，下半区显示当前模块操作界面。
4. 保留现有控制面能力，避免“好看但不能用”。
5. 对外仍是单文件 HTML，减少前端熵。

## Progress

- [x] 重写页面骨架、样式和导航结构。
- [x] 把周报、深度解读、人工中转、配置表单按模块重新布局。
- [x] 把状态 banner、doctor 告警、人工中转状态整合到“交互日志”区域。
- [x] 调整测试，确保关键入口仍可见、关键字段仍可提交。
- [x] 跑 UI 定向测试、harness-check、全量测试。

## 验证

- `./.venv/bin/python -m pytest tests/test_config_ui.py -q`
- `./scripts/run_science_monitor.sh harness-check`
- `./scripts/run_science_monitor.sh entropy-check`
- `./scripts/run_science_monitor.sh maintenance-check --auto-repair --max-passes 2`
- `./.venv/bin/python -m pytest -q`

## 完成标准

- 左侧导航和右侧主体区可正常渲染
- 周报、深度解读入口明显可见
- provider、路径、本机私有配置、人工中转导入仍可操作
- 测试与 gate 全部通过

## 结果

- `config-ui` 已重做为左侧导航 + 右侧交互日志 / 操作区结构
- 左侧导航当前包含：总览、周报、深度解读、人工中转、设置
- 周报与深度解读已提升为主导航模块
- 页面层已从单个超大 Python 文件拆为：
  - `config_ui_page.py`
  - `config_ui_page_sections.py`
  - `ui_assets/config_ui.css`
  - `ui_assets/config_ui.js`
- 熵检查已恢复通过，没有为这次页面重做放宽预算

## 验证结果

- `./.venv/bin/python -m pytest tests/test_config_ui.py -q` -> 通过
- `./scripts/run_science_monitor.sh entropy-check` -> 通过
- `./scripts/run_science_monitor.sh harness-check` -> 通过
- `./scripts/run_science_monitor.sh maintenance-check --auto-repair --max-passes 2` -> 通过
- `./.venv/bin/python -m pytest -q` -> 通过
