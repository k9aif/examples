# SPDX-License-Identifier: Apache-2.0
"""
The accounts payable demo's runtime, wired the K9-AIF way and the same way as das.k9x.ai: the shared Redpanda,
one Router, one Orchestrator, the K9X Rules Engine and K9X HIL.

  submit()  -> K9EventRouter.route(event_type="openai.ap.invoice") -> Kafka openai.ap.in
  consumer  -> APOrchestrator.execute_flow() -> squad -> pending_hil, completed, or rejected
  K9X HIL   -> Kafka hil.replies.openai-ap-payments -> K9EventRouter (listen_for_hil_replies) resumes the flow

The Router and the Orchestrator share one RoutingStateStore (where pending HIL flows wait) and the agents share one
PausedRunStore (where the paused OpenAI runs wait): PostgreSQL (database/schema from config.yaml postgres) when
enabled, else SQLite under runtime/. The page talks to K9X HIL through its REST API with an API key that stays on
this server (HIL_API_URL, HIL_API_KEY).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from k9_aif_abb.k9_adapters.openai_agents import OpenAIHILAdapter
from k9_aif_abb.k9_core.messaging.k9_event_bus import K9EventBus
from k9_aif_abb.k9_core.router.k9_event_router import K9EventRouter
from k9_aif_abb.k9_security.vulnerability.shield_governance import ShieldGovernance
from k9_aif_abb.k9_security.zero_trust.guards import DefaultZeroTrustGuard, RoleBasedAuthorizationGuard
from k9_aif_abb.k9_squad.squad_loader import SquadLoader
from k9_aif_abb.k9_storage.paused_run_store import PausedRunStore
from k9_aif_abb.k9_storage.routing_state_store import RoutingStateStore

from .orchestrator import APOrchestrator
from .tools import CAPABILITIES

log = logging.getLogger("accounts_payable")

AGENTS_DIR = Path(__file__).resolve().parent / "agents"
EVENT_TYPE = "openai.ap.invoice"
IN_TOPIC = "openai.ap.in"
STATUS_TOPIC = "openai.ap.status"   # status events (pending_hil, ...): never the orchestrator's own input
HIL_QUEUE = "openai-ap-payments"
RUN_TTL_S = 24 * 3600                # K9X HIL's own TTL on the queue (then reject)
ROLE_POLICY = {"accounts_payable.invoice": ["customer", "staff"]}

# Demo invoices (the page offers these; a visitor can't type an arbitrary invoice).
INVOICES = {
    "small": "Invoice INV-1043 from Acme Supplies for $900.00, office supplies.",
    "large": "Invoice INV-1042 from Acme Supplies for $48,500.00, warehouse racking.",
    "bank": "Invoice INV-2001 from Globex Logistics for $6,200.00, freight for October.",
    "blocked": "Invoice INV-4001 from Umbrella Corp for $1,250.00, lab consumables.",
}


def _db(config: Dict[str, Any]):
    pg = config.get("postgres") or {}
    if str(pg.get("enabled", "")).strip().lower() in ("1", "true", "yes"):   # from .env: a string, not a bool
        from k9_aif_abb.k9_storage.postgres_database_storage import PostgresDatabaseStorage
        db = PostgresDatabaseStorage(config=config)
        schema = pg.get("schema")
        if schema and schema != "public":
            from sqlalchemy import text
            with db.engine.begin() as conn:                      # the demo's own schema, created once
                conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        return db
    from k9_aif_abb.k9_storage.sqlite_database_storage import SQLiteDatabaseStorage
    return SQLiteDatabaseStorage(db_path=(config.get("hil") or {}).get("db_path") or "./runtime/ap_state.db")


class APRuntime:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        broker = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092").split(",")[0].strip()
        group = (config.get("messaging") or {}).get("group_id", "openai-demo")
        self.bus_router = K9EventBus(broker_url=broker, group_id=f"{group}-router", topic=STATUS_TOPIC, config=config)
        self.bus_orch = K9EventBus(broker_url=broker, group_id=f"{group}-ap", topic=STATUS_TOPIC, config=config)
        db = _db(config)
        self.state = RoutingStateStore(db=db)
        governance = ShieldGovernance(config)
        self.router = K9EventRouter(config=config, message_bus=self.bus_router, governance=governance,
                                    state_store=self.state)
        hil = OpenAIHILAdapter(store=PausedRunStore(db), config=config, queue=HIL_QUEUE)
        squads = SquadLoader.from_agents(AGENTS_DIR, config, agent_kwargs={"capabilities": CAPABILITIES,
                                                                          "hil_adapter": hil})
        self.orchestrator = APOrchestrator(
            config=config, message_bus=self.bus_orch, governance=governance, hil_state_store=self.state,
            zero_trust_guard=DefaultZeroTrustGuard(authorization_guard=RoleBasedAuthorizationGuard(ROLE_POLICY)),
            squads=squads)
        self.runs: Dict[str, Dict[str, Any]] = {}
        self._tasks: List[asyncio.Task] = []
        hil_cfg = config.get("hil_api") or {}
        self.hil_url = (os.environ.get("HIL_API_URL") or hil_cfg.get("url") or "").rstrip("/")
        self.hil_key = os.environ.get("HIL_API_KEY", "")

    # ── lifecycle ─────────────────────────────────────────────────────────
    async def start(self) -> None:
        self._tasks = [asyncio.create_task(self.router.listen_for_hil_replies()),
                       asyncio.create_task(self.bus_orch.subscribe_async(self._on_event, topics=[IN_TOPIC]))]
        log.info("[accounts_payable] listening on %s and hil.replies.*", IN_TOPIC)

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()

    # ── the flow ──────────────────────────────────────────────────────────
    def submit(self, which: str, owner: str) -> str:
        if which not in INVOICES:
            raise ValueError(f"unknown invoice {which!r}")
        now = time.time()
        for old in [k for k, r in self.runs.items() if now - r["created"] > RUN_TTL_S]:   # the page's view only
            self.runs.pop(old, None)
        run_id = "AP-" + uuid.uuid4().hex[:10].upper()
        self.runs[run_id] = {"run_id": run_id, "owner": owner, "invoice": which, "status": "submitted",
                             "events": [self._event("Router", f"event_type {EVENT_TYPE} published to {IN_TOPIC}")],
                             "created": time.time()}
        self.router.route({"event_type": EVENT_TYPE, "run_id": run_id, "prompt": INVOICES[which],
                           "principal_id": owner, "roles": ["customer"], "action_type": "accounts_payable.invoice"})
        return run_id

    async def _on_event(self, payload: Dict[str, Any]) -> None:
        run_id = payload.get("run_id", "")
        run = self.runs.get(run_id)
        resumed = "hil_decision" in payload
        if run is not None:
            run["status"] = "resuming" if resumed else "running"
            run["events"].append(self._event("Orchestrator", "resumed after the decision in K9X HIL" if resumed
                                             else "running the squad"))
        try:
            out = await asyncio.to_thread(self.orchestrator.execute_flow, payload)
        except Exception as exc:                                  # recorded for the page, then raised (delivery)
            if run is not None:
                run["status"], run["error"] = "error", f"{type(exc).__name__}: {exc}"
            raise
        if run is not None:
            self._record(run, out, payload)

    def _record(self, run: Dict[str, Any], out: Dict[str, Any], payload: Dict[str, Any]) -> None:
        if out.get("status") == "pending_hil":
            run["status"], run["correlation_id"] = "pending_hil", out.get("correlation_id")
            run["events"].append(self._event("Orchestrator", "paused: K9X HIL task published on "
                                             f"hil.requests.{HIL_QUEUE}"))
            so_far = out.get("so_far") or {}
            run["invoice_fields"] = _json((so_far.get("invoice_agent") or {}).get("output"))
            run["decision"] = (so_far.get("rules_check") or {}).get("output")
            return
        squad = out.get("ap_invoice") or {}
        run["invoice_fields"] = _json(squad.get("invoice_agent", {}).get("output")) or run.get("invoice_fields")
        run["decision"] = squad.get("rules_check", {}).get("output") or run.get("decision")
        run["payment"] = (squad.get("payment") or {}).get("output")
        decided = (payload.get("hil_decision") or {})
        if decided:
            run["hil_decision"] = {"action": decided.get("action"), "actor": decided.get("actor"),
                                   "comment": decided.get("comment")}
        rejected_by_rules = (run["decision"] or {}).get("decision") == "reject"
        rejected_by_person = bool(decided) and decided.get("action") != "complete"
        run["status"] = "rejected" if (rejected_by_rules or rejected_by_person) else "completed"
        run["events"].append(self._event("Orchestrator", "rejected by the rules: not paid" if rejected_by_rules
                                         else "rejected in K9X HIL: not paid" if rejected_by_person
                                         else "completed"))

    def view(self, run_id: str, owner: str) -> Optional[Dict[str, Any]]:
        run = self.runs.get(run_id)
        if not run or run["owner"] != owner:
            return None
        return {k: v for k, v in run.items() if k != "owner"}

    # ── K9X HIL, through its REST API (the key never leaves this server) ──
    def _hil(self, method: str, path: str, **kw) -> Any:
        if not (self.hil_url and self.hil_key):
            raise RuntimeError("K9X HIL API not configured (HIL_API_URL, HIL_API_KEY)")
        resp = requests.request(method, f"{self.hil_url}/api{path}", headers={"X-API-Key": self.hil_key},
                                timeout=10, **kw)
        resp.raise_for_status()
        return resp.json()

    def hil_task(self, run_id: str, owner: str) -> Optional[Dict[str, Any]]:
        run = self.runs.get(run_id)
        if not run or run["owner"] != owner or not run.get("correlation_id"):
            return None
        tasks = self._hil("GET", "/tasks", params={"correlation_id": run["correlation_id"]})
        return tasks[0] if tasks else None

    def hil_decide(self, run_id: str, owner: str, action: str, comment: str) -> Dict[str, Any]:
        if action not in ("complete", "reject"):
            raise ValueError("action must be complete or reject")
        task = self.hil_task(run_id, owner)
        if not task:
            raise LookupError("no K9X HIL task for this run yet")
        out = self._hil("POST", f"/tasks/{task['id']}/action", json={"action": action, "comment": comment or None})
        self.runs[run_id]["events"].append(self._event("K9X HIL", f"decision: {'approved' if action == 'complete' else 'rejected'}"
                                                       " (published on hil.replies." + HIL_QUEUE + ")"))
        return out

    @staticmethod
    def _event(who: str, what: str) -> Dict[str, Any]:
        return {"t": time.strftime("%H:%M:%S"), "who": who, "what": what}


def _json(text: Any) -> Any:
    if isinstance(text, str):
        try:
            return json.loads(text)
        except ValueError:
            return text
    return text
