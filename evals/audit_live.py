"""Local-only live audit. Not the portable assignment evaluator.

Run: uv run --directory backend python ../evals/audit_live.py
Uses original scenario inputs, a cloned disposable DB per scenario, real configured
LLM calls, the actual ASGI /messages route, and unchanged isolated PaySwift servers.
"""

import asyncio
import contextvars
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import asyncpg
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent import llm
from app.agent.prompts import PROMPT_VERSION, SYSTEM_PROMPT
from app.core.config import get_settings
from app.core.database import get_db_session, get_engine, get_session_factory
from app.integrations.payswift import get_payswift_client
from app.main import create_app
from app.models import Conversation, Dispute, DisputeItem, Message, OpsQueue, PaymentIntent
from app.realtime.publisher import drain
from app.scripts.seed import seed_data
from app.services import auth_service, message_service, payment_worker
from app.services.payment_reconciliation import match_payout, reference_for
from app.services.trace_service import safe_json

REPORT = ROOT / "evals/reports/final-audit"
LOGS = ROOT / "ai-logs/final-audit"
CURRENT = contextvars.ContextVar("audit_scenario", default=None)
CALLS = {}
ORIGINAL_EXTRACT = llm.extract


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(safe_json(value), indent=2, ensure_ascii=False) + "\n")


async def observed_extract(**kwargs):
    """Observe the real extractor; never substitute an answer or a label."""
    label = CURRENT.get()
    settings = get_settings()
    record = {
        "provider": settings.llm_provider,
        "model": settings.bedrock_model_id
        if settings.llm_provider == "amazon"
        else settings.groq_model,
        "prompt_version": PROMPT_VERSION,
        "system_prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
        "input": kwargs,
        "started_at": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
    }
    CALLS.setdefault(label, []).append(record)
    start = time.perf_counter()
    try:
        result = await ORIGINAL_EXTRACT(**kwargs)
        record["validated_model_output"] = result.model_dump(mode="json")
        return result
    except BaseException as exc:
        record["failure"] = type(exc).__name__
        raise
    finally:
        record["latency_seconds"] = round(time.perf_counter() - start, 4)
        if label:
            save(LOGS / f"{label}-llm.json", CALLS[label])


async def admin(url, sql):
    assert url.host in {"localhost", "127.0.0.1", "::1"}
    conn = await asyncpg.connect(
        host=url.host,
        port=url.port or 5432,
        user=url.username,
        password=url.password,
        database="postgres",
        timeout=10,
    )
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


def db_name(name):
    assert name.startswith("quickdrop_audit_") and all(c.isalnum() or c == "_" for c in name)
    return '"' + name + '"'


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def sandbox(label):
    port = free_port()
    log = open(REPORT / "checks" / f"{label}-sandbox.txt", "w")
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "payswift/server.pyc")],
        cwd=ROOT / "payswift",
        env={**os.environ, "PORT": str(port)},
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=1) as http:
            for _ in range(40):
                if proc.poll() is not None:
                    raise RuntimeError("isolated_sandbox_exited")
                try:
                    if (await http.get(url + "/health")).status_code == 200:
                        return proc, log, url
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.1)
        raise RuntimeError("isolated_sandbox_not_ready")
    except BaseException:
        proc.terminate()
        proc.wait(timeout=3)
        log.close()
        raise


