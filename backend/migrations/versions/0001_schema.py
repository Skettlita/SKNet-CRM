"""Create the PostgreSQL 17 foundation, including schemas, tables and views."""

from pathlib import Path

from alembic import op


revision = "0001_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
    op.execute(sql)


def downgrade() -> None:
    raise RuntimeError("La reversión del esquema inicial requiere restaurar un respaldo.")
