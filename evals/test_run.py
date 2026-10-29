"""Black-box evaluator proofs: no application dependencies or imports."""

import contextlib
import importlib.util
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

spec = importlib.util.spec_from_file_location("portable", Path(__file__).with_name("run.py"))
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


class EvaluatorTests(unittest.TestCase):
    def test_incomplete_http_server_cannot_pass(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = run.evaluate(
                f"http://127.0.0.1:{server.server_port}",
                {
                    "rider_id": "R003",
                    "scenario": "incomplete",
                    "expected": {"payout": 25},
                    "turns": [],
                },
                wait=0,
            )
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("Trace must be a list", result["errors"][0])
            self.assertEqual(result["provider_payment"], "NOT VERIFIED")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_valid_http_only_payment_and_duplicate(self):
        state = {"posted": False, "posts": 0}
        reply = "Verified 34; payment request created, not yet confirmed"
        trace = [
            {
                "at": "2026-09-23T10:00:00+05:30",
                "type": "decision",
                "name": "financial_result",
                "input": None,
                "output": {"outcomes": [{"kind": "authorized", "amount": "34"}]},
            },
            {
                "at": "2026-09-23T10:00:01+05:30",
                "type": "reply",
                "name": "answer",
                "input": None,
                "output": reply,
            },
        ]

        class Handler(BaseHTTPRequestHandler):
            def send(self, value):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(value).encode())

            def do_GET(self):
                if self.path.startswith("/trace/"):
                    self.send(trace if state["posted"] else [])
                elif self.path.startswith("/v1/payouts"):
                    self.send(
                        {
                            "data": [
                                {
                                    "payout_id": "pout_test",
                                    "rider_id": "R007",
                                    "amount": 34,
                                    "status": "processed",
                                    "reference": "one",
                                }
                            ]
                            if state["posted"]
                            else [],
                            "count": int(state["posted"]),
                        }
                    )
                else:
                    self.send([])

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                assert payload["received_at"] == "2026-09-23T09:45:00+05:30"
                state["posted"] = True
                state["posts"] += 1
                self.send({"reply": reply})

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        turn = {
            "from": "rider",
            "message_id": "original",
            "text": "missing surge",
            "received_at": "2026-09-23T09:45:00+05:30",
        }
        try:
            value = run.evaluate(
                base,
                {
                    "rider_id": "R007",
                    "scenario": "duplicate",
                    "expected": {"payout": 34, "approval": None, "escalation": "no"},
                    "turns": [turn, turn],
                },
                provider=base,
                wait=0,
            )
            self.assertEqual(value["status"], "PASS", value)
            self.assertEqual(state["posts"], 2)
            self.assertEqual(len(value["provider_ledger"]), 1)
            # Equal amounts are separate authorizations, not a set: never hide a duplicate.
            state["posted"] = False
            trace[0]["output"]["outcomes"].append({"kind": "authorized", "amount": "34"})
            duplicated = run.evaluate(
                base,
                {
                    "rider_id": "R007",
                    "scenario": "duplicate authorization",
                    "expected": {"payout": 34, "approval": None, "escalation": "no"},
                    "turns": [turn],
                },
                provider=base,
                wait=0,
            )
            self.assertEqual(duplicated["authorization"], "FAIL")
            self.assertEqual(duplicated["provider_payment"], "PASS")
            self.assertEqual(duplicated["status"], "FAIL")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_retry_keeps_original_payload_and_failure_visible(self):
        from unittest.mock import patch

        payload = {"message_id": "same", "text": "same"}
        with (
            patch.object(
                run, "http", side_effect=[run.EvaluationError("retry", 503), {"reply": "final"}]
            ) as http,
            patch.object(run.time, "sleep"),
        ):
            reply, attempts = run.submit("http://localhost", payload)
        self.assertEqual(reply, {"reply": "final"})
        self.assertEqual([attempt["status"] for attempt in attempts], [503, 200])
        self.assertEqual(http.call_args_list[0], http.call_args_list[1])

    def test_nonlocal_requires_explicit_consent(self):
        with contextlib.redirect_stderr(__import__("io").StringIO()), self.assertRaises(SystemExit):
            run.main(["https://example.com"])

    def test_one_of_and_optional_escalation(self):
        expected = {
            "one_of": [{"payout": 15, "approval": 10}, {"payout": 10, "approval": 15}],
            "escalation": "optional",
        }
        self.assertTrue(run.verdict(expected, 10, 15, True))
        self.assertTrue(run.verdict(expected, 15, 10, False))
        self.assertFalse(run.verdict(expected, 10, 25, False))

    def test_exact_trace_contract(self):
        with self.assertRaises(run.EvaluationError):
            run.validate_trace([{"type": "decision"}])
        with self.assertRaises(run.EvaluationError):
            run.validate_pending([{"id": "x"}])

    def test_original_scenarios_intact(self):
        scenarios = json.loads(
            (Path(__file__).resolve().parents[1] / "data/conversations.json").read_text()
        )
        self.assertEqual(len(scenarios), 24)
        turns = [t for s in scenarios for t in s["turns"] if t["from"] == "rider"]
        self.assertEqual(len(turns), 30)
        duplicate = scenarios[4]["turns"]
        self.assertEqual(duplicate[0]["message_id"], duplicate[1]["message_id"])


if __name__ == "__main__":
    unittest.main()