async def snapshot(factory):
    async with factory() as session:

        def columns(row, names):
            return {name: getattr(row, name) for name in names}

        return safe_json(
            {
                "disputes": [
                    columns(
                        r,
                        [
                            "id",
                            "rider_id",
                            "conversation_id",
                            "status",
                            "verified_amount",
                            "details",
                        ],
                    )
                    for r in await session.scalars(select(Dispute))
                ],
                "items": [
                    columns(
                        r,
                        [
                            "dispute_id",
                            "source_type",
                            "source_id",
                            "expected_amount",
                            "actual_amount",
                            "difference",
                        ],
                    )
                    for r in await session.scalars(select(DisputeItem))
                ],
                "intents": [
                    columns(
                        r,
                        [
                            "id",
                            "dispute_id",
                            "rider_id",
                            "status",
                            "amount",
                            "payment_type",
                            "provider_payout_id",
                            "idempotency_key",
                            "auto_pay_date",
                            "authorization",
                            "post_started_at",
                            "last_reconciled_at",
                            "retry_count",
                            "next_retry_at",
                        ],
                    )
                    for r in await session.scalars(select(PaymentIntent))
                ],
                "queues": [
                    columns(
                        r,
                        [
                            "id",
                            "dispute_id",
                            "type",
                            "status",
                            "amount",
                            "reason",
                            "assigned_to",
                            "resolved_at",
                        ],
                    )
                    for r in await session.scalars(select(OpsQueue))
                ],
                "messages": [
                    columns(
                        r,
                        [
                            "id",
                            "message_id",
                            "sender_type",
                            "content",
                            "received_at",
                            "processing_status",
                            "agent_state",
                            "is_internal",
                            "conversation_id",
                        ],
                    )
                    for r in await session.scalars(
                        select(Message).order_by(Message.created_at, Message.id)
                    )
                ],
            }
        )


async def complete_agent(factory, message_id):
    deadline = time.monotonic() + 100
    while time.monotonic() < deadline:
        async with factory() as session:
            row = await session.scalar(select(Message).where(Message.message_id == message_id))
            if row and row.processing_status == "COMPLETED":
                return row.webhook_reply
        await message_service.resume_one(factory)
        await asyncio.sleep(0.2)
    return None


async def settle(factory, client, seconds=45):
    deadline = time.monotonic() + seconds
    errors = []
    while time.monotonic() < deadline:
        async with factory() as session:
            active = list(
                await session.scalars(
                    select(PaymentIntent).where(
                        PaymentIntent.status.in_(["PENDING", "PROCESSING", "UNKNOWN"])
                    )
                )
            )
        if not active:
            break
        try:
            await payment_worker.process_one(factory, client)
        except Exception as exc:
            errors.append(type(exc).__name__)
            break
        await asyncio.sleep(0.2)
    return errors


def assess(scenario, state, traces, ledger):
    expected = scenario["expected"]
    options = expected.get(
        "one_of", [{"payout": expected.get("payout", 0), "approval": expected.get("approval")}]
    )
    approvals = [
        q
        for q in state["queues"]
        if q["type"] == "approval" and q["status"] in ["PENDING", "IN_REVIEW"]
    ]
    auto = sum(int(i["amount"]) for i in state["intents"] if i["payment_type"] == "AUTO")
    amount = sum(int(q["amount"]) for q in approvals) if approvals else None
    decision_escalations = [
        t for t in traces if t["name"] in ["agent_escalation", "agent_investigation_exhausted"]
    ]
    financial_match = any({"payout": auto, "approval": amount} == option for option in options)
    escalation_match = expected.get("escalation") != "no" or not decision_escalations
    mentions = expected.get("reply_mentions", [])
    reply_text = " ".join(m["content"] for m in state["messages"] if m["sender_type"] == "AI")
    reply_mentions = all(mention in reply_text for mention in mentions)
    confirmed = []
    unmatched = []
    for intent in state["intents"]:
        result = match_payout(
            ledger,
            rider_id=intent["rider_id"],
            reference=reference_for(intent["id"]),
            amount=__import__("decimal").Decimal(intent["amount"]),
            provider_id=intent["provider_payout_id"],
        )
        if intent["status"] == "SUCCEEDED" and result.kind == "CONFIRMED":
            confirmed.append(intent)
        else:
            unmatched.append(
                {"id": intent["id"], "status": intent["status"], "provider_check": result.kind}
            )
    provider_amount = sum(p.amount for p in ledger)
    confirmed_amount = sum(int(i["amount"]) for i in confirmed)
    execution_match = any(
        confirmed_amount == opt["payout"] and provider_amount == opt["payout"] and not unmatched
        for opt in options
    )
    decision = financial_match and escalation_match
    # Semantics are reported separately; amounts mentioned in text are never settlement proof.
    return {
        "decision_status": "PASS" if decision else "FAIL",
        "execution_status": "PASS" if execution_match else "FAIL",
        "overall_status": "PASS" if decision and execution_match and reply_mentions else "FAIL",
        "expected": expected,
        "auto_authorized_amount": auto,
        "pending_approval_amount": amount,
        "pending_approval_count": len(approvals),
        "verified_dispute_amounts": [d["verified_amount"] for d in state["disputes"]],
        "agent_escalation_count": len(decision_escalations),
        "all_escalation_count": sum(q["type"] == "escalation" for q in state["queues"]),
        "provider_confirmed_amount": confirmed_amount,
        "provider_ledger_amount": provider_amount,
        "unconfirmed_intents": unmatched,
        "reply_mentions_pass": reply_mentions,
        "settlement_required": any(opt["payout"] > 0 for opt in options),
        "financial_match": financial_match,
        "escalation_match": escalation_match,
    }


