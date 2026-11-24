"""Persist authentication settings and seed the phase two permission catalog."""

from alembic import op


revision = "0003_access"
down_revision = "0002_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE core.users
            ADD COLUMN temporary_password_expires_at timestamptz,
            ADD COLUMN temporary_password_used_at timestamptz,
            ADD COLUMN compact_view boolean NOT NULL DEFAULT false;

        ALTER TABLE core.password_reset_tokens ADD COLUMN purpose text NOT NULL DEFAULT 'reset'
            CHECK (purpose IN ('reset', 'verify'));

        CREATE TABLE core.auth_attempts (
            bucket text PRIMARY KEY,
            attempts integer NOT NULL CHECK (attempts > 0),
            expires_at timestamptz NOT NULL
        );
        CREATE INDEX auth_attempts_expiry ON core.auth_attempts(expires_at);

        INSERT INTO core.permissions(code, description) VALUES
          ('dashboard.read', 'Ver el panel'),
          ('users.read', 'Listar usuarios'),
          ('users.write', 'Crear, editar y desactivar cuentas y asignar roles'),
          ('users.reset', 'Emitir contraseñas temporales'),
          ('roles.read', 'Ver roles y permisos'),
          ('roles.write', 'Crear y editar roles')
        ON CONFLICT (code) DO NOTHING;

        INSERT INTO platform.permissions(code, description)
            SELECT code, description FROM core.permissions
            WHERE code IN ('dashboard.read','users.read','users.write','users.reset','roles.read','roles.write')
        ON CONFLICT (code) DO NOTHING;

        INSERT INTO platform.permissions(code, description) VALUES
          ('system.read', 'Consultar el estado de la instalación'),
          ('settings.read', 'Consultar la configuración de registro y prueba'),
          ('settings.write', 'Configurar el registro y el plan de prueba'),
          ('companies.create', 'Dar de alta una empresa'),
          ('support.reset', 'Restablecer acceso ISP con identidad verificada')
        ON CONFLICT (code) DO NOTHING;

        INSERT INTO platform.features(code, name, implemented)
          VALUES ('ACCESS', 'Usuarios y permisos', true)
        ON CONFLICT (code) DO UPDATE SET implemented = true;

        INSERT INTO platform.plan_features(plan_version_id, feature_id)
          SELECT v.id, f.id FROM platform.plan_versions v
          JOIN platform.plans p ON p.id = v.plan_id CROSS JOIN platform.features f
          WHERE p.code = 'TRIAL' AND f.code = 'ACCESS'
        ON CONFLICT (plan_version_id, feature_id) DO NOTHING;
    """)


def downgrade() -> None:
    raise RuntimeError("La configuración de acceso activa requiere una migración correctiva.")
