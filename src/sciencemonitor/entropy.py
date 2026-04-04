from __future__ import annotations

import ast
import json
from dataclasses import dataclass
from pathlib import Path

from .config import project_root


@dataclass(frozen=True)
class EntropyIssue:
    category: str
    subject: str
    metric: int | str
    limit: int | str
    severity: str
    message: str


@dataclass(frozen=True)
class EntropyCheckReport:
    passed: bool
    module_line_counts: dict[str, int]
    function_lengths: dict[str, int]
    import_cycles: list[tuple[str, ...]]
    unused_imports: dict[str, list[str]]
    issues: list[EntropyIssue]
    budget_path: Path


def maintenance_budget_path(root: Path | None = None) -> Path:
    return (root or project_root()) / "config" / "maintenance_budget.json"


def load_maintenance_budget(root: Path | None = None) -> dict:
    path = maintenance_budget_path(root)
    if not path.exists():
        raise FileNotFoundError(f"缺少维护预算文件：{path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("maintenance_budget.json 顶层必须是对象。")
    return payload


def run_entropy_check(root: Path | None = None) -> EntropyCheckReport:
    project = root or project_root()
    budget = load_maintenance_budget(project)
    source_root = project / "src" / "sciencemonitor"
    module_line_counts = _collect_module_line_counts(source_root)
    function_lengths = _collect_function_lengths(source_root)
    import_cycles = _collect_import_cycles(source_root)
    unused_imports = _collect_unused_imports(source_root)
    issues = _evaluate_entropy_budget(
        budget=budget,
        module_line_counts=module_line_counts,
        function_lengths=function_lengths,
        import_cycles=import_cycles,
        unused_imports=unused_imports,
    )
    return EntropyCheckReport(
        passed=not issues,
        module_line_counts=module_line_counts,
        function_lengths=function_lengths,
        import_cycles=import_cycles,
        unused_imports=unused_imports,
        issues=issues,
        budget_path=maintenance_budget_path(project),
    )


def render_entropy_check_summary(report: EntropyCheckReport) -> str:
    lines = [
        "Entropy check summary:",
        f"- passed={report.passed}",
        f"- issues={len(report.issues)}",
        f"- budget={report.budget_path}",
    ]
    largest_modules = sorted(report.module_line_counts.items(), key=lambda item: item[1], reverse=True)[:5]
    if largest_modules:
        lines.append("- largest_modules:")
        for name, count in largest_modules:
            lines.append(f"  - {name}: {count}")
    if report.import_cycles:
        lines.append("- import_cycles:")
        for cycle in report.import_cycles:
            lines.append(f"  - {' -> '.join(cycle)} -> {cycle[0]}")
    if report.unused_imports:
        lines.append("- unused_imports:")
        for module_name, sources in sorted(report.unused_imports.items()):
            lines.append(f"  - {module_name}: {', '.join(sources)}")
    if report.issues:
        lines.append("- violations:")
        for issue in report.issues:
            lines.append(f"  - [{issue.severity}] {issue.message}")
    else:
        lines.append("- violations: none")
    return "\n".join(lines)


def _collect_module_line_counts(source_root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in sorted(source_root.glob("*.py")):
        counts[path.name] = sum(1 for _ in path.open("r", encoding="utf-8"))
    return counts


def _collect_function_lengths(source_root: Path) -> dict[str, int]:
    lengths: dict[str, int] = {}
    for path in sorted(source_root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and hasattr(node, "end_lineno"):
                key = f"{path.name}::{node.name}"
                lengths[key] = int(node.end_lineno) - int(node.lineno) + 1
    return lengths


def _collect_import_cycles(source_root: Path) -> list[tuple[str, ...]]:
    modules = {path.stem: path for path in source_root.glob("*.py")}
    imports: dict[str, set[str]] = {name: set() for name in modules}
    for name, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                target = _resolve_import_target(node.module, modules)
                if target and target != name:
                    imports[name].add(target)
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith("from ."):
                continue
            target = stripped.split()[1][1:].split(".")[0]
            if target in modules and target != name:
                imports[name].add(target)

    cycles: set[tuple[str, ...]] = set()

    def dfs(start: str, node: str, path: list[str]) -> None:
        for nxt in sorted(imports[node]):
            if nxt == start and len(path) > 1:
                rotations = [tuple(path[i:] + path[:i]) for i in range(len(path))]
                cycles.add(min(rotations))
                continue
            if nxt in path or len(path) >= len(modules):
                continue
            dfs(start, nxt, path + [nxt])

    for module_name in sorted(modules):
        dfs(module_name, module_name, [module_name])
    return sorted(cycles)


def _collect_unused_imports(source_root: Path) -> dict[str, list[str]]:
    unused: dict[str, list[str]] = {}
    for path in sorted(source_root.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        tree = ast.parse(text)
        used_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        module_unused: list[str] = []
        for node in tree.body:
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if _is_compatibility_reexport_import(node, lines):
                continue
            for alias in node.names:
                alias_name = alias.asname or alias.name.split(".")[-1]
                if alias_name == "annotations" or alias_name in used_names:
                    continue
                import_source = alias.name if isinstance(node, ast.Import) else f"{node.module}.{alias.name}" if node.module else alias.name
                module_unused.append(import_source)
        if module_unused:
            unused[path.name] = sorted(module_unused)
    return unused


def _is_compatibility_reexport_import(node: ast.Import | ast.ImportFrom, lines: list[str]) -> bool:
    start = int(node.lineno) - 1
    end = int(getattr(node, "end_lineno", node.lineno))
    for index in range(start, min(end, len(lines))):
        if "Compatibility re-export" in lines[index]:
            return True

    index = start - 1
    while index >= 0:
        stripped = lines[index].strip()
        if not stripped:
            index -= 1
            continue
        if stripped.startswith("#") and "Compatibility re-export" in stripped:
            return True
        return False
    return False


def _resolve_import_target(module: str | None, modules: dict[str, Path]) -> str | None:
    if not module:
        return None
    if module.startswith("sciencemonitor."):
        target = module.split(".", 1)[1].split(".", 1)[0]
        return target if target in modules else None
    if module.startswith("."):
        target = module[1:].split(".", 1)[0]
        return target if target in modules else None
    return None


def _evaluate_entropy_budget(
    *,
    budget: dict,
    module_line_counts: dict[str, int],
    function_lengths: dict[str, int],
    import_cycles: list[tuple[str, ...]],
    unused_imports: dict[str, list[str]],
) -> list[EntropyIssue]:
    global_limits = budget.get("global_limits", {})
    default_module_limit = int(global_limits.get("default_module_max_lines", 600))
    default_function_limit = int(global_limits.get("default_function_max_lines", 80))
    package_total_limit = int(global_limits.get("package_total_max_lines", 0))
    module_limits = {str(key): int(value) for key, value in budget.get("module_line_limits", {}).items()}
    function_limits = {str(key): int(value) for key, value in budget.get("function_length_limits", {}).items()}
    allowed_cycles = {tuple(item) for item in budget.get("allowed_import_cycles", []) if isinstance(item, list)}

    package_total = sum(module_line_counts.values())
    return [
        *_package_total_issues(package_total=package_total, package_total_limit=package_total_limit),
        *_module_line_issues(
            module_line_counts=module_line_counts,
            module_limits=module_limits,
            default_module_limit=default_module_limit,
        ),
        *_function_length_issues(
            function_lengths=function_lengths,
            function_limits=function_limits,
            default_function_limit=default_function_limit,
        ),
        *_import_cycle_issues(import_cycles=import_cycles, allowed_cycles=allowed_cycles),
        *_unused_import_issues(unused_imports),
    ]


def _package_total_issues(*, package_total: int, package_total_limit: int) -> list[EntropyIssue]:
    if not package_total_limit or package_total <= package_total_limit:
        return []
    return [
        EntropyIssue(
            category="package_total_lines",
            subject="src/sciencemonitor",
            metric=package_total,
            limit=package_total_limit,
            severity="error",
            message=f"总代码行数超出预算：{package_total} > {package_total_limit}",
        )
    ]


def _module_line_issues(
    *,
    module_line_counts: dict[str, int],
    module_limits: dict[str, int],
    default_module_limit: int,
) -> list[EntropyIssue]:
    issues: list[EntropyIssue] = []
    for module_name, line_count in sorted(module_line_counts.items()):
        limit = module_limits.get(module_name, default_module_limit)
        if line_count > limit:
            issues.append(
                EntropyIssue(
                    category="module_lines",
                    subject=module_name,
                    metric=line_count,
                    limit=limit,
                    severity="error",
                    message=f"{module_name} 行数超出预算：{line_count} > {limit}",
                )
            )
    return issues


def _function_length_issues(
    *,
    function_lengths: dict[str, int],
    function_limits: dict[str, int],
    default_function_limit: int,
) -> list[EntropyIssue]:
    issues: list[EntropyIssue] = []
    for function_name, length in sorted(function_lengths.items()):
        limit = function_limits.get(function_name, default_function_limit)
        if length > limit:
            issues.append(
                EntropyIssue(
                    category="function_lines",
                    subject=function_name,
                    metric=length,
                    limit=limit,
                    severity="error",
                    message=f"{function_name} 长度超出预算：{length} > {limit}",
                )
            )
    return issues


def _import_cycle_issues(
    *,
    import_cycles: list[tuple[str, ...]],
    allowed_cycles: set[tuple[str, ...]],
) -> list[EntropyIssue]:
    issues: list[EntropyIssue] = []
    for cycle in import_cycles:
        if cycle not in allowed_cycles:
            issues.append(
                EntropyIssue(
                    category="import_cycle",
                    subject=" -> ".join(cycle),
                    metric="cycle",
                    limit="allowed list",
                    severity="error",
                    message=f"发现未登记的 import cycle：{' -> '.join(cycle)} -> {cycle[0]}",
                )
            )
    return issues


def _unused_import_issues(unused_imports: dict[str, list[str]]) -> list[EntropyIssue]:
    issues: list[EntropyIssue] = []
    for module_name, imports in sorted(unused_imports.items()):
        for import_source in imports:
            issues.append(
                EntropyIssue(
                    category="unused_import",
                    subject=f"{module_name}::{import_source}",
                    metric="unused",
                    limit="0",
                    severity="error",
                    message=f"{module_name} 存在未使用导入：{import_source}",
                )
            )
    return issues
