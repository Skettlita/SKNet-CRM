from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from app.auth.store import ISP, row, rows
from app.connectivity.config import stale_seconds
from app.platform.routes import read


router = APIRouter(prefix=ISP.path + "/monitoring", tags=["Monitoreo"])
Offset = Query(0, ge=0)
Limit = Query(25, ge=1, le=100)

DEVICES = """
  WITH projection AS (
    SELECT d.id,d.device_code,d.name,coalesce(dt.name,d.device_type) AS device_type,inventory_device.type_id,
        d.device_category,d.device_role,d.site_id,d.client_id,
        s.name AS site_name, c.name AS client_name, host(d.effective_ip) AS effective_ip,d.ip_mode,
        ct.name AS collector_name,ct.id AS collector_id,d.monitoring_enabled,d.monitoring_requested,
        current.last_check_at,current.last_success_at,current.last_latency_ms,current.last_packet_loss_pct,
        current.changed_at,current.consecutive_failures,current.status AS last_confirmed_status,
        CASE
          WHEN d.assignment_state<>'INSTALLED' THEN 'NOT_INSTALLED'
          WHEN d.effective_ip IS NULL THEN 'NO_ADDRESS'
          WHEN EXISTS (SELECT 1 FROM crm.device_targets x WHERE x.company_id=d.company_id AND x.id<>d.id
            AND x.monitoring_requested AND x.administrative_active AND x.assignment_state='INSTALLED'
            AND x.archived_at IS NULL AND x.effective_ip=d.effective_ip
            AND (NOT d.monitoring_requested OR (x.created_at,x.id)<(d.created_at,d.id))) THEN 'DUPLICATE'
          WHEN ct.id IS NULL OR ct.container_state<>'RUNNING' OR ct.last_heartbeat_at IS NULL
            OR ct.last_heartbeat_at<=now()-make_interval(secs=>:stale) THEN 'COLLECTOR_UNAVAILABLE'
          WHEN NOT EXISTS (SELECT 1 FROM connectivity.vpn_routes r WHERE r.company_id=d.company_id
            AND r.tunnel_id=t.id AND r.enabled AND d.effective_ip <<= r.destination_network) THEN 'UNAUTHORIZED_NETWORK'
          ELSE NULL END AS eligibility_reason,
        CASE
          WHEN NOT d.administrative_active OR d.retired_at IS NOT NULL THEN 'DISABLED'
          WHEN d.effective_ip IS NULL OR d.assignment_state<>'INSTALLED' THEN 'UNCONFIGURED'
          WHEN NOT d.monitoring_requested THEN 'DISABLED'
          WHEN ct.last_heartbeat_at IS NOT NULL AND ct.last_heartbeat_at<=now()-make_interval(secs=>:stale) THEN 'STALE'
          WHEN ct.container_state IN ('EXITED','MISSING') AND ct.last_heartbeat_at IS NOT NULL THEN 'STALE'
          WHEN ct.enabled AND t.connection_status='DISCONNECTED' THEN 'UNREACHABLE'
          WHEN NOT d.monitoring_enabled OR ct.id IS NULL OR t.last_probe_at IS NULL OR t.connection_status<>'CONNECTED'
            OR t.consecutive_failures>0 THEN 'UNKNOWN'
          WHEN t.last_probe_at<=now()-make_interval(secs=>:stale) THEN 'STALE'
          WHEN current.transport_epoch IS DISTINCT FROM t.monitor_epoch THEN 'UNKNOWN'
          WHEN current.last_valid_check_at IS NULL THEN 'UNKNOWN'
          WHEN current.last_valid_check_at<=now()-make_interval(secs=>greatest(30,3*coalesce(p.interval_seconds,30))) THEN 'STALE'
          ELSE current.status END AS status
    FROM crm.device_targets d
    JOIN crm.devices inventory_device ON (inventory_device.company_id,inventory_device.id)=(d.company_id,d.id)
    JOIN inventory.device_types dt ON (dt.company_id,dt.id)=(d.company_id,inventory_device.type_id)
    LEFT JOIN crm.sites s ON (s.company_id,s.id)=(d.company_id,d.site_id)
    LEFT JOIN crm.clients c ON (c.company_id,c.id)=(d.company_id,d.client_id)
    LEFT JOIN monitoring.icmp_profiles p ON (p.company_id,p.device_id)=(d.company_id,d.id)
    LEFT JOIN monitoring.device_status current ON (current.company_id,current.device_id,current.device_config_revision)=(d.company_id,d.id,d.config_revision)
    LEFT JOIN connectivity.collectors ct ON ct.company_id=d.company_id AND ct.enabled AND ct.retired_at IS NULL
    LEFT JOIN connectivity.vpn_tunnels t ON (t.company_id,t.collector_id)=(ct.company_id,ct.id) AND t.retired_at IS NULL
    WHERE d.company_id=:company AND (d.archived_at IS NULL OR d.id=CAST(:device AS uuid))
  )
"""

