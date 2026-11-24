# SKNet — diagramas por schema

Modelo consolidado. Relaciones de referencia simplificadas; cardinalidades opcionales y restricciones únicas/compuestas se consultan en schema.sql. Entidades de otros schemas se muestran solo como referencias.

## audit

```mermaid
erDiagram
    CORE_USERS ||--o{ AUDIT_EVENTS : "actor_user_id"
    CORE_COMPANIES ||--o{ AUDIT_EVENTS : "company_id"
    AUDIT_EVENTS {
        uuid id PK
        uuid actor_user_id FK
        uuid company_id FK
        text action
        text entity_type
        uuid entity_id
        jsonb before_data
        jsonb after_data
        text reason
        timestamptz occurred_at
    }
    CORE_COMPANIES {
        uuid id PK
    }
    CORE_USERS {
        uuid id PK
    }
```

## billing

```mermaid
erDiagram
    CORE_COMPANIES ||--o{ BILLING_BILLING_PROFILES : "company_id"
    CRM_CLIENTS ||--o{ BILLING_BILLING_PROFILES : "company_id,client_id"
    CORE_COMPANIES ||--o{ BILLING_CHARGES : "company_id"
    CRM_SERVICES ||--o{ BILLING_CHARGES : "company_id,client_id,service_id"
    CRM_SERVICES ||--o{ BILLING_CHARGES : "company_id,service_id"
    CRM_CLIENTS ||--o{ BILLING_CHARGES : "company_id,client_id"
    CORE_COMPANIES ||--o{ BILLING_PAYMENTS : "company_id"
    CORE_MEMBERSHIPS ||--o{ BILLING_PAYMENTS : "company_id,received_by"
    CRM_CLIENTS ||--o{ BILLING_PAYMENTS : "company_id,client_id"
    CORE_COMPANIES ||--o{ BILLING_PAYMENT_ALLOCATIONS : "company_id"
    BILLING_PAYMENTS ||--o{ BILLING_PAYMENT_ALLOCATIONS : "company_id,client_id,currency,payment_id"
    BILLING_CHARGES ||--o{ BILLING_PAYMENT_ALLOCATIONS : "company_id,client_id,currency,charge_id"
    BILLING_PAYMENTS ||--o{ BILLING_PAYMENT_ALLOCATIONS : "company_id,payment_id"
    BILLING_CHARGES ||--o{ BILLING_PAYMENT_ALLOCATIONS : "company_id,charge_id"
    CORE_COMPANIES ||--o{ BILLING_RECEIPTS : "company_id"
    BILLING_PAYMENTS ||--o{ BILLING_RECEIPTS : "company_id,payment_id"
    CORE_COMPANIES ||--o{ BILLING_ADJUSTMENTS : "company_id"
    BILLING_CHARGES ||--o{ BILLING_ADJUSTMENTS : "company_id,charge_id"
    CORE_MEMBERSHIPS ||--o{ BILLING_ADJUSTMENTS : "company_id,created_by"
    BILLING_ADJUSTMENTS {
        uuid id PK
        uuid company_id FK
        uuid charge_id FK
        numeric amount
        text reason
        uuid created_by FK
        timestamptz created_at
    }
    BILLING_BILLING_PROFILES {
        uuid id PK
        uuid company_id FK
        uuid client_id FK
        smallint billing_day
        integer payment_term_days
        char currency
        timestamptz created_at
    }
    BILLING_CHARGES {
        uuid id PK
        uuid company_id FK
        uuid client_id FK
        uuid service_id FK
        text description
        text charge_type
        date period_start
        date period_end
        date generated_on
        date due_on
        numeric amount
        char currency
        timestamptz created_at
    }
    BILLING_PAYMENT_ALLOCATIONS {
        uuid id PK
        uuid company_id FK
        uuid client_id FK
        uuid payment_id FK
        uuid charge_id FK
        char currency FK
        numeric amount
        timestamptz created_at
    }
    BILLING_PAYMENTS {
        uuid id PK
        uuid company_id FK
        uuid client_id FK
        numeric amount
        char currency
        text method
        text reference
        uuid received_by FK
        timestamptz paid_at
        timestamptz voided_at
        text void_reason
    }
    BILLING_RECEIPTS {
        uuid id PK
        uuid company_id FK
        uuid payment_id FK
        text receipt_number
        timestamptz issued_at
        timestamptz voided_at
    }
    CORE_COMPANIES {
        uuid id PK
    }
    CORE_MEMBERSHIPS {
        uuid id PK
    }
    CRM_CLIENTS {
        uuid id PK
    }
    CRM_SERVICES {
        uuid id PK
    }
```

## connectivity

