import ast
from pathlib import Path
from typing import Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
PYTHON_SOURCE_DIRECTORIES: Final[tuple[Path, ...]] = (
    PROJECT_ROOT / "src" / "cloud_automations",
    PROJECT_ROOT / "tests",
)
PROHIBITED_NAMES: Final[frozenset[str]] = frozenset({"Any", "Protocol", "cast", "dataclass", "print"})


def source_paths() -> list[Path]:
    """Return every application and test Python source file."""

    return [path for directory in PYTHON_SOURCE_DIRECTORIES for path in sorted(directory.rglob("*.py"))]


def documented_nodes(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef]:
    """Return every Python definition requiring a docstring."""

    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    ]


def source_violations(path: Path) -> list[str]:
    """Return AGENTS.md convention violations for one source file."""

    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)
    violations = top_level_violations(path, source, tree)
    violations.extend(docstring_violations(path, lines, tree))
    violations.extend(prohibited_name_violations(path, tree))

    return violations


def top_level_violations(path: Path, source: str, tree: ast.Module) -> list[str]:
    """Return prohibited module docstring and opening-comment violations."""

    violations: list[str] = []
    first_line = next((line for line in source.splitlines() if line.strip()), "")

    if first_line.lstrip().startswith("#"):
        violations.append(f"{path}: top-of-file comments are not allowed")

    if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant):
        if isinstance(tree.body[0].value.value, str):
            violations.append(f"{path}: module docstrings are not allowed")

    return violations


def docstring_violations(
    path: Path,
    lines: list[str],
    tree: ast.AST,
) -> list[str]:
    """Return definition docstring and spacing violations."""

    violations: list[str] = []
    for node in documented_nodes(tree):
        docstring = ast.get_docstring(node, clean=False)

        if docstring is None or "\n" in docstring:
            violations.append(f"{path}:{node.lineno}: definitions need one-line docstrings")

            continue

        docstring_node = node.body[0]
        docstring_end = docstring_node.end_lineno

        if docstring_end is None or docstring_end == len(lines) or lines[docstring_end].strip():
            violations.append(f"{path}:{node.lineno}: definitions need a blank line after their docstring")

    return violations


def prohibited_name_violations(path: Path, tree: ast.AST) -> list[str]:
    """Return prohibited construct violations."""

    violations: list[str] = []
    for node in ast.walk(tree):
        match node:
            case ast.Name(id=name) if name in PROHIBITED_NAMES:
                violations.append(f"{path}:{node.lineno}: prohibited construct {name}")
            case ast.Attribute(attr=name) if name in PROHIBITED_NAMES:
                violations.append(f"{path}:{node.lineno}: prohibited construct {name}")
            case ast.ImportFrom(names=aliases):
                violations.extend(
                    f"{path}:{node.lineno}: prohibited construct {alias.name}"
                    for alias in aliases
                    if alias.name in PROHIBITED_NAMES
                )

    return violations


class TestPythonConventions:
    """Test source conformance with enforceable Python conventions."""

    def test_source_files_follow_project_conventions(self) -> None:
        """Reject source files that violate enforceable AGENTS.md conventions."""

        violations = [violation for path in source_paths() for violation in source_violations(path)]

        assert not violations, "\n".join(violations)