INCIDENTS = """
    WITH event_rows AS (
      SELECT i.id,i.device_id,d.name,d.device_code,i.device_category,c.name AS client_name,s.name AS site_name,
        i.started_at,i.ended_at,i.end_reason,i.incident_type AS kind,i.summary,
        extract(epoch FROM coalesce(i.ended_at,now())-i.started_at)::bigint AS duration_seconds
      FROM monitoring.incidents i JOIN crm.devices d ON (d.company_id,d.id)=(i.company_id,i.device_id)
      LEFT JOIN crm.clients c ON (c.company_id,c.id)=(i.company_id,i.client_id)
      LEFT JOIN crm.sites s ON (s.company_id,s.id)=(i.company_id,i.site_id)
      WHERE i.company_id=:company
      UNION ALL
      SELECT i.id,NULL::uuid,case i.kind when 'VPN' then 'Transporte WireGuard' else 'Collector' end,NULL::text,
        NULL::text,NULL::text,NULL::text,i.started_at,i.ended_at,NULL::text,i.kind,i.reason,
        extract(epoch FROM coalesce(i.ended_at,now())-i.started_at)::bigint
      FROM monitoring.transport_incidents i WHERE i.company_id=:company
    )
"""


def totals(db, company):
    counts = rows(db, DEVICES + """
        SELECT status,count(*) AS total,count(*) FILTER(WHERE monitoring_enabled) AS monitored FROM projection GROUP BY status
    """, company=company, stale=stale_seconds(), device=None)
    return {"monitored": sum(item["monitored"] for item in counts), "states": {item["status"]: item["total"] for item in counts}}


@router.get("/devices")
def devices(request: Request, q: str = Query("", max_length=120), status: str | None = None,
            category: str | None = None, role: str | None = None,
            client_id: UUID | None = None, site_id: UUID | None = None, device_type: str | None = None, type_id: UUID | None = None,
            offset: int = Offset, limit: int = Limit):
    with read(request, "monitoring.read", ISP) as (db, actor):
        entries = rows(db, DEVICES + """
            SELECT *,CASE WHEN status=last_confirmed_status THEN extract(epoch FROM now()-changed_at)::bigint END AS duration_seconds
            FROM projection WHERE
              (CAST(:status AS text) IS NULL OR status=:status)
              AND (CAST(:category AS text) IS NULL OR device_category=:category)
              AND (CAST(:role AS text) IS NULL OR device_role=:role)
              AND (CAST(:client AS uuid) IS NULL OR client_id=:client)
              AND (CAST(:site AS uuid) IS NULL OR site_id=:site)
              AND (CAST(:type AS text) IS NULL OR strpos(lower(device_type),lower(:type))>0)
              AND (CAST(:type_id AS uuid) IS NULL OR type_id=:type_id)
              AND strpos(lower(concat_ws(' ',name,device_code,client_name,site_name,effective_ip)),lower(:q))>0
            ORDER BY lower(name),id OFFSET :offset LIMIT :limit
        """, company=actor.company, stale=stale_seconds(), device=None, status=status, category=category,
            role=role, client=client_id, site=site_id, type=device_type, type_id=type_id, q=q.strip(), offset=offset, limit=limit + 1)
        return {"items": entries[:limit], "has_more": len(entries)>limit, **totals(db, actor.company)}


