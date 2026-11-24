-- SKNet: modelo consolidado V1 y horizonte funcional, PostgreSQL 17. Solo BD nueva.
-- No contiene API, procesos automaticos, RLS ni datos reales. Ver README.
CREATE SCHEMA core;
CREATE SCHEMA platform;
CREATE SCHEMA crm;
CREATE SCHEMA inventory;
CREATE SCHEMA billing;
CREATE SCHEMA platform_billing;
CREATE SCHEMA audit;
CREATE SCHEMA monitoring;
CREATE SCHEMA connectivity;

CREATE TABLE core.companies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    tax_id text,
    email text,
    phone text,
    timezone text NOT NULL DEFAULT 'America/La_Paz',
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'INACTIVE', 'CLOSED')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE core.users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    email text NOT NULL CHECK (position('@' in email) > 1),
    username text NOT NULL CHECK (username ~ '^[A-Za-z0-9_.-]{3,64}$'),
    account_scope text NOT NULL CHECK (account_scope IN ('ISP','SAAS')),
    email_verified_at timestamptz,
    must_change_password boolean NOT NULL DEFAULT false,
    last_login_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, account_scope),
    password_hash text NOT NULL,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE core.memberships (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    user_id uuid NOT NULL UNIQUE,
    account_scope text GENERATED ALWAYS AS ('ISP'::text) STORED,
    FOREIGN KEY (user_id, account_scope) REFERENCES core.users(id, account_scope),
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, user_id),
    UNIQUE (company_id, id),
    FOREIGN KEY (user_id) REFERENCES core.users(id)
);

CREATE TABLE core.permissions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL UNIQUE,
    description text NOT NULL
);

CREATE TABLE core.roles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    name text NOT NULL,
    description text,
    UNIQUE (company_id, name),
    UNIQUE (company_id, id)
);

CREATE TABLE core.membership_roles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    membership_id uuid NOT NULL,
    role_id uuid NOT NULL,
    UNIQUE (membership_id, role_id),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, membership_id) REFERENCES core.memberships(company_id, id),
    FOREIGN KEY (company_id, role_id) REFERENCES core.roles(company_id, id)
);

CREATE TABLE core.role_permissions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    role_id uuid NOT NULL,
    permission_id uuid NOT NULL,
    UNIQUE (role_id, permission_id),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, role_id) REFERENCES core.roles(company_id, id),
    FOREIGN KEY (permission_id) REFERENCES core.permissions(id)
);

CREATE TABLE core.password_reset_tokens (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL,
    token_hash text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    CHECK (expires_at > created_at),
    revoked_at timestamptz,
    used_at timestamptz,
    FOREIGN KEY (user_id) REFERENCES core.users(id)
);

CREATE TABLE core.sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES core.users(id),
    account_scope text NOT NULL,
    token_hash text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    last_seen_at timestamptz,
    revoked_at timestamptz,
    CHECK (expires_at > created_at),
    FOREIGN KEY (user_id, account_scope) REFERENCES core.users(id, account_scope)
);

CREATE TABLE platform.staff (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL,
    account_scope text GENERATED ALWAYS AS ('SAAS'::text) STORED,
    FOREIGN KEY (user_id, account_scope) REFERENCES core.users(id, account_scope),
    active boolean NOT NULL DEFAULT true,
    UNIQUE (user_id),
    FOREIGN KEY (user_id) REFERENCES core.users(id)
);

CREATE TABLE platform.roles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL UNIQUE,
    description text
);

CREATE TABLE platform.permissions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL UNIQUE,
    description text NOT NULL
);

CREATE TABLE platform.staff_roles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    staff_id uuid NOT NULL,
    role_id uuid NOT NULL,
    UNIQUE (staff_id, role_id),
    FOREIGN KEY (staff_id) REFERENCES platform.staff(id),
    FOREIGN KEY (role_id) REFERENCES platform.roles(id)
);

CREATE TABLE platform.role_permissions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    role_id uuid NOT NULL,
    permission_id uuid NOT NULL,
    UNIQUE (role_id, permission_id),
    FOREIGN KEY (role_id) REFERENCES platform.roles(id),
    FOREIGN KEY (permission_id) REFERENCES platform.permissions(id)
);

CREATE TABLE platform.plans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL UNIQUE,
    name text NOT NULL,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE platform.plan_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id uuid NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    monthly_price numeric(14,2) NOT NULL CHECK (monthly_price >= 0),
    currency char(3) NOT NULL DEFAULT 'BOB',
    trial_days integer,
    max_clients integer,
    max_devices integer,
    max_users integer,
    min_poll_interval_seconds integer,
    retention_days integer,
    effective_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (plan_id, version),
    CHECK (trial_days IS NULL OR trial_days > 0),
    CHECK (max_clients IS NULL OR max_clients > 0),
    CHECK (max_devices IS NULL OR max_devices > 0),
    CHECK (max_users IS NULL OR max_users > 0),
    CHECK (min_poll_interval_seconds IS NULL OR min_poll_interval_seconds > 0),
    CHECK (retention_days IS NULL OR retention_days > 0),
    FOREIGN KEY (plan_id) REFERENCES platform.plans(id)
);

CREATE TABLE platform.features (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code text NOT NULL UNIQUE,
    name text NOT NULL,
    implemented boolean NOT NULL DEFAULT false
);

CREATE TABLE platform.plan_features (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_version_id uuid NOT NULL,
    feature_id uuid NOT NULL,
    UNIQUE (plan_version_id, feature_id),
    FOREIGN KEY (plan_version_id) REFERENCES platform.plan_versions(id),
    FOREIGN KEY (feature_id) REFERENCES platform.features(id)
);

CREATE TABLE platform.settings (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    public_signup_enabled boolean NOT NULL DEFAULT false,
    default_plan_version_id uuid NOT NULL REFERENCES platform.plan_versions(id),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE platform.subscriptions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    plan_version_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'TRIAL' CHECK (status IN ('TRIAL', 'ACTIVE', 'GRACE', 'SUSPENDED', 'CANCELLED')),
    starts_at timestamptz NOT NULL DEFAULT now(),
    ends_at timestamptz,
    billing_day smallint NOT NULL DEFAULT 1 CHECK (billing_day BETWEEN 1 AND 31),
    payment_term_days integer NOT NULL DEFAULT 10 CHECK (payment_term_days >= 0),
    CHECK (ends_at IS NULL OR ends_at >= starts_at),
    UNIQUE (company_id, id),
    FOREIGN KEY (plan_version_id) REFERENCES platform.plan_versions(id)
);