async def ops_flow(http, factory, client, rider):
    """Exercise real authenticated routes; credentials/cookies never enter artifacts."""
    result = {"rider_id": rider, "checks": {}}
    check = result["checks"]
    user_email = "audit-" + uuid4().hex + "@test.invalid"
    password = secrets.token_urlsafe(32)
    async with factory() as session, session.begin():
        await auth_service.seed_admin(session, user_email, password)
    check["unauthorized_rejected"] = (await http.get("/auth/me")).status_code == 401
    login = await http.post("/auth/login", json={"email": user_email, "password": password})
    check["login"] = login.status_code == 200
    check["session_validation"] = (await http.get("/auth/me")).status_code == 200
    async with factory() as session:
        case = await session.scalar(
            select(OpsQueue).where(OpsQueue.type == "approval", OpsQueue.status == "PENDING")
        )
        if case is None:
            result["workflow_status"] = (
                "NOT TESTED: live scenario did not produce a pending approval"
            )
        else:
            dispute = await session.get(Dispute, case.dispute_id)
            cid = str(dispute.conversation_id)
            base = "/ui/ops/conversations/" + cid
            check["takeover"] = (await http.post(base + "/takeover")).status_code == 200
            check["human_reply"] = (
                await http.post(
                    base + "/messages",
                    json={
                        "text": "We are reviewing this claim.",
                        "client_request_id": str(uuid4()),
                    },
                )
            ).status_code == 201
            note = "Private audit-only note " + uuid4().hex
            check["internal_note"] = (
                await http.post(
                    base + "/notes", json={"text": note, "client_request_id": str(uuid4())}
                )
            ).status_code == 201
            public = await http.get(f"/ui/conversations/{cid}/messages", params={"rider_id": rider})
            # Create signed rider context for the protected reader without weakening access checks.
            await http.post("/ui/demo/rider", json={"rider_id": rider})
            public = await http.get(f"/ui/conversations/{cid}/messages", params={"rider_id": rider})
            check["private_note_hidden"] = public.status_code == 200 and note not in public.text
            check["human_reply_visible"] = (
                public.status_code == 200 and "We are reviewing this claim." in public.text
            )
            # Same historical timestamp as the claim, separate message ID only for this Ops test.
            human = await http.post(
                "/messages",
                json={
                    "message_id": "audit.human." + uuid4().hex,
                    "rider_id": rider,
                    "text": "Any update?",
                    "received_at": dispute.details["request"]["received_at"],
                },
            )
            check["ai_bypassed_in_human_mode"] = (
                human.status_code == 200 and "support" in human.json()["reply"].lower()
            )
            check["handback_blocked_while_pending"] = (
                await http.post(base + "/handoff")
            ).status_code == 409
            if rider == "R016":
                action = await http.post(f"/ui/ops/cases/{case.id}/approve")
                result["approval_http_status"] = action.status_code
                result["approval_body"] = action.json()
                check["approval_authorized"] = action.status_code == 200
                check["repeat_approval_rejected"] = (
                    await http.post(f"/ui/ops/cases/{case.id}/approve")
                ).status_code == 409
                result["worker_errors"] = await settle(factory, client)
            else:
                action = await http.post(
                    f"/ui/ops/cases/{case.id}/reject",
                    json={
                        "reason": "Audit exercises the rejection branch; no transfer authorized."
                    },
                )
                check["rejection"] = action.status_code == 200
                check["repeat_rejection_rejected"] = (
                    await http.post(
                        f"/ui/ops/cases/{case.id}/reject", json={"reason": "duplicate decision"}
                    )
                ).status_code == 409
            result["after_state"] = await snapshot(factory)
            ledger = await client.ledger(rider)
            result["provider_ledger"] = [p.model_dump(mode="json") for p in ledger]
            if rider == "R016":
                intents = result["after_state"]["intents"]
                check["exactly_one_425_intent"] = (
                    len(intents) == 1
                    and int(intents[0]["amount"]) == 425
                    and intents[0]["payment_type"] == "OPS_APPROVED"
                )
                check["425_provider_confirmed"] = (
                    len(ledger) == 1
                    and ledger[0].amount == 425
                    and intents
                    and intents[0]["status"] == "SUCCEEDED"
                )
            else:
                check["no_payment_after_rejection"] = (
                    not ledger and not result["after_state"]["intents"]
                )
                check["queue_rejected"] = all(
                    q["status"] == "REJECTED"
                    for q in result["after_state"]["queues"]
                    if q["type"] == "approval"
                )
            check["resolution"] = (
                await http.post(base + "/resolve", json={"reason": "Audit workflow completion"})
            ).status_code == 200
            result["workflow_status"] = "PASS" if all(check.values()) else "FAIL"
    check["logout"] = (await http.post("/auth/logout")).status_code == 204
    check["session_revoked"] = (await http.get("/auth/me")).status_code == 401
    return result


