import re
from io import StringIO
from pathlib import Path
from tokenize import COMMENT, generate_tokens
from typing import ClassVar, Final, TypedDict

from astroid import nodes
from pylint.checkers import BaseChecker
from pylint.lint import PyLinter

type DefinitionNode = nodes.FunctionDef | nodes.AsyncFunctionDef | nodes.ClassDef
type MessageDefinition = tuple[str, str, str]

__all__: Final[tuple[str, ...]] = ("PythonRulesChecker", "register")

CAMEL_CASE_BOUNDARY_PATTERN: Final[re.Pattern[str]] = re.compile(r"([a-z0-9])([A-Z])")
INLINE_REGEX_METHODS: Final[frozenset[str]] = frozenset(
    {
        "re.findall",
        "re.finditer",
        "re.fullmatch",
        "re.match",
        "re.search",
        "re.split",
        "re.sub",
        "re.subn",
    }
)


class RuleConfig(TypedDict):
    """Define the mechanically enforceable Python rule configuration."""

    prohibited_constructs: frozenset[str]
    banned_terminology: tuple[str, ...]


RULE_CONFIG: Final[RuleConfig] = RuleConfig(
    prohibited_constructs=frozenset({"Any", "Protocol", "cast", "dataclass", "print"}),
    banned_terminology=("best effort", "seed", "seeds", "seeding"),
)
BANNED_TERMINOLOGY_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = tuple(
    (term, re.compile(rf"\b{re.escape(term)}\b")) for term in RULE_CONFIG["banned_terminology"]
)


def banned_terminology(value: str) -> str | None:
    """Return the first banned term found in prose or an identifier."""

    separated_camel_case = CAMEL_CASE_BOUNDARY_PATTERN.sub(r"\1 \2", value)
    normalized = separated_camel_case.replace("_", " ").replace("-", " ").lower()

    return next(
        (term for term, pattern in BANNED_TERMINOLOGY_PATTERNS if pattern.search(normalized)),
        None,
    )


def is_dunder(name: str) -> bool:
    """Return whether a name uses Python's double-underscore convention."""

    return name.startswith("__") and name.endswith("__")