CREATE TABLE platform.subscription_history (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    subscription_id uuid NOT NULL,
    changed_by uuid,
    previous_status text,
    new_status text NOT NULL,
    previous_plan_version_id uuid,
    new_plan_version_id uuid,
    reason text,
    changed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, subscription_id) REFERENCES platform.subscriptions(company_id, id),
    FOREIGN KEY (changed_by) REFERENCES core.users(id),
    FOREIGN KEY (previous_plan_version_id) REFERENCES platform.plan_versions(id),
    FOREIGN KEY (new_plan_version_id) REFERENCES platform.plan_versions(id)
);

CREATE TABLE platform.support_tickets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    requested_by uuid,
    origin text NOT NULL DEFAULT 'USER' CHECK (origin IN ('USER','SYSTEM')),
    fault_key text,
    assigned_staff_id uuid,
    subject text NOT NULL,
    description text NOT NULL,
    status text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'ASSIGNED', 'IN_PROGRESS', 'RESOLVED', 'CLOSED', 'CANCELLED')),
    priority text NOT NULL DEFAULT 'NORMAL' CHECK (priority IN ('LOW', 'NORMAL', 'HIGH', 'CRITICAL')),
    closure_reason text,
    opened_at timestamptz NOT NULL DEFAULT now(),
    closed_at timestamptz,
    CHECK (status <> 'CANCELLED' OR NULLIF(btrim(closure_reason),'') IS NOT NULL),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, requested_by) REFERENCES core.memberships(company_id, id),
    FOREIGN KEY (assigned_staff_id) REFERENCES platform.staff(id),
    CHECK ((origin='USER' AND requested_by IS NOT NULL AND fault_key IS NULL) OR (origin='SYSTEM' AND requested_by IS NULL AND fault_key IS NOT NULL))
);
CREATE UNIQUE INDEX support_one_active_fault ON platform.support_tickets(company_id,fault_key) WHERE origin='SYSTEM' AND status IN ('OPEN','ASSIGNED','IN_PROGRESS','RESOLVED');

CREATE TABLE platform.support_ticket_comments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    ticket_id uuid NOT NULL,
    author_user_id uuid NOT NULL,
    body text NOT NULL,
    internal boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, ticket_id) REFERENCES platform.support_tickets(company_id, id),
    FOREIGN KEY (author_user_id) REFERENCES core.users(id)
);

CREATE TABLE platform.support_ticket_history (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    ticket_id uuid NOT NULL,
    changed_by uuid,
    actor_type text NOT NULL DEFAULT 'USER' CHECK (actor_type IN ('USER','SYSTEM')),
    CHECK ((actor_type='USER') = (changed_by IS NOT NULL)),
    previous_status text,
    new_status text NOT NULL CHECK (new_status IN ('OPEN', 'ASSIGNED', 'IN_PROGRESS', 'RESOLVED', 'CLOSED', 'CANCELLED')),
    reason text,
    changed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, ticket_id) REFERENCES platform.support_tickets(company_id, id),
    FOREIGN KEY (changed_by) REFERENCES core.users(id)
);

CREATE TABLE platform.support_access_logs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    staff_id uuid NOT NULL,
    reason text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    ended_at timestamptz,
    CHECK (expires_at > started_at),
    UNIQUE (company_id, id),
    FOREIGN KEY (staff_id) REFERENCES platform.staff(id)
);

CREATE TABLE crm.clients (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    client_code text NOT NULL,
    client_type text NOT NULL DEFAULT 'PERSON' CHECK (client_type IN ('PERSON', 'COMPANY')),
    name text NOT NULL,
    document_type text,
    document_number text,
    email text,
    phone text,
    status text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'INACTIVE', 'CLOSED')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, client_code),
    UNIQUE (company_id, id)
);

CREATE TABLE crm.client_contacts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    client_id uuid NOT NULL,
    name text NOT NULL,
    position text,
    email text,
    phone text,
    is_primary boolean NOT NULL DEFAULT false,
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, client_id) REFERENCES crm.clients(company_id, id)
);

CREATE TABLE crm.sites (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    client_id uuid,
    name text NOT NULL,
    site_type text NOT NULL CHECK (site_type IN ('CLIENT_SITE', 'WAREHOUSE', 'OFFICE', 'NODE', 'TOWER', 'WORKSHOP', 'OTHER')),
    address text,
    city text,
    latitude numeric(9,6),
    longitude numeric(9,6),
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((site_type = 'CLIENT_SITE') = (client_id IS NOT NULL)),
    CHECK (latitude BETWEEN -90 AND 90),
    CHECK (longitude BETWEEN -180 AND 180),
    UNIQUE (company_id, client_id, id),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, client_id) REFERENCES crm.clients(company_id, id)
);

CREATE TABLE crm.client_addresses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    client_id uuid NOT NULL,
    address text NOT NULL,
    city text,
    address_type text NOT NULL DEFAULT 'OTHER' CHECK (address_type IN ('BILLING', 'LEGAL', 'OTHER')),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, client_id) REFERENCES crm.clients(company_id, id)
);

CREATE TABLE crm.service_plans (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    name text NOT NULL,
    service_type text NOT NULL,
    monthly_price numeric(14,2) NOT NULL CHECK (monthly_price >= 0),
    download_mbps integer,
    upload_mbps integer,
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, id)
);

