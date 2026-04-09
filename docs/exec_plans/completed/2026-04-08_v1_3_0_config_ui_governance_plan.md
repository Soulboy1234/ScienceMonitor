# 2026-04-08 v1.3.0 config UI governance plan

## Goal

Rework the local `config-ui` control surface so it matches the current harness controls without changing the core report-generation logic.

## Scope

- Make provider switching explicit and visually prominent.
- Show public `config/paths.json`, local private `config/local.paths.json`, and the effective output path separately.
- Add a minimal `chatgpt_web_manual` status panel for pending/ready/stale requests.
- Add a minimal UI import action for already-created manual response JSON files.
- Keep existing report/deep-read operation buttons working.
- Keep runtime data, logs, caches, and local private paths out of versioned source.
- Cover the changed UI behavior with tests.

## Non-goals

- Do not redesign the entire visual style.
- Do not add weekly-report strong content review.
- Do not migrate historical outputs.
- Do not commit `config/local.paths.json`.
- Do not change the manual request generation format.

## Progress

- [x] Audit current UI and control paths.
- [x] Implement UI control surface updates.
- [x] Add tests.
- [x] Validate with `pytest` / `harness-check` / `entropy-check` / `git diff --check`.

## Validation status

- `./.venv/bin/python -m pytest tests/test_config_ui.py -q` -> `6 passed`
- `./scripts/run_science_monitor.sh harness-check` -> passed
- `./scripts/run_science_monitor.sh entropy-check` -> passed
- `./.venv/bin/python -m pytest -q` -> `133 passed`
- `./scripts/run_science_monitor.sh maintenance-check --auto-repair --max-passes 2` -> passed
- `git diff --check` -> passed

## Result

- Provider switching is now prominent in the settings form.
- The UI separates public `config/paths.json`, private `config/local.paths.json`, and the effective runtime output path.
- The UI shows compact `chatgpt_web_manual` request status and provides an import form for existing response JSON files.
- UI save logic preserves public path config and writes private local paths only to `config/local.paths.json`.
- Tests cover the new render and save behavior.