async def evaluate(index, scenario, base_url, template, run_id):
    label = f"scenario-{index:02d}-{scenario['rider_id']}"
    CURRENT.set(label)
    database = f"quickdrop_audit_{run_id}_{index:02d}"
    await admin(base_url, f"CREATE DATABASE {db_name(database)} TEMPLATE {db_name(template)}")
    engine = None
    proc = None
    http = None
    log = None
    result = {
        "scenario_id": index,
        "rider_id": scenario["rider_id"],
        "scenario": scenario["scenario"],
        "turns": [],
        "transport": "actual FastAPI ASGI route, in-process HTTP",
        "llm_mode": "LIVE, no model labels or mocked responses",
        "payment_worker_mode": "existing durable worker functions, no scheduling overrides",
    }
    try:
        proc, log, provider_url = await sandbox(label)
        os.environ["DATABASE_URL"] = base_url.set(database=database).render_as_string(
            hide_password=False
        )
        os.environ["PAYSWIFT_BASE_URL"] = provider_url
        get_settings.cache_clear()
        engine = create_async_engine(get_settings().sqlalchemy_url, hide_parameters=True)
        factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
        client = get_payswift_client()
        app = create_app()
        app.dependency_overrides[get_session_factory] = lambda: factory

        async def session_dependency():
            async with factory() as session:
                yield session

        app.dependency_overrides[get_db_session] = session_dependency
        http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 45678)),
            base_url="http://audit.local",
            timeout=15,
        )
        result["health_http_status"] = (await http.get("/health")).status_code
        for turn in scenario["turns"]:
            if turn["from"] != "rider":
                continue
            payload = {key: turn[key] for key in ["message_id", "text", "received_at"]}
            payload["rider_id"] = scenario["rider_id"]
            start = time.perf_counter()
            response = await http.post("/messages", json=payload)
            entry = {
                "request": payload,
                "http_status": response.status_code,
                "webhook_latency_seconds": round(time.perf_counter() - start, 4),
                "initial_response": response.json(),
            }
            if response.status_code == 200:
                final = await complete_agent(factory, payload["message_id"])
                entry["final_reply"] = final
                entry["total_agent_seconds"] = round(time.perf_counter() - start, 4)
                entry["completed"] = final is not None
                replay = await http.post("/messages", json=payload)
                entry["idempotent_replay"] = (
                    replay.status_code == 200 and replay.json().get("reply") == final
                )
                # Preserve the decision before invoking payment execution.
                entry["decision_state_before_payment_worker"] = await snapshot(factory)
                entry["worker_errors"] = await settle(factory, client, seconds=30)
            result["turns"].append(entry)
        result["state"] = await snapshot(factory)
        trace = await http.get("/trace/" + scenario["rider_id"])
        result["trace_http_status"] = trace.status_code
        traces = trace.json() if trace.status_code == 200 else []
        pending = await http.get("/ops/pending")
        result["ops_pending_http_status"] = pending.status_code
        result["ops_pending"] = pending.json()
        ledger = await client.ledger(scenario["rider_id"])
        result["provider_ledger"] = [p.model_dump(mode="json") for p in ledger]
        result.update(assess(scenario, result["state"], traces, ledger))
        result["tool_calls"] = [t["name"] for t in traces if t["type"] == "tool_call"]
        result["decision_events"] = [t for t in traces if t["type"] == "decision"]
        result["webhook_budget_pass"] = all(
            t["http_status"] == 200 and t["webhook_latency_seconds"] < 10 for t in result["turns"]
        )
        result["trace_contract_pass"] = (
            trace.status_code == 200
            and all(set(["at", "type", "name", "input", "output"]) <= set(t) for t in traces)
            and [t["at"] for t in traces] == sorted(t["at"] for t in traces)
        )
        result["all_turns_completed"] = all(t.get("completed") for t in result["turns"])
        result["llm_calls"] = len(CALLS.get(label, []))
        save(LOGS / f"{label}-traces.json", traces)
        if scenario["rider_id"] in {"R016", "R034"}:
            ops = await ops_flow(http, factory, client, scenario["rider_id"])
            save(REPORT / f"ops-{scenario['rider_id']}.json", ops)
        print(
            f"{label}: decision={result['decision_status']}, execution={result['execution_status']}, confirmed={result['provider_confirmed_amount']}",
            flush=True,
        )
    except Exception as exc:
        result.update({"overall_status": "FAIL", "error_type": type(exc).__name__})
        print(label + ": audit error " + type(exc).__name__, flush=True)
    finally:
        save(REPORT / f"{label}.json", result)
        save(LOGS / f"{label}-llm.json", CALLS.get(label, []))
        await drain()
        if http:
            await http.aclose()
        if get_payswift_client.cache_info().currsize:
            await get_payswift_client().aclose()
            get_payswift_client.cache_clear()
        if engine:
            await engine.dispose()
        if get_engine.cache_info().currsize:
            await get_engine().dispose()
            get_engine.cache_clear()
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        if log:
            log.close()
        await admin(base_url, f"DROP DATABASE {db_name(database)} WITH (FORCE)")
    return result