CREATE TABLE crm.services (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    client_id uuid NOT NULL,
    site_id uuid NOT NULL,
    plan_id uuid NOT NULL,
    monthly_price numeric(14,2) NOT NULL CHECK (monthly_price >= 0),
    access_method text NOT NULL DEFAULT 'OTHER' CHECK (access_method IN ('PPPOE','DHCP','STATIC','OTHER')),
    ip_assignment text CHECK (ip_assignment IN ('DYNAMIC','FIXED')),
    pppoe_username text,
    service_ip inet,
    service_ip_observed_at timestamptz,
    access_mac macaddr,
    access_router_id uuid,
    technical_notes text,
    CHECK (pppoe_username IS NULL OR access_method = 'PPPOE'),
    CHECK (access_method <> 'STATIC' OR ip_assignment IS NULL OR ip_assignment = 'FIXED'),
    status text NOT NULL DEFAULT 'PENDING'  CHECK (status IN ('PENDING', 'ACTIVE', 'SUSPENDED', 'CANCELLED')),
    activated_at timestamptz,
    cancelled_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, client_id, id),
    UNIQUE (company_id, site_id, id),
    FOREIGN KEY (company_id, client_id, site_id) REFERENCES crm.sites(company_id, client_id, id),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, client_id) REFERENCES crm.clients(company_id, id),
    FOREIGN KEY (company_id, site_id) REFERENCES crm.sites(company_id, id),
    FOREIGN KEY (company_id, plan_id) REFERENCES crm.service_plans(company_id, id)
);

CREATE TABLE crm.service_status_history (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    service_id uuid NOT NULL,
    changed_by uuid,
    previous_status text,
    new_status text NOT NULL,
    reason text,
    changed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, service_id) REFERENCES crm.services(company_id, id),
    FOREIGN KEY (company_id, changed_by) REFERENCES core.memberships(company_id, id)
);

CREATE TABLE crm.documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    client_id uuid NOT NULL,
    uploaded_by uuid NOT NULL,
    file_name text NOT NULL,
    storage_key text NOT NULL,
    mime_type text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, client_id, id),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, client_id) REFERENCES crm.clients(company_id, id),
    FOREIGN KEY (company_id, uploaded_by) REFERENCES core.memberships(company_id, id)
);

CREATE TABLE crm.contracts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    client_id uuid NOT NULL,
    service_id uuid,
    document_id uuid NOT NULL,
    contract_number text NOT NULL,
    start_date date NOT NULL,
    end_date date,
    status text NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT', 'ACTIVE', 'EXPIRED', 'CANCELLED')),
    UNIQUE (company_id, contract_number),
    CHECK (end_date IS NULL OR end_date >= start_date),
    FOREIGN KEY (company_id, client_id, service_id) REFERENCES crm.services(company_id, client_id, id),
    FOREIGN KEY (company_id, client_id, document_id) REFERENCES crm.documents(company_id, client_id, id),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, client_id) REFERENCES crm.clients(company_id, id),
    FOREIGN KEY (company_id, service_id) REFERENCES crm.services(company_id, id),
    FOREIGN KEY (company_id, document_id) REFERENCES crm.documents(company_id, id)
);

CREATE TABLE crm.client_notes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    client_id uuid NOT NULL,
    author_id uuid NOT NULL,
    body text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, client_id) REFERENCES crm.clients(company_id, id),
    FOREIGN KEY (company_id, author_id) REFERENCES core.memberships(company_id, id)
);

CREATE TABLE crm.tags (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    name text NOT NULL,
    UNIQUE (company_id, name),
    UNIQUE (company_id, id)
);

CREATE TABLE crm.client_tags (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    client_id uuid NOT NULL,
    tag_id uuid NOT NULL,
    UNIQUE (client_id, tag_id),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, client_id) REFERENCES crm.clients(company_id, id),
    FOREIGN KEY (company_id, tag_id) REFERENCES crm.tags(company_id, id)
);

CREATE TABLE crm.tickets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    client_id uuid NOT NULL,
    service_id uuid,
    created_by uuid NOT NULL,
    assigned_to uuid,
    ticket_number text NOT NULL,
    subject text NOT NULL,
    description text NOT NULL,
    priority text NOT NULL DEFAULT 'NORMAL' CHECK (priority IN ('LOW', 'NORMAL', 'HIGH', 'CRITICAL')),
    status text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'ASSIGNED', 'IN_PROGRESS', 'RESOLVED', 'CLOSED', 'CANCELLED')),
    resolution text,
    closure_reason text,
    opened_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    closed_at timestamptz,
    UNIQUE (company_id, ticket_number),
    FOREIGN KEY (company_id, client_id, service_id) REFERENCES crm.services(company_id, client_id, id),
    CHECK (status <> 'CANCELLED' OR NULLIF(btrim(closure_reason),'') IS NOT NULL),
    CHECK (status NOT IN ('RESOLVED','CLOSED') OR NULLIF(btrim(resolution),'') IS NOT NULL),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, client_id) REFERENCES crm.clients(company_id, id),
    FOREIGN KEY (company_id, service_id) REFERENCES crm.services(company_id, id),
    FOREIGN KEY (company_id, created_by) REFERENCES core.memberships(company_id, id),
    FOREIGN KEY (company_id, assigned_to) REFERENCES core.memberships(company_id, id)
);

CREATE TABLE crm.ticket_comments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    ticket_id uuid NOT NULL,
    author_id uuid NOT NULL,
    body text NOT NULL,
    internal boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, ticket_id) REFERENCES crm.tickets(company_id, id),
    FOREIGN KEY (company_id, author_id) REFERENCES core.memberships(company_id, id)
);

CREATE TABLE crm.ticket_status_history (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    ticket_id uuid NOT NULL,
    changed_by uuid NOT NULL,
    previous_status text,
    new_status text NOT NULL CHECK (new_status IN ('OPEN', 'ASSIGNED', 'IN_PROGRESS', 'RESOLVED', 'CLOSED', 'CANCELLED')),
    reason text,
    changed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, ticket_id) REFERENCES crm.tickets(company_id, id),
    FOREIGN KEY (company_id, changed_by) REFERENCES core.memberships(company_id, id)
);

CREATE TABLE crm.work_orders (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    ticket_id uuid NOT NULL,
    order_number text NOT NULL,
    title text NOT NULL,
    description text,
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')),
    scheduled_at timestamptz,
    completed_at timestamptz,
    result text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, order_number),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, ticket_id) REFERENCES crm.tickets(company_id, id)
);

CREATE TABLE crm.work_order_assignments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    work_order_id uuid NOT NULL,
    membership_id uuid NOT NULL,
    assigned_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (work_order_id, membership_id),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, work_order_id) REFERENCES crm.work_orders(company_id, id),
    FOREIGN KEY (company_id, membership_id) REFERENCES core.memberships(company_id, id)
);

