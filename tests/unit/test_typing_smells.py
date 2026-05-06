"""X.2.o.5 — custom AST lint catching typing smells pyright doesn't flag.

Two checks today, both extensible — drop a new ``Check`` into
``CHECKS`` and the runner picks it up:

- **bare-str-id** — function parameters named like ID identifiers
  (``visual_id``, ``sheet_id``, ``dashboard_id``, ``filter_group_id``,
  ``parameter_name``) annotated as bare ``str`` instead of the
  matching NewType wrapper from ``common/ids.py``. The X.2.o.3
  sweep wrapped these on the async path; the lint keeps them
  wrapped going forward.

- **explicit-any** — explicit ``Any`` in a type annotation (parameter,
  return, AnnAssign). Pyright doesn't have ``reportExplicitAny``
  (basedpyright only), so this fills the gap. ``Any`` is sometimes
  principled (DB drivers, JSON values, ``getattr`` dispatch); those
  sites suppress per-line with a one-line WHY.

Suppression
-----------

Per-line: append ``# typing-smell: ignore[<check-name>]`` to the
same line as the offending annotation. Multiple check names are
comma-separated::

    cur: Any = ...  # typing-smell: ignore[explicit-any]: psycopg sync cursor
    pool: Any  # typing-smell: ignore[explicit-any,bare-str-id]

Per-file: drop ``# typing-smell: ignore-file[<check-name>]`` on
its own line anywhere in the file. Use this when an entire file
opts out of a check (e.g. ``models.py`` keeps explicit Any in QS
JSON shape returns)::

    # typing-smell: ignore-file[explicit-any]

Adding a check
--------------

1. Subclass ``Check`` (override ``find_smells`` returning
   ``Iterable[Smell]``).
2. Append the instance to ``CHECKS`` with its scoped file paths.

Scope
-----

Each check picks its own scope. ``bare-str-id`` runs on the full
pyright strict include (whatever ``pyproject.toml`` declares).
``explicit-any`` runs on a tighter subset where we want zero
unprincipled ``Any`` — start with the freshest files (``db.py``,
``_sql_executor.py``, ``_tree_fetcher.py``, ``server.py``,
``config.py``) and grow as files get cleaned.
"""

from __future__ import annotations

import ast
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"

# IDs we recognize as needing a NewType. Maps the snake-case
# parameter name to the matching NewType class name in common/ids.py.
ID_NEWTYPES: dict[str, str] = {
    "sheet_id": "SheetId",
    "visual_id": "VisualId",
    "filter_group_id": "FilterGroupId",
    "parameter_name": "ParameterName",
    "dashboard_id": "DashboardId",
}

_INLINE_IGNORE_RE = re.compile(
    r"#\s*typing-smell:\s*ignore\[([A-Za-z0-9_,\-\s]+)\]"
)
_FILE_IGNORE_RE = re.compile(
    r"#\s*typing-smell:\s*ignore-file\[([A-Za-z0-9_,\-\s]+)\]"
)


@dataclass(frozen=True)
class Smell:
    """One lint hit. Lineno is 1-based; checker name is the rule key."""
    file: Path
    lineno: int
    checker: str
    message: str


@dataclass
class Check:
    """One lint rule. Subclasses override ``find_smells``.

    Each Check declares its own scoped files (typically a subset of
    the pyright include list). The runner collects all smells then
    applies per-line + per-file suppression filtering.
    """
    name: str
    description: str
    files: list[Path] = field(default_factory=list)

    def find_smells(self, src: str, tree: ast.AST, file: Path) -> Iterable[Smell]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Check: bare-str-id
# ---------------------------------------------------------------------------


class _BareStrIdVisitor(ast.NodeVisitor):
    """Walk function signatures, flag ID-named parameters typed as ``str``."""

    def __init__(self, file: Path) -> None:
        self.file = file
        self.smells: list[Smell] = []

    def _check_args(self, args: list[ast.arg]) -> None:
        for arg in args:
            if arg.annotation is None:
                continue
            ann = arg.annotation
            # Bare ``str`` annotation; or ``Optional[str]`` / ``str | None``
            # etc. — only flag the bare-str case to keep the rule tight.
            if isinstance(ann, ast.Name) and ann.id == "str":
                expected = ID_NEWTYPES.get(arg.arg)
                if expected is not None:
                    self.smells.append(Smell(
                        file=self.file,
                        lineno=arg.lineno,
                        checker="bare-str-id",
                        message=(
                            f"parameter {arg.arg!r} typed as bare ``str``; "
                            f"use ``{expected}`` from common.ids instead "
                            f"(or add ``# typing-smell: ignore[bare-str-id]`` "
                            f"with a one-line reason)"
                        ),
                    ))

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_args(node.args.args)
        self._check_args(node.args.kwonlyargs)
        self._check_args(node.args.posonlyargs)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_args(node.args.args)
        self._check_args(node.args.kwonlyargs)
        self._check_args(node.args.posonlyargs)
        self.generic_visit(node)


class BareStrIdCheck(Check):
    def find_smells(self, src: str, tree: ast.AST, file: Path) -> Iterable[Smell]:
        v = _BareStrIdVisitor(file)
        v.visit(tree)
        return v.smells