def finalize_results(results, settings):
    for result in results:
        if "decision_status" not in result:
            continue
        result["eventual_scenario_status"] = result["overall_status"]
        result["delivery_status"] = (
            "PASS"
            if all(
                turn.get("http_status") == 200
                and turn.get("initial_response", {}).get("reply") == turn.get("final_reply")
                for turn in result["turns"]
            )
            else "FAIL"
        )
        result["end_to_end_status"] = (
            "PASS"
            if (
                result["eventual_scenario_status"] == "PASS"
                and result["delivery_status"] == "PASS"
                and result.get("webhook_budget_pass")
            )
            else "FAIL"
        )
        result["worker_execution_status"] = (
            "PASS"
            if result.get("state", {}).get("intents") and not result.get("unconfirmed_intents")
            else "NOT APPLICABLE"
            if not result.get("state", {}).get("intents")
            else "FAIL"
        )
        if not result.get("llm_calls"):
            result["llm_bypass_reason"] = (
                "Application input-policy guard rejected the request before invoking the LLM; no model call was fabricated."
            )
        save(REPORT / f"scenario-{result['scenario_id']:02d}-{result['rider_id']}.json", result)
    complete = [r for r in results if "decision_status" in r]
    turns = [t for r in complete for t in r["turns"]]
    metrics = {
        "scenario_count": len(results),
        "decision_pass": sum(r["decision_status"] == "PASS" for r in complete),
        "execution_pass": sum(r["execution_status"] == "PASS" for r in complete),
        "eventual_pass": sum(r["eventual_scenario_status"] == "PASS" for r in complete),
        "delivery_pass": sum(r["delivery_status"] == "PASS" for r in complete),
        "end_to_end_pass": sum(r["end_to_end_status"] == "PASS" for r in complete),
        "auto_intents": sum(len(r["state"]["intents"]) for r in complete),
        "confirmed_auto_amount": sum(r["provider_confirmed_amount"] for r in complete),
        "webhook_turns": len(turns),
        "acknowledgment_turns": sum(
            t["initial_response"].get("reply") != t.get("final_reply") for t in turns
        ),
        "max_webhook_seconds": max((t["webhook_latency_seconds"] for t in turns), default=0),
        "max_final_agent_seconds": max((t.get("total_agent_seconds", 0) for t in turns), default=0),
        "deferred_scenarios": [
            r["scenario_id"] for r in complete if r["delivery_status"] == "FAIL"
        ],
    }
    records = [call for calls in CALLS.values() for call in calls]
    save(
        REPORT / "llm-metrics.json",
        {
            "invocations": len(records),
            "validated_responses": sum("validated_model_output" in c for c in records),
            "foreground_cancellations": sum(c.get("failure") == "CancelledError" for c in records),
            "extraction_unavailable": sum(
                c.get("failure") == "ExtractionUnavailable" for c in records
            ),
            "mean_invocation_seconds": round(
                sum(c["latency_seconds"] for c in records) / max(1, len(records)), 3
            ),
            "max_invocation_seconds": max((c["latency_seconds"] for c in records), default=0),
            "latency_scope": "Wrapper wall time; cancellation does not prove upstream synchronous SDK cancellation.",
        },
    )
    save(
        REPORT / "live-24-results.json",
        {
            "provider": settings.llm_provider,
            "model": settings.bedrock_model_id
            if settings.llm_provider == "amazon"
            else settings.groq_model,
            "prompt_version": PROMPT_VERSION,
            "summary": metrics,
            "results": results,
            "isolation": "Fresh per-scenario PostgreSQL/PaySwift and separate Redis; original received_at preserved.",
            "settlement_wait_seconds_per_turn": 30,
            "result_definitions": {
                "decision_status": "Persisted authorization/approval amounts and agent escalation vs original expected outcomes.",
                "execution_status": "Actual PaySwift-correlated confirmed total vs original expected payout; zero-transfer cases included.",
                "worker_execution_status": "Conditional on intents actually produced; absent expected intent is NOT a passed worker execution.",
                "eventual_scenario_status": "Decision, execution and targeted reply facts after durable continuation/replay.",
                "delivery_status": "Original webhook contains final reply, rather than acknowledgment.",
                "end_to_end_status": "Eventual success and final useful original reply within 10 seconds.",
            },
        },
    )