CREATE TABLE crm.work_order_history (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    work_order_id uuid NOT NULL,
    changed_by uuid NOT NULL,
    previous_status text,
    new_status text NOT NULL,
    reason text,
    changed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, work_order_id) REFERENCES crm.work_orders(company_id, id),
    FOREIGN KEY (company_id, changed_by) REFERENCES core.memberships(company_id, id)
);

CREATE TABLE crm.tasks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    client_id uuid NOT NULL,
    assigned_to uuid,
    title text NOT NULL,
    description text,
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')),
    due_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, client_id) REFERENCES crm.clients(company_id, id),
    FOREIGN KEY (company_id, assigned_to) REFERENCES core.memberships(company_id, id)
);

CREATE TABLE crm.activities (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    client_id uuid NOT NULL,
    created_by uuid NOT NULL,
    activity_type text NOT NULL,
    subject text NOT NULL,
    description text,
    activity_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, client_id) REFERENCES crm.clients(company_id, id),
    FOREIGN KEY (company_id, created_by) REFERENCES core.memberships(company_id, id)
);

CREATE TABLE inventory.products (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    sku text NOT NULL,
    name text NOT NULL,
    brand text,
    model text,
    tracking_type text NOT NULL DEFAULT 'QUANTITY' CHECK (tracking_type IN ('QUANTITY', 'SERIAL')),
    unit text NOT NULL DEFAULT 'unit',
    active boolean NOT NULL DEFAULT true,
    UNIQUE (company_id, sku),
    UNIQUE (company_id, id)
);

CREATE TABLE inventory.warehouses (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    site_id uuid NOT NULL,
    name text NOT NULL,
    UNIQUE (company_id, site_id),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, site_id) REFERENCES crm.sites(company_id, id)
);

CREATE TABLE inventory.storage_locations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    warehouse_id uuid NOT NULL,
    code text NOT NULL,
    description text,
    UNIQUE (warehouse_id, code),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, warehouse_id) REFERENCES inventory.warehouses(company_id, id)
);

CREATE TABLE inventory.stock_movements (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    product_id uuid NOT NULL,
    from_location_id uuid,
    to_location_id uuid,
    work_order_id uuid,
    performed_by uuid NOT NULL,
    quantity numeric(14,3) NOT NULL CHECK (quantity > 0),
    reason text NOT NULL,
    moved_at timestamptz NOT NULL DEFAULT now(),
    CHECK (from_location_id IS NOT NULL OR to_location_id IS NOT NULL),
    CHECK (from_location_id IS DISTINCT FROM to_location_id),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, product_id) REFERENCES inventory.products(company_id, id),
    FOREIGN KEY (company_id, from_location_id) REFERENCES inventory.storage_locations(company_id, id),
    FOREIGN KEY (company_id, to_location_id) REFERENCES inventory.storage_locations(company_id, id),
    FOREIGN KEY (company_id, work_order_id) REFERENCES crm.work_orders(company_id, id),
    FOREIGN KEY (company_id, performed_by) REFERENCES core.memberships(company_id, id)
);

CREATE TABLE inventory.assets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    product_id uuid NOT NULL,
    current_site_id uuid,
    current_storage_location_id uuid,
    asset_code text NOT NULL,
    serial_number text,
    ownership text NOT NULL DEFAULT 'COMPANY' CHECK (ownership IN ('COMPANY', 'CLIENT')),
    status text NOT NULL DEFAULT 'IN_STOCK' CHECK (status IN ('IN_STOCK', 'INSTALLED', 'REPAIR', 'RETIRED')),
    purchase_date date,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, asset_code),
    UNIQUE (company_id, product_id, serial_number),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, product_id) REFERENCES inventory.products(company_id, id),
    FOREIGN KEY (company_id, current_site_id) REFERENCES crm.sites(company_id, id),
    FOREIGN KEY (company_id, current_storage_location_id) REFERENCES inventory.storage_locations(company_id, id)
);

CREATE TABLE inventory.asset_movements (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    asset_id uuid NOT NULL,
    from_site_id uuid,
    to_site_id uuid,
    from_storage_location_id uuid,
    to_storage_location_id uuid,
    work_order_id uuid,
    performed_by uuid NOT NULL,
    reason text NOT NULL,
    moved_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, asset_id) REFERENCES inventory.assets(company_id, id),
    FOREIGN KEY (company_id, from_site_id) REFERENCES crm.sites(company_id, id),
    FOREIGN KEY (company_id, to_site_id) REFERENCES crm.sites(company_id, id),
    FOREIGN KEY (company_id, from_storage_location_id) REFERENCES inventory.storage_locations(company_id, id),
    FOREIGN KEY (company_id, to_storage_location_id) REFERENCES inventory.storage_locations(company_id, id),
    FOREIGN KEY (company_id, work_order_id) REFERENCES crm.work_orders(company_id, id),
    FOREIGN KEY (company_id, performed_by) REFERENCES core.memberships(company_id, id)
);

CREATE TABLE connectivity.network_pools (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL UNIQUE,
    docker_pool cidr NOT NULL CHECK (family(docker_pool)=4 AND masklen(docker_pool)<=30),
    wireguard_pool cidr NOT NULL CHECK (family(wireguard_pool)=4 AND masklen(wireguard_pool)<=31),
    port_start integer NOT NULL CHECK (port_start BETWEEN 1 AND 65535),
    port_end integer NOT NULL CHECK (port_end BETWEEN 1 AND 65535),
    endpoint_host text NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    CHECK (port_end >= port_start),
    CHECK (NOT (docker_pool && wireguard_pool))
);

