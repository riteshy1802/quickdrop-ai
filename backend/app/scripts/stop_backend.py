"""Stop this checkout's local Uvicorn process trees on Linux."""

import argparse
import os
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Process:
    pid: int
    parent: int
    started: str
    state: str
    args: tuple[str, ...]
    cwd: Path | None


def processes():
    result = {}
    for directory in Path("/proc").iterdir():
        if not directory.name.isdigit():
            continue
        try:
            if directory.stat().st_uid != os.getuid():
                continue
            fields = (directory / "stat").read_text().rpartition(")")[2].split()
            args = tuple(
                part.decode(errors="replace")
                for part in (directory / "cmdline").read_bytes().split(b"\0")
                if part
            )
            try:
                cwd = (directory / "cwd").resolve(strict=True)
            except OSError:
                cwd = None
            pid = int(directory.name)
            result[pid] = Process(pid, int(fields[1]), fields[19], fields[0], args, cwd)
        except (OSError, ValueError, IndexError):
            continue  # A process can exit while /proc is being read.
    return result


def targets(snapshot, root):
    protected = {os.getpid()}
    cursor = snapshot.get(os.getpid())
    while cursor and cursor.parent not in protected:
        protected.add(cursor.parent)
        cursor = snapshot.get(cursor.parent)
    selected = set()
    for pid, process in snapshot.items():
        if not process.args or pid in protected:
            continue
        is_launcher = (
            Path(process.args[0]).name in {"make", "gmake"}
            and process.cwd == root
            and any(arg in {"backend", "backend-dev"} for arg in process.args[1:])
            and all(
                arg in {"backend", "backend-dev"} or arg.startswith("-") or "=" in arg
                for arg in process.args[1:]
            )
        )
        is_api = (
            process.cwd == root / "backend"
            and "app.main:app" in process.args
            and any(Path(arg).name == "uvicorn" for arg in process.args[:4])
        )
        if is_launcher or is_api:
            selected.add(pid)
    while True:
        children = {
            pid for pid, p in snapshot.items() if p.parent in selected and pid not in protected
        }
        if children <= selected:
            break
        selected |= children

    def depth(pid):
        ancestors = set()
        parent = snapshot[pid].parent
        while parent in selected and parent not in ancestors:
            ancestors.add(parent)
            parent = snapshot[parent].parent
        return len(ancestors)

    return {pid: snapshot[pid] for pid in sorted(selected, key=depth) if pid not in protected}


def still_running(process):
    try:
        fields = (Path("/proc") / str(process.pid) / "stat").read_text().rpartition(")")[2].split()
        return fields[19] == process.started and fields[0] != "Z"
    except (OSError, IndexError):
        return False


def send(process, sig):
    # Start time fences PID reuse between discovery and signal delivery.
    if still_running(process):
        try:
            os.kill(process.pid, sig)
        except ProcessLookupError:
            pass


def stop(root=ROOT, timeout=8, dry_run=False):
    selected = targets(processes(), root)
    if not selected:
        print("No local backend processes found for this checkout.")
        return 0
    print(
        ("Would stop" if dry_run else "Stopping")
        + " backend PIDs: "
        + ", ".join(map(str, selected))
    )
    if dry_run:
        return 0
    # Signal launchers/reload supervisors before waiting, so children cannot restart.
    for process in selected.values():
        send(process, signal.SIGTERM)
        if process.state in {"T", "t"}:
            send(process, signal.SIGCONT)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and any(still_running(p) for p in selected.values()):
        time.sleep(0.1)
    remaining = [p for p in selected.values() if still_running(p)]
    for process in remaining:
        send(process, signal.SIGKILL)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline and any(still_running(p) for p in remaining):
        time.sleep(0.05)
    if any(still_running(p) for p in remaining):
        print("Some backend processes could not be stopped.", file=sys.stderr)
        return 1
    print("Backend and its child processes stopped.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="List matching PIDs without stopping them"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=8,
        help="Seconds before forcing remaining processes to stop",
    )
    args = parser.parse_args()
    if not sys.platform.startswith("linux"):
        parser.error("This command requires Linux /proc.")
    if not 0 <= args.timeout <= 300:
        parser.error("--timeout must be between 0 and 300 seconds")
    raise SystemExit(stop(timeout=args.timeout, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
