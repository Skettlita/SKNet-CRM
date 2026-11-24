from alembic import context
from sqlalchemy import create_engine, pool

from app.db import database_url


if context.is_offline_mode():
    context.configure(url=database_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(database_url(), poolclass=pool.NullPool, hide_parameters=True)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection)
            with context.begin_transaction():
                connection.exec_driver_sql("SELECT pg_advisory_xact_lock(52773, 1)")
                context.run_migrations()
    finally:
        engine.dispose()