```mermaid
erDiagram
    CORE_COMPANIES ||--o{ CONNECTIVITY_COLLECTORS : "company_id"
    CORE_COMPANIES ||--o{ CONNECTIVITY_RESOURCE_ALLOCATIONS : "company_id"
    CONNECTIVITY_NETWORK_POOLS ||--o{ CONNECTIVITY_RESOURCE_ALLOCATIONS : "pool_id"
    CONNECTIVITY_COLLECTORS ||--o{ CONNECTIVITY_RESOURCE_ALLOCATIONS : "company_id,collector_id"
    CORE_COMPANIES ||--o{ CONNECTIVITY_VPN_TUNNELS : "company_id"
    CONNECTIVITY_RESOURCE_ALLOCATIONS ||--o{ CONNECTIVITY_VPN_TUNNELS : "company_id,collector_id,allocation_id"
    CORE_COMPANIES ||--o{ CONNECTIVITY_VPN_ROUTES : "company_id"
    CONNECTIVITY_VPN_TUNNELS ||--o{ CONNECTIVITY_VPN_ROUTES : "company_id,tunnel_id"
    CORE_COMPANIES ||--o{ CONNECTIVITY_COLLECTOR_CREDENTIALS : "company_id"
    CONNECTIVITY_COLLECTORS ||--o{ CONNECTIVITY_COLLECTOR_CREDENTIALS : "company_id,collector_id"
    CORE_COMPANIES ||--o{ CONNECTIVITY_PROVISIONING_JOBS : "company_id"
    CORE_USERS ||--o{ CONNECTIVITY_PROVISIONING_JOBS : "requested_by_user_id"
    CONNECTIVITY_COLLECTORS ||--o{ CONNECTIVITY_PROVISIONING_JOBS : "company_id,collector_id"
    CORE_COMPANIES ||--o{ CONNECTIVITY_VPN_EVENTS : "company_id"
    CONNECTIVITY_VPN_TUNNELS ||--o{ CONNECTIVITY_VPN_EVENTS : "company_id,tunnel_id"
    CONNECTIVITY_COLLECTOR_CREDENTIALS {
        uuid id PK
        uuid company_id FK
        uuid collector_id FK
        text token_hash
        timestamptz created_at
        timestamptz expires_at
        timestamptz revoked_at
    }
    CONNECTIVITY_COLLECTORS {
        uuid id PK
        uuid company_id FK
        text name
        text docker_container_id
        text provisioning_status
        boolean enabled
        timestamptz last_heartbeat_at
        text last_error
        bigint config_revision
        timestamptz created_at
        timestamptz retired_at
    }
    CONNECTIVITY_NETWORK_POOLS {
        uuid id PK
        text name
        cidr docker_pool
        cidr wireguard_pool
        integer port_start
        integer port_end
        text endpoint_host
        boolean enabled
    }
    CONNECTIVITY_PROVISIONING_JOBS {
        uuid id PK
        uuid company_id FK
        uuid collector_id FK
        uuid requested_by_user_id FK
        text operation
        text idempotency_key
        text status
        integer attempts
        text last_error
        timestamptz created_at
        timestamptz started_at
        timestamptz finished_at
    }
    CONNECTIVITY_RESOURCE_ALLOCATIONS {
        uuid id PK
        uuid company_id FK
        uuid collector_id FK
        uuid pool_id FK
        text docker_network_name
        cidr docker_subnet
        cidr wireguard_subnet
        integer external_udp_port
        text edge_rule_tag
        text status
        timestamptz reserved_at
        timestamptz released_at
    }
    CONNECTIVITY_VPN_EVENTS {
        uuid id PK
        uuid company_id FK
        uuid tunnel_id FK
        text event_type
        text detail
        timestamptz occurred_at
    }
    CONNECTIVITY_VPN_ROUTES {
        uuid id PK
        uuid company_id FK
        uuid tunnel_id FK
        cidr destination_network
        boolean enabled
    }
    CONNECTIVITY_VPN_TUNNELS {
        uuid id PK
        uuid company_id FK
        uuid collector_id FK
        uuid allocation_id FK
        text interface_name
        text server_public_key
        text peer_public_key
        text private_key_ref
        text endpoint_host
        integer internal_udp_port
        integer keepalive_seconds
        integer mtu
        boolean enabled
        text connection_status
        timestamptz last_handshake_at
        timestamptz last_probe_at
        timestamptz last_success_at
        integer consecutive_failures
        timestamptz created_at
        timestamptz retired_at
    }
    CORE_COMPANIES {
        uuid id PK
    }
    CORE_USERS {
        uuid id PK
    }
```

## core

```mermaid
erDiagram
    CORE_COMPANIES ||--o{ CORE_MEMBERSHIPS : "company_id"
    CORE_USERS ||--o{ CORE_MEMBERSHIPS : "user_id,account_scope"
    CORE_USERS ||--o{ CORE_MEMBERSHIPS : "user_id"
    CORE_COMPANIES ||--o{ CORE_ROLES : "company_id"
    CORE_COMPANIES ||--o{ CORE_MEMBERSHIP_ROLES : "company_id"
    CORE_MEMBERSHIPS ||--o{ CORE_MEMBERSHIP_ROLES : "company_id,membership_id"
    CORE_ROLES ||--o{ CORE_MEMBERSHIP_ROLES : "company_id,role_id"
    CORE_COMPANIES ||--o{ CORE_ROLE_PERMISSIONS : "company_id"
    CORE_ROLES ||--o{ CORE_ROLE_PERMISSIONS : "company_id,role_id"
    CORE_PERMISSIONS ||--o{ CORE_ROLE_PERMISSIONS : "permission_id"
    CORE_USERS ||--o{ CORE_PASSWORD_RESET_TOKENS : "user_id"
    CORE_USERS ||--o{ CORE_SESSIONS : "user_id"
    CORE_USERS ||--o{ CORE_SESSIONS : "user_id,account_scope"
    CORE_COMPANIES {
        uuid id PK
        text name
        text tax_id
        text email
        text phone
        text timezone
        text status
        timestamptz created_at
    }
    CORE_MEMBERSHIP_ROLES {
        uuid id PK
        uuid company_id FK
        uuid membership_id FK
        uuid role_id FK
    }
    CORE_MEMBERSHIPS {
        uuid id PK
        uuid company_id FK
        uuid user_id FK
        text account_scope FK
        boolean active
        timestamptz created_at
    }
    CORE_PASSWORD_RESET_TOKENS {
        uuid id PK
        uuid user_id FK
        text token_hash
        timestamptz created_at
        timestamptz expires_at
        timestamptz revoked_at
        timestamptz used_at
    }
    CORE_PERMISSIONS {
        uuid id PK
        text code
        text description
    }
    CORE_ROLE_PERMISSIONS {
        uuid id PK
        uuid company_id FK
        uuid role_id FK
        uuid permission_id FK
    }
    CORE_ROLES {
        uuid id PK
        uuid company_id FK
        text name
        text description
    }
    CORE_SESSIONS {
        uuid id PK
        uuid user_id FK
        text account_scope FK
        text token_hash
        timestamptz created_at
        timestamptz expires_at
        timestamptz last_seen_at
        timestamptz revoked_at
    }
    CORE_USERS {
        uuid id PK
        text name
        text email
        text username
        text account_scope
        timestamptz email_verified_at
        boolean must_change_password
        timestamptz last_login_at
        timestamptz updated_at
        text password_hash
        boolean active
        timestamptz created_at
    }
```

