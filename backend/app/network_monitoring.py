import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, IPvAnyAddress, model_validator

from app.auth.schemas import Input
from app.auth.store import execute, row, rows
from app.connectivity.config import stale_seconds


class Measurement(Input):
    device_id: UUID
    measurement_id: UUID
    revision: int = Field(ge=1)
    epoch: int = Field(ge=1)
    checked_at: AwareDatetime
    ip: IPvAnyAddress
    result: Literal["REACHABLE", "NO_REPLY", "ERROR", "SKIPPED_VPN"]
    sent: int | None = Field(None, ge=1, le=10)
    received: int | None = Field(None, ge=0, le=10)
    latency_min: float | None = Field(None, ge=0, le=120000, allow_inf_nan=False)
    latency_avg: float | None = Field(None, ge=0, le=120000, allow_inf_nan=False)
    latency_max: float | None = Field(None, ge=0, le=120000, allow_inf_nan=False)
    diagnostic: Literal["PING_ERROR", "VPN_CHANGED", "RESULT_UNAVAILABLE"] | None = None

    @model_validator(mode="after")
    def coherent(self):
        samples = (self.latency_min, self.latency_avg, self.latency_max)
        if self.ip.version != 4:
            raise ValueError("Solo se aceptan muestras IPv4.")
        if self.result in {"ERROR", "SKIPPED_VPN"}:
            if any(value is not None for value in (self.sent, self.received, *samples)):
                raise ValueError("Muestra sin mediciones incoherente.")
        elif not self.sent or self.received is None or self.received > self.sent:
            raise ValueError("Conteos ICMP incoherentes.")
        elif self.result == "REACHABLE":
            if not self.received or None in samples or not samples[0] <= samples[1] <= samples[2]:
                raise ValueError("Latencias ICMP incoherentes.")
        elif self.received or any(value is not None for value in samples):
            raise ValueError("Una muestra sin respuesta no lleva latencias.")
        return self


class Results(Input):
    items: list[Measurement] = Field(min_length=1, max_length=100)


def eligible(db, target):
    if not target["tunnel_id"] or not target["peer_public_key"]:
        return []
    return rows(db, """
        WITH plan AS (
          SELECT v.max_devices,v.min_poll_interval_seconds
          FROM platform.subscriptions p JOIN platform.plan_versions v ON v.id=p.plan_version_id
          JOIN core.companies c ON c.id=p.company_id
          WHERE p.company_id=:company AND c.status='ACTIVE' AND p.status IN ('ACTIVE','TRIAL','GRACE')
            AND p.starts_at<=now() AND (p.ends_at IS NULL OR p.ends_at>now())
            AND EXISTS (SELECT 1 FROM platform.plan_features pf JOIN platform.features f ON f.id=pf.feature_id
                        WHERE pf.plan_version_id=v.id AND f.code='ICMP' AND f.implemented)
        ), ranked AS (
          SELECT d.id,d.client_id,d.site_id,d.device_category,host(d.effective_ip) AS ip,d.config_revision AS revision,
                 p.interval_seconds,p.timeout_ms,p.packet_count,p.latency_warning_ms,p.loss_warning_pct,
                 p.loss_failure_pct,p.failure_threshold,p.recovery_threshold,d.created_at,
                 row_number() OVER(PARTITION BY d.effective_ip ORDER BY d.created_at,d.id) AS address_rank
          FROM crm.device_targets d JOIN monitoring.icmp_profiles p ON (p.company_id,p.device_id)=(d.company_id,d.id)
          JOIN crm.sites s ON (s.company_id,s.id)=(d.company_id,d.site_id)
          LEFT JOIN crm.clients c ON (c.company_id,c.id)=(s.company_id,s.client_id)
          CROSS JOIN plan
          WHERE d.company_id=:company AND d.monitoring_requested AND p.enabled
            AND d.administrative_active AND d.retired_at IS NULL AND d.archived_at IS NULL
            AND d.assignment_state='INSTALLED' AND s.active AND s.archived_at IS NULL
            AND (c.id IS NULL OR (c.status='ACTIVE' AND c.archived_at IS NULL))
            AND d.effective_ip IS NOT NULL AND p.interval_seconds>=coalesce(plan.min_poll_interval_seconds,5)
            AND EXISTS (SELECT 1 FROM connectivity.vpn_routes r WHERE r.company_id=:company AND r.tunnel_id=:tunnel
                        AND r.enabled AND d.effective_ip <<= r.destination_network)
        )
        SELECT * FROM ranked WHERE address_rank=1 ORDER BY created_at,id
        LIMIT (SELECT max_devices FROM plan)
    """, company=target["company_id"], tunnel=target["tunnel_id"])


