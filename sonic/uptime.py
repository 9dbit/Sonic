"""SONIC Internet Uptime v1.5.0.

Device-authenticated, idempotent HTTPS reachability ingestion, owner-only
24-hour report, and honest missing-data accounting. This is NOT ISP-certified
uptime, packet loss, or a speed test.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import BigInteger, Boolean, Index, Integer, String, delete, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from . import auth
from .config import database_ready, setting
from .db import Base, get_db

router = APIRouter(prefix="/api/uptime", tags=["internet-uptime"])
INTERVAL_MS = 30_000
RETENTION_MS = 30 * 86400_000
TARGETS = ("google", "cloudflare")


class UptimeSample(Base):
    __tablename__ = "internet_uptime_samples_v150"
    __table_args__ = (Index("ix_uptime_device_time_v150", "device_id", "observed_at_ms"),)
    device_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    sample_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    observed_at_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    google_ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    cloudflare_ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    google_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cloudflare_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SampleInput(Strict):
    sample_id: str = Field(min_length=36, max_length=36)
    observed_at_ms: int = Field(ge=1)
    google_ok: bool
    cloudflare_ok: bool
    google_ms: int | None = Field(default=None, ge=1, le=10000)
    cloudflare_ms: int | None = Field(default=None, ge=1, le=10000)

    @model_validator(mode="after")
    def check(self):
        try:
            parsed = UUID(self.sample_id)
            if parsed.version != 4 or str(parsed) != self.sample_id:
                raise ValueError("Expected canonical UUID4")
        except (ValueError, AttributeError):
            raise ValueError("Expected a version-4 sample UUID") from None
        for name in TARGETS:
            ok = getattr(self, name + "_ok")
            latency = getattr(self, name + "_ms")
            if (ok and latency is None) or (not ok and latency is not None):
                raise ValueError("Latency must be present only for reachable HTTPS targets")
        return self


class IngestBody(Strict):
    device_id: str = Field(min_length=1, max_length=80)
    samples: list[SampleInput] = Field(min_length=1, max_length=60)


def ensure_db():
    if not database_ready():
        raise HTTPException(503, "Uptime monitoring requires durable database")


def expected_device():
    return setting("SONIC_DEVICE_ID", "TRADEVICEPC")


def utc_ms():
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def iso(t):
    return datetime.fromtimestamp(t / 1000, tz=timezone.utc).isoformat()


@router.post("/ingest")
def ingest(payload: IngestBody, request: Request, db: Session = Depends(get_db)):
    auth.require_device(request)
    ensure_db()
    if payload.device_id != expected_device():
        raise HTTPException(403, "Device not allowed")
    if len({s.sample_id for s in payload.samples}) != len(payload.samples):
        raise HTTPException(422, "Duplicated sample in batch")
    now = utc_ms()
    for s in payload.samples:
        if s.observed_at_ms < now - RETENTION_MS or s.observed_at_ms > now + 300_000:
            raise HTTPException(422, "Uptime sample outside permitted 30-day window or future clock skew")
    ids = [s.sample_id for s in payload.samples]
    existing = set(db.scalars(select(UptimeSample.sample_id).where(
        UptimeSample.device_id == payload.device_id,
        UptimeSample.sample_id.in_(ids))).all())
    for s in payload.samples:
        if s.sample_id in existing:
            row = db.get(UptimeSample, (payload.device_id, s.sample_id))
            if (row.observed_at_ms != s.observed_at_ms or
                row.google_ok != s.google_ok or row.cloudflare_ok != s.cloudflare_ok or
                row.google_ms != s.google_ms or row.cloudflare_ms != s.cloudflare_ms):
                raise HTTPException(409, "Sample ID replay differs from stored record")
            continue
        db.add(UptimeSample(device_id=payload.device_id, sample_id=s.sample_id,
                            observed_at_ms=s.observed_at_ms, google_ok=s.google_ok,
                            cloudflare_ok=s.cloudflare_ok, google_ms=s.google_ms,
                            cloudflare_ms=s.cloudflare_ms))
    db.flush()
    # Keep only 30 days; this is an additive table and cannot touch other SONIC data.
    db.execute(delete(UptimeSample).where(
        UptimeSample.device_id == payload.device_id,
        UptimeSample.observed_at_ms < now - RETENTION_MS))
    db.commit()
    return {"acknowledged": ids, "accepted": len(ids), "new": len(ids)-len(existing),
            "source": "authenticated_windows_https_sampler"}


def report(db: Session, hours: int = 24, *, now_ms: int | None = None):
    if not 1 <= hours <= 168:
        raise ValueError("Report window must be within 1-168 hours")
    end = now_ms if now_ms is not None else utc_ms()
    start = end - hours * 3600_000
    expected = hours * 120
    device = expected_device()
    records = db.scalars(select(UptimeSample).where(
        UptimeSample.device_id == device,
        UptimeSample.observed_at_ms >= start,
        UptimeSample.observed_at_ms <= end).order_by(
        UptimeSample.observed_at_ms)).all()
    # One record per 30-second slot, so retries/jitter cannot inflate coverage.
    slots = {}
    for s in records:
        slot = (s.observed_at_ms - start) // INTERVAL_MS
        if 0 <= slot < expected:
            slots[slot] = s
    up = sum(bool(s.google_ok or s.cloudflare_ok) for s in slots.values())
    down = len(slots) - up
    degraded = sum(bool(s.google_ok) != bool(s.cloudflare_ok) for s in slots.values())
    known = len(slots)
    unknown = max(0, expected - known)
    coverage = round(known * 100 / expected, 2)
    observed = round(up * 100 / known, 2) if known else None
    earliest_slot = min(slots) if slots else None
    # Never declare the full 24h measured if monitoring started too recently
    # or there are significant missing samples (sleep/restart/outage of sampler).
    ready = known > 0 and earliest_slot <= 2 and coverage >= 99.0
    status = "ready" if ready else ("partial" if known else "no_data")
    latency = [v for s in slots.values() for ok,v in
               ((s.google_ok,s.google_ms),(s.cloudflare_ok,s.cloudflare_ms))
               if ok and v is not None]
    mean_ms = round(sum(latency)/len(latency), 1) if latency else None
    probe_success = sum(int(s.google_ok)+int(s.cloudflare_ok) for s in slots.values())
    probe_success_pct = round(probe_success * 100/(known*2), 2) if known else None

    incidents = []
    current = None
    for i in sorted(slots):
        s = slots[i]
        if not s.google_ok and not s.cloudflare_ok:
            if current and i == current["last_index"]+1:
                current["last_index"] = i
                current["samples"] += 1
            else:
                current = {"first_index": i, "last_index": i, "samples": 1}
                incidents.append(current)
        else:
            current = None
    outages = [{
        "started_at_utc": iso(start+x["first_index"]*INTERVAL_MS),
        "ended_at_utc": iso(start+(x["last_index"]+1)*INTERVAL_MS),
        "approx_duration_seconds": x["samples"]*30
    } for x in incidents[-40:]]

    bins = []
    count_bins = 48 if hours >= 24 else min(48, hours*2)
    for b in range(count_bins):
        first = b*expected//count_bins
        last = (b+1)*expected//count_bins
        chosen = [slots[i] for i in range(first,last) if i in slots]
        missing = (last-first)-len(chosen)
        failures = sum(not (s.google_ok or s.cloudflare_ok) for s in chosen)
        partial = sum(s.google_ok != s.cloudflare_ok for s in chosen)
        state = ("unknown" if not chosen or missing > (last-first)//2 else
                 "down" if failures else "degraded" if partial else "up")
        bins.append({"at_utc": iso(start+first*INTERVAL_MS),
                     "state": state, "samples": len(chosen),
                     "missing": missing})
    return {
        "device_id": device, "scope": "TRADEVICEPC_https_reachability",
        "window_hours": hours, "from_utc": iso(start), "to_utc": iso(end),
        "status": status,
        "uptime_pct": observed if ready else None,
        "observed_uptime_pct": observed,
        "coverage_pct": coverage,
        "known_seconds": known * 30,
        "unknown_seconds": unknown * 30,
        "approx_down_seconds": down * 30,
        "degraded_seconds": degraded * 30,
        "samples_expected": expected,
        "samples_recorded": known,
        "up_samples": up,
        "down_samples": down,
        "degraded_samples": degraded,
        "avg_https_latency_ms": mean_ms,
        "https_probe_success_pct": probe_success_pct,
        "outage_count": len(incidents),
        "outages": outages,
        "timeline": bins,
        "targets": list(TARGETS),
        "availability_definition": "At least one of two fixed HTTPS 204 endpoints reachable from TRADEVICEPC.",
        "measurement_note": "Every 30-second sample represents approximately 30 seconds. Missing coverage is unknown, not automatically uptime or downtime. HTTPS probe failures are not ICMP packet loss or ISP-certified downtime.",
        "ready_rule": "Full-window percentage is shown only when at least 99% of slots are measured and coverage begins within 90 seconds of the window start.",
    }


@router.get("/summary")
def uptime_summary(hours: int = Query(default=24, ge=1, le=168),
                   _: dict = Depends(auth.require_owner),
                   db: Session = Depends(get_db)):
    ensure_db()
    return report(db, hours)


def is_uptime_question(message: str) -> bool:
    """Narrow question routing; never mistakes arbitrary PC actions for uptime."""
    import re
    if not isinstance(message, str) or len(message) > 3500:
        return False
    value = message.casefold()
    return bool(
        re.search(r"\b(uptime|availability)\b", value) and
        re.search(r"\b(internet|koneksi|jaringan|network|isp)\b", value)
    )


def uptime_reply(snapshot: dict) -> str:
    """User-language reply grounded entirely in stored samples, not fabricated data."""
    if snapshot["status"] == "no_data":
        return ("Belum ada data monitoring koneksi internet TRADEVICEPC. "
                "Pengukuran baru akan tersedia setelah Companion menyimpan dan "
                "menyinkronkan sampel HTTPS setiap 30 detik.")
    coverage = snapshot["coverage_pct"]
    observed = snapshot["observed_uptime_pct"]
    downtime = snapshot["approx_down_seconds"]
    unknown = snapshot["unknown_seconds"]
    count = snapshot["outage_count"]
    if snapshot["status"] != "ready":
        return (f"Monitoring internet TRADEVICEPC belum mencakup 24 jam lengkap. "
                f"Cakupan data {coverage:.2f} persen. Pada sampel yang tersedia, "
                f"keberhasilan koneksi {observed:.2f} persen, dengan sekitar "
                f"{downtime//60} menit kegagalan kedua endpoint dan "
                f"{unknown//60} menit belum terukur. "
                "Persentase uptime 24 jam belum dapat dinyatakan sampai cakupannya cukup.")
    avg = snapshot["avg_https_latency_ms"]
    latency = f" Rata-rata respons HTTPS {avg:.1f} milidetik." if avg is not None else ""
    return (f"Uptime koneksi internet TRADEVICEPC selama {snapshot['window_hours']} jam "
            f"terakhir adalah {observed:.2f} persen, "
            f"berdasarkan cakupan sampel {coverage:.2f} persen. "
            f"Kegagalan kedua endpoint sekitar {downtime//60} menit dalam "
            f"{count} kejadian, dan ada {unknown//60} menit tanpa pengukuran."
            + latency + " Ini pengukuran konektivitas HTTPS, bukan SLA ISP.")
