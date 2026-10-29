"""Portable, standard-library-only HTTP evaluator. Use fresh isolated sandbox state.

No backend imports, database access, credentials or implementation-specific endpoints.
Use a fresh deployment for the suite. Shared-rider scenarios compare the cumulative
ledger and existing obligations; message IDs and expected outcomes remain unchanged.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from decimal import Decimal
from pathlib import Path


class EvaluationError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def http(base, path, payload=None, timeout=10):
    request = urllib.request.Request(
        base.rstrip("/") + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except (OSError, ValueError, urllib.error.HTTPError) as exc:
        raise EvaluationError(
            f"{path}: {type(exc).__name__} status={getattr(exc, 'code', 'unavailable')}",
            status=getattr(exc, "code", None),
        ) from None


def submit(base, payload):
    """Model vendor retries faithfully; never change IDs or treat retry as initial delivery."""
    attempts = []
    for number in range(4):
        start = time.monotonic()
        try:
            reply = http(base, "/messages", payload)
        except EvaluationError as exc:
            attempts.append(
                {"status": exc.status, "reply": None, "seconds": round(time.monotonic() - start, 4)}
            )
            if exc.status not in {None, 429, 502, 503, 504} or number == 3:
                raise
            time.sleep(1)
        else:
            attempts.append(
                {
                    "status": 200,
                    "reply": reply.get("reply") if isinstance(reply, dict) else None,
                    "seconds": round(time.monotonic() - start, 4),
                }
            )
            return reply, attempts


def iso(value):
    if not isinstance(value, str):
        raise EvaluationError("Timestamp must be an ISO string")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise EvaluationError("Timestamp must be timezone-aware")


def validate_trace(value):
    if not isinstance(value, list):
        raise EvaluationError("Trace must be a list")
    for row in value:
        if not isinstance(row, dict) or not {"at", "type", "name", "input", "output"} <= row.keys():
            raise EvaluationError("Invalid trace step schema")
        iso(row["at"])
        if row["type"] not in {"message_in", "tool_call", "decision", "reply", "error"}:
            raise EvaluationError("Invalid trace type")
        if not isinstance(row["name"], str) or (
            row["input"] is not None and not isinstance(row["input"], dict)
        ):
            raise EvaluationError("Invalid trace name/input")
    return value


def validate_pending(value):
    if not isinstance(value, list):
        raise EvaluationError("Ops pending must be a list")
    for row in value:
        if (
            not isinstance(row, dict)
            or not {"id", "rider_id", "type", "amount", "reason", "created_at"} <= row.keys()
        ):
            raise EvaluationError("Invalid pending item schema")
        iso(row["created_at"])
        if row["type"] not in {"approval", "escalation"}:
            raise EvaluationError("Invalid pending type")
        if row["type"] == "approval":
            Decimal(str(row["amount"]))
    return value


def ledger(base, rider):
    value = http(base, "/v1/payouts?" + urllib.parse.urlencode({"rider_id": rider}))
    # Supplied PaySwift returns a list; tolerate an explicitly wrapped provider list.
    if isinstance(value, dict):
        value = value.get("data", value.get("payouts"))
    if not isinstance(value, list):
        raise EvaluationError("Invalid provider ledger")
    if any(
        not isinstance(row, dict) or not {"payout_id", "amount", "status"} <= row.keys()
        for row in value
    ):
        raise EvaluationError("Invalid provider payout")
    return value


def new_rows(before, after, key):
    known = {json.dumps(row.get(key), sort_keys=True) for row in before}
    return [row for row in after if json.dumps(row.get(key), sort_keys=True) not in known]


def verdict(expected, approved, paid, escalated):
    alternatives = expected.get("one_of", [expected])
    return any(
        Decimal(str(option.get("payout", expected.get("payout", 0)))) == paid
        and Decimal(str(option.get("approval", expected.get("approval")) or 0)) == approved
        and (
            expected.get("escalation", "optional") == "optional"
            or escalated == (expected.get("escalation") == "yes")
        )
        for option in alternatives
    )


def evaluate(base, scenario, provider=None, wait=35, allow_existing=False):
    rider = scenario["rider_id"]
    result = {
        "rider_id": rider,
        "scenario": scenario["scenario"],
        "expected": scenario["expected"],
        "requests": [],
        "errors": [],
        "decision": "NOT VERIFIED",
        "authorization": "NOT VERIFIED",
        "provider_payment": "NOT VERIFIED",
        "initial_final_delivery": "NOT VERIFIED",
    }
    try:
        before_trace = validate_trace(http(base, "/trace/" + rider))
        before_pending = validate_pending(http(base, "/ops/pending"))
        before_ledger = None
        if provider:
            try:
                before_ledger = ledger(provider, rider)
            except EvaluationError as exc:
                result["provider_error"] = str(exc)
        # Refuse shared financial state rather than incorrectly crediting old payouts.
        if not allow_existing and (
            before_trace or any(row["rider_id"] == rider for row in before_pending) or before_ledger
        ):
            raise EvaluationError(
                "Rider already has state: run this scenario on a fresh isolated deployment"
            )
        seen = {}
        trace = before_trace
        for turn in scenario["turns"]:
            if turn["from"] != "rider":
                continue
            payload = {key: turn[key] for key in ("message_id", "text", "received_at")}
            payload["rider_id"] = rider
            start = time.monotonic()
            reply, attempts = submit(base, payload)
            elapsed = attempts[0]["seconds"]
            if (
                not isinstance(reply, dict)
                or not isinstance(reply.get("reply"), str)
                or not reply["reply"].strip()
            ):
                raise EvaluationError(
                    "POST /messages must return an object with a nonempty string reply"
                )
            if turn["message_id"] in seen and seen[turn["message_id"]] != reply:
                raise EvaluationError("Duplicate message returned a different response")
            seen[turn["message_id"]] = reply
            immediate = validate_trace(http(base, "/trace/" + rider))
            final_now = any(
                row["type"] == "reply" and row["output"] == reply["reply"]
                for row in immediate[len(trace) :]
            )
            if payload["message_id"] in {r["payload"]["message_id"] for r in result["requests"]}:
                final_now = any(
                    row["type"] == "reply" and row["output"] == reply["reply"] for row in immediate
                )
            request = {
                "payload": payload,
                "http_status": attempts[0]["status"],
                "http_attempts": attempts,
                "initial_reply": attempts[0]["reply"],
                "accepted_reply": reply["reply"],
                "initial_latency_seconds": round(elapsed, 4),
                "initial_final": final_now and attempts[0]["status"] == 200,
                "vendor_received_final": final_now,
            }
            deadline = time.monotonic() + wait
            trace = immediate
            while not final_now and time.monotonic() < deadline:
                time.sleep(0.5)
                trace = validate_trace(http(base, "/trace/" + rider))
                finals = [row for row in trace[len(immediate) :] if row["type"] == "reply"]
                if finals:
                    request["eventual_final_reply"] = finals[-1]["output"]
                    break
            request["time_to_eventual_seconds"] = round(time.monotonic() - start, 4)
            result["requests"].append(request)
        pending = validate_pending(http(base, "/ops/pending"))
        ops = [row for row in pending if row["rider_id"] == rider]
        approved = sum(
            (Decimal(str(row["amount"])) for row in ops if row["type"] == "approval"), Decimal(0)
        )
        escalated = any(row["type"] == "escalation" for row in ops)
        # A verified financial decision requires numeric evidence from public traces.
        # Step names are not standardized; unsupported implementations stay NOT VERIFIED.
        outcomes = []
        for row in trace:
            output = row["output"]
            if isinstance(output, dict) and isinstance(output.get("outcomes"), list):
                outcomes.extend(output["outcomes"])
        amounts = {
            Decimal(str(item["amount"]))
            for item in outcomes
            if item.get("kind") == "authorized" and "amount" in item
        }
        # Deduplicate replayed outcomes; actual provider ledger is checked separately.
        authorized = sum(amounts, Decimal(0))
        if outcomes or any(
            row["type"] == "decision"
            and row["name"] in {"clarification_requested", "input_policy_rejected"}
            for row in trace
        ):
            # Zero-payment cases still require trace evidence, not just silence.
            decision_paid = authorized
            result["decision"] = (
                "PASS"
                if verdict(scenario["expected"], approved, decision_paid, escalated)
                else "FAIL"
            )
            if not outcomes and any(
                option.get("payout", 0)
                for option in scenario["expected"].get("one_of", [scenario["expected"]])
            ):
                result["decision"] = "NOT VERIFIED"
        result["authorization"] = (
            result["decision"]
            if outcomes
            else ("NOT APPLICABLE" if result["decision"] == "PASS" else "NOT VERIFIED")
        )
        paid = None
        if provider and before_ledger is not None:
            deadline = time.monotonic() + wait
            while True:
                observed = ledger(provider, rider)
                fresh = observed
                paid = sum(
                    (Decimal(str(row["amount"])) for row in fresh if row["status"] == "processed"),
                    Decimal(0),
                )
                if paid >= authorized or time.monotonic() >= deadline:
                    break
                time.sleep(0.5)
            references = [row.get("reference") for row in fresh]
            duplicate = len(references) != len(set(references))
            uncertain = any(row["status"] not in {"processed", "failed"} for row in fresh)
            result["provider_payment"] = (
                "PASS"
                if not duplicate
                and not uncertain
                and verdict(scenario["expected"], approved, paid, escalated)
                else "FAIL"
            )
            result["provider_ledger"] = fresh
        mentions = scenario["expected"].get("reply_mentions", [])
        replies = " ".join(
            r["accepted_reply"] + " " + r.get("eventual_final_reply", "")
            for r in result["requests"]
        )
        result["reply_mentions"] = all(str(value) in replies for value in mentions)
        result["initial_final_delivery"] = (
            "PASS"
            if all(
                r["initial_final"] and r["initial_latency_seconds"] < 10 for r in result["requests"]
            )
            else "FAIL"
        )
        result["actual"] = {
            "authorized": str(authorized),
            "approval": str(approved),
            "provider_paid": str(paid) if paid is not None else None,
            "escalated": escalated,
        }
    except (EvaluationError, ValueError, TypeError, KeyError) as exc:
        result["errors"].append(str(exc))
    result["status"] = (
        "PASS"
        if not result["errors"]
        and all(
            (result[key] == "PASS" or (key == "authorization" and result[key] == "NOT APPLICABLE"))
            for key in ("decision", "authorization", "provider_payment", "initial_final_delivery")
        )
        and result.get("reply_mentions", False)
        else "FAIL"
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--payswift-url", default="http://localhost:8081")
    parser.add_argument(
        "--allow-nonlocal",
        action="store_true",
        help="Explicit consent for side effects on a nonlocal TEST deployment",
    )
    parser.add_argument(
        "--scenario", type=int, help="1-based scenario selector for fresh per-scenario deployments"
    )
    parser.add_argument("--wait", type=float, default=35)
    parser.add_argument("--output", type=Path, default=Path("evals/results.json"))
    args = parser.parse_args(argv)
    for url in (args.url, args.payswift_url):
        if url is None:
            continue
        parts = urllib.parse.urlparse(url)
        if parts.scheme not in {"http", "https"} or parts.username or parts.password:
            parser.error("Use an HTTP(S) URL without embedded credentials")
        if parts.hostname not in {"localhost", "127.0.0.1", "::1"} and not args.allow_nonlocal:
            parser.error(
                "Nonlocal tests require --allow-nonlocal; never use production/shared data"
            )
    print("WARNING: financial side effects; use disposable API, database and PaySwift state.")
    scenarios = json.loads(
        (Path(__file__).resolve().parents[1] / "data/conversations.json").read_text()
    )
    if args.scenario is not None and not 1 <= args.scenario <= len(scenarios):
        parser.error("Invalid scenario number")
    results = []
    evaluated_riders = set()
    for index, scenario in enumerate(scenarios, 1):
        if args.scenario is not None and args.scenario != index:
            continue
        value = evaluate(
            args.url,
            scenario,
            args.payswift_url,
            args.wait,
            scenario["rider_id"] in evaluated_riders,
        )
        evaluated_riders.add(scenario["rider_id"])
        value["scenario_id"] = index
        results.append(value)
        print(
            f"{index:02} {scenario['rider_id']} {value['status']}: "
            f"decision={value['decision']} authorization={value['authorization']} "
            f"provider={value['provider_payment']} initial={value['initial_final_delivery']}"
        )
        for error in value["errors"]:
            print("  " + error)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"results": results}, indent=2, ensure_ascii=False) + "\n")
    return 0 if results and all(row["status"] == "PASS" for row in results) else 1


if __name__ == "__main__":
    sys.exit(main())