CREATE TABLE connectivity.collectors (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    name text NOT NULL UNIQUE,
    docker_container_id text UNIQUE,
    provisioning_status text NOT NULL DEFAULT 'PENDING' CHECK (provisioning_status IN ('PENDING','PROVISIONING','WAITING_PUBLIC_KEY','WAITING_HANDSHAKE','READY','ERROR','DISABLED')),
    enabled boolean NOT NULL DEFAULT true,
    last_heartbeat_at timestamptz,
    last_error text,
    config_revision bigint NOT NULL DEFAULT 1 CHECK (config_revision > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    retired_at timestamptz,
    UNIQUE (company_id,id)
);
CREATE UNIQUE INDEX collectors_one_current ON connectivity.collectors(company_id) WHERE retired_at IS NULL;

CREATE TABLE connectivity.resource_allocations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    collector_id uuid NOT NULL,
    pool_id uuid NOT NULL REFERENCES connectivity.network_pools(id),
    docker_network_name text NOT NULL,
    docker_subnet cidr NOT NULL CHECK (family(docker_subnet)=4 AND masklen(docker_subnet)=30),
    wireguard_subnet cidr NOT NULL CHECK (family(wireguard_subnet)=4 AND masklen(wireguard_subnet)=31),
    external_udp_port integer NOT NULL CHECK (external_udp_port BETWEEN 1 AND 65535),
    edge_rule_tag text UNIQUE,
    status text NOT NULL DEFAULT 'RESERVED' CHECK (status IN ('RESERVED','ACTIVE','RELEASING','RELEASED')),
    reserved_at timestamptz NOT NULL DEFAULT now(),
    released_at timestamptz,
    CHECK ((status='RELEASED') = (released_at IS NOT NULL)),
    CHECK (NOT (docker_subnet && wireguard_subnet)),
    UNIQUE (company_id,id),
    UNIQUE (company_id,collector_id,id),
    FOREIGN KEY (company_id,collector_id) REFERENCES connectivity.collectors(company_id,id)
);
CREATE UNIQUE INDEX allocations_docker_unique ON connectivity.resource_allocations(docker_subnet) WHERE released_at IS NULL;
CREATE UNIQUE INDEX allocations_wg_unique ON connectivity.resource_allocations(wireguard_subnet) WHERE released_at IS NULL;
CREATE UNIQUE INDEX allocations_port_unique ON connectivity.resource_allocations(external_udp_port) WHERE released_at IS NULL;
CREATE UNIQUE INDEX allocations_network_unique ON connectivity.resource_allocations(docker_network_name) WHERE released_at IS NULL;
CREATE UNIQUE INDEX allocations_collector_unique ON connectivity.resource_allocations(collector_id) WHERE released_at IS NULL;

CREATE TABLE connectivity.vpn_tunnels (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    collector_id uuid NOT NULL,
    allocation_id uuid NOT NULL UNIQUE,
    interface_name text NOT NULL DEFAULT 'wg0',
    server_public_key text NOT NULL,
    peer_public_key text,
    private_key_ref text NOT NULL,
    endpoint_host text NOT NULL,
    internal_udp_port integer NOT NULL DEFAULT 51820 CHECK (internal_udp_port BETWEEN 1 AND 65535),
    keepalive_seconds integer NOT NULL DEFAULT 25 CHECK (keepalive_seconds BETWEEN 0 AND 65535),
    mtu integer NOT NULL DEFAULT 1420 CHECK (mtu BETWEEN 576 AND 65535),
    enabled boolean NOT NULL DEFAULT true,
    connection_status text NOT NULL DEFAULT 'UNKNOWN' CHECK (connection_status IN ('UNKNOWN','CONNECTED','DISCONNECTED')),
    last_handshake_at timestamptz,
    last_probe_at timestamptz,
    last_success_at timestamptz,
    consecutive_failures integer NOT NULL DEFAULT 0 CHECK (consecutive_failures>=0),
    created_at timestamptz NOT NULL DEFAULT now(),
    retired_at timestamptz,
    UNIQUE (company_id,id),
    FOREIGN KEY (company_id,collector_id,allocation_id) REFERENCES connectivity.resource_allocations(company_id,collector_id,id)
);
CREATE UNIQUE INDEX tunnels_one_current ON connectivity.vpn_tunnels(collector_id) WHERE retired_at IS NULL;

CREATE TABLE connectivity.vpn_routes (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    tunnel_id uuid NOT NULL,
    destination_network cidr NOT NULL CHECK (family(destination_network)=4 AND masklen(destination_network)>0),
    enabled boolean NOT NULL DEFAULT true,
    UNIQUE (tunnel_id,destination_network),
    UNIQUE (company_id,id),
    FOREIGN KEY (company_id,tunnel_id) REFERENCES connectivity.vpn_tunnels(company_id,id)
);

CREATE TABLE connectivity.collector_credentials (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    collector_id uuid NOT NULL,
    token_hash text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    revoked_at timestamptz,
    CHECK (expires_at IS NULL OR expires_at>created_at),
    UNIQUE (company_id,id),
    FOREIGN KEY (company_id,collector_id) REFERENCES connectivity.collectors(company_id,id)
);

CREATE TABLE connectivity.provisioning_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    collector_id uuid NOT NULL,
    requested_by_user_id uuid REFERENCES core.users(id),
    operation text NOT NULL CHECK (operation IN ('CREATE','CONFIGURE','ROTATE_KEY','RECONCILE','DISABLE','REMOVE')),
    idempotency_key text NOT NULL,
    status text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','RUNNING','SUCCEEDED','FAILED','CANCELLED')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts>=0),
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    UNIQUE (collector_id,idempotency_key),
    UNIQUE (company_id,id),
    FOREIGN KEY (company_id,collector_id) REFERENCES connectivity.collectors(company_id,id)
);
CREATE UNIQUE INDEX jobs_one_running ON connectivity.provisioning_jobs(collector_id) WHERE status='RUNNING';

CREATE TABLE connectivity.vpn_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    tunnel_id uuid NOT NULL,
    event_type text NOT NULL CHECK (event_type IN ('CONNECTED','DISCONNECTED','CONFIG_CHANGED','ERROR','DISABLED')),
    detail text,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id,id),
    FOREIGN KEY (company_id,tunnel_id) REFERENCES connectivity.vpn_tunnels(company_id,id)
);