def transport(db, target):
    if not target["tunnel_id"]:
        return {"epoch": 1, "healthy": False, "last_success_at": None}
    return row(db, """
        SELECT monitor_epoch AS epoch,last_success_at, (
            connection_status='CONNECTED' AND consecutive_failures=0 AND last_probe_at>now()-make_interval(secs=>:stale)
            AND last_success_at>now()-make_interval(secs=>:stale) AND enabled
            AND :fresh AND :running AND :applied
        ) IS TRUE AS healthy FROM connectivity.vpn_tunnels WHERE id=:id
    """, stale=stale_seconds(), fresh=target["heartbeat_fresh"], running=target["container_state"] == "RUNNING",
        applied=target["applied_revision"] == target["config_revision"], id=target["tunnel_id"])


def targets(db, target):
    data = eligible(db, target)
    assigned = [item["id"] for item in data]
    execute(db, """
        UPDATE crm.devices SET monitoring_enabled=(id=ANY(CAST(:ids AS uuid[]))),
            collector_id=CASE WHEN id=ANY(CAST(:ids AS uuid[])) THEN :collector ELSE collector_id END
        WHERE company_id=:company AND (
          (id=ANY(CAST(:ids AS uuid[])) AND (NOT monitoring_enabled OR collector_id IS DISTINCT FROM :collector))
          OR (monitoring_enabled AND collector_id=:collector AND NOT(id=ANY(CAST(:ids AS uuid[]))))
        )
    """, ids=assigned, collector=target["id"], company=target["company_id"])
    result = transport(db, target)
    fields = ("id", "ip", "revision", "interval_seconds", "timeout_ms", "packet_count", "latency_warning_ms",
              "loss_warning_pct", "loss_failure_pct", "failure_threshold", "recovery_threshold")
    return {"epoch": result["epoch"], "healthy": result["healthy"],
            "items": [{key: entry[key] for key in fields} for entry in data]}


def ingest(db, target, batch):
    allowed = {item["id"]: item for item in eligible(db, target)}
    link = transport(db, target)
    now = datetime.now(UTC)
    accepted = 0
    for sample in sorted(batch.items, key=lambda item: (item.checked_at, item.measurement_id)):
        expected = allowed.get(sample.device_id)
        if (not expected or expected["revision"] != sample.revision or expected["ip"] != str(sample.ip)
                or not now - timedelta(hours=24) <= sample.checked_at <= now + timedelta(seconds=15)
                or sample.sent is not None and sample.sent != expected["packet_count"]):
            continue
        healthy = link["healthy"] and sample.epoch == link["epoch"]
        valid = healthy and sample.result in {"REACHABLE", "NO_REPLY"}
        loss = ((Decimal(sample.sent - sample.received) * 100 / sample.sent).quantize(Decimal(".01"))
                if sample.sent is not None else None)
        good = bool(sample.received and loss < expected["loss_failure_pct"]) if valid else None
        saved = execute(db, """
            INSERT INTO monitoring.icmp_checks(company_id,device_id,collector_id,measurement_id,device_config_revision,
              checked_at,target_ip,result,packets_sent,packets_received,latency_ms,latency_min_ms,latency_max_ms,
              packet_loss_pct,error_detail,transport_healthy,acceptable)
            VALUES (:company,:device,:collector,:measurement,:revision,:at,CAST(:ip AS inet),:result,:sent,:received,
                :avg,:min,:max,:loss,:diagnostic,:healthy,:good)
            ON CONFLICT (collector_id,measurement_id) DO NOTHING RETURNING id
        """, company=target["company_id"], device=sample.device_id, collector=target["id"], measurement=sample.measurement_id,
            revision=sample.revision, at=sample.checked_at, ip=expected["ip"], result=sample.result, sent=sample.sent,
            received=sample.received, avg=sample.latency_avg, min=sample.latency_min, max=sample.latency_max,
            loss=loss, diagnostic=sample.diagnostic, healthy=healthy, good=good).scalar_one_or_none()
        if saved:
            accepted += 1
            if healthy:
                consolidate(db, target["company_id"], expected, sample, link, loss, good)
    return {"accepted": accepted, "ignored": len(batch.items)-accepted}


