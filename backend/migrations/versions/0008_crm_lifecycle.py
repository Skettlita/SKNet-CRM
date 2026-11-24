"""Explicit archival and deletion permissions for CRM records."""

from alembic import op

revision = "0008_crm_lifecycle"
down_revision = "0007_crm_workflow"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("clients", "services", "service_plans", "sites", "devices"):
        op.execute(f"ALTER TABLE crm.{table} ADD COLUMN archived_at timestamptz")
    op.execute("UPDATE crm.devices SET archived_at=retired_at WHERE retired_at IS NOT NULL")
    op.execute("""
        WITH owners AS MATERIALIZED (
            SELECT r.id,r.company_id FROM core.roles r
            WHERE r.name='Administración' AND r.description='Administración inicial de la empresa'
              AND NOT EXISTS (
                  SELECT 1 FROM core.permissions p WHERE NOT EXISTS (
                      SELECT 1 FROM core.role_permissions rp WHERE rp.company_id=r.company_id AND rp.role_id=r.id AND rp.permission_id=p.id
                  )
              )
        ), added AS (
            INSERT INTO core.permissions(code,description)
            SELECT section || '.' || action, label || ' ' || concept
            FROM (VALUES ('clients','clientes'),('services','servicios'),('internet_plans','planes de Internet'),
                         ('sites','sitios'),('devices','dispositivos')) AS modules(section,concept)
            CROSS JOIN (VALUES ('archive','Archivar'),('delete','Eliminar definitivamente')) AS actions(action,label)
            RETURNING id
        )
        INSERT INTO core.role_permissions(company_id,role_id,permission_id)
        SELECT o.company_id,o.id,p.id FROM owners o CROSS JOIN added p;
    """)


def downgrade():
    raise RuntimeError("Usa una migración correctiva para conservar el historial y el archivado.")
