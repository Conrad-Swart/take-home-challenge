"""One-command run.

Creates a virtual environment on first use, installs dependencies, opens the
browser, and starts the server. Works on Windows, macOS, and Linux.

Usage: python run.py
"""
import os
import socket
import subprocess
import sys
import threading
import time
import venv
import webbrowser
from pathlib import Path


HERE = Path(__file__).parent
VENV = HERE / ".venv"
MARKER = VENV / ".deps-installed"
REQS = HERE / "requirements.txt"
PORT = 8000
HOST = "127.0.0.1"

if sys.platform == "win32":
    VPY = VENV / "Scripts" / "python.exe"
else:
    VPY = VENV / "bin" / "python"


def ensure_venv():
    if VENV.exists():
        return
    print("Creating virtual environment...")
    venv.create(VENV, with_pip=True)


def ensure_deps():
    if MARKER.exists() and MARKER.stat().st_mtime > REQS.stat().st_mtime:
        return
    print("Installing dependencies (first run takes 2-3 minutes)...")
    subprocess.run([str(VPY), "-m", "pip", "install", "--upgrade", "pip", "-q"], check=True)
    subprocess.run([str(VPY), "-m", "pip", "install", "-r", str(REQS), "-q"], check=True)
    MARKER.touch()


def port_in_use(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        try:
            s.connect((HOST, port))
            return True
        except OSError:
            return False


def _win_kill_stale(port: int, excluded_pids: set) -> list:
    """Find and kill Python processes holding `port` on Windows. Returns a
    list of killed PIDs."""
    excluded_str = ",".join(str(p) for p in excluded_pids)
    ps = (
        f"$mine=@({excluded_str}); "
        f"$conns = Get-NetTCPConnection -LocalPort {port} "
        f"-State Listen,Established,SynSent,SynReceived -ErrorAction SilentlyContinue; "
        "$pids = $conns.OwningProcess | Sort-Object -Unique; "
        "foreach ($p in $pids) { "
        "  if ($p -eq 0 -or $mine -contains $p) { continue } "
        "  $proc = Get-Process -Id $p -ErrorAction SilentlyContinue "
        "  if (-not $proc) { continue } "
        "  if ($proc.ProcessName -match '^(python|pythonw|uvicorn|node)$') { "
        "    Stop-Process -Id $p -Force -ErrorAction SilentlyContinue; "
        "    Write-Output $p "
        "  } "
        "}"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=8,
        )
        return [line.strip() for line in r.stdout.splitlines() if line.strip()]
    except Exception:
        return []


def _posix_kill_stale(port: int, excluded_pids: set) -> list:
    """Find and kill Python processes holding `port` on POSIX. Returns a
    list of killed PIDs."""
    killed = []
    try:
        out = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
            capture_output=True, text=True, timeout=5,
        )
    except FileNotFoundError:
        return killed
    except Exception:
        return killed

    for pid_str in out.stdout.split():
        try:
            pid = int(pid_str)
        except ValueError:
            continue
        if pid in excluded_pids:
            continue
        try:
            with open(f"/proc/{pid}/comm") as f:
                name = f.read().strip()
        except (FileNotFoundError, PermissionError):
            name = ""
        if name.startswith("python") or name.startswith("uvicorn"):
            try:
                os.kill(pid, 15)
                killed.append(str(pid))
            except OSError:
                pass
    return killed


def clear_stale_server(port: int):
    """If a previous Clever Dictate instance is still holding the port,
    kill it. Only kills python/uvicorn processes so we never touch an
    unrelated app that happens to be on the same port. Retries a few
    times to survive a slow process shutdown."""
    if not port_in_use(port):
        return

    my_pid = os.getpid()
    parent_pid = os.getppid() if hasattr(os, "getppid") else 0
    excluded = {my_pid, parent_pid}

    print(f"Port {port} is busy. Attempting to free it...")

    for attempt in range(3):
        if sys.platform == "win32":
            killed = _win_kill_stale(port, excluded)
        else:
            killed = _posix_kill_stale(port, excluded)

        if killed:
            print(f"  killed PID(s): {', '.join(killed)}")

        # Give Windows a moment to release the socket.
        time.sleep(1.0)

        if not port_in_use(port):
            print(f"Port {port} is free.")
            return

    print(
        f"Port {port} is still in use after cleanup. Something non-Python "
        f"may be holding it. Run this to see what:\n"
        f"  Get-NetTCPConnection -LocalPort {port}\n"
        f"Then close that program, or edit run.py to use a different port."
    )
    sys.exit(1)


def open_browser_soon():
    time.sleep(3)
    try:
        webbrowser.open(f"http://localhost:{PORT}")
    except Exception:
        pass


def main():
    os.chdir(HERE)
    (HERE / "data").mkdir(exist_ok=True)
    ensure_venv()
    ensure_deps()

    # Re-exec inside the venv so uvicorn.run() runs in-process. This is
    # what makes Ctrl+C reliably stop the server on Windows.
    if Path(sys.executable).resolve() != VPY.resolve():
        os.execv(str(VPY), [str(VPY), str(Path(__file__).resolve())])

    # We are now the venv Python. Clear any leftover instance BEFORE we
    # bind, so run.py is self-healing across crashes and Ctrl+C exits
    # that did not fully release the socket.
    clear_stale_server(PORT)

    threading.Thread(target=open_browser_soon, daemon=True).start()

    print()
    print(f"Clever Dictate running at http://localhost:{PORT}")
    print("Press Ctrl+C to stop.")
    print()

    import uvicorn
    uvicorn.run("app:app", host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