## crm

```mermaid
erDiagram
    CORE_COMPANIES ||--o{ CRM_CLIENTS : "company_id"
    CORE_COMPANIES ||--o{ CRM_CLIENT_CONTACTS : "company_id"
    CRM_CLIENTS ||--o{ CRM_CLIENT_CONTACTS : "company_id,client_id"
    CORE_COMPANIES ||--o{ CRM_SITES : "company_id"
    CRM_CLIENTS ||--o{ CRM_SITES : "company_id,client_id"
    CORE_COMPANIES ||--o{ CRM_CLIENT_ADDRESSES : "company_id"
    CRM_CLIENTS ||--o{ CRM_CLIENT_ADDRESSES : "company_id,client_id"
    CORE_COMPANIES ||--o{ CRM_SERVICE_PLANS : "company_id"
    CORE_COMPANIES ||--o{ CRM_SERVICES : "company_id"
    CRM_SITES ||--o{ CRM_SERVICES : "company_id,client_id,site_id"
    CRM_CLIENTS ||--o{ CRM_SERVICES : "company_id,client_id"
    CRM_SITES ||--o{ CRM_SERVICES : "company_id,site_id"
    CRM_SERVICE_PLANS ||--o{ CRM_SERVICES : "company_id,plan_id"
    CORE_COMPANIES ||--o{ CRM_SERVICE_STATUS_HISTORY : "company_id"
    CRM_SERVICES ||--o{ CRM_SERVICE_STATUS_HISTORY : "company_id,service_id"
    CORE_MEMBERSHIPS ||--o{ CRM_SERVICE_STATUS_HISTORY : "company_id,changed_by"
    CORE_COMPANIES ||--o{ CRM_DOCUMENTS : "company_id"
    CRM_CLIENTS ||--o{ CRM_DOCUMENTS : "company_id,client_id"
    CORE_MEMBERSHIPS ||--o{ CRM_DOCUMENTS : "company_id,uploaded_by"
    CORE_COMPANIES ||--o{ CRM_CONTRACTS : "company_id"
    CRM_SERVICES ||--o{ CRM_CONTRACTS : "company_id,client_id,service_id"
    CRM_DOCUMENTS ||--o{ CRM_CONTRACTS : "company_id,client_id,document_id"
    CRM_CLIENTS ||--o{ CRM_CONTRACTS : "company_id,client_id"
    CRM_SERVICES ||--o{ CRM_CONTRACTS : "company_id,service_id"
    CRM_DOCUMENTS ||--o{ CRM_CONTRACTS : "company_id,document_id"
    CORE_COMPANIES ||--o{ CRM_CLIENT_NOTES : "company_id"
    CRM_CLIENTS ||--o{ CRM_CLIENT_NOTES : "company_id,client_id"
    CORE_MEMBERSHIPS ||--o{ CRM_CLIENT_NOTES : "company_id,author_id"
    CORE_COMPANIES ||--o{ CRM_TAGS : "company_id"
    CORE_COMPANIES ||--o{ CRM_CLIENT_TAGS : "company_id"
    CRM_CLIENTS ||--o{ CRM_CLIENT_TAGS : "company_id,client_id"
    CRM_TAGS ||--o{ CRM_CLIENT_TAGS : "company_id,tag_id"
    CORE_COMPANIES ||--o{ CRM_TICKETS : "company_id"
    CRM_SERVICES ||--o{ CRM_TICKETS : "company_id,client_id,service_id"
    CRM_CLIENTS ||--o{ CRM_TICKETS : "company_id,client_id"
    CRM_SERVICES ||--o{ CRM_TICKETS : "company_id,service_id"
    CORE_MEMBERSHIPS ||--o{ CRM_TICKETS : "company_id,created_by"
    CORE_MEMBERSHIPS ||--o{ CRM_TICKETS : "company_id,assigned_to"
    CORE_COMPANIES ||--o{ CRM_TICKET_COMMENTS : "company_id"
    CRM_TICKETS ||--o{ CRM_TICKET_COMMENTS : "company_id,ticket_id"
    CORE_MEMBERSHIPS ||--o{ CRM_TICKET_COMMENTS : "company_id,author_id"
    CORE_COMPANIES ||--o{ CRM_TICKET_STATUS_HISTORY : "company_id"
    CRM_TICKETS ||--o{ CRM_TICKET_STATUS_HISTORY : "company_id,ticket_id"
    CORE_MEMBERSHIPS ||--o{ CRM_TICKET_STATUS_HISTORY : "company_id,changed_by"
    CORE_COMPANIES ||--o{ CRM_WORK_ORDERS : "company_id"
    CRM_TICKETS ||--o{ CRM_WORK_ORDERS : "company_id,ticket_id"
    CORE_COMPANIES ||--o{ CRM_WORK_ORDER_ASSIGNMENTS : "company_id"
    CRM_WORK_ORDERS ||--o{ CRM_WORK_ORDER_ASSIGNMENTS : "company_id,work_order_id"
    CORE_MEMBERSHIPS ||--o{ CRM_WORK_ORDER_ASSIGNMENTS : "company_id,membership_id"
    CORE_COMPANIES ||--o{ CRM_WORK_ORDER_HISTORY : "company_id"
    CRM_WORK_ORDERS ||--o{ CRM_WORK_ORDER_HISTORY : "company_id,work_order_id"
    CORE_MEMBERSHIPS ||--o{ CRM_WORK_ORDER_HISTORY : "company_id,changed_by"
    CORE_COMPANIES ||--o{ CRM_TASKS : "company_id"
    CRM_CLIENTS ||--o{ CRM_TASKS : "company_id,client_id"
    CORE_MEMBERSHIPS ||--o{ CRM_TASKS : "company_id,assigned_to"
    CORE_COMPANIES ||--o{ CRM_ACTIVITIES : "company_id"
    CRM_CLIENTS ||--o{ CRM_ACTIVITIES : "company_id,client_id"
    CORE_MEMBERSHIPS ||--o{ CRM_ACTIVITIES : "company_id,created_by"
    CORE_COMPANIES ||--o{ CRM_DEVICES : "company_id"
    CONNECTIVITY_COLLECTORS ||--o{ CRM_DEVICES : "company_id,collector_id"
    CRM_SERVICES ||--o{ CRM_DEVICES : "company_id,site_id,service_id"
    CRM_SERVICES ||--o{ CRM_DEVICES : "company_id,service_id"
    CRM_SITES ||--o{ CRM_DEVICES : "company_id,site_id"
    INVENTORY_ASSETS ||--o{ CRM_DEVICES : "company_id,asset_id"
    CRM_DEVICES ||--o{ CRM_SERVICES : "company_id,access_router_id"
    CONNECTIVITY_COLLECTORS {
        uuid id PK
    }
    CORE_COMPANIES {
        uuid id PK
    }
    CORE_MEMBERSHIPS {
        uuid id PK
    }
    CRM_ACTIVITIES {
        uuid id PK
        uuid company_id FK
        uuid client_id FK
        uuid created_by FK
        text activity_type
        text subject
        text description
        timestamptz activity_at
    }
    CRM_CLIENT_ADDRESSES {
        uuid id PK
        uuid company_id FK
        uuid client_id FK
        text address
        text city
        text address_type
    }
    CRM_CLIENT_CONTACTS {
        uuid id PK
        uuid company_id FK
        uuid client_id FK
        text name
        text position
        text email
        text phone
        boolean is_primary
    }
    CRM_CLIENT_NOTES {
        uuid id PK
        uuid company_id FK
        uuid client_id FK
        uuid author_id FK
        text body
        timestamptz created_at
    }
    CRM_CLIENT_TAGS {
        uuid id PK
        uuid company_id FK
        uuid client_id FK
        uuid tag_id FK
    }
    CRM_CLIENTS {
        uuid id PK
        uuid company_id FK
        text client_code
        text client_type
        text name
        text document_type
        text document_number
        text email
        text phone
        text status
        timestamptz created_at
    }
    CRM_CONTRACTS {
        uuid id PK
        uuid company_id FK
        uuid client_id FK
        uuid service_id FK
        uuid document_id FK
        text contract_number
        date start_date
        date end_date
        text status
    }
    CRM_DEVICES {
        uuid id PK
        uuid company_id FK
        uuid service_id FK
        uuid site_id FK
        uuid asset_id FK
        text name
        text device_type
        text device_role
        uuid collector_id FK
        bigint config_revision
        text brand
        text model
        text serial_number
        macaddr mac_address
        inet ip_address
        boolean monitoring_enabled
        timestamptz installed_at
        timestamptz retired_at
        timestamptz created_at
    }
    CRM_DOCUMENTS {
        uuid id PK
        uuid company_id FK
        uuid client_id FK
        uuid uploaded_by FK
        text file_name
        text storage_key
        text mime_type
        timestamptz created_at
    }
    CRM_SERVICE_PLANS {
        uuid id PK
        uuid company_id FK
        text name
        text service_type
        numeric monthly_price
        integer download_mbps
        integer upload_mbps
        boolean active
        timestamptz created_at
    }
    CRM_SERVICE_STATUS_HISTORY {
        uuid id PK
        uuid company_id FK
        uuid service_id FK
        uuid changed_by FK
        text previous_status
        text new_status
        text reason
        timestamptz changed_at
    }
    CRM_SERVICES {
        uuid id PK
        uuid company_id FK
        uuid client_id FK
        uuid site_id FK
        uuid plan_id FK
        numeric monthly_price
        text access_method
        text ip_assignment
        text pppoe_username
        inet service_ip
        timestamptz service_ip_observed_at
        macaddr access_mac
        uuid access_router_id FK
        text technical_notes
        text status
        timestamptz activated_at
        timestamptz cancelled_at
        timestamptz created_at
    }
    CRM_SITES {
        uuid id PK
        uuid company_id FK
        uuid client_id FK
        text name
        text site_type
        text address
        text city
        numeric latitude
        numeric longitude
        boolean active
        timestamptz created_at
    }
    CRM_TAGS {
        uuid id PK
        uuid company_id FK
        text name
    }
    CRM_TASKS {
        uuid id PK
        uuid company_id FK
        uuid client_id FK
        uuid assigned_to FK
        text title
        text description
        text status
        timestamptz due_at
        timestamptz created_at
    }
    CRM_TICKET_COMMENTS {
        uuid id PK
        uuid company_id FK
        uuid ticket_id FK
        uuid author_id FK
        text body
        boolean internal
        timestamptz created_at
    }
    CRM_TICKET_STATUS_HISTORY {
        uuid id PK
        uuid company_id FK
        uuid ticket_id FK
        uuid changed_by FK
        text previous_status
        text new_status
        text reason
        timestamptz changed_at
    }
    CRM_TICKETS {
        uuid id PK
        uuid company_id FK
        uuid client_id FK
        uuid service_id FK
        uuid created_by FK
        uuid assigned_to FK
        text ticket_number
        text subject
        text description
        text priority
        text status
        text resolution
        text closure_reason
        timestamptz opened_at
        timestamptz resolved_at
        timestamptz closed_at
    }
    CRM_WORK_ORDER_ASSIGNMENTS {
        uuid id PK
        uuid company_id FK
        uuid work_order_id FK
        uuid membership_id FK
        timestamptz assigned_at
    }
    CRM_WORK_ORDER_HISTORY {
        uuid id PK
        uuid company_id FK
        uuid work_order_id FK
        uuid changed_by FK
        text previous_status
        text new_status
        text reason
        timestamptz changed_at
    }
    CRM_WORK_ORDERS {
        uuid id PK
        uuid company_id FK
        uuid ticket_id FK
        text order_number
        text title
        text description
        text status
        timestamptz scheduled_at
        timestamptz completed_at
        text result
        timestamptz created_at
    }
    INVENTORY_ASSETS {
        uuid id PK
    }
```

