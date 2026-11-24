"""Track immutable collector images and controlled replacement jobs."""

from alembic import op

revision = "0013_collector_upgrades"
down_revision = "0012_device_catalogs"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE connectivity.collectors
          ADD COLUMN current_image text, ADD COLUMN observed_image text, ADD COLUMN available_image text;
        ALTER TABLE connectivity.provisioning_jobs DROP CONSTRAINT provisioning_jobs_operation_check;
        ALTER TABLE connectivity.provisioning_jobs
          ADD CONSTRAINT provisioning_jobs_operation_check
            CHECK (operation IN ('CREATE','CONFIGURE','ROTATE_KEY','RECONCILE','DISABLE','REMOVE','UPGRADE')),
          ADD COLUMN previous_image text, ADD COLUMN desired_image text,
          ADD COLUMN verify_after timestamptz,
          ADD COLUMN rollback_started boolean NOT NULL DEFAULT false,
          ADD COLUMN rolled_back boolean NOT NULL DEFAULT false;
        ALTER TABLE connectivity.network_pools ADD COLUMN residual_resources jsonb NOT NULL DEFAULT '[]';
    """)


def downgrade():
    op.execute("""
        DELETE FROM connectivity.provisioning_jobs WHERE operation='UPGRADE';
        ALTER TABLE connectivity.provisioning_jobs DROP CONSTRAINT provisioning_jobs_operation_check;
        ALTER TABLE connectivity.provisioning_jobs
          ADD CONSTRAINT provisioning_jobs_operation_check
            CHECK (operation IN ('CREATE','CONFIGURE','ROTATE_KEY','RECONCILE','DISABLE','REMOVE')),
          DROP COLUMN previous_image, DROP COLUMN desired_image, DROP COLUMN verify_after,
          DROP COLUMN rollback_started, DROP COLUMN rolled_back;
        ALTER TABLE connectivity.collectors DROP COLUMN current_image, DROP COLUMN observed_image, DROP COLUMN available_image;
        ALTER TABLE connectivity.network_pools DROP COLUMN residual_resources;
    """)