CREATE TABLE crm.devices (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    service_id uuid,
    site_id uuid NOT NULL,
    asset_id uuid,
    name text NOT NULL,
    device_type text NOT NULL,
    device_role text NOT NULL DEFAULT 'ENDPOINT' CHECK (device_role IN ('NODE','INTERMEDIATE','ENDPOINT')),
    collector_id uuid,
    config_revision bigint NOT NULL DEFAULT 1 CHECK (config_revision>0),
    FOREIGN KEY (company_id,collector_id) REFERENCES connectivity.collectors(company_id,id),
    brand text,
    model text,
    serial_number text,
    mac_address macaddr,
    ip_address inet,
    monitoring_enabled boolean NOT NULL DEFAULT false,
    installed_at timestamptz,
    retired_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (ip_address IS NULL OR (family(ip_address)=4 AND masklen(ip_address)=32)),
    CHECK (NOT monitoring_enabled OR (ip_address IS NOT NULL AND collector_id IS NOT NULL AND retired_at IS NULL)),
    FOREIGN KEY (company_id, site_id, service_id) REFERENCES crm.services(company_id, site_id, id),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, service_id) REFERENCES crm.services(company_id, id),
    FOREIGN KEY (company_id, site_id) REFERENCES crm.sites(company_id, id),
    FOREIGN KEY (company_id, asset_id) REFERENCES inventory.assets(company_id, id)
);

ALTER TABLE crm.services ADD CONSTRAINT services_access_router_fk FOREIGN KEY (company_id,access_router_id) REFERENCES crm.devices(company_id,id);
CREATE UNIQUE INDEX devices_active_monitor_ip ON crm.devices(collector_id,ip_address) WHERE retired_at IS NULL AND collector_id IS NOT NULL AND ip_address IS NOT NULL;

CREATE TABLE billing.billing_profiles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    client_id uuid NOT NULL,
    billing_day smallint NOT NULL DEFAULT 1 CHECK (billing_day BETWEEN 1 AND 31),
    payment_term_days integer NOT NULL DEFAULT 10 CHECK (payment_term_days >= 0),
    currency char(3) NOT NULL DEFAULT 'BOB',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, client_id),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, client_id) REFERENCES crm.clients(company_id, id)
);

CREATE TABLE billing.charges (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    client_id uuid NOT NULL,
    service_id uuid NOT NULL,
    description text NOT NULL,
    charge_type text NOT NULL DEFAULT 'MONTHLY' CHECK (charge_type IN ('MONTHLY', 'OTHER')),
    period_start date,
    period_end date,
    generated_on date NOT NULL,
    due_on date NOT NULL,
    amount numeric(14,2) NOT NULL CHECK (amount > 0),
    currency char(3) NOT NULL DEFAULT 'BOB',
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (due_on >= generated_on),
    CHECK (charge_type <> 'MONTHLY' OR (period_start IS NOT NULL AND period_end IS NOT NULL AND period_end > period_start)),
    UNIQUE (company_id, client_id, currency, id),
    FOREIGN KEY (company_id, client_id, service_id) REFERENCES crm.services(company_id, client_id, id),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, service_id) REFERENCES crm.services(company_id, id),
    FOREIGN KEY (company_id, client_id) REFERENCES crm.clients(company_id, id)
);

CREATE TABLE billing.payments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    client_id uuid NOT NULL,
    amount numeric(14,2) NOT NULL CHECK (amount > 0),
    currency char(3) NOT NULL DEFAULT 'BOB',
    method text NOT NULL,
    reference text,
    received_by uuid NOT NULL,
    paid_at timestamptz NOT NULL DEFAULT now(),
    voided_at timestamptz,
    void_reason text,
    UNIQUE (company_id, client_id, currency, id),
    CHECK (voided_at IS NULL OR NULLIF(btrim(void_reason),'') IS NOT NULL),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, received_by) REFERENCES core.memberships(company_id, id),
    FOREIGN KEY (company_id, client_id) REFERENCES crm.clients(company_id, id)
);

CREATE TABLE billing.payment_allocations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    client_id uuid NOT NULL,
    payment_id uuid NOT NULL,
    charge_id uuid NOT NULL,
    currency char(3) NOT NULL DEFAULT 'BOB',
    amount numeric(14,2) NOT NULL CHECK (amount > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (payment_id, charge_id),
    FOREIGN KEY (company_id, client_id, currency, payment_id) REFERENCES billing.payments(company_id, client_id, currency, id),
    FOREIGN KEY (company_id, client_id, currency, charge_id) REFERENCES billing.charges(company_id, client_id, currency, id),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, payment_id) REFERENCES billing.payments(company_id, id),
    FOREIGN KEY (company_id, charge_id) REFERENCES billing.charges(company_id, id)
);

CREATE TABLE billing.receipts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    payment_id uuid NOT NULL,
    receipt_number text NOT NULL,
    issued_at timestamptz NOT NULL DEFAULT now(),
    voided_at timestamptz,
    UNIQUE (company_id, receipt_number),
    UNIQUE (payment_id),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, payment_id) REFERENCES billing.payments(company_id, id)
);

CREATE TABLE billing.adjustments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    charge_id uuid NOT NULL,
    amount numeric(14,2) NOT NULL CHECK (amount <> 0),
    reason text NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, charge_id) REFERENCES billing.charges(company_id, id),
    FOREIGN KEY (company_id, created_by) REFERENCES core.memberships(company_id, id)
);

CREATE TABLE platform_billing.charges (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    subscription_id uuid NOT NULL,
    description text NOT NULL,
    charge_type text NOT NULL DEFAULT 'MONTHLY' CHECK (charge_type IN ('MONTHLY', 'OTHER')),
    period_start date,
    period_end date,
    generated_on date NOT NULL,
    due_on date NOT NULL,
    amount numeric(14,2) NOT NULL CHECK (amount > 0),
    currency char(3) NOT NULL DEFAULT 'BOB',
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (due_on >= generated_on),
    CHECK (charge_type <> 'MONTHLY' OR (period_start IS NOT NULL AND period_end IS NOT NULL AND period_end > period_start)),
    UNIQUE (company_id, currency, id),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, subscription_id) REFERENCES platform.subscriptions(company_id, id)
);

CREATE TABLE platform_billing.payments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    amount numeric(14,2) NOT NULL CHECK (amount > 0),
    currency char(3) NOT NULL DEFAULT 'BOB',
    method text NOT NULL,
    reference text,
    received_by uuid NOT NULL,
    paid_at timestamptz NOT NULL DEFAULT now(),
    voided_at timestamptz,
    void_reason text,
    UNIQUE (company_id, currency, id),
    CHECK (voided_at IS NULL OR NULLIF(btrim(void_reason),'') IS NOT NULL),
    UNIQUE (company_id, id),
    FOREIGN KEY (received_by) REFERENCES platform.staff(id)
);