## inventory

```mermaid
erDiagram
    CORE_COMPANIES ||--o{ INVENTORY_PRODUCTS : "company_id"
    CORE_COMPANIES ||--o{ INVENTORY_WAREHOUSES : "company_id"
    CRM_SITES ||--o{ INVENTORY_WAREHOUSES : "company_id,site_id"
    CORE_COMPANIES ||--o{ INVENTORY_STORAGE_LOCATIONS : "company_id"
    INVENTORY_WAREHOUSES ||--o{ INVENTORY_STORAGE_LOCATIONS : "company_id,warehouse_id"
    CORE_COMPANIES ||--o{ INVENTORY_STOCK_MOVEMENTS : "company_id"
    INVENTORY_PRODUCTS ||--o{ INVENTORY_STOCK_MOVEMENTS : "company_id,product_id"
    INVENTORY_STORAGE_LOCATIONS ||--o{ INVENTORY_STOCK_MOVEMENTS : "company_id,from_location_id"
    INVENTORY_STORAGE_LOCATIONS ||--o{ INVENTORY_STOCK_MOVEMENTS : "company_id,to_location_id"
    CRM_WORK_ORDERS ||--o{ INVENTORY_STOCK_MOVEMENTS : "company_id,work_order_id"
    CORE_MEMBERSHIPS ||--o{ INVENTORY_STOCK_MOVEMENTS : "company_id,performed_by"
    CORE_COMPANIES ||--o{ INVENTORY_ASSETS : "company_id"
    INVENTORY_PRODUCTS ||--o{ INVENTORY_ASSETS : "company_id,product_id"
    CRM_SITES ||--o{ INVENTORY_ASSETS : "company_id,current_site_id"
    INVENTORY_STORAGE_LOCATIONS ||--o{ INVENTORY_ASSETS : "company_id,current_storage_location_id"
    CORE_COMPANIES ||--o{ INVENTORY_ASSET_MOVEMENTS : "company_id"
    INVENTORY_ASSETS ||--o{ INVENTORY_ASSET_MOVEMENTS : "company_id,asset_id"
    CRM_SITES ||--o{ INVENTORY_ASSET_MOVEMENTS : "company_id,from_site_id"
    CRM_SITES ||--o{ INVENTORY_ASSET_MOVEMENTS : "company_id,to_site_id"
    INVENTORY_STORAGE_LOCATIONS ||--o{ INVENTORY_ASSET_MOVEMENTS : "company_id,from_storage_location_id"
    INVENTORY_STORAGE_LOCATIONS ||--o{ INVENTORY_ASSET_MOVEMENTS : "company_id,to_storage_location_id"
    CRM_WORK_ORDERS ||--o{ INVENTORY_ASSET_MOVEMENTS : "company_id,work_order_id"
    CORE_MEMBERSHIPS ||--o{ INVENTORY_ASSET_MOVEMENTS : "company_id,performed_by"
    CORE_COMPANIES {
        uuid id PK
    }
    CORE_MEMBERSHIPS {
        uuid id PK
    }
    CRM_SITES {
        uuid id PK
    }
    CRM_WORK_ORDERS {
        uuid id PK
    }
    INVENTORY_ASSET_MOVEMENTS {
        uuid id PK
        uuid company_id FK
        uuid asset_id FK
        uuid from_site_id FK
        uuid to_site_id FK
        uuid from_storage_location_id FK
        uuid to_storage_location_id FK
        uuid work_order_id FK
        uuid performed_by FK
        text reason
        timestamptz moved_at
    }
    INVENTORY_ASSETS {
        uuid id PK
        uuid company_id FK
        uuid product_id FK
        uuid current_site_id FK
        uuid current_storage_location_id FK
        text asset_code
        text serial_number
        text ownership
        text status
        date purchase_date
        timestamptz created_at
    }
    INVENTORY_PRODUCTS {
        uuid id PK
        uuid company_id FK
        text sku
        text name
        text brand
        text model
        text tracking_type
        text unit
        boolean active
    }
    INVENTORY_STOCK_MOVEMENTS {
        uuid id PK
        uuid company_id FK
        uuid product_id FK
        uuid from_location_id FK
        uuid to_location_id FK
        uuid work_order_id FK
        uuid performed_by FK
        numeric quantity
        text reason
        timestamptz moved_at
    }
    INVENTORY_STORAGE_LOCATIONS {
        uuid id PK
        uuid company_id FK
        uuid warehouse_id FK
        text code
        text description
    }
    INVENTORY_WAREHOUSES {
        uuid id PK
        uuid company_id FK
        uuid site_id FK
        text name
    }
```

