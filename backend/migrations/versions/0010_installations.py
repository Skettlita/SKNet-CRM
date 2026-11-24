"""Installation orders, their technicians, equipment, and change history."""

from alembic import op

revision = "0010_installations"
down_revision = "0009_device_assignment"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE crm.commercial_counters DROP CONSTRAINT commercial_counters_entity_check;
        ALTER TABLE crm.commercial_counters ADD CONSTRAINT commercial_counters_entity_check
          CHECK(entity IN ('client','service','site','device','installation'));
        CREATE TABLE crm.installations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES core.companies(id),
            installation_code text NOT NULL,
            client_id uuid NOT NULL,
            site_id uuid NOT NULL,
            service_id uuid NOT NULL,
            created_by uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            scheduled_at timestamptz,
            completed_at timestamptz,
            archived_at timestamptz,
            status text NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','SCHEDULED','IN_PROGRESS','COMPLETED','CANCELLED')),
            priority text NOT NULL DEFAULT 'NORMAL' CHECK(priority IN ('LOW','NORMAL','HIGH','CRITICAL')),
            observations text,
            technical_notes text,
            verification text,
            UNIQUE(company_id,id),
            UNIQUE(company_id,installation_code),
            FOREIGN KEY(company_id,client_id,service_id) REFERENCES crm.services(company_id,client_id,id),
            FOREIGN KEY(company_id,site_id,service_id) REFERENCES crm.services(company_id,site_id,id),
            FOREIGN KEY(company_id,created_by) REFERENCES core.memberships(company_id,id)
        );
        CREATE UNIQUE INDEX installations_active_service ON crm.installations(company_id,service_id)
          WHERE status IN ('PENDING','SCHEDULED','IN_PROGRESS');
        CREATE INDEX installations_queue ON crm.installations(company_id,status,created_at DESC);
        CREATE TABLE crm.installation_technicians (
            company_id uuid NOT NULL, installation_id uuid NOT NULL, membership_id uuid NOT NULL,
            assigned_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY(company_id,installation_id,membership_id),
            FOREIGN KEY(company_id,installation_id) REFERENCES crm.installations(company_id,id),
            FOREIGN KEY(company_id,membership_id) REFERENCES core.memberships(company_id,id)
        );
        CREATE TABLE crm.installation_devices (
            company_id uuid NOT NULL, installation_id uuid NOT NULL, device_id uuid NOT NULL,
            added_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY(company_id,installation_id,device_id),
            FOREIGN KEY(company_id,installation_id) REFERENCES crm.installations(company_id,id),
            FOREIGN KEY(company_id,device_id) REFERENCES crm.devices(company_id,id)
        );
        CREATE TABLE crm.installation_history (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL, installation_id uuid NOT NULL, actor_id uuid NOT NULL,
            occurred_at timestamptz NOT NULL DEFAULT now(),
            action text NOT NULL, previous_status text NOT NULL, new_status text NOT NULL, detail text,
            FOREIGN KEY(company_id,installation_id) REFERENCES crm.installations(company_id,id),
            FOREIGN KEY(company_id,actor_id) REFERENCES core.memberships(company_id,id)
        );
        CREATE INDEX installation_history_order ON crm.installation_history(company_id,installation_id,occurred_at DESC);
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
            INSERT INTO core.permissions(code,description) VALUES
              ('installations.read','Consultar instalaciones'),('installations.create','Registrar instalaciones'),
              ('installations.write','Programar y gestionar instalaciones'),('installations.complete','Completar instalaciones'),
              ('installations.archive','Archivar instalaciones'),('installations.delete','Eliminar borradores de instalaciones')
            RETURNING id
        )
        INSERT INTO core.role_permissions(company_id,role_id,permission_id)
        SELECT o.company_id,o.id,p.id FROM owners o CROSS JOIN added p;
    """)


def downgrade():
    raise RuntimeError("Usa una migración correctiva para conservar las órdenes.")
