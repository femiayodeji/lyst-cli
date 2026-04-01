from sqlalchemy import create_engine, text, inspect
from app.config import load_config


def get_engine():
    config = load_config()
    if not config.db.connection:
        raise ValueError("No database configured. Run: lyst config set --connection <connection-string>")
    
    # Build connect_args based on database type
    connect_args = {}
    conn_str = config.db.connection.lower()
    
    if conn_str.startswith('postgresql'):
        connect_args = {'connect_timeout': 10}
    elif conn_str.startswith('mysql'):
        connect_args = {'connect_timeout': 10}
    
    return create_engine(config.db.connection, connect_args=connect_args if connect_args else {})


def get_db_type() -> str:
    engine = get_engine()
    return engine.dialect.name


def get_schema() -> str:
    """Get database schema with raw identifiers - LLM handles dialect-specific quoting."""
    engine = get_engine()
    inspector = inspect(engine)
    schema_lines = []

    for table_name in inspector.get_table_names():
        schema_lines.append(f"Table: {table_name}")

        for col in inspector.get_columns(table_name):
            schema_lines.append(f"  - {col['name']} ({col['type']})")

        foreign_keys = inspector.get_foreign_keys(table_name)
        for fk in foreign_keys:
            schema_lines.append(
                f"  - FK: {fk['constrained_columns']} -> {fk['referred_table']}({fk['referred_columns']})"
            )

        schema_lines.append("")

    return "\n".join(schema_lines)


def run_query(sql: str) -> tuple[list, list]:
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        columns = list(result.keys())
        rows = [list(row) for row in result.fetchall()]
    return columns, rows