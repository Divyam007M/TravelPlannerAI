"""
WanderAI — Single-command dev launcher
Run: python start.py
Starts both backend (FastAPI on :8000) and frontend (Vite on :5173) together.
Press Ctrl+C once to stop both.
"""

import subprocess
import threading
import sys
import os
import signal
import time

# ── ANSI colour codes ─────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
YELLOW = "\033[93m"
RED    = "\033[91m"
GREEN  = "\033[92m"
DIM    = "\033[2m"

ROOT    = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.join(ROOT, "backend")
FRONTEND = os.path.join(ROOT, "frontend")

processes: list[subprocess.Popen] = []


def prefix_stream(stream, label: str, colour: str):
    """Read lines from a subprocess stream and print them with a coloured prefix."""
    try:
        for raw in iter(stream.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip()
            if line:
                print(f"{colour}{BOLD}[{label}]{RESET} {line}", flush=True)
    except Exception:
        pass


def stream_process(proc: subprocess.Popen, label: str, colour: str):
    """Attach prefix_stream to both stdout and stderr of a process."""
    t_out = threading.Thread(target=prefix_stream, args=(proc.stdout, label, colour), daemon=True)
    t_err = threading.Thread(target=prefix_stream, args=(proc.stderr, label, colour), daemon=True)
    t_out.start()
    t_err.start()


def stop_all(signum=None, frame=None):
    print(f"\n{RED}{BOLD}Shutting down both servers...{RESET}")
    for p in processes:
        try:
            p.terminate()
        except Exception:
            pass
    # Give them a moment to exit gracefully
    time.sleep(1)
    for p in processes:
        try:
            p.kill()
        except Exception:
            pass
    print(f"{DIM}All stopped. Goodbye!{RESET}")
    sys.exit(0)


def check_env():
    env_path = os.path.join(BACKEND, ".env")
    if not os.path.exists(env_path):
        print(f"{RED}{BOLD}[ERROR]{RESET} backend/.env not found!")
        print(f"{YELLOW}  Copy the template and add your key:{RESET}")
        print(f"  cd backend")
        print(f"  copy .env.example .env   (then edit with your GROQ_API_KEY)")
        sys.exit(1)


def main():
    # Enable ANSI on Windows
    if sys.platform == "win32":
        os.system("color")

    print(f"\n{BOLD}{CYAN}{'='*52}{RESET}")
    print(f"{BOLD}{CYAN}  ✈️  WanderAI Dev Launcher{RESET}")
    print(f"{BOLD}{CYAN}{'='*52}{RESET}")
    print(f"{DIM}  Backend  → http://localhost:8000{RESET}")
    print(f"{DIM}  Frontend → http://localhost:5173{RESET}")
    print(f"{DIM}  Press Ctrl+C to stop both servers{RESET}")
    print(f"{CYAN}{'='*52}{RESET}\n")

    check_env()

    # ── Detect python executable ──────────────────────────────────
    python = sys.executable  # same python that's running this script

    # ── Start FastAPI backend ─────────────────────────────────────
    print(f"{CYAN}{BOLD}[backend]{RESET}  Starting FastAPI on :8000 ...")
    backend_proc = subprocess.Popen(
        [python, "main.py"],
        cwd=BACKEND,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    processes.append(backend_proc)
    stream_process(backend_proc, "backend", CYAN)

    # Brief pause so backend starts before frontend tries to proxy it
    time.sleep(2)

    # ── Start Vite frontend ───────────────────────────────────────
    print(f"{YELLOW}{BOLD}[frontend]{RESET} Starting Vite on :5173 ...")
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    frontend_proc = subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=FRONTEND,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    processes.append(frontend_proc)
    stream_process(frontend_proc, "frontend", YELLOW)

    # ── Register Ctrl+C handler ───────────────────────────────────
    signal.signal(signal.SIGINT, stop_all)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, stop_all)

    # ── Wait — exit if either process dies unexpectedly ──────────
    try:
        while True:
            # Check if backend died
            if backend_proc.poll() is not None:
                print(f"\n{RED}{BOLD}[backend] process exited unexpectedly (code {backend_proc.returncode}).{RESET}")
                stop_all()

            # Check if frontend died
            if frontend_proc.poll() is not None:
                print(f"\n{RED}{BOLD}[frontend] process exited unexpectedly (code {frontend_proc.returncode}).{RESET}")
                stop_all()

            time.sleep(1)
    except KeyboardInterrupt:
        stop_all()


if __name__ == "__main__":
    main()