class PythonRulesChecker(BaseChecker):
    """Check Python source against mechanically enforceable project rules."""

    name = "python-rules"
    msgs: ClassVar[dict[str, MessageDefinition]] = {
        "C9501": (
            "Definition %s needs a one-line docstring",
            "missing-definition-docstring",
            "Every function, method, and class requires a one-line docstring.",
        ),
        "C9502": (
            "Definition %s must use a one-line docstring",
            "multiline-definition-docstring",
            "Definition docstrings must stay on one line.",
        ),
        "C9503": (
            "Definition %s needs a blank line after its docstring",
            "missing-blank-line-after-docstring",
            "A blank physical line must separate every definition docstring from its body.",
        ),
        "C9504": (
            "Module docstrings are not allowed",
            "forbidden-module-docstring",
            "Python modules must begin with imports or remain empty.",
        ),
        "C9505": (
            "Top-of-file comments are not allowed",
            "forbidden-opening-comment",
            "Python modules must not begin with comments or encoding headers.",
        ),
        "C9506": (
            "Forbidden Python construct %s",
            "forbidden-python-construct",
            "Project rules prohibit loose or legacy Python constructs.",
        ),
        "C9507": (
            "Leading underscore is not allowed for %s",
            "invalid-leading-underscore",
            "Only nested definitions and Python dunder names may start with underscores.",
        ),
        "C9508": (
            "Parent-relative import is not allowed",
            "parent-relative-import",
            "Imports must use absolute package paths outside __main__.py.",
        ),
        "C9509": (
            "Direct environment read %s is not allowed",
            "direct-environment-read",
            "Environment-backed values must come from typed settings.",
        ),
        "C9510": (
            "Banned Python terminology %s",
            "banned-python-terminology",
            "Identifiers, docstrings, and comments must use behavior-specific terminology.",
        ),
        "C9511": (
            "Application model %s must be defined under a models directory",
            "model-outside-models-directory",
            "Application data models belong in intuitive modules under models directories.",
        ),
        "C9512": (
            "Logger instances must use the lowercase name logger",
            "uppercase-logger-name",
            "Logger instances are runtime collaborators rather than constants.",
        ),
        "C9513": (
            "Inline regex call %s is not allowed",
            "inline-regex-call",
            "Regular expressions must be compiled once at module scope.",
        ),
    }

    def __init__(self, linter: PyLinter) -> None:
        """Initialize per-module source state."""

        super().__init__(linter)

        self.source_lines: list[str] = []

    def visit_module(self, node: nodes.Module) -> None:
        """Load module source and check module-level text conventions."""

        source = Path(node.file).read_text(encoding="utf-8")
        self.source_lines = source.splitlines()

        first_line = next(
            (
                (line_number, line)
                for line_number, line in enumerate(self.source_lines, start=1)
                if line.strip()
            ),
            None,
        )

        if first_line is not None and first_line[1].lstrip().startswith("#"):
            self.add_message("forbidden-opening-comment", node=node, line=first_line[0])

        if node.doc_node is not None:
            self.add_message("forbidden-module-docstring", node=node.doc_node)

            self.check_text_terminology(node.doc_node.value, node=node.doc_node)

        for token in generate_tokens(StringIO(source).readline):
            if token.type == COMMENT:
                self.check_text_terminology(token.string, node=node, line=token.start[0])

    def leave_module(self, node: nodes.Module) -> None:
        """Clear per-module source state."""

        self.source_lines = []

    def visit_functiondef(self, node: nodes.FunctionDef) -> None:
        """Check a synchronous function definition."""

        self.check_definition(node)
        self.check_definition_name(node)

    def visit_asyncfunctiondef(self, node: nodes.AsyncFunctionDef) -> None:
        """Check an asynchronous function definition."""

        self.check_definition(node)
        self.check_definition_name(node)

    def visit_classdef(self, node: nodes.ClassDef) -> None:
        """Check a class definition."""

        self.check_definition(node)
        self.check_definition_name(node)

        if self.is_base_model(node) and "models" not in Path(node.root().file).parts:
            self.add_message("model-outside-models-directory", node=node, args=(node.name,))

    def visit_name(self, node: nodes.Name) -> None:
        """Check a referenced Python name."""

        self.check_prohibited_construct(node.name, node)
        self.check_identifier_terminology(node.name, node)

    def visit_assignname(self, node: nodes.AssignName) -> None:
        """Check an assigned Python name."""

        self.check_prohibited_construct(node.name, node)
        self.check_identifier_terminology(node.name, node)

        if isinstance(node.scope(), nodes.Module):
            self.check_leading_underscore(node.name, node, allowed=False)

            if node.name == "LOGGER":
                self.add_message("uppercase-logger-name", node=node)

    def visit_attribute(self, node: nodes.Attribute) -> None:
        """Check an attribute reference and direct environment access."""

        self.check_prohibited_construct(node.attrname, node)
        self.check_identifier_terminology(node.attrname, node)

        if node.as_string() in {"os.environ", "os.environ.get"}:
            self.add_message("direct-environment-read", node=node, args=("os.environ",))

    def visit_call(self, node: nodes.Call) -> None:
        """Check direct environment function calls."""

        function_name = node.func.as_string()

        if function_name == "os.getenv":
            self.add_message("direct-environment-read", node=node, args=("os.getenv",))

        if function_name in INLINE_REGEX_METHODS:
            self.add_message("inline-regex-call", node=node, args=(function_name,))

    def visit_importfrom(self, node: nodes.ImportFrom) -> None:
        """Check imported constructs and parent-relative imports."""

        for imported_name, imported_alias in node.names:
            self.check_prohibited_construct(imported_name, node)
            self.check_identifier_terminology(imported_name, node)

            if imported_alias is not None:
                self.check_identifier_terminology(imported_alias, node)

        if node.level and Path(node.root().file).name != "__main__.py":
            self.add_message("parent-relative-import", node=node)

    def check_definition(self, node: DefinitionNode) -> None:
        """Check one definition's docstring and spacing."""

        docstring = node.doc_node

        if docstring is None:
            self.add_message("missing-definition-docstring", node=node, args=(node.name,))

            return

        self.check_text_terminology(docstring.value, node=docstring)

        if "\n" in docstring.value:
            self.add_message("multiline-definition-docstring", node=node, args=(node.name,))

        following_line = docstring.tolineno

        if following_line >= len(self.source_lines) or self.source_lines[following_line].strip():
            self.add_message("missing-blank-line-after-docstring", node=node, args=(node.name,))

    def is_base_model(self, node: nodes.ClassDef) -> bool:
        """Return whether a class directly extends Pydantic BaseModel."""

        return any(base.as_string() in {"BaseModel", "pydantic.BaseModel"} for base in node.bases)

    def check_definition_name(self, node: DefinitionNode) -> None:
        """Check one definition's name conventions."""

        self.check_identifier_terminology(node.name, node)

        if isinstance(node, nodes.ClassDef):
            allowed = isinstance(node.parent, nodes.ClassDef)
        else:
            allowed = isinstance(node.parent, nodes.FunctionDef | nodes.AsyncFunctionDef)

        self.check_leading_underscore(node.name, node, allowed)

    def check_prohibited_construct(self, name: str, node: nodes.NodeNG) -> None:
        """Report a prohibited Python construct."""

        if name in RULE_CONFIG["prohibited_constructs"]:
            self.add_message("forbidden-python-construct", node=node, args=(name,))

    def check_leading_underscore(self, name: str, node: nodes.NodeNG, allowed: bool) -> None:
        """Report a disallowed leading underscore."""

        if name.startswith("_") and not is_dunder(name) and not allowed:
            self.add_message("invalid-leading-underscore", node=node, args=(name,))

    def check_identifier_terminology(self, name: str, node: nodes.NodeNG) -> None:
        """Report banned terminology in an identifier."""

        term = banned_terminology(name)

        if term is not None:
            self.add_message("banned-python-terminology", node=node, args=(term,))

    def check_text_terminology(
        self,
        value: str,
        *,
        node: nodes.NodeNG | None = None,
        line: int | None = None,
    ) -> None:
        """Report banned terminology in a docstring or comment."""

        term = banned_terminology(value)

        if term is not None:
            self.add_message("banned-python-terminology", node=node, line=line, args=(term,))


def register(linter: PyLinter) -> None:
    """Register the shared Python rules checker."""

    linter.register_checker(PythonRulesChecker(linter))
