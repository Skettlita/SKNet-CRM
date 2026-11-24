"""Add ISP catalogues and relate device units to them without rewriting legacy labels."""

from alembic import op

revision = "0012_device_catalogs"
down_revision = "0011_icmp_monitoring"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("device_types", "manufacturers"):
        op.execute(f"""
            CREATE TABLE inventory.{table} (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL REFERENCES core.companies(id),
                name text NOT NULL CHECK(length(btrim(name))>0),
                name_key text GENERATED ALWAYS AS (lower(regexp_replace(btrim(name),'[[:space:]]+',' ','g'))) STORED,
                active boolean NOT NULL DEFAULT true,
                UNIQUE(company_id,id), UNIQUE(company_id,name_key)
            );
        """)
    op.execute("""
        CREATE TABLE inventory.device_models (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_id uuid NOT NULL REFERENCES core.companies(id),
            type_id uuid NOT NULL, manufacturer_id uuid NOT NULL,
            name text NOT NULL CHECK(length(btrim(name))>0), active boolean NOT NULL DEFAULT true,
            UNIQUE(company_id,id), UNIQUE(company_id,type_id,manufacturer_id,name),
            UNIQUE(company_id,type_id,manufacturer_id,id),
            FOREIGN KEY(company_id,type_id) REFERENCES inventory.device_types(company_id,id),
            FOREIGN KEY(company_id,manufacturer_id) REFERENCES inventory.manufacturers(company_id,id)
        );
        ALTER TABLE crm.devices ADD COLUMN type_id uuid, ADD COLUMN manufacturer_id uuid, ADD COLUMN model_id uuid;
        INSERT INTO inventory.device_types(company_id,name)
            SELECT company_id,min(coalesce(nullif(btrim(device_type),''),'Sin tipo registrado'))
            FROM crm.devices GROUP BY company_id,lower(regexp_replace(coalesce(nullif(btrim(device_type),''),'Sin tipo registrado'),'[[:space:]]+',' ','g'));
        INSERT INTO inventory.manufacturers(company_id,name)
            SELECT company_id,min(btrim(brand)) FROM crm.devices WHERE nullif(btrim(brand),'') IS NOT NULL
            GROUP BY company_id,lower(regexp_replace(btrim(brand),'[[:space:]]+',' ','g'));
        UPDATE crm.devices d SET type_id=t.id FROM inventory.device_types t
            WHERE d.company_id=t.company_id AND t.name_key=lower(regexp_replace(coalesce(nullif(btrim(d.device_type),''),'Sin tipo registrado'),'[[:space:]]+',' ','g'));
        UPDATE crm.devices d SET manufacturer_id=m.id FROM inventory.manufacturers m
            WHERE d.company_id=m.company_id AND m.name_key=lower(regexp_replace(btrim(d.brand),'[[:space:]]+',' ','g'));
        INSERT INTO inventory.device_models(company_id,type_id,manufacturer_id,name)
            SELECT DISTINCT company_id,type_id,manufacturer_id,btrim(model) FROM crm.devices
            WHERE manufacturer_id IS NOT NULL AND nullif(btrim(model),'') IS NOT NULL;
        UPDATE crm.devices d SET model_id=m.id FROM inventory.device_models m
            WHERE (d.company_id,d.type_id,d.manufacturer_id,btrim(d.model))=(m.company_id,m.type_id,m.manufacturer_id,m.name);
        ALTER TABLE crm.devices ALTER COLUMN type_id SET NOT NULL,
            ADD FOREIGN KEY(company_id,type_id) REFERENCES inventory.device_types(company_id,id),
            ADD FOREIGN KEY(company_id,manufacturer_id) REFERENCES inventory.manufacturers(company_id,id),
            ADD FOREIGN KEY(company_id,model_id) REFERENCES inventory.device_models(company_id,id),
            ADD FOREIGN KEY(company_id,type_id,manufacturer_id,model_id)
                REFERENCES inventory.device_models(company_id,type_id,manufacturer_id,id),
            ADD CHECK(model_id IS NULL OR manufacturer_id IS NOT NULL);
        CREATE INDEX devices_model_stock ON crm.devices(company_id,model_id,device_category,assignment_state);
        WITH admins AS MATERIALIZED (
            SELECT r.id,r.company_id FROM core.roles r
            WHERE r.name='Administración' AND r.description='Administración inicial de la empresa'
                AND NOT EXISTS(SELECT 1 FROM core.permissions p WHERE NOT EXISTS(
                    SELECT 1 FROM core.role_permissions rp WHERE rp.company_id=r.company_id AND rp.role_id=r.id AND rp.permission_id=p.id))
        ), added AS (
            INSERT INTO core.permissions(code,description) VALUES
                ('inventory.read','Consultar stock y catálogos de equipos'),
                ('inventory.write','Administrar catálogos y registrar lotes de equipos')
            RETURNING id
        )
        INSERT INTO core.role_permissions(company_id,role_id,permission_id)
            SELECT a.company_id,a.id,n.id FROM admins a CROSS JOIN added n;
    """)


def downgrade():
    raise RuntimeError("Usa una revisión correctiva para conservar los catálogos y las unidades.")