## monitoring

```mermaid
erDiagram
    CORE_COMPANIES ||--o{ MONITORING_ICMP_PROFILES : "company_id"
    CRM_DEVICES ||--o{ MONITORING_ICMP_PROFILES : "company_id,device_id"
    CORE_COMPANIES ||--o{ MONITORING_ICMP_CHECKS : "company_id"
    CONNECTIVITY_COLLECTORS ||--o{ MONITORING_ICMP_CHECKS : "company_id,collector_id"
    CRM_DEVICES ||--o{ MONITORING_ICMP_CHECKS : "company_id,device_id"
    CORE_COMPANIES ||--o{ MONITORING_DEVICE_STATUS : "company_id"
    CRM_DEVICES ||--o{ MONITORING_DEVICE_STATUS : "company_id,device_id"
    CORE_COMPANIES ||--o{ MONITORING_INCIDENTS : "company_id"
    CRM_DEVICES ||--o{ MONITORING_INCIDENTS : "company_id,device_id"
    CORE_COMPANIES ||--o{ MONITORING_STATUS_EVENTS : "company_id"
    CRM_DEVICES ||--o{ MONITORING_STATUS_EVENTS : "company_id,device_id"
    CORE_COMPANIES ||--o{ MONITORING_ALERTS : "company_id"
    MONITORING_INCIDENTS ||--o{ MONITORING_ALERTS : "company_id,incident_id"
    CRM_DEVICES ||--o{ MONITORING_ALERTS : "company_id,device_id"
    CONNECTIVITY_VPN_TUNNELS ||--o{ MONITORING_ALERTS : "company_id,tunnel_id"
    CORE_MEMBERSHIPS ||--o{ MONITORING_ALERTS : "company_id,acknowledged_by"
    CONNECTIVITY_COLLECTORS {
        uuid id PK
    }
    CONNECTIVITY_VPN_TUNNELS {
        uuid id PK
    }
    CORE_COMPANIES {
        uuid id PK
    }
    CORE_MEMBERSHIPS {
        uuid id PK
    }
    CRM_DEVICES {
        uuid id PK
    }
    MONITORING_ALERTS {
        uuid id PK
        uuid company_id FK
        uuid incident_id FK
        uuid device_id FK
        uuid tunnel_id FK
        text event_type
        text severity
        text message
        timestamptz created_at
        uuid acknowledged_by FK
        timestamptz acknowledged_at
    }
    MONITORING_DEVICE_STATUS {
        uuid id PK
        uuid company_id FK
        uuid device_id FK
        text status
        timestamptz last_check_at
        timestamptz last_success_at
        numeric last_latency_ms
        numeric last_packet_loss_pct
        timestamptz last_valid_check_at
        uuid last_measurement_id
        bigint device_config_revision
        integer consecutive_failures
        integer consecutive_successes
        timestamptz changed_at
    }
    MONITORING_ICMP_CHECKS {
        uuid id PK
        uuid company_id FK
        uuid device_id FK
        uuid collector_id FK
        uuid measurement_id
        bigint device_config_revision
        timestamptz checked_at
        timestamptz received_at
        smallint packets_sent
        smallint packets_received
        text result
        numeric latency_ms
        numeric packet_loss_pct
        text error_detail
    }
    MONITORING_ICMP_PROFILES {
        uuid id PK
        uuid company_id FK
        uuid device_id FK
        boolean enabled
        integer interval_seconds
        integer timeout_ms
        smallint packet_count
        numeric latency_warning_ms
        numeric loss_warning_pct
        numeric loss_failure_pct
        smallint failure_threshold
        smallint recovery_threshold
    }
    MONITORING_INCIDENTS {
        uuid id PK
        uuid company_id FK
        uuid device_id FK
        text incident_type
        timestamptz started_at
        timestamptz detected_at
        timestamptz ended_at
        text end_reason
        text summary
    }
    MONITORING_STATUS_EVENTS {
        uuid id PK
        uuid company_id FK
        uuid device_id FK
        text previous_status
        text new_status
        text reason
        timestamptz occurred_at
    }
```

