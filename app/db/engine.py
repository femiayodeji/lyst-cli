import logging
import time
from collections import defaultdict

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine

from app.config import load_config
from app.state import AppState

_log = logging.getLogger(__name__)


def get_engine(state: AppState) -> Engine:
    config = load_config(state.db_connection_override)
    conn_str = config.db.connection
    if not conn_str:
        raise ValueError("No database configured. Set LYST_DB_CONNECTION or use the /config/db endpoint.")
    if conn_str not in state.engines:
        connect_args: dict = {}
        lower = conn_str.lower()
        if lower.startswith("postgresql"):
            connect_args = {"connect_timeout": 10}
        elif lower.startswith("mysql"):
            connect_args = {"connect_timeout": 10}
        state.engines[conn_str] = create_engine(conn_str, connect_args=connect_args)
        _log.debug("Created new engine for %s…", conn_str[:30])
    return state.engines[conn_str]


def get_db_type(state: AppState) -> str:
    return get_engine(state).dialect.name


def _build_schema(col_rows, fk_rows) -> str:
    tables: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in col_rows:
        tables[row.table_name].append((row.column_name, str(row.data_type)))

    fks: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in fk_rows:
        entry = fks[row.table_name].setdefault(
            row.constraint_name,
            {"constrained_columns": [], "referred_table": row.referred_table, "referred_columns": []},
        )
        entry["constrained_columns"].append(row.column_name)
        entry["referred_columns"].append(row.referred_column)

    lines: list[str] = []
    for table_name in sorted(tables):
        lines.append(f"Table: {table_name}")
        for col_name, data_type in tables[table_name]:
            lines.append(f"  - {col_name} ({data_type})")
        for fk in fks.get(table_name, {}).values():
            lines.append(
                f"  - FK: {fk['constrained_columns']} -> {fk['referred_table']}({fk['referred_columns']})"
            )
        lines.append("")
    return "\n".join(lines)


def _schema_postgresql(engine: Engine) -> str:
    col_sql = text("""
        SELECT cls.relname AS table_name,
               a.attname  AS column_name,
               pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type
        FROM   pg_class cls
        JOIN   pg_namespace n  ON n.oid  = cls.relnamespace
        JOIN   pg_attribute a  ON a.attrelid = cls.oid
        WHERE  cls.relkind = 'r'
          AND  n.nspname   = 'public'
          AND  a.attnum    > 0
          AND  NOT a.attisdropped
        ORDER  BY cls.relname, a.attnum
    """)
    fk_sql = text("""
        SELECT src.relname   AS table_name,
               c.conname     AS constraint_name,
               a_src.attname AS column_name,
               tgt.relname   AS referred_table,
               a_tgt.attname AS referred_column
        FROM   pg_constraint c
        JOIN   pg_class     src   ON src.oid = c.conrelid
        JOIN   pg_class     tgt   ON tgt.oid = c.confrelid
        JOIN   pg_namespace n     ON n.oid   = src.relnamespace
        CROSS  JOIN LATERAL generate_subscripts(c.conkey, 1) s(idx)
        JOIN   pg_attribute a_src ON a_src.attrelid = c.conrelid  AND a_src.attnum = c.conkey[s.idx]
        JOIN   pg_attribute a_tgt ON a_tgt.attrelid = c.confrelid AND a_tgt.attnum = c.confkey[s.idx]
        WHERE  c.contype = 'f' AND n.nspname = 'public'
        ORDER  BY table_name, constraint_name, s.idx
    """)
    with engine.connect() as conn:
        return _build_schema(conn.execute(col_sql).fetchall(), conn.execute(fk_sql).fetchall())


def _schema_mysql(engine: Engine) -> str:
    col_sql = text("""
        SELECT table_name, column_name, column_type AS data_type
        FROM   information_schema.columns
        WHERE  table_schema = DATABASE()
        ORDER  BY table_name, ordinal_position
    """)
    fk_sql = text("""
        SELECT kcu.table_name,
               kcu.constraint_name,
               kcu.column_name,
               kcu.referenced_table_name  AS referred_table,
               kcu.referenced_column_name AS referred_column
        FROM   information_schema.key_column_usage kcu
        WHERE  kcu.table_schema = DATABASE()
          AND  kcu.referenced_table_name IS NOT NULL
        ORDER  BY kcu.table_name, kcu.constraint_name, kcu.ordinal_position
    """)
    with engine.connect() as conn:
        return _build_schema(conn.execute(col_sql).fetchall(), conn.execute(fk_sql).fetchall())


def _schema_inspector(engine: Engine) -> str:
    inspector = inspect(engine)
    lines: list[str] = []
    for table_name in inspector.get_table_names():
        lines.append(f"Table: {table_name}")
        for col in inspector.get_columns(table_name):
            lines.append(f"  - {col['name']} ({col['type']})")
        for fk in inspector.get_foreign_keys(table_name):
            lines.append(
                f"  - FK: {fk['constrained_columns']} -> {fk['referred_table']}({fk['referred_columns']})"
            )
        lines.append("")
    return "\n".join(lines)


def get_schema(state: AppState) -> str:
    engine = get_engine(state)
    dialect = engine.dialect.name
    t0 = time.monotonic()
    if dialect == "postgresql":
        result = _schema_postgresql(engine)
    elif dialect in ("mysql", "mariadb"):
        result = _schema_mysql(engine)
    else:
        result = _schema_inspector(engine)
    _log.info("Schema loaded (%s) in %.3fs", dialect, time.monotonic() - t0)
    return result


def run_query(sql: str, state: AppState) -> tuple[list, list]:
    engine = get_engine(state)
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        columns = list(result.keys())
        rows = [list(row) for row in result.fetchall()]
    return columns, rows