def consolidate(db, company, expected, sample, link, loss, good):
    epoch = link["epoch"]
    previous = row(db, """
        SELECT * FROM monitoring.device_status WHERE company_id=:company AND device_id=:device FOR UPDATE
    """, company=company, device=sample.device_id)
    if previous and previous["last_check_at"] and previous["last_check_at"] >= sample.checked_at:
        return
    same_revision = previous and previous["device_config_revision"] == sample.revision
    state = previous["status"] if same_revision else "UNKNOWN"
    same_context = same_revision and previous["transport_epoch"] == epoch and previous["last_valid_check_at"] and (
        sample.checked_at - previous["last_valid_check_at"] <= timedelta(seconds=max(30, 3*expected["interval_seconds"]))
    )
    fail = (previous["consecutive_failures"] if same_context else 0) + 1 if good is False else 0
    success = (previous["consecutive_successes"] if same_context else 0) + 1 if good is True else 0
    failure_since = (previous["failure_since"] if same_context and previous["consecutive_failures"] else sample.checked_at) if fail else None
    next_state = state
    if good is False:
        if fail >= expected["failure_threshold"] and link["last_success_at"] >= failure_since:
            next_state = "DOWN"
        elif state != "DOWN":
            next_state = "DEGRADED"
    elif good is True and (state != "DOWN" or success >= expected["recovery_threshold"]):
        next_state = "DEGRADED" if loss > expected["loss_warning_pct"] or sample.latency_avg > expected["latency_warning_ms"] else "UP"
    execute(db, """
        INSERT INTO monitoring.device_status(company_id,device_id,status,last_check_at,last_success_at,last_latency_ms,
          last_packet_loss_pct,last_valid_check_at,last_measurement_id,device_config_revision,consecutive_failures,
          consecutive_successes,changed_at,failure_since,transport_epoch)
        VALUES (:company,:device,:state,:at,:success_at,:latency,:loss,:valid,:measurement,:revision,:fail,:success,:changed,:since,:epoch)
        ON CONFLICT (device_id) DO UPDATE SET status=EXCLUDED.status,last_check_at=EXCLUDED.last_check_at,
          last_success_at=EXCLUDED.last_success_at,last_latency_ms=EXCLUDED.last_latency_ms,
          last_packet_loss_pct=EXCLUDED.last_packet_loss_pct,last_valid_check_at=EXCLUDED.last_valid_check_at,
          last_measurement_id=EXCLUDED.last_measurement_id,device_config_revision=EXCLUDED.device_config_revision,
          consecutive_failures=EXCLUDED.consecutive_failures,consecutive_successes=EXCLUDED.consecutive_successes,
          changed_at=EXCLUDED.changed_at,failure_since=EXCLUDED.failure_since,transport_epoch=EXCLUDED.transport_epoch
    """, company=company, device=sample.device_id, state=next_state, at=sample.checked_at,
        success_at=sample.checked_at if good else previous["last_success_at"] if same_revision else None,
        latency=sample.latency_avg, loss=loss,
        valid=sample.checked_at if good is not None else previous["last_valid_check_at"] if same_context else None,
        measurement=sample.measurement_id, revision=sample.revision, fail=fail, success=success, since=failure_since, epoch=epoch,
        changed=previous["changed_at"] if same_revision and state == next_state else sample.checked_at)
    if next_state != state:
        execute(db, """
            INSERT INTO monitoring.status_events(company_id,device_id,previous_status,new_status,reason,occurred_at)
            VALUES (:company,:device,:before,:after,'Política de comprobaciones ICMP',:at)
        """, company=company, device=sample.device_id, before=state, after=next_state, at=sample.checked_at)
    if next_state == "DOWN" and state != "DOWN":
        execute(db, """
            INSERT INTO monitoring.incidents(company_id,device_id,started_at,detected_at,summary,client_id,site_id,device_category)
            VALUES (:company,:device,:since,:at,'Fallo ICMP confirmado',:client,:site,:category)
            ON CONFLICT (device_id,incident_type) WHERE ended_at IS NULL DO NOTHING
        """, company=company, device=sample.device_id, since=failure_since, at=sample.checked_at,
            client=expected["client_id"], site=expected["site_id"], category=expected["device_category"])
    if good and success >= expected["recovery_threshold"] and next_state in {"UP", "DEGRADED"}:
        execute(db, """
            UPDATE monitoring.incidents SET ended_at=greatest(started_at,:at),end_reason='RECOVERED'
            WHERE company_id=:company AND device_id=:device AND incident_type='ICMP_UNREACHABLE' AND ended_at IS NULL
        """, company=company, device=sample.device_id, at=sample.checked_at)