## platform

```mermaid
erDiagram
    CORE_USERS ||--o{ PLATFORM_STAFF : "user_id,account_scope"
    CORE_USERS ||--o{ PLATFORM_STAFF : "user_id"
    PLATFORM_STAFF ||--o{ PLATFORM_STAFF_ROLES : "staff_id"
    PLATFORM_ROLES ||--o{ PLATFORM_STAFF_ROLES : "role_id"
    PLATFORM_ROLES ||--o{ PLATFORM_ROLE_PERMISSIONS : "role_id"
    PLATFORM_PERMISSIONS ||--o{ PLATFORM_ROLE_PERMISSIONS : "permission_id"
    PLATFORM_PLANS ||--o{ PLATFORM_PLAN_VERSIONS : "plan_id"
    PLATFORM_PLAN_VERSIONS ||--o{ PLATFORM_PLAN_FEATURES : "plan_version_id"
    PLATFORM_FEATURES ||--o{ PLATFORM_PLAN_FEATURES : "feature_id"
    PLATFORM_PLAN_VERSIONS ||--o{ PLATFORM_SETTINGS : "default_plan_version_id"
    CORE_COMPANIES ||--o{ PLATFORM_SUBSCRIPTIONS : "company_id"
    PLATFORM_PLAN_VERSIONS ||--o{ PLATFORM_SUBSCRIPTIONS : "plan_version_id"
    CORE_COMPANIES ||--o{ PLATFORM_SUBSCRIPTION_HISTORY : "company_id"
    PLATFORM_SUBSCRIPTIONS ||--o{ PLATFORM_SUBSCRIPTION_HISTORY : "company_id,subscription_id"
    CORE_USERS ||--o{ PLATFORM_SUBSCRIPTION_HISTORY : "changed_by"
    PLATFORM_PLAN_VERSIONS ||--o{ PLATFORM_SUBSCRIPTION_HISTORY : "previous_plan_version_id"
    PLATFORM_PLAN_VERSIONS ||--o{ PLATFORM_SUBSCRIPTION_HISTORY : "new_plan_version_id"
    CORE_COMPANIES ||--o{ PLATFORM_SUPPORT_TICKETS : "company_id"
    CORE_MEMBERSHIPS ||--o{ PLATFORM_SUPPORT_TICKETS : "company_id,requested_by"
    PLATFORM_STAFF ||--o{ PLATFORM_SUPPORT_TICKETS : "assigned_staff_id"
    CORE_COMPANIES ||--o{ PLATFORM_SUPPORT_TICKET_COMMENTS : "company_id"
    PLATFORM_SUPPORT_TICKETS ||--o{ PLATFORM_SUPPORT_TICKET_COMMENTS : "company_id,ticket_id"
    CORE_USERS ||--o{ PLATFORM_SUPPORT_TICKET_COMMENTS : "author_user_id"
    CORE_COMPANIES ||--o{ PLATFORM_SUPPORT_TICKET_HISTORY : "company_id"
    PLATFORM_SUPPORT_TICKETS ||--o{ PLATFORM_SUPPORT_TICKET_HISTORY : "company_id,ticket_id"
    CORE_USERS ||--o{ PLATFORM_SUPPORT_TICKET_HISTORY : "changed_by"
    CORE_COMPANIES ||--o{ PLATFORM_SUPPORT_ACCESS_LOGS : "company_id"
    PLATFORM_STAFF ||--o{ PLATFORM_SUPPORT_ACCESS_LOGS : "staff_id"
    CORE_COMPANIES {
        uuid id PK
    }
    CORE_MEMBERSHIPS {
        uuid id PK
    }
    CORE_USERS {
        uuid id PK
    }
    PLATFORM_FEATURES {
        uuid id PK
        text code
        text name
        boolean implemented
    }
    PLATFORM_PERMISSIONS {
        uuid id PK
        text code
        text description
    }
    PLATFORM_PLAN_FEATURES {
        uuid id PK
        uuid plan_version_id FK
        uuid feature_id FK
    }
    PLATFORM_PLAN_VERSIONS {
        uuid id PK
        uuid plan_id FK
        integer version
        numeric monthly_price
        char currency
        integer trial_days
        integer max_clients
        integer max_devices
        integer max_users
        integer min_poll_interval_seconds
        integer retention_days
        timestamptz effective_at
    }
    PLATFORM_PLANS {
        uuid id PK
        text code
        text name
        boolean active
        timestamptz created_at
    }
    PLATFORM_ROLE_PERMISSIONS {
        uuid id PK
        uuid role_id FK
        uuid permission_id FK
    }
    PLATFORM_ROLES {
        uuid id PK
        text name
        text description
    }
    PLATFORM_SETTINGS {
        boolean singleton PK
        boolean public_signup_enabled
        uuid default_plan_version_id FK
        timestamptz updated_at
    }
    PLATFORM_STAFF {
        uuid id PK
        uuid user_id FK
        text account_scope FK
        boolean active
    }
    PLATFORM_STAFF_ROLES {
        uuid id PK
        uuid staff_id FK
        uuid role_id FK
    }
    PLATFORM_SUBSCRIPTION_HISTORY {
        uuid id PK
        uuid company_id FK
        uuid subscription_id FK
        uuid changed_by FK
        text previous_status
        text new_status
        uuid previous_plan_version_id FK
        uuid new_plan_version_id FK
        text reason
        timestamptz changed_at
    }
    PLATFORM_SUBSCRIPTIONS {
        uuid id PK
        uuid company_id FK
        uuid plan_version_id FK
        text status
        timestamptz starts_at
        timestamptz ends_at
        smallint billing_day
        integer payment_term_days
    }
    PLATFORM_SUPPORT_ACCESS_LOGS {
        uuid id PK
        uuid company_id FK
        uuid staff_id FK
        text reason
        timestamptz started_at
        timestamptz expires_at
        timestamptz ended_at
    }
    PLATFORM_SUPPORT_TICKET_COMMENTS {
        uuid id PK
        uuid company_id FK
        uuid ticket_id FK
        uuid author_user_id FK
        text body
        boolean internal
        timestamptz created_at
    }
    PLATFORM_SUPPORT_TICKET_HISTORY {
        uuid id PK
        uuid company_id FK
        uuid ticket_id FK
        uuid changed_by FK
        text actor_type
        text previous_status
        text new_status
        text reason
        timestamptz changed_at
    }
    PLATFORM_SUPPORT_TICKETS {
        uuid id PK
        uuid company_id FK
        uuid requested_by FK
        text origin
        text fault_key
        uuid assigned_staff_id FK
        text subject
        text description
        text status
        text priority
        text closure_reason
        timestamptz opened_at
        timestamptz closed_at
    }
```