@router.get("/device-types")
def type_choices(request: Request, offset: int = Offset, limit: int = Limit):
    with read(request, "monitoring.read", ISP) as (db, actor):
        options = rows(db, """
            SELECT id,name FROM inventory.device_types WHERE company_id=:company
            ORDER BY lower(name),id LIMIT :limit OFFSET :offset
        """, company=actor.company, limit=limit+1, offset=offset)
        return {"items": options[:limit], "has_more": len(options)>limit}


@router.get("/devices/{device_id}")
def detail(request: Request, device_id: UUID, period: Literal["30m","1h","24h","7d"] = "24h"):
    with read(request, "monitoring.read", ISP) as (db, actor):
        device = row(db, DEVICES + " SELECT * FROM projection WHERE id=:device",
                     company=actor.company, stale=stale_seconds(), device=device_id)
        if device is None:
            raise HTTPException(404, "Dispositivo no encontrado.")
        window, minutes = {"30m": (30, 2), "1h": (60, 5), "24h": (1440, 60), "7d": (10080, 240)}[period]
        arguments = {"company": actor.company, "device": device_id, "window": window, "minutes": minutes}
        samples = rows(db, """
            SELECT checked_at,host(target_ip) AS ip,result,packets_sent,packets_received,latency_ms,latency_min_ms,
              latency_max_ms,packet_loss_pct,transport_healthy,error_detail
            FROM monitoring.icmp_checks WHERE company_id=:company AND device_id=:device
              AND checked_at>=now()-make_interval(mins=>:window) ORDER BY checked_at DESC LIMIT 40
        """, company=actor.company, device=device_id, window=window)
        series = rows(db, """
            WITH axis AS (
              SELECT generate_series(date_bin(make_interval(mins=>:minutes),now()-make_interval(mins=>:window),'2000-01-01'::timestamptz),
                date_bin(make_interval(mins=>:minutes),now(),'2000-01-01'::timestamptz),make_interval(mins=>:minutes)) AS bucket
            ), grouped AS (
              SELECT date_bin(make_interval(mins=>:minutes),checked_at,'2000-01-01'::timestamptz) AS bucket,
                avg(latency_ms) FILTER(WHERE acceptable IS NOT NULL) AS latency,
                avg(packet_loss_pct) FILTER(WHERE acceptable IS NOT NULL) AS loss,
                100.0*count(*) FILTER(WHERE acceptable) / nullif(count(acceptable),0) AS availability,
                count(acceptable) AS valid_samples
              FROM monitoring.icmp_checks WHERE company_id=:company AND device_id=:device
                AND checked_at>=now()-make_interval(mins=>:window)
              GROUP BY 1
            )
            SELECT axis.bucket,grouped.latency,grouped.loss,grouped.availability,coalesce(grouped.valid_samples,0) AS valid_samples
            FROM axis LEFT JOIN grouped USING(bucket) ORDER BY axis.bucket
        """, **arguments)
        incidents = rows(db, INCIDENTS + " SELECT * FROM event_rows WHERE device_id=:id ORDER BY started_at DESC LIMIT 50",
                         company=actor.company, id=device_id)
        return {**device, "samples": samples, "series": series, "incidents": incidents}


@router.get("/incidents")
def incidents(request: Request, q: str = Query("", max_length=120), active: bool | None = None,
              kind: str | None = None, offset: int = Offset, limit: int = Limit):
    with read(request, "monitoring.read", ISP) as (db, actor):
        entries = rows(db, INCIDENTS + """
            SELECT * FROM event_rows WHERE (CAST(:active AS boolean) IS NULL OR (ended_at IS NULL)=:active)
              AND (CAST(:kind AS text) IS NULL OR kind=:kind OR device_category=:kind)
              AND strpos(lower(concat_ws(' ',name,device_code,site_name,client_name,summary)),lower(:q))>0
            ORDER BY started_at DESC,id OFFSET :offset LIMIT :limit
        """, company=actor.company, q=q.strip(), active=active, kind=kind, offset=offset, limit=limit+1)
        return {"items": entries[:limit], "has_more": len(entries)>limit}
