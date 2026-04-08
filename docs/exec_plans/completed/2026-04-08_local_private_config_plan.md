# Local Private Config Plan

## 目标

让公开仓库永远只包含通用默认路径，同时允许本机在项目内保留可见、可直接编辑的私人输出路径。

## 方案

- 新增 `config/local.paths.json` 作为本机私有覆盖文件
- `.gitignore` 忽略 `config/local.*.json`
- 程序加载顺序：
  1. 环境变量 `SCIENCEMONITOR_OUTPUT_ROOT`
  2. `config/local.paths.json`
  3. `config/paths.json`
  4. 默认 `out`
- 新增 `config/local.paths.example.json` 作为公开示例
- 更新 `PROJECT_CONFIG.md`、README 和相关测试

## 非目标

- 不把私人路径写回公开 `PROJECT_CONFIG.md`
- 不改变 `PROJECT_CONFIG.md -> config/paths.json` 的同步机制
- 不把本地私有文件上传 GitHub

## 验收

- 本机存在 `config/local.paths.json` 时，`doctor` 显示私人输出路径
- `git status` 不显示 `config/local.paths.json`
- `config/paths.json` 仍为公开安全默认值 `out`
- 配置同步和测试通过

## 完成记录

- 已实现 `config/local.paths.json` 本机私有覆盖
- 已新增公开示例 `config/local.paths.example.json`
- 已更新 `.gitignore`，只上传示例，不上传真实本机路径
- 已更新 `PROJECT_CONFIG.md`、README、AGENTS 和相关用户指南
- 已补 `tests/test_config.py` 覆盖本地覆盖优先级
