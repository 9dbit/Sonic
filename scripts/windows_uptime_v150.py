"""SONIC Internet Uptime Monitor v1.5.0: durable local HTTPS availability sampling.

Runs ONLY on an authorized Windows Companion, independently of its cloud polling.
Two fixed HTTPS 204 checks every 30 seconds. No arbitrary destinations, ports,
shell commands, DNS details, response bodies, IPs, or credentials are collected.
This measures endpoint reachability from this PC, not a certified ISP SLA.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from uuid import uuid4

INTERVAL_SECONDS = 30
RETENTION_DAYS = 30
BATCH_MAX = 60
TIMEOUT = 3
TARGETS = (
    ("google", "https://www.google.com/generate_204"),
    ("cloudflare", "https://cp.cloudflare.com/generate_204"),
)
FIELDS = ("sample_id", "observed_at_ms", "google_ok", "cloudflare_ok",
          "google_ms", "cloudflare_ms")


def utc_ms():
    return int(time.time() * 1000)


def probe_one(url: str):
    start = time.monotonic()
    try:
        req = Request(url, headers={"User-Agent": "SONIC-Uptime/1.5", "Cache-Control": "no-cache"})
        with urlopen(req, timeout=TIMEOUT) as response:
            # A transparent proxy/captive portal often returns 200 instead of 204.
            ok = response.status == 204
        duration = min(10000, max(1, int((time.monotonic() - start) * 1000)))
        return ok, duration if ok else None
    except Exception:
        # Do not persist or send exception text; it may contain network details.
        return False, None


def sample_once(now_ms=None):
    google_ok, google_ms = probe_one(TARGETS[0][1])
    cloudflare_ok, cloudflare_ms = probe_one(TARGETS[1][1])
    return {
        "sample_id": str(uuid4()),
        "observed_at_ms": int(now_ms if now_ms is not None else utc_ms()),
        "google_ok": google_ok,
        "cloudflare_ok": cloudflare_ok,
        "google_ms": google_ms,
        "cloudflare_ms": cloudflare_ms,
    }


class UptimeJournal:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._prepare()

    def _conn(self):
        c = sqlite3.connect(str(self.path), timeout=5)
        c.execute("PRAGMA busy_timeout=5000")
        return c

    def _prepare(self):
        with self._conn() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("""CREATE TABLE IF NOT EXISTS samples (
                sample_id TEXT PRIMARY KEY,
                observed_at_ms INTEGER NOT NULL,
                google_ok INTEGER NOT NULL,
                cloudflare_ok INTEGER NOT NULL,
                google_ms INTEGER,
                cloudflare_ms INTEGER,
                uploaded INTEGER NOT NULL DEFAULT 0
            )""")
            c.execute("CREATE INDEX IF NOT EXISTS ix_samples_upload ON samples(uploaded, observed_at_ms)")

    def add(self, value):
        with self._conn() as c:
            c.execute("""INSERT OR IGNORE INTO samples
                (sample_id, observed_at_ms, google_ok, cloudflare_ok, google_ms, cloudflare_ms)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (value["sample_id"], int(value["observed_at_ms"]),
                 int(value["google_ok"]), int(value["cloudflare_ok"]),
                 value["google_ms"], value["cloudflare_ms"]))
            c.execute("DELETE FROM samples WHERE observed_at_ms < ?",
                      (utc_ms() - RETENTION_DAYS * 86400000,))

    def pending(self, limit=BATCH_MAX):
        with self._conn() as c:
            rows = c.execute("""SELECT sample_id, observed_at_ms, google_ok, cloudflare_ok,
                                       google_ms, cloudflare_ms FROM samples
                                WHERE uploaded=0 ORDER BY observed_at_ms, sample_id LIMIT ?""",
                             (min(BATCH_MAX, max(1, int(limit))),)).fetchall()
        return [{**dict(zip(FIELDS, row)),
                 "google_ok": bool(row[2]),
                 "cloudflare_ok": bool(row[3])} for row in rows]

    def acknowledge(self, ids):
        # Mark only IDs acknowledged by the actual server, never all pending rows.
        if not ids:
            return
        with self._conn() as c:
            c.executemany("UPDATE samples SET uploaded=1 WHERE sample_id=?",
                          ((i,) for i in ids))

    def counts(self):
        with self._conn() as c:
            return c.execute("SELECT COUNT(*), SUM(CASE WHEN uploaded=0 THEN 1 ELSE 0 END) FROM samples").fetchone()


class UptimeSampler:
    def __init__(self, journal, interval=INTERVAL_SECONDS, sample=sample_once):
        self.journal = journal
        self.interval = interval
        self.sample = sample
        self.stop = threading.Event()
        self.thread = None

    def start(self):
        if self.thread is not None:
            return
        self.thread = threading.Thread(target=self._loop, daemon=True, name="sonic-uptime")
        self.thread.start()

    def _loop(self):
        next_at = time.monotonic()
        while not self.stop.is_set():
            try:
                self.journal.add(self.sample())
            except Exception:
                # A failed local write does not interfere with trading or Companion.
                pass
            next_at += self.interval
            # Suspend/hibernate, network stalls, and long pauses are UNKNOWN, not
            # backfilled with artificial uptime or downtime samples.
            if next_at < time.monotonic():
                next_at = time.monotonic() + self.interval
            self.stop.wait(max(0.0, next_at - time.monotonic()))

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=5)


def enabled():
    return os.name == "nt" and os.getenv("SONIC_UPTIME_ENABLED", "1").lower() in ("1", "true", "yes")


def start_monitor(root=None):
    if not enabled():
        return None
    here = Path(root) if root is not None else Path(__file__).resolve().parent
    journal = UptimeJournal(here / "state" / "internet-uptime-v150.sqlite3")
    sampler = UptimeSampler(journal)
    sampler.start()
    return sampler


def upload_pending(journal, api, device_id):
    rows = journal.pending()
    if not rows:
        return {"sent": 0}
    response = api("/api/uptime/ingest", {"device_id": device_id, "samples": rows})
    accepted = response.get("acknowledged", [])
    allowed = {x["sample_id"] for x in rows}
    if not isinstance(accepted, list) or len(accepted) != len(rows) or set(accepted) != allowed:
        raise RuntimeError("UPTIME_RECEIPT_MISMATCH")
    journal.acknowledge(accepted)
    return {"sent": len(accepted)}
