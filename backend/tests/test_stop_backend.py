"""Backend shutdown is scoped to this checkout and tested with temporary processes."""

import os
import signal
import subprocess
import sys
import time

from app.scripts import stop_backend as module


def test_selection_excludes_workers_other_checkouts_and_mixed_make_targets(tmp_path):
    def process(pid, parent, args, cwd):
        return module.Process(pid, parent, str(pid), "S", tuple(args), cwd)

    rows = [
        process(101, 1, ["make", "backend"], tmp_path),
        process(102, 101, ["uv", "run", "uvicorn", "app.main:app"], tmp_path / "backend"),
        process(103, 102, ["python", "child"], tmp_path / "backend"),
        process(201, 1, ["python", "-m", "app.workers.main"], tmp_path / "backend"),
        process(202, 1, ["node", "next"], tmp_path / "frontend"),
        process(203, 1, ["uvicorn", "app.main:app"], tmp_path / "another"),
        process(301, 1, ["make", "backend", "frontend"], tmp_path),
        process(302, 301, ["uvicorn", "app.main:app"], tmp_path / "backend"),
        process(303, 301, ["node", "next"], tmp_path / "frontend"),
    ]
    selected = module.targets({p.pid: p for p in rows}, tmp_path)
    assert set(selected) == {101, 102, 103, 302}
    assert list(selected).index(101) < list(selected).index(102) < list(selected).index(103)


def test_dry_run_does_not_signal(monkeypatch, tmp_path):
    process = module.Process(101, 1, "101", "S", ("uvicorn", "app.main:app"), tmp_path / "backend")
    monkeypatch.setattr(module, "processes", lambda: {101: process})
    monkeypatch.setattr(
        module.os, "kill", lambda *args: (_ for _ in ()).throw(AssertionError("Unexpected signal"))
    )
    assert module.stop(tmp_path, dry_run=True) == 0


def test_stuck_parent_and_child_are_stopped_but_worker_survives(tmp_path):
    backend = tmp_path / "backend"
    backend.mkdir()
    script = backend / "uvicorn"
    child_ready = backend / "child-ready"
    script.write_text(
        "import signal,subprocess,sys,time\n"
        "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
        "child=subprocess.Popen([sys.executable,'-c',"
        '"import signal,time; from pathlib import Path; '
        "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        "Path('child-ready').touch(); time.sleep(30)\"])\n"
        "time.sleep(30)\n"
    )
    api = subprocess.Popen([sys.executable, str(script), "app.main:app"], cwd=backend)
    worker = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], cwd=backend)
    captured = {}
    try:
        deadline = time.monotonic() + 3
        while not child_ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert child_ready.exists()
        captured = module.targets(module.processes(), tmp_path)
        assert api.pid in captured and worker.pid not in captured
        assert len(captured) == 2
        assert module.stop(tmp_path, timeout=0.1) == 0
        api.wait(timeout=2)
        assert not any(module.still_running(p) for p in captured.values())
        assert worker.poll() is None
        assert module.stop(tmp_path, timeout=0) == 0
    finally:
        for process in captured.values():
            module.send(process, signal.SIGKILL)
        for process in (api, worker):
            if process.poll() is None:
                os.kill(process.pid, signal.SIGKILL)
            process.wait(timeout=2)