# ---------------------------------------------------------------------------
# Check: explicit-any
# ---------------------------------------------------------------------------


class _ExplicitAnyVisitor(ast.NodeVisitor):
    """Walk all type annotations, flag ``Any`` (Name or Attribute form)."""

    def __init__(self, file: Path) -> None:
        self.file = file
        self.smells: list[Smell] = []

    def _scan(self, ann: ast.AST | None) -> None:
        if ann is None:
            return
        for sub in ast.walk(ann):
            if isinstance(sub, ast.Name) and sub.id == "Any":
                self.smells.append(self._mk(sub.lineno))
            elif isinstance(sub, ast.Attribute) and sub.attr == "Any":
                self.smells.append(self._mk(sub.lineno))

    def _mk(self, lineno: int) -> Smell:
        return Smell(
            file=self.file,
            lineno=lineno,
            checker="explicit-any",
            message=(
                "explicit ``Any`` in annotation — replace with a real "
                "type or suppress with ``# typing-smell: ignore[explicit-any]`` "
                "and a one-line reason"
            ),
        )

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._scan(node.annotation)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        for arg in node.args.args + node.args.kwonlyargs + node.args.posonlyargs:
            self._scan(arg.annotation)
        self._scan(node.returns)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        for arg in node.args.args + node.args.kwonlyargs + node.args.posonlyargs:
            self._scan(arg.annotation)
        self._scan(node.returns)
        self.generic_visit(node)


class ExplicitAnyCheck(Check):
    def find_smells(self, src: str, tree: ast.AST, file: Path) -> Iterable[Smell]:
        v = _ExplicitAnyVisitor(file)
        v.visit(tree)
        return v.smells


# ---------------------------------------------------------------------------
# Suppression filtering
# ---------------------------------------------------------------------------


def _line_suppressors(line: str) -> set[str]:
    m = _INLINE_IGNORE_RE.search(line)
    if not m:
        return set()
    return {tok.strip() for tok in m.group(1).split(",") if tok.strip()}


def _file_suppressors(src: str) -> set[str]:
    out: set[str] = set()
    for line in src.splitlines():
        m = _FILE_IGNORE_RE.search(line)
        if m:
            for tok in m.group(1).split(","):
                if tok.strip():
                    out.add(tok.strip())
    return out


def _is_suppressed(smell: Smell, lines: list[str], file_supp: set[str]) -> bool:
    if smell.checker in file_supp:
        return True
    if 0 < smell.lineno <= len(lines):
        if smell.checker in _line_suppressors(lines[smell.lineno - 1]):
            return True
    return False


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def _expand_paths(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        if p.is_dir():
            out.extend(sorted(p.rglob("*.py")))
        else:
            out.append(p)
    return out


def _read_pyright_include() -> list[Path]:
    data = tomllib.loads(PYPROJECT.read_text())
    rel = data["tool"]["pyright"]["include"]
    return [REPO_ROOT / r for r in rel]


def _build_checks() -> list[Check]:
    pyright_scope = _read_pyright_include()
    # Tighter scope for explicit-any: the freshest async files where
    # X.2.o just landed. Models.py / l2 / tree have legacy Any uses
    # the tree-pattern relies on (Visual subtype dispatch, AWS JSON
    # shapes); they get the file-level opt-out below if needed.
    explicit_any_scope = [
        REPO_ROOT / "src/quicksight_gen/common/db.py",
        REPO_ROOT / "src/quicksight_gen/common/html/_sql_executor.py",
        REPO_ROOT / "src/quicksight_gen/common/html/_tree_fetcher.py",
        REPO_ROOT / "src/quicksight_gen/common/html/server.py",
        REPO_ROOT / "src/quicksight_gen/common/config.py",
    ]
    return [
        BareStrIdCheck(
            name="bare-str-id",
            description=(
                "function parameters named like IDs must use the matching "
                "NewType from common/ids.py instead of bare ``str``"
            ),
            files=_expand_paths(pyright_scope),
        ),
        ExplicitAnyCheck(
            name="explicit-any",
            description=(
                "explicit ``Any`` in annotations is a smell — replace with "
                "a real type or suppress per-line with a WHY"
            ),
            files=explicit_any_scope,
        ),
    ]


def _collect_smells() -> list[Smell]:
    out: list[Smell] = []
    for check in _build_checks():
        for file in check.files:
            src = file.read_text()
            tree = ast.parse(src)
            file_supp = _file_suppressors(src)
            lines = src.splitlines()
            for smell in check.find_smells(src, tree, file):
                if _is_suppressed(smell, lines, file_supp):
                    continue
                out.append(smell)
    return out


def test_no_typing_smells() -> None:
    """The only test in this module — assert zero unsuppressed smells.

    Failure prints every smell with file:line and the check that
    flagged it. To fix: rewrite the annotation OR add a per-line
    ``# typing-smell: ignore[<check-name>]`` with a one-line reason.
    """
    smells = _collect_smells()
    if not smells:
        return
    lines = ["typing smells found:"]
    for s in smells:
        rel = s.file.relative_to(REPO_ROOT)
        lines.append(f"  {rel}:{s.lineno} [{s.checker}] {s.message}")
    pytest.fail("\n".join(lines))
