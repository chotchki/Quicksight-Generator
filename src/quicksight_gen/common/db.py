"""Dialect-aware database connection + script execution helpers (P.9d).

Used by the CLI (``demo apply``) and the e2e harness fixtures. Both
need to:

  - Open a DB-API 2.0 connection against either Postgres (psycopg2)
    or Oracle (oracledb), keyed off ``cfg.dialect``.
  - Run multi-statement DDL/DML scripts. psycopg2 accepts the whole
    script in one ``cursor.execute`` call; oracledb requires per-
    statement execution and treats PL/SQL blocks (``BEGIN…END;``) as
    one unit.

Both surfaces existed inline in ``cli.py`` before P.9d. Lifting them
here lets ``tests/e2e/test_harness_end_to_end.py`` consume the same
helpers instead of hardcoding psycopg2 (which raised
``ProgrammingError`` at setup when the harness ran against an Oracle
config — see PLAN.md P.9d).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

from quicksight_gen.common.config import Config
from quicksight_gen.common.sql import Dialect


__all__ = [
    "connect_demo_db",
    "execute_script",
    "oracle_dsn",
    "split_oracle_script",
]


def oracle_dsn(url: str) -> str:
    """Translate a SQLAlchemy-style Oracle URL into an oracledb DSN.

    Accepts either form:
      - ``oracle+oracledb://user:pass@host:port/?service_name=XEPDB1``
      - ``user/pass@host:port/XEPDB1`` (oracledb's native format)

    Returns a string ``oracledb.connect()`` understands.
    """
    if url.startswith(("oracle://", "oracle+oracledb://")):
        parsed = urlparse(url)
        user = parsed.username or ""
        pw = parsed.password or ""
        host = parsed.hostname or "localhost"
        port = parsed.port or 1521
        service = (
            parse_qs(parsed.query).get("service_name", [None])[0]
            or parsed.path.lstrip("/")
            or "FREEPDB1"
        )
        return f"{user}/{pw}@{host}:{port}/{service}"
    return url


def connect_demo_db(cfg: Config) -> Any:
    """Open a DB-API 2.0 connection to ``cfg.demo_database_url``.

    Branches on ``cfg.dialect``:
      - Postgres: psycopg2 (from the ``[demo]`` extra).
      - Oracle: oracledb thin client (from the ``[demo-oracle]`` extra).

    Raises:
      ImportError: if the matching driver isn't installed. The error
        message names the extras-install command.
      ValueError: if ``cfg.demo_database_url`` is unset or
        ``cfg.dialect`` isn't recognized.
    """
    if cfg.demo_database_url is None:
        raise ValueError(
            "cfg.demo_database_url is unset; set it in your config YAML "
            "or via QS_GEN_DEMO_DATABASE_URL."
        )
    if cfg.dialect is Dialect.POSTGRES:
        try:
            import psycopg2  # type: ignore[import-untyped]
        except ImportError as e:
            raise ImportError(
                "psycopg2 is required for Postgres connections. "
                "Install it with: pip install 'quicksight-gen[demo]'"
            ) from e
        return psycopg2.connect(cfg.demo_database_url)
    if cfg.dialect is Dialect.ORACLE:
        try:
            import oracledb  # type: ignore[import-untyped]
        except ImportError as e:
            raise ImportError(
                "oracledb is required for Oracle connections. "
                "Install it with: pip install 'quicksight-gen[demo-oracle]'"
            ) from e
        return oracledb.connect(oracle_dsn(cfg.demo_database_url))
    raise ValueError(
        f"Unknown dialect {cfg.dialect!r}. "
        "Set 'dialect: postgres' or 'dialect: oracle' in your config."
    )


def execute_script(cur: Any, sql: str, *, dialect: Dialect) -> None:
    """Run a multi-statement SQL string against ``cur``.

    Postgres (psycopg2): the whole string in one ``execute`` call works.
    Oracle (oracledb): ``cursor.execute`` requires single statements (not
    PL/SQL blocks; not ``;``-separated). Splits via
    ``split_oracle_script`` and executes each statement individually,
    surfacing which statement (out of N) failed and the first 1500
    characters of its body for triage.
    """
    if dialect is Dialect.POSTGRES:
        cur.execute(sql)
        return
    for i, stmt in enumerate(split_oracle_script(sql)):
        try:
            cur.execute(stmt)
        except Exception as e:
            preview = stmt.strip()[:1500]
            raise RuntimeError(
                f"Oracle stmt #{i} failed ({type(e).__name__}: {e})\n"
                f"  Preview: {preview}"
            ) from e


def split_oracle_script(sql: str) -> list[str]:
    """Split an Oracle-style script into individual statements.

    Handles PL/SQL blocks (anything starting with ``BEGIN`` or
    ``DECLARE`` and ending with ``END;``) as one unit; everything else
    splits on bare ``;``.

    Trailing-semicolon contract differs between the two:

    - **PL/SQL blocks**: the ``;`` is part of the ``END;`` terminator
      and Oracle's parser rejects the block without it
      (PLS-00103 "encountered end-of-file"). Keep it.
    - **Plain SQL statements**: ``oracledb.Cursor.execute`` rejects
      a trailing ``;`` ("invalid character"). Strip it.
    """
    statements: list[str] = []
    buffer: list[str] = []
    in_plsql = False
    for raw_line in sql.splitlines():
        line = raw_line.rstrip()
        # Strip the trailing ``-- comment`` before checking for the
        # statement terminator; a ``;`` inside a SQL line-comment is
        # commentary, not a statement boundary, and treating it as one
        # falsely splits the next CREATE block off into a comment-only
        # "statement" that Oracle rejects with ORA-00900.
        code = line.split("--", 1)[0].rstrip()
        stripped_code = code.strip()
        if not in_plsql and stripped_code.upper().startswith(
            ("BEGIN ", "DECLARE")
        ):
            in_plsql = True
        buffer.append(line)
        if in_plsql:
            # PL/SQL block ends at "END;" (the ; is the PL/SQL
            # statement terminator — keep it, the parser needs it).
            if stripped_code.upper().endswith("END;"):
                statements.append("\n".join(buffer).rstrip())
                buffer = []
                in_plsql = False
        else:
            if stripped_code.endswith(";"):
                # Plain SQL: oracledb rejects the trailing ; — strip.
                stmt = "\n".join(buffer).rstrip().rstrip(";")
                # Skip comment-only buffers (the buffer is all whitespace
                # + comment text). We only need stripped-code non-empty;
                # the actual SQL body content doesn't matter for emit.
                if stripped_code:
                    statements.append(stmt)
                buffer = []
    # Trailing buffer (no final semicolon)
    tail = "\n".join(buffer).strip()
    if tail:
        statements.append(tail)
    return statements
