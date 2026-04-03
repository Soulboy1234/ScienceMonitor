# Runtime Hardening Phase 3

## Purpose / Big Picture

第三阶段从 harness engineering 的“控制面治理”进入“运行加固”。

目标不是继续整理文档，而是让程序在真正运行前就能检查出：

- 配置同步段是否可解析
- 运行时模板是否齐全且契约合法
- 标签配置是否结构完整
- 研究偏好是否能稳定落地到结构化配置

这样后续无论是在 Codex 环境、还是脱离 Codex 的独立环境运行，启动前都能尽早暴露配置和控制面问题。

## Scope

- `doctor.py`
- `config.py`
- 相关测试
- 必要的变更记录

## Progress

- [x] 新增第三阶段运行加固计划
- [x] 给 `doctor` 接入 `PROJECT_CONFIG.md` 同步段检查
- [x] 给 `doctor` 接入研究偏好落地文件结构检查
- [x] 给 `doctor` 接入三类运行时模板存在性与契约检查
- [x] 给 `doctor` 接入 `focus_tags.json` 的轻量结构检查
- [x] 补测试并验证 `doctor` CLI 输出
- [x] 给 `doctor` 接入 `PROJECT_CONFIG.md` 与运行时 JSON 的漂移检查
- [x] 新增 GitHub Actions CI，执行 consistency doctor 和 `pytest`
- [x] 新增 golden eval 框架、基线样例与本地命令
- [x] 把 golden eval 接入 CI
- [x] 给深度解读接入生成后本地审核、自动修正和复核闭环
- [x] 给单篇总结接入生成后本地审核、自动修正和复核闭环
- [x] 给周报接入轻量生成后审核，先稳定模板格式和空行结构
- [x] 进入更深一层的运行加固：更细粒度漂移检查

## Plan of Work

1. 先把 `PROJECT_CONFIG.md` 同步段和运行时落地文件之间的关系纳入检查
2. 再把三类运行时模板的存在性与契约合法性纳入检查
3. 再把 `focus_tags.json` 和研究偏好的结构有效性纳入检查
4. 最后补测试并跑全量验证

## Concrete Steps

1. 给 `doctor` 增加结构化 consistency checks
2. 保持检查逻辑尽量复用现有模板/配置校验函数，不另造一套规则
3. 为每类失败给出可定位的 warning 或 error 文案
4. 更新测试覆盖缺模板、坏配置、同步段异常等场景

## Success Criteria

- `doctor` 能覆盖当前主要运行控制面
- 关键配置问题能在启动前被明确提示
- 不引入第二套 source-of-truth
- 测试通过

## Completion Note

这一阶段已经完成。

完成标志：

- 启动前控制面检查、配置漂移检查、CI、golden eval 和真实案例 eval 已全部接入
- 报告生成不再只依赖一次模型输出，关键链路已有本地审核和自动修正闭环
- 剩余工作主要是增加更多真实案例和更细的内容审校规则，不再属于第三阶段的基础运行加固
