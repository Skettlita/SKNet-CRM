"""Extend existing CRM records and authorize the ISP workspace."""

from alembic import op


revision = "0005_enterprise"
down_revision = "0004_platform"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE crm.clients ADD COLUMN observations text;
        ALTER TABLE crm.sites ADD COLUMN description text;
        ALTER TABLE crm.service_plans
            ADD COLUMN description text, ADD COLUMN observations text,
            ADD COLUMN currency char(3) NOT NULL DEFAULT 'BOB';
        ALTER TABLE crm.services
            ADD COLUMN contracted_on date, ADD COLUMN observations text,
            ADD COLUMN currency char(3) NOT NULL DEFAULT 'BOB';
        ALTER TABLE crm.devices
            ADD COLUMN description text,
            ADD COLUMN administrative_active boolean NOT NULL DEFAULT true,
            ADD COLUMN monitoring_requested boolean NOT NULL DEFAULT false,
            ADD CONSTRAINT devices_request_requires_ip CHECK (NOT monitoring_requested OR ip_address IS NOT NULL);
        CREATE UNIQUE INDEX devices_pending_monitor_ip ON crm.devices(company_id, ip_address)
            WHERE collector_id IS NULL AND monitoring_requested AND administrative_active AND retired_at IS NULL;
        CREATE INDEX audit_company_entity_idx ON audit.events(company_id, entity_type, entity_id, occurred_at DESC);

        UPDATE platform.features SET implemented = true WHERE code = 'CRM';
        INSERT INTO platform.features(code, name, implemented)
            VALUES ('ICMP_CONFIG', 'Configuración ICMP', true);
        INSERT INTO platform.plan_features(plan_version_id, feature_id)
            SELECT v.id, f.id FROM platform.plan_versions v
            JOIN platform.plans p ON p.id=v.plan_id CROSS JOIN platform.features f
            WHERE p.code='TRIAL' AND f.code IN ('CRM','ICMP_CONFIG')
            ON CONFLICT DO NOTHING;

        WITH full_roles AS MATERIALIZED (
            SELECT rp.company_id,rp.role_id FROM core.role_permissions rp
            JOIN core.permissions p ON p.id=rp.permission_id
            WHERE p.code IN ('dashboard.read','users.read','users.write','users.reset','roles.read','roles.write')
            GROUP BY rp.company_id,rp.role_id HAVING count(DISTINCT p.code)=6
        ), added AS (
            INSERT INTO core.permissions(code,description) VALUES
              ('clients.read','Consultar clientes, contactos y direcciones'),
              ('clients.create','Registrar clientes'),
              ('clients.write','Editar clientes, contactos, direcciones y notas'),
              ('clients.status','Activar y desactivar clientes'),
              ('internet_plans.read','Consultar planes de Internet'),
              ('internet_plans.create','Registrar planes de Internet'),
              ('internet_plans.write','Editar planes de Internet'),
              ('internet_plans.status','Activar y desactivar planes de Internet'),
              ('services.read','Consultar servicios contratados'),
              ('services.create','Registrar servicios contratados'),
              ('services.write','Editar servicios contratados'),
              ('services.status','Cambiar estado de servicios'),
              ('sites.read','Consultar sitios'),
              ('sites.create','Registrar sitios'),
              ('sites.write','Editar sitios'),
              ('sites.status','Activar y desactivar sitios'),
              ('devices.read','Consultar dispositivos'),
              ('devices.create','Registrar dispositivos'),
              ('devices.write','Editar dispositivos'),
              ('devices.status','Activar y desactivar dispositivos'),
              ('icmp.read','Consultar configuración ICMP'),
              ('icmp.write','Administrar configuración ICMP e intención de monitoreo'),
              ('infrastructure.read','Consultar infraestructura de red'),
              ('crm_history.read','Consultar historial del CRM')
            RETURNING id
        )
        INSERT INTO core.role_permissions(company_id,role_id,permission_id)
            SELECT company_id,role_id,id FROM full_roles CROSS JOIN added;
    """)


def downgrade():
    raise RuntimeError("La revisión conserva datos de CRM. Usa una migración correctiva.")