CREATE TABLE platform_billing.payment_allocations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    payment_id uuid NOT NULL,
    charge_id uuid NOT NULL,
    currency char(3) NOT NULL DEFAULT 'BOB',
    amount numeric(14,2) NOT NULL CHECK (amount > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (payment_id, charge_id),
    FOREIGN KEY (company_id, currency, payment_id) REFERENCES platform_billing.payments(company_id, currency, id),
    FOREIGN KEY (company_id, currency, charge_id) REFERENCES platform_billing.charges(company_id, currency, id),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, payment_id) REFERENCES platform_billing.payments(company_id, id),
    FOREIGN KEY (company_id, charge_id) REFERENCES platform_billing.charges(company_id, id)
);

CREATE TABLE platform_billing.receipts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    payment_id uuid NOT NULL,
    receipt_number text NOT NULL,
    issued_at timestamptz NOT NULL DEFAULT now(),
    voided_at timestamptz,
    UNIQUE (company_id, receipt_number),
    UNIQUE (payment_id),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, payment_id) REFERENCES platform_billing.payments(company_id, id)
);

CREATE TABLE platform_billing.adjustments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    charge_id uuid NOT NULL,
    amount numeric(14,2) NOT NULL CHECK (amount <> 0),
    reason text NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, charge_id) REFERENCES platform_billing.charges(company_id, id),
    FOREIGN KEY (created_by) REFERENCES platform.staff(id)
);

CREATE TABLE audit.events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id uuid,
    company_id uuid,
    action text NOT NULL,
    entity_type text NOT NULL,
    entity_id uuid,
    before_data jsonb,
    after_data jsonb,
    reason text,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (actor_user_id) REFERENCES core.users(id),
    FOREIGN KEY (company_id) REFERENCES core.companies(id)
);

CREATE TABLE monitoring.icmp_profiles (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    device_id uuid NOT NULL,
    enabled boolean NOT NULL DEFAULT true,
    interval_seconds integer NOT NULL DEFAULT 30 CHECK (interval_seconds BETWEEN 5 AND 86400),
    timeout_ms integer NOT NULL DEFAULT 2000 CHECK (timeout_ms BETWEEN 100 AND 10000),
    packet_count smallint NOT NULL DEFAULT 5 CHECK (packet_count BETWEEN 1 AND 10),
    latency_warning_ms numeric(12,3) NOT NULL DEFAULT 200 CHECK (latency_warning_ms>0),
    loss_warning_pct numeric(5,2) NOT NULL DEFAULT 0 CHECK (loss_warning_pct BETWEEN 0 AND 99.99),
    loss_failure_pct numeric(5,2) NOT NULL DEFAULT 30 CHECK (loss_failure_pct BETWEEN 0 AND 99.99),
    CHECK (loss_warning_pct <= loss_failure_pct),
    failure_threshold smallint NOT NULL DEFAULT 3 CHECK (failure_threshold > 0),
    recovery_threshold smallint NOT NULL DEFAULT 2 CHECK (recovery_threshold > 0),
    UNIQUE (device_id),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, device_id) REFERENCES crm.devices(company_id, id)
);

CREATE TABLE monitoring.icmp_checks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    device_id uuid NOT NULL,
    collector_id uuid NOT NULL,
    measurement_id uuid NOT NULL,
    device_config_revision bigint NOT NULL CHECK (device_config_revision>0),
    checked_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    packets_sent smallint,
    packets_received smallint,
    UNIQUE (collector_id,measurement_id),
    FOREIGN KEY (company_id,collector_id) REFERENCES connectivity.collectors(company_id,id),
    result text NOT NULL CHECK (result IN ('REACHABLE', 'NO_REPLY', 'ERROR', 'SKIPPED_VPN')),
    latency_ms numeric(12,3),
    packet_loss_pct numeric(5,2),
    error_detail text,
    CHECK (latency_ms >= 0),
    CHECK ((result IN ('ERROR','SKIPPED_VPN') AND packets_sent IS NULL AND packets_received IS NULL AND latency_ms IS NULL AND packet_loss_pct IS NULL) OR
           (result IN ('REACHABLE','NO_REPLY') AND packets_sent IS NOT NULL AND packets_sent>0 AND packets_received IS NOT NULL AND packets_received BETWEEN 0 AND packets_sent AND packet_loss_pct IS NOT NULL AND
             ((result='NO_REPLY' AND packets_received=0 AND latency_ms IS NULL AND packet_loss_pct=100) OR (result='REACHABLE' AND packets_received>0 AND latency_ms IS NOT NULL AND packet_loss_pct<100)))),
    CHECK (packet_loss_pct BETWEEN 0 AND 100),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, device_id) REFERENCES crm.devices(company_id, id)
);

CREATE TABLE monitoring.device_status (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    device_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'UNKNOWN' CHECK (status IN ('UNKNOWN', 'UP', 'DOWN', 'DEGRADED')),
    last_check_at timestamptz,
    last_success_at timestamptz,
    last_latency_ms numeric(12,3),
    last_packet_loss_pct numeric(5,2) CHECK (last_packet_loss_pct BETWEEN 0 AND 100),
    last_valid_check_at timestamptz,
    last_measurement_id uuid,
    device_config_revision bigint NOT NULL DEFAULT 1 CHECK (device_config_revision>0),
    consecutive_failures integer NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
    consecutive_successes integer NOT NULL DEFAULT 0 CHECK (consecutive_successes >= 0),
    changed_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (device_id),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, device_id) REFERENCES crm.devices(company_id, id)
);

CREATE TABLE monitoring.incidents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    device_id uuid NOT NULL,
    incident_type text NOT NULL DEFAULT 'ICMP_UNREACHABLE',
    started_at timestamptz NOT NULL,
    detected_at timestamptz NOT NULL DEFAULT now(),
    ended_at timestamptz,
    end_reason text,
    summary text,
    CHECK (ended_at IS NULL OR ended_at >= started_at),
    UNIQUE (company_id, id),
    FOREIGN KEY (company_id, device_id) REFERENCES crm.devices(company_id, id)
);

