"""Add platform permissions and versioned commercial terms."""

from alembic import op


revision = "0004_platform"
down_revision = "0003_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE platform.plan_versions
            ADD COLUMN description text NOT NULL DEFAULT '',
            ADD COLUMN billing_period text NOT NULL DEFAULT 'MONTHLY'
                CHECK (billing_period IN ('MONTHLY', 'YEARLY'));

        ALTER TABLE platform.subscription_history
            ADD COLUMN previous_starts_at timestamptz,
            ADD COLUMN previous_ends_at timestamptz,
            ADD COLUMN new_starts_at timestamptz,
            ADD COLUMN new_ends_at timestamptz;

        WITH full_roles AS MATERIALIZED (
            SELECT rp.role_id FROM platform.role_permissions rp
            JOIN platform.permissions p ON p.id = rp.permission_id
            WHERE p.code IN ('dashboard.read','users.read','users.write','users.reset',
                'roles.read','roles.write','system.read','settings.read','settings.write',
                'companies.create','support.reset')
            GROUP BY rp.role_id HAVING count(DISTINCT p.code) = 11
        ), added AS (
            INSERT INTO platform.permissions(code,description) VALUES
                ('companies.read','Consultar empresas'),
                ('companies.write','Editar, suspender y activar empresas'),
                ('companies.users.read','Consultar usuarios de una empresa'),
                ('plans.read','Consultar planes SaaS'),
                ('plans.write','Crear, editar y desactivar planes SaaS'),
                ('subscriptions.read','Consultar suscripciones e historial'),
                ('subscriptions.write','Asignar y cambiar suscripciones'),
                ('support.read','Consultar tickets SaaS'),
                ('support.write','Asignar y gestionar tickets SaaS'),
                ('support.reply','Responder a tickets SaaS'),
                ('audit.read','Consultar auditoría')
            ON CONFLICT (code) DO UPDATE SET description = EXCLUDED.description
            RETURNING id
        )
        INSERT INTO platform.role_permissions(role_id, permission_id)
            SELECT role_id, id FROM full_roles CROSS JOIN added
            ON CONFLICT (role_id, permission_id) DO NOTHING;

        WITH full_roles AS MATERIALIZED (
            SELECT rp.company_id, rp.role_id FROM core.role_permissions rp
            JOIN core.permissions p ON p.id = rp.permission_id
            WHERE p.code IN ('dashboard.read','users.read','users.write','users.reset','roles.read','roles.write')
            GROUP BY rp.company_id, rp.role_id HAVING count(DISTINCT p.code) = 6
        ), added AS (
            INSERT INTO core.permissions(code,description) VALUES
                ('support.read','Consultar el soporte de SKNet para la empresa'),
                ('support.create','Enviar solicitudes a SKNet'),
                ('support.reply','Responder a solicitudes de soporte')
            ON CONFLICT (code) DO UPDATE SET description = EXCLUDED.description
            RETURNING id
        )
        INSERT INTO core.role_permissions(company_id, role_id, permission_id)
            SELECT company_id, role_id, id FROM full_roles CROSS JOIN added
            ON CONFLICT (role_id, permission_id) DO NOTHING;

        INSERT INTO platform.features(code,name,implemented)
            VALUES ('SAAS_SUPPORT','Soporte de SKNet',true)
            ON CONFLICT (code) DO UPDATE SET implemented=true;

        INSERT INTO platform.plan_features(plan_version_id, feature_id)
            SELECT v.id, f.id FROM platform.plan_versions v
            JOIN platform.plans p ON p.id = v.plan_id
            JOIN platform.features f ON f.code = 'SAAS_SUPPORT'
            WHERE p.code = 'TRIAL'
            ON CONFLICT (plan_version_id,feature_id) DO NOTHING;

        CREATE INDEX support_tickets_company_opened_idx ON platform.support_tickets(company_id, opened_at DESC);
        CREATE INDEX audit_occurred_idx ON audit.events(occurred_at DESC, id DESC);
    """)


def downgrade() -> None:
    raise RuntimeError("La revisión contiene condiciones y datos históricos. Usa una migración correctiva.")