## platform_billing

```mermaid
erDiagram
    CORE_COMPANIES ||--o{ PLATFORM_BILLING_CHARGES : "company_id"
    PLATFORM_SUBSCRIPTIONS ||--o{ PLATFORM_BILLING_CHARGES : "company_id,subscription_id"
    CORE_COMPANIES ||--o{ PLATFORM_BILLING_PAYMENTS : "company_id"
    PLATFORM_STAFF ||--o{ PLATFORM_BILLING_PAYMENTS : "received_by"
    CORE_COMPANIES ||--o{ PLATFORM_BILLING_PAYMENT_ALLOCATIONS : "company_id"
    PLATFORM_BILLING_PAYMENTS ||--o{ PLATFORM_BILLING_PAYMENT_ALLOCATIONS : "company_id,currency,payment_id"
    PLATFORM_BILLING_CHARGES ||--o{ PLATFORM_BILLING_PAYMENT_ALLOCATIONS : "company_id,currency,charge_id"
    PLATFORM_BILLING_PAYMENTS ||--o{ PLATFORM_BILLING_PAYMENT_ALLOCATIONS : "company_id,payment_id"
    PLATFORM_BILLING_CHARGES ||--o{ PLATFORM_BILLING_PAYMENT_ALLOCATIONS : "company_id,charge_id"
    CORE_COMPANIES ||--o{ PLATFORM_BILLING_RECEIPTS : "company_id"
    PLATFORM_BILLING_PAYMENTS ||--o{ PLATFORM_BILLING_RECEIPTS : "company_id,payment_id"
    CORE_COMPANIES ||--o{ PLATFORM_BILLING_ADJUSTMENTS : "company_id"
    PLATFORM_BILLING_CHARGES ||--o{ PLATFORM_BILLING_ADJUSTMENTS : "company_id,charge_id"
    PLATFORM_STAFF ||--o{ PLATFORM_BILLING_ADJUSTMENTS : "created_by"
    CORE_COMPANIES {
        uuid id PK
    }
    PLATFORM_STAFF {
        uuid id PK
    }
    PLATFORM_SUBSCRIPTIONS {
        uuid id PK
    }
    PLATFORM_BILLING_ADJUSTMENTS {
        uuid id PK
        uuid company_id FK
        uuid charge_id FK
        numeric amount
        text reason
        uuid created_by FK
        timestamptz created_at
    }
    PLATFORM_BILLING_CHARGES {
        uuid id PK
        uuid company_id FK
        uuid subscription_id FK
        text description
        text charge_type
        date period_start
        date period_end
        date generated_on
        date due_on
        numeric amount
        char currency
        timestamptz created_at
    }
    PLATFORM_BILLING_PAYMENT_ALLOCATIONS {
        uuid id PK
        uuid company_id FK
        uuid payment_id FK
        uuid charge_id FK
        char currency FK
        numeric amount
        timestamptz created_at
    }
    PLATFORM_BILLING_PAYMENTS {
        uuid id PK
        uuid company_id FK
        numeric amount
        char currency
        text method
        text reference
        uuid received_by FK
        timestamptz paid_at
        timestamptz voided_at
        text void_reason
    }
    PLATFORM_BILLING_RECEIPTS {
        uuid id PK
        uuid company_id FK
        uuid payment_id FK
        text receipt_number
        timestamptz issued_at
        timestamptz voided_at
    }
```
