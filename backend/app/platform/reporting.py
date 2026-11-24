from app.auth.store import row, rows


AUDIT_FIELDS = """
    e.id,e.company_id,e.actor_user_id,u.name AS actor,
    COALESCE(u.account_scope,'SYSTEM') AS scope,e.action,e.entity_type,e.entity_id,e.occurred_at
"""
AUDIT_JOIN = "FROM audit.events e LEFT JOIN core.users u ON u.id=e.actor_user_id"


def redact(value):
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        sensitive = ("password", "passwd", "token", "secret", "privatekey", "apikey", "authorization", "credential")
        return {
            key: redact(item) for key, item in value.items()
            if not any(word in key.lower().replace("_", "").replace("-", "") for word in sensitive)
        }
    return value


def audit_events(db, company, scope, action, search, offset, limit):
    entries = rows(db, f"""
        SELECT {AUDIT_FIELDS},e.before_data,e.after_data,e.reason {AUDIT_JOIN}
        WHERE (CAST(:company AS uuid) IS NULL OR e.company_id=:company)
          AND (CAST(:scope AS text) IS NULL OR COALESCE(u.account_scope,'SYSTEM')=:scope)
          AND (CAST(:action AS text) IS NULL OR e.action=:action)
          AND strpos(lower(concat_ws(' ',u.name,e.action,e.entity_type)),lower(:search)) > 0
        ORDER BY e.occurred_at DESC,e.id DESC OFFSET :offset LIMIT :limit
    """, company=company, scope=scope, action=action, search=search, offset=offset, limit=limit)
    return [{**entry, "before_data": redact(entry["before_data"]), "after_data": redact(entry["after_data"])}
            for entry in entries]


def dashboard(db, permissions):
    result = {}
    if "companies.read" in permissions:
        result["companies"] = row(db, """
            SELECT count(*) AS registered, count(*) FILTER (WHERE status='ACTIVE') AS active,
                   count(*) FILTER (WHERE status='INACTIVE') AS suspended FROM core.companies
        """)
    if "subscriptions.read" in permissions:
        distribution = rows(db, """
            SELECT p.code, p.name, count(*) AS companies
            FROM platform.subscriptions s JOIN platform.plan_versions v ON v.id=s.plan_version_id
            JOIN platform.plans p ON p.id=v.plan_id
            WHERE s.status IN ('TRIAL','ACTIVE','GRACE') AND s.starts_at<=now()
              AND (s.ends_at IS NULL OR s.ends_at>now())
            GROUP BY p.id,p.code,p.name ORDER BY companies DESC,p.code
        """)
        result["subscriptions"] = {
            "active": sum(entry["companies"] for entry in distribution),
            "trial": sum(entry["companies"] for entry in distribution if entry["code"] == "TRIAL"),
            "distribution": distribution,
            "revenue_available": False,
        }
    if "users.read" in permissions:
        result["staff_users"] = row(db, "SELECT count(*) AS total FROM platform.staff")["total"]
    if "companies.users.read" in permissions:
        result["isp_users"] = row(db, "SELECT count(*) AS total FROM core.memberships")["total"]
    if "support.read" in permissions:
        result["open_tickets"] = row(db, """
            SELECT count(*) AS total FROM platform.support_tickets WHERE status IN ('OPEN','ASSIGNED','IN_PROGRESS')
        """)["total"]
    if "audit.read" in permissions:
        result["activity"] = rows(db, f"""
            SELECT {AUDIT_FIELDS} {AUDIT_JOIN}
            WHERE u.account_scope='SAAS' OR e.actor_user_id IS NULL
            ORDER BY e.occurred_at DESC,e.id DESC LIMIT 8
        """)
    if "system.read" in permissions:
        from app.connectivity.config import stale_seconds

        result["infrastructure"] = row(db, """
            SELECT (SELECT count(*) FROM connectivity.collectors WHERE retired_at IS NULL) AS collectors,
                   (SELECT max(received_at) FROM monitoring.icmp_checks) AS last_measurement,
                   (SELECT count(*) FROM connectivity.vpn_tunnels t JOIN connectivity.collectors c
                      ON c.id=t.collector_id AND c.company_id=t.company_id
                    WHERE t.retired_at IS NULL AND c.retired_at IS NULL AND t.enabled AND c.enabled AND NOT c.simulated
                      AND t.connection_status='CONNECTED' AND t.last_probe_at>now()-make_interval(secs=>:stale)
                      AND c.last_heartbeat_at>now()-make_interval(secs=>:stale)) AS connected
        """, stale=stale_seconds())
    return result
