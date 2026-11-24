"""Persist ICMP latency extrema, transport visibility and operational incidents."""

from alembic import op

revision = "0011_icmp_monitoring"
down_revision = "0010_installations"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE monitoring.icmp_profiles DROP CONSTRAINT icmp_profiles_loss_failure_pct_check;
        ALTER TABLE monitoring.icmp_profiles ALTER COLUMN loss_failure_pct SET DEFAULT 40,
          ADD CONSTRAINT icmp_profiles_loss_failure_pct_check CHECK(loss_failure_pct BETWEEN 0 AND 100);
        ALTER TABLE monitoring.icmp_checks ADD COLUMN latency_min_ms numeric(12,3),
          ADD COLUMN latency_max_ms numeric(12,3), ADD COLUMN target_ip inet,
          ADD COLUMN transport_healthy boolean NOT NULL DEFAULT false,
          ADD COLUMN acceptable boolean;
        ALTER TABLE monitoring.device_status ADD COLUMN transport_epoch bigint NOT NULL DEFAULT 0,
          ADD COLUMN failure_since timestamptz;
        ALTER TABLE monitoring.incidents ADD COLUMN client_id uuid, ADD COLUMN site_id uuid,
          ADD COLUMN device_category text,
          ADD FOREIGN KEY(company_id,client_id) REFERENCES crm.clients(company_id,id),
          ADD FOREIGN KEY(company_id,site_id) REFERENCES crm.sites(company_id,id);
        ALTER TABLE connectivity.vpn_tunnels ADD COLUMN monitor_epoch bigint NOT NULL DEFAULT 1;
        CREATE INDEX icmp_checks_retention ON monitoring.icmp_checks(received_at);
        CREATE INDEX monitoring_incidents_open_company ON monitoring.incidents(company_id,started_at DESC)
          WHERE ended_at IS NULL;
        CREATE TABLE monitoring.transport_incidents (
           id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
           company_id uuid NOT NULL,
           collector_id uuid NOT NULL,
           kind text NOT NULL CHECK(kind IN ('VPN','COLLECTOR')),
           started_at timestamptz NOT NULL DEFAULT now(),
           ended_at timestamptz,
           reason text NOT NULL,
           FOREIGN KEY(company_id,collector_id) REFERENCES connectivity.collectors(company_id,id)
        );
        CREATE UNIQUE INDEX transport_one_open ON monitoring.transport_incidents(collector_id,kind) WHERE ended_at IS NULL;
        CREATE INDEX transport_incidents_company ON monitoring.transport_incidents(company_id,started_at DESC);
        UPDATE platform.features SET implemented=true WHERE code='ICMP';
        INSERT INTO platform.plan_features(plan_version_id,feature_id)
          SELECT v.id,f.id FROM platform.plan_versions v
          JOIN platform.plans p ON p.id=v.plan_id CROSS JOIN platform.features f WHERE p.code='TRIAL' AND f.code='ICMP'
          ON CONFLICT DO NOTHING;
        WITH owners AS MATERIALIZED (
            SELECT r.id,r.company_id FROM core.roles r
            WHERE r.name='Administración' AND r.description='Administración inicial de la empresa'
              AND NOT EXISTS (
                SELECT 1 FROM core.permissions p WHERE NOT EXISTS (
                  SELECT 1 FROM core.role_permissions rp
                  WHERE rp.company_id=r.company_id AND rp.role_id=r.id AND rp.permission_id=p.id
                )
              )
        ), added AS (
            INSERT INTO core.permissions(code,description) VALUES ('monitoring.read','Consultar monitoreo e incidentes')
            RETURNING id
        )
        INSERT INTO core.role_permissions(company_id,role_id,permission_id)
        SELECT o.company_id,o.id,p.id FROM owners o CROSS JOIN added p;
    """)


def downgrade():
    raise RuntimeError("Usa una migración correctiva para conservar mediciones e incidentes.")