def sync_transport(db, target, kind, failed, reason):
    if failed:
        execute(db, """
            INSERT INTO monitoring.transport_incidents(company_id,collector_id,kind,reason)
            VALUES (:company,:collector,:kind,:reason)
            ON CONFLICT (collector_id,kind) WHERE ended_at IS NULL DO NOTHING
        """, company=target["company_id"], collector=target["id"], kind=kind, reason=reason)
    else:
        execute(db, """
            UPDATE monitoring.transport_incidents SET ended_at=now()
            WHERE company_id=:company AND collector_id=:collector AND kind=:kind AND ended_at IS NULL
        """, company=target["company_id"], collector=target["id"], kind=kind)


def sweep(db, *, retain=False):
    records = rows(db, """
        SELECT id,company_id,enabled,retired_at,last_heartbeat_at,container_state,
          last_heartbeat_at<now()-make_interval(secs=>:stale) AS late
        FROM connectivity.collectors c WHERE last_heartbeat_at IS NOT NULL AND
          ((retired_at IS NULL AND enabled) OR EXISTS (SELECT 1 FROM monitoring.transport_incidents i
                WHERE i.collector_id=c.id AND i.ended_at IS NULL))
    """, stale=stale_seconds())
    for target in records:
        live = target["enabled"] and not target["retired_at"]
        sync_transport(db, target, "COLLECTOR", bool(live and target["late"]), "Heartbeat del collector vencido")
        if not live:
            sync_transport(db, target, "VPN", False, "")
    if retain:
        days = min(3650, max(1, int(os.getenv("SKNET_ICMP_RETENTION_DAYS", "30"))))
        execute(db, """
            DELETE FROM monitoring.icmp_checks WHERE id IN (
                SELECT x.id FROM monitoring.icmp_checks x
                LEFT JOIN platform.subscriptions s ON s.company_id=x.company_id AND s.status<>'CANCELLED'
                LEFT JOIN platform.plan_versions v ON v.id=s.plan_version_id
                WHERE x.received_at<now()-make_interval(days=>least(:days,(
                    SELECT min(version.retention_days) FROM platform.subscriptions sub
                    JOIN platform.plan_versions version ON version.id=sub.plan_version_id WHERE sub.status<>'CANCELLED'
                )))
                AND x.received_at<now()-make_interval(days=>coalesce(v.retention_days,:days))
                ORDER BY x.received_at LIMIT 5000
            )
        """, days=days)
