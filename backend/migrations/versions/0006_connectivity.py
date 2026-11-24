"""Persist provisioner leases, desired networks and diagnostic state."""

from alembic import op

revision = "0006_connectivity"
down_revision = "0005_enterprise"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE connectivity.collectors
            ADD COLUMN desired_routes cidr[] NOT NULL DEFAULT '{}',
            ADD COLUMN container_state text NOT NULL DEFAULT 'UNKNOWN',
            ADD COLUMN provisioning_step text NOT NULL DEFAULT 'QUEUED',
            ADD COLUMN diagnostic text,
            ADD COLUMN simulated boolean NOT NULL DEFAULT false,
            ADD COLUMN applied_revision bigint;
        ALTER TABLE connectivity.network_pools
            ADD COLUMN observed_networks cidr[] NOT NULL DEFAULT '{}',
            ADD COLUMN observed_ports integer[] NOT NULL DEFAULT '{}',
            ADD COLUMN observed_at timestamptz;
        ALTER TABLE connectivity.provisioning_jobs
            ADD COLUMN lease_id uuid,
            ADD COLUMN lease_expires_at timestamptz,
            ADD COLUMN error_code text;
        CREATE INDEX provisioning_jobs_pending_idx
            ON connectivity.provisioning_jobs(created_at) WHERE status IN ('PENDING','RUNNING');
        ALTER TABLE connectivity.resource_allocations ADD COLUMN bind_address inet;

        INSERT INTO platform.features (code,name,implemented)
            VALUES ('CONNECTIVITY','Conectividad WireGuard',true);
        INSERT INTO platform.plan_features(plan_version_id,feature_id)
            SELECT v.id,f.id FROM platform.plan_versions v
            JOIN platform.plans p ON p.id=v.plan_id CROSS JOIN platform.features f
            WHERE p.code='TRIAL' AND f.code='CONNECTIVITY' ON CONFLICT DO NOTHING;

        WITH full_roles AS MATERIALIZED (
            SELECT rp.company_id,rp.role_id FROM core.role_permissions rp
            JOIN core.permissions p ON p.id=rp.permission_id
            WHERE p.code IN ('dashboard.read','users.read','users.write','users.reset','roles.read','roles.write')
            GROUP BY rp.company_id,rp.role_id HAVING count(DISTINCT p.code)=6
        ), added AS (
            INSERT INTO core.permissions(code,description) VALUES
               ('connectivity.read','Consultar conectividad propia'),
               ('connectivity.write','Solicitar y configurar conectividad propia')
            RETURNING id
        )
        INSERT INTO core.role_permissions(company_id,role_id,permission_id)
            SELECT company_id,role_id,id FROM full_roles CROSS JOIN added;

        WITH full_roles AS MATERIALIZED (
            SELECT rp.role_id FROM platform.role_permissions rp
            JOIN platform.permissions p ON p.id=rp.permission_id
            WHERE p.code IN ('dashboard.read','system.read','companies.read','settings.write','roles.write')
            GROUP BY rp.role_id HAVING count(DISTINCT p.code)=5
        ), added AS (
            INSERT INTO platform.permissions(code,description) VALUES
               ('connectivity.read','Consultar infraestructura y trabajos'),
               ('connectivity.write','Reintentar, rotar credenciales y retirar infraestructura administrada')
            RETURNING id
        )
        INSERT INTO platform.role_permissions(role_id,permission_id)
            SELECT role_id,id FROM full_roles CROSS JOIN added;
    """)


def downgrade():
    raise RuntimeError("Usa una migración correctiva para conservar las reservas y trabajos.")