def prepare_metadata(settings):
    immutable = [
        "BRIEF.md",
        "SUBMISSION.md",
        "docs/policy.md",
        "data/conversations.json",
        "data/riders.csv",
        "data/trips.csv",
        "data/payout_lines.csv",
        "payswift/server.pyc",
    ]
    source = [
        p
        for folder in ["backend/app", "backend/alembic", "frontend/src"]
        for p in (ROOT / folder).rglob("*")
        if p.is_file() and p.suffix in {".py", ".ts", ".tsx", ".css"}
    ]
    source += [
        ROOT / p
        for p in [
            "backend/uv.lock",
            "backend/pyproject.toml",
            "frontend/package.json",
            "frontend/package-lock.json",
            ".github/workflows/workflow.yml",
            "docker-compose.yml",
            "Makefile",
        ]
    ]
    save(
        REPORT / "manifest.json",
        {
            "git_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "dirty_files": subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=ROOT, text=True
            ).splitlines(),
            "provider": settings.llm_provider,
            "model": settings.bedrock_model_id
            if settings.llm_provider == "amazon"
            else settings.groq_model,
            "app_env": settings.app_env,
            "configured_demo_clock": str(settings.app_reference_time),
            "foreground_seconds": settings.agent_foreground_seconds,
            "worker_seconds": settings.agent_job_seconds,
            "hashes": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in immutable},
            "tested_working_tree_sha256": {
                str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(source)
            },
            "snapshot_note": "Base commit plus exact current dirty-tree fingerprints; credentials excluded.",
        },
    )


