"""Allow unassigned assets and resolve management addresses without duplication."""

from alembic import op

revision = "0009_device_assignment"
down_revision = "0008_crm_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE crm.devices ALTER COLUMN site_id DROP NOT NULL,
          DROP CONSTRAINT devices_request_requires_ip,
          ADD COLUMN ip_mode text NOT NULL DEFAULT 'NONE',
          ADD COLUMN assignment_state text NOT NULL DEFAULT 'AVAILABLE',
          ADD COLUMN ownership text NOT NULL DEFAULT 'UNKNOWN';
        DO $$
        DECLARE keyname text;
        BEGIN
            SELECT conname INTO STRICT keyname FROM pg_constraint
            WHERE conrelid='crm.devices'::regclass AND contype='c'
              AND pg_get_constraintdef(oid) LIKE '%monitoring_enabled%';
            EXECUTE format('ALTER TABLE crm.devices DROP CONSTRAINT %I',keyname);
        END $$;
        UPDATE crm.devices SET ip_mode=CASE WHEN ip_address IS NULL THEN 'NONE' ELSE 'INDEPENDENT' END,
          assignment_state=CASE WHEN retired_at IS NULL THEN 'INSTALLED' ELSE 'RETIRED' END;
        ALTER TABLE crm.devices
          ADD CONSTRAINT devices_assignment_rules CHECK (
              (assignment_state='AVAILABLE' AND site_id IS NULL AND service_id IS NULL)
              OR (assignment_state IN ('ASSIGNED','INSTALLED') AND site_id IS NOT NULL)
              OR assignment_state IN ('MAINTENANCE','RETIRED')
          ),
          ADD CONSTRAINT devices_mode_rules CHECK (
              (ip_mode='INDEPENDENT' AND ip_address IS NOT NULL)
              OR (ip_mode='SERVICE' AND ip_address IS NULL AND service_id IS NOT NULL AND site_id IS NOT NULL)
              OR (ip_mode='NONE' AND ip_address IS NULL)
          ),
          ADD CONSTRAINT devices_monitored_assignment CHECK (NOT monitoring_enabled OR (
              ip_mode<>'NONE' AND site_id IS NOT NULL AND collector_id IS NOT NULL AND retired_at IS NULL
              AND assignment_state='INSTALLED'
          )),
          ADD CONSTRAINT devices_ownership_value CHECK (ownership IN ('ISP','CUSTOMER','THIRD_PARTY','UNKNOWN'));
        CREATE TABLE crm.device_assignments (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL,
            device_id uuid NOT NULL,
            actor_id uuid NOT NULL,
            occurred_at timestamptz NOT NULL DEFAULT now(),
            previous_data jsonb,
            current_data jsonb NOT NULL,
            reason text,
            FOREIGN KEY (company_id,device_id) REFERENCES crm.devices(company_id,id),
            FOREIGN KEY (company_id,actor_id) REFERENCES core.memberships(company_id,id)
        );
        CREATE INDEX device_assignments_timeline ON crm.device_assignments(company_id,device_id,occurred_at DESC,id);
        CREATE VIEW crm.device_targets AS
          SELECT d.*,s.client_id,
            CASE WHEN d.ip_mode='INDEPENDENT' THEN d.ip_address
                 WHEN d.ip_mode='SERVICE' AND family(c.service_ip)=4 AND c.archived_at IS NULL
                      AND c.status<>'CANCELLED' THEN c.service_ip END AS effective_ip
          FROM crm.devices d
          LEFT JOIN crm.sites s ON (s.company_id,s.id)=(d.company_id,d.site_id)
          LEFT JOIN crm.services c ON (c.company_id,c.id)=(d.company_id,d.service_id);
    """)


def downgrade():
    raise RuntimeError("Usa una migración correctiva para conservar el historial de equipos.")
