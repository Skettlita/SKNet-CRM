"""Add company counters, site and device classifications, and integrated registration."""

from alembic import op


revision = "0007_crm_workflow"
down_revision = "0006_connectivity"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE crm.commercial_counters (
            company_id uuid NOT NULL REFERENCES core.companies(id),
            entity text NOT NULL CHECK (entity IN ('client','service','site','device')),
            last_number bigint NOT NULL CHECK (last_number > 0),
            PRIMARY KEY (company_id,entity)
        );
        WITH ordinal AS (
            SELECT company_id,substring(client_code FROM '^CLI-([0-9]{1,19})$')::numeric AS value
            FROM crm.clients
        )
        INSERT INTO crm.commercial_counters(company_id,entity,last_number)
        SELECT company_id,'client',max(value)::bigint FROM ordinal
        WHERE value BETWEEN 1 AND 9223372036854775807 GROUP BY company_id;

        ALTER TABLE crm.sites DROP CONSTRAINT sites_site_type_check, DROP CONSTRAINT sites_check;
        ALTER TABLE crm.sites ADD COLUMN site_category text, ADD COLUMN client_address_id uuid;
        ALTER TABLE crm.client_addresses ADD CONSTRAINT client_addresses_customer_key UNIQUE (company_id,client_id,id);
        UPDATE crm.sites SET
            site_category=CASE WHEN client_id IS NOT NULL THEN 'CUSTOMER'
                WHEN site_type IN ('NODE','TOWER') THEN 'NETWORK' ELSE 'FACILITY' END,
            site_type=CASE site_type WHEN 'CLIENT_SITE' THEN 'CUSTOMER_OTHER' WHEN 'NODE' THEN 'NETWORK_OTHER'
                WHEN 'OFFICE' THEN 'ADMIN_OFFICE' WHEN 'OTHER' THEN 'FACILITY_OTHER' ELSE site_type END;
        ALTER TABLE crm.sites ALTER COLUMN site_category SET NOT NULL,
            ADD CONSTRAINT sites_category_client_check CHECK ((site_category='CUSTOMER') = (client_id IS NOT NULL)),
            ADD CONSTRAINT sites_category_type_check CHECK (
              (site_category='CUSTOMER' AND site_type IN ('HOME','CLIENT_OFFICE','BRANCH','BUILDING','BUSINESS_INSTALLATION','CUSTOMER_OTHER'))
              OR (site_category='NETWORK' AND site_type IN ('MAIN_NODE','DISTRIBUTION_NODE','TOWER','BASE_STATION','DATA_CENTER','ACCESS_POINT','NETWORK_OTHER'))
              OR (site_category='FACILITY' AND site_type IN ('ADMIN_OFFICE','WAREHOUSE','WORKSHOP','OPERATIONS_CENTER','FACILITY_OTHER'))
            ),
            ADD CONSTRAINT sites_customer_address_fk FOREIGN KEY (company_id,client_id,client_address_id)
                REFERENCES crm.client_addresses(company_id,client_id,id),
            ADD CONSTRAINT sites_linked_address_check CHECK (
                client_address_id IS NULL OR (client_id IS NOT NULL AND address IS NULL AND city IS NULL)
            );
        CREATE INDEX sites_company_category_idx ON crm.sites(company_id,site_category,site_type);
        CREATE INDEX sites_company_client_idx ON crm.sites(company_id,client_id);

        ALTER TABLE crm.devices ADD COLUMN device_category text, ADD COLUMN capabilities text[] NOT NULL DEFAULT '{}';
        UPDATE crm.devices d SET device_category=CASE WHEN s.client_id IS NOT NULL THEN 'CUSTOMER_EQUIPMENT' ELSE 'INFRASTRUCTURE' END
        FROM crm.sites s WHERE (s.company_id,s.id)=(d.company_id,d.site_id);
        WITH known AS (
            SELECT company_id,access_router_id,array_agg(DISTINCT
                CASE access_method WHEN 'PPPOE' THEN 'PPPOE_SERVER' WHEN 'DHCP' THEN 'DHCP_SERVER' ELSE 'ACCESS_ROUTER' END
                ORDER BY CASE access_method WHEN 'PPPOE' THEN 'PPPOE_SERVER' WHEN 'DHCP' THEN 'DHCP_SERVER' ELSE 'ACCESS_ROUTER' END
            ) AS capabilities
            FROM crm.services WHERE access_router_id IS NOT NULL GROUP BY company_id,access_router_id
        )
        UPDATE crm.devices d SET capabilities=k.capabilities FROM known k
        WHERE (d.company_id,d.id)=(k.company_id,k.access_router_id) AND d.device_category='INFRASTRUCTURE';
        ALTER TABLE crm.devices ALTER COLUMN device_category SET NOT NULL,
            ADD CONSTRAINT devices_category_check CHECK (device_category IN ('INFRASTRUCTURE','CUSTOMER_EQUIPMENT')),
            ADD CONSTRAINT devices_capabilities_check CHECK (
                array_position(capabilities,NULL) IS NULL
                AND capabilities <@ ARRAY['PPPOE_SERVER','DHCP_SERVER','ACCESS_ROUTER','DISTRIBUTION']::text[]
                AND (device_category='INFRASTRUCTURE' OR cardinality(capabilities)=0)
            );
        CREATE INDEX devices_company_site_idx ON crm.devices(company_id,site_id);
        CREATE INDEX services_access_router_idx ON crm.services(company_id,access_router_id) WHERE access_router_id IS NOT NULL;

        ALTER TABLE crm.services ADD COLUMN installation_situation text NOT NULL DEFAULT 'UNDEFINED'
            CHECK (installation_situation IN ('NEW','EXISTING','UNDEFINED'));
    """)
    # Table and prefix pairs are migration constants. Old tables have no commercial code in these columns.
    for table, entity, prefix in (("services", "service", "SRV"), ("sites", "site", "SIT"), ("devices", "device", "DSP")):
        op.execute(f"""
            ALTER TABLE crm.{table} ADD COLUMN {entity}_code text;
            WITH numbered AS (
                SELECT id,row_number() OVER (PARTITION BY company_id ORDER BY created_at,id) AS ordinal
                FROM crm.{table}
            )
            UPDATE crm.{table} t SET {entity}_code='{prefix}-' ||
                lpad(n.ordinal::text,greatest(6,length(n.ordinal::text)),'0')
            FROM numbered n WHERE n.id=t.id;
            INSERT INTO crm.commercial_counters(company_id,entity,last_number)
            SELECT company_id,'{entity}',count(*) FROM crm.{table} GROUP BY company_id;
            ALTER TABLE crm.{table} ALTER COLUMN {entity}_code SET NOT NULL,
                ADD CONSTRAINT {table}_company_code_key UNIQUE (company_id,{entity}_code);
        """)


def downgrade():
    raise RuntimeError("Usa una migración correctiva para conservar los códigos comerciales y las relaciones.")