async def main():
    REPORT.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    assert settings.app_env == "development" and settings.sqlalchemy_url.host in {
        "localhost",
        "127.0.0.1",
        "::1",
    }
    prepare_metadata(settings)
    base_url = settings.sqlalchemy_url
    run_id = uuid4().hex[:10]
    template = f"quickdrop_audit_{run_id}_template"
    redis_name = "quickdrop-audit-redis-" + run_id
    os.environ["APP_REFERENCE_TIME"] = ""
    # Isolated Redis prevents live audit events reaching the developer's Ops UI.
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "--name",
            redis_name,
            "-p",
            "127.0.0.1::6379",
            "redis:7-alpine",
            "redis-server",
            "--save",
            "",
            "--appendonly",
            "no",
        ],
        check=True,
        capture_output=True,
    )
    redis_port = (
        subprocess.check_output(["docker", "port", redis_name, "6379/tcp"], text=True)
        .strip()
        .rsplit(":", 1)[1]
    )
    os.environ["REDIS_URL"] = "redis://127.0.0.1:" + redis_port + "/0"
    llm.extract = observed_extract
    results = []
    try:
        await admin(base_url, f"CREATE DATABASE {db_name(template)}")
        url = base_url.set(database=template)
        env = {**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False)}
        migration = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT / "backend",
            env=env,
            capture_output=True,
            text=True,
            timeout=45,
        )
        (REPORT / "checks/audit-migrations.txt").write_text(migration.stdout + migration.stderr)
        assert migration.returncode == 0
        engine = create_async_engine(url, hide_parameters=True)
        try:
            async with async_sessionmaker(engine)() as session, session.begin():
                counts = await seed_data(session)
                save(REPORT / "seed-counts.json", counts)
        finally:
            await engine.dispose()
        scenarios = json.loads((ROOT / "data/conversations.json").read_text())
        for index, scenario in enumerate(scenarios, 1):
            results.append(await evaluate(index, scenario, base_url, template, run_id))
            save(
                REPORT / "live-24-results.json",
                {
                    "provider": settings.llm_provider,
                    "model": settings.bedrock_model_id
                    if settings.llm_provider == "amazon"
                    else settings.groq_model,
                    "prompt_version": PROMPT_VERSION,
                    "isolation": "fresh cloned PostgreSQL + fresh unchanged PaySwift process per scenario; isolated Redis; original official received_at preserved; real leases/retries/audit clock",
                    "settlement_wait_seconds_per_turn": 30,
                    "results": results,
                },
            )
    finally:
        llm.extract = ORIGINAL_EXTRACT
        await admin(base_url, f"DROP DATABASE IF EXISTS {db_name(template)} WITH (FORCE)")
        subprocess.run(["docker", "rm", "-f", redis_name], capture_output=True)
    finalize_results(results, settings)
    print("Live audit completed: " + str(len(results)) + " scenarios.", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