-- Heartbeat se registra en connectivity.collectors (una fuente de verdad).
CREATE TABLE monitoring.status_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    device_id uuid NOT NULL,
    previous_status text NOT NULL,
    new_status text NOT NULL,
    reason text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (company_id,id),
    FOREIGN KEY (company_id,device_id) REFERENCES crm.devices(company_id,id)
);

CREATE TABLE monitoring.alerts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id uuid NOT NULL REFERENCES core.companies(id),
    incident_id uuid,
    device_id uuid,
    tunnel_id uuid,
    event_type text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('INFO','WARNING','CRITICAL')),
    message text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    acknowledged_by uuid,
    acknowledged_at timestamptz,
    CHECK (device_id IS NOT NULL OR tunnel_id IS NOT NULL),
    UNIQUE (company_id,id),
    FOREIGN KEY (company_id,incident_id) REFERENCES monitoring.incidents(company_id,id),
    FOREIGN KEY (company_id,device_id) REFERENCES crm.devices(company_id,id),
    FOREIGN KEY (company_id,tunnel_id) REFERENCES connectivity.vpn_tunnels(company_id,id),
    FOREIGN KEY (company_id,acknowledged_by) REFERENCES core.memberships(company_id,id)
);

CREATE UNIQUE INDEX users_email_scope_unique ON core.users(account_scope,lower(email));
CREATE UNIQUE INDEX users_username_scope_unique ON core.users(account_scope,lower(username));
CREATE UNIQUE INDEX subscriptions_one_current ON platform.subscriptions(company_id) WHERE status <> 'CANCELLED';
CREATE UNIQUE INDEX devices_one_active_asset ON crm.devices(asset_id) WHERE asset_id IS NOT NULL AND retired_at IS NULL;
CREATE UNIQUE INDEX billing_monthly_once ON billing.charges(service_id, period_start) WHERE charge_type = 'MONTHLY';
CREATE UNIQUE INDEX platform_monthly_once ON platform_billing.charges(subscription_id, period_start) WHERE charge_type = 'MONTHLY';
CREATE UNIQUE INDEX incidents_one_open ON monitoring.incidents(device_id, incident_type) WHERE ended_at IS NULL;
CREATE INDEX icmp_checks_device_time ON monitoring.icmp_checks(company_id, device_id, checked_at DESC);
CREATE INDEX audit_company_time ON audit.events(company_id, occurred_at DESC);

CREATE VIEW billing.charge_balances AS
SELECT c.*, c.amount + COALESCE(a.total,0) - COALESCE(p.total,0) AS balance
FROM billing.charges c
LEFT JOIN (SELECT charge_id, sum(amount) AS total FROM billing.adjustments GROUP BY charge_id) a ON a.charge_id=c.id
LEFT JOIN (SELECT pa.charge_id, sum(pa.amount) AS total FROM billing.payment_allocations pa JOIN billing.payments p ON p.id=pa.payment_id WHERE p.voided_at IS NULL GROUP BY pa.charge_id) p ON p.charge_id=c.id;

CREATE VIEW platform_billing.charge_balances AS
SELECT c.*, c.amount + COALESCE(a.total,0) - COALESCE(p.total,0) AS balance
FROM platform_billing.charges c
LEFT JOIN (SELECT charge_id, sum(amount) AS total FROM platform_billing.adjustments GROUP BY charge_id) a ON a.charge_id=c.id
LEFT JOIN (SELECT pa.charge_id, sum(pa.amount) AS total FROM platform_billing.payment_allocations pa JOIN platform_billing.payments p ON p.id=pa.payment_id WHERE p.voided_at IS NULL GROUP BY pa.charge_id) p ON p.charge_id=c.id;

CREATE VIEW billing.account_status AS
SELECT c.company_id, c.id AS client_id, COALESCE(b.currency, 'BOB') AS currency, COALESCE(sum(greatest(b.balance,0)),0) AS pending_amount,
 COALESCE(sum(greatest(b.balance,0)) FILTER (WHERE b.due_on < (now() AT TIME ZONE co.timezone)::date),0) AS overdue_amount,
 CASE WHEN bool_or(b.balance > 0 AND b.due_on < (now() AT TIME ZONE co.timezone)::date) THEN 'OVERDUE'
      WHEN bool_or(b.balance > 0) THEN 'PENDING' ELSE 'CURRENT' END AS financial_status
FROM crm.clients c JOIN core.companies co ON co.id=c.company_id
LEFT JOIN billing.charge_balances b ON b.company_id=c.company_id AND b.client_id=c.id
GROUP BY c.company_id,c.id,co.timezone,b.currency;

CREATE VIEW platform_billing.account_status AS
SELECT co.id AS company_id, COALESCE(b.currency, 'BOB') AS currency,
 COALESCE(sum(greatest(b.balance,0)),0) AS pending_amount,
 COALESCE(sum(greatest(b.balance,0)) FILTER (WHERE b.due_on < (now() AT TIME ZONE co.timezone)::date),0) AS overdue_amount,
 CASE WHEN bool_or(b.balance > 0 AND b.due_on < (now() AT TIME ZONE co.timezone)::date) THEN 'OVERDUE'
      WHEN bool_or(b.balance > 0) THEN 'PENDING' ELSE 'CURRENT' END AS financial_status
FROM core.companies co LEFT JOIN platform_billing.charge_balances b ON b.company_id=co.id
GROUP BY co.id,co.timezone,b.currency;

-- Stock no serializado: movimientos como fuente de verdad.
CREATE VIEW inventory.stock AS
SELECT x.company_id, x.product_id, x.location_id, sum(x.quantity) AS quantity
FROM (
 SELECT company_id,product_id,to_location_id AS location_id,quantity FROM inventory.stock_movements WHERE to_location_id IS NOT NULL
 UNION ALL
 SELECT company_id,product_id,from_location_id,-quantity FROM inventory.stock_movements WHERE from_location_id IS NOT NULL
) x JOIN inventory.products p ON p.id=x.product_id AND p.company_id=x.company_id
WHERE p.tracking_type='QUANTITY' GROUP BY x.company_id,x.product_id,x.location_id;
