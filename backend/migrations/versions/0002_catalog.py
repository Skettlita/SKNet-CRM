"""Initialize the platform catalog and free trial."""

from pathlib import Path

from alembic import op


revision = "0002_catalog"
down_revision = "0001_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql = Path(__file__).with_suffix(".sql").read_text(encoding="utf-8")
    op.execute(sql)


def downgrade() -> None:
    raise RuntimeError("El catálogo puede estar en uso. Utiliza una migración correctiva.")
