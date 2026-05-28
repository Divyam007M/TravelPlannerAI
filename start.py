"""
WanderAI - Unified Dev Launcher
================================
COMBINED mode (default):
    python start.py
    - Builds the React frontend once (skips if already built, use --rebuild to force)
    - Starts ONE FastAPI server on :8000 that serves both the API and the React UI
    - Opens your browser -> http://localhost:8000

DEV mode (Vite hot-reload):
    python start.py --dev
    - Starts FastAPI on :8000  (API only)
    - Starts Vite on :5173     (UI with HMR for instant code changes)
    - Opens browser -> http://localhost:5173

PUBLIC URL:
    python start.py --tunnel        (combined + public URL)
    python start.py --dev --tunnel  (dev + public URL)

Press Ctrl+C once to stop everything.
"""

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

# ── ANSI colours (pure ASCII escape sequences) ────────────────────
R  = "\033[0m"
B  = "\033[1m"
CY = "\033[96m"
YL = "\033[93m"
GR = "\033[92m"
RD = "\033[91m"
MG = "\033[95m"
DM = "\033[2m"

ROOT     = Path(__file__).parent.resolve()
BACKEND  = ROOT / "backend"
FRONTEND = ROOT / "frontend"
DIST     = FRONTEND / "dist"
PYTHON   = sys.executable
NPM      = "npm.cmd" if sys.platform == "win32" else "npm"

processes: list[subprocess.Popen] = []


# ── Utilities ─────────────────────────────────────────────────────
def log(tag: str, colour: str, msg: str):
    print(f"{colour}{B}[{tag}]{R} {msg}", flush=True)


def stream(proc: subprocess.Popen, tag: str, colour: str, filter_fn=None):
    """Forward subprocess output lines with a coloured tag prefix."""
    def _read(pipe):
        try:
            for raw in iter(pipe.readline, b""):
                line = raw.decode("utf-8", errors="replace").rstrip()
                if not line:
                    continue
                if filter_fn:
                    filter_fn(line)
                else:
                    print(f"{colour}{B}[{tag}]{R} {DM}{line}{R}", flush=True)
        except Exception:
            pass
    for pipe in (proc.stdout, proc.stderr):
        threading.Thread(target=_read, args=(pipe,), daemon=True).start()


def stop_all(signum=None, frame=None):
    print(f"\n{RD}{B}Shutting down...{R}")
    for p in processes:
        try:
            p.terminate()
        except Exception:
            pass
    time.sleep(1)
    for p in processes:
        try:
            p.kill()
        except Exception:
            pass
    print(f"{DM}All stopped. Goodbye!{R}\n")
    sys.exit(0)


def check_env():
    if not (BACKEND / ".env").exists():
        print(f"\n{RD}{B}[ERROR]{R} backend/.env not found!")
        print(f"{YL}  Create it:{R}")
        print(f"    copy backend\\.env.example backend\\.env")
        print(f"    (then fill in your GROQ_API_KEY)\n")
        sys.exit(1)


def get_local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return ""


def print_banner(mode: str):
    if sys.platform == "win32":
        os.system("color")
    bar = "=" * 56
    print(f"\n{CY}{bar}{R}")
    print(f"{CY}{B}  WanderAI Travel Planner  |  {mode}{R}")
    print(f"{CY}{bar}{R}\n")


def print_urls(app_url: str, api_url: str, network_url: str = "", pub_url: str = ""):
    bar = "-" * 56
    print(f"\n{GR}{bar}{R}")
    print(f"{GR}{B}  >> App is running!{R}")
    print(f"  {B}App    :{R} {app_url}")
    if network_url:
        print(f"  {B}Network:{R} {network_url}  {DM}(phones/tablets on same WiFi){R}")
    if pub_url:
        print(f"  {MG}{B}Public :{R} {pub_url}  {DM}(shareable link!){R}")
    print(f"  {B}Health :{R} {api_url}/api/health")
    print(f"{GR}{bar}{R}")
    print(f"{DM}  Ctrl+C to stop{R}\n")


# ── Frontend build ────────────────────────────────────────────────
def build_frontend(force: bool = False):
    if DIST.is_dir() and not force:
        log("build", GR, f"Frontend already built. Skipping. (--rebuild to force)")
        return True

    log("build", YL, "Building React frontend...")
    result = subprocess.run(
        [NPM, "run", "build"],
        cwd=str(FRONTEND),
        capture_output=False,
    )
    if result.returncode != 0:
        log("build", RD, "Frontend build FAILED. Check errors above.")
        return False
    log("build", GR, "Frontend build complete.")
    return True


# ── Tunnel helpers ────────────────────────────────────────────────
def try_cloudflared(url: str) -> str:
    if not shutil.which("cloudflared"):
        return ""
    log("tunnel", MG, "Starting cloudflared quick tunnel...")
    try:
        proc = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", url],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        processes.append(proc)
        for _ in range(50):
            line = proc.stdout.readline().decode("utf-8", errors="replace").strip()
            for word in line.split():
                if word.startswith("https://") and "cloudflare" in word:
                    log("tunnel", MG, f"Public URL -> {word}")
                    return word
            time.sleep(0.3)
    except Exception as e:
        log("tunnel", RD, f"cloudflared error: {e}")
    return ""


def try_localtunnel(port: int) -> str:
    log("tunnel", MG, "Trying localtunnel...")
    try:
        proc = subprocess.Popen(
            [NPM, "exec", "--yes", "--", "localtunnel", "--port", str(port)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        processes.append(proc)
        for _ in range(50):
            line = proc.stdout.readline().decode("utf-8", errors="replace").strip()
            if "your url is" in line.lower():
                for word in line.split():
                    if word.startswith("https://"):
                        log("tunnel", MG, f"Public URL -> {word}")
                        return word
            if proc.poll() is not None:
                break
            time.sleep(0.3)
    except Exception as e:
        log("tunnel", RD, f"localtunnel error: {e}")
    return ""


def open_tunnel(app_url: str, port: int) -> str:
    pub = try_cloudflared(app_url)
    if not pub:
        pub = try_localtunnel(port)
    if not pub:
        log("tunnel", YL,
            "No tunnel tool found. Install cloudflared:\n"
            "         winget install Cloudflare.cloudflared")
    return pub


# ── Combined mode: one server, one URL ───────────────────────────
def run_combined(args):
    """Build frontend once, run ONE FastAPI server that serves everything."""
    print_banner("Combined (single server on :8000)")
    check_env()

    if not build_frontend(force=args.rebuild):
        sys.exit(1)

    log("server", CY, "Starting WanderAI on http://localhost:8000 ...")
    server = subprocess.Popen(
        [PYTHON, "main.py"],
        cwd=str(BACKEND),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    processes.append(server)

    def _filter(line: str):
        low = line.lower()
        if any(k in low for k in ("error", "exception", "traceback", "critical", "warning")):
            log("server", RD, line)
        elif "uvicorn running" in low or "application startup" in low:
            log("server", GR, line)

    stream(server, "server", CY, filter_fn=_filter)

    # Poll until /api/health responds
    log("server", CY, "Waiting for server to be ready...")
    for _ in range(20):
        time.sleep(0.5)
        if server.poll() is not None:
            log("server", RD, f"Server crashed (exit {server.returncode}). Check backend/.env")
            sys.exit(1)
        try:
            import urllib.request
            urllib.request.urlopen("http://localhost:8000/api/health", timeout=1)
            break
        except Exception:
            pass
    else:
        log("server", YL, "Server is taking longer than usual — continuing anyway...")

    log("server", GR, "Server is up.")

    pub_url = ""
    if args.tunnel:
        pub_url = open_tunnel("http://localhost:8000", 8000)

    local_ip = get_local_ip()
    network_url = f"http://{local_ip}:8000" if local_ip else ""
    print_urls("http://localhost:8000", "http://localhost:8000", network_url, pub_url)

    if not args.no_browser:
        time.sleep(0.5)
        webbrowser.open(pub_url or "http://localhost:8000")

    try:
        while True:
            if server.poll() is not None:
                log("server", RD, f"Server exited unexpectedly (code {server.returncode}).")
                stop_all()
            time.sleep(1)
    except KeyboardInterrupt:
        stop_all()


# ── Dev mode: Vite HMR + FastAPI ─────────────────────────────────
def run_dev(args):
    """Dev mode: Vite (HMR on :5173) + FastAPI (:8000) separately."""
    print_banner("Dev (Vite :5173  |  FastAPI :8000)")
    check_env()

    log("backend", CY, "Starting FastAPI on http://localhost:8000 ...")
    backend = subprocess.Popen(
        [PYTHON, "main.py"],
        cwd=str(BACKEND),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    processes.append(backend)

    def _be_filter(line: str):
        low = line.lower()
        if any(k in low for k in ("error", "exception", "traceback", "critical")):
            log("backend", RD, line)
        elif "uvicorn running" in low or "startup complete" in low:
            log("backend", GR, line)

    stream(backend, "backend", CY, filter_fn=_be_filter)
    time.sleep(2)

    if backend.poll() is not None:
        log("backend", RD, "Backend crashed. Is GROQ_API_KEY set in backend/.env?")
        sys.exit(1)
    log("backend", GR, "Backend up.")

    log("frontend", YL, "Starting Vite on http://localhost:5173 (--host enabled) ...")
    vite_ready = threading.Event()
    frontend = subprocess.Popen(
        [NPM, "run", "dev", "--", "--host"],
        cwd=str(FRONTEND),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    processes.append(frontend)

    def _fe_filter(line: str):
        # Vite outputs arrow chars — decode to ASCII friendly form
        safe = line.encode("ascii", errors="replace").decode("ascii")
        if any(k in safe for k in ("ready", "Local", "Network", ">")):
            log("frontend", YL, safe)
            if "ready" in safe or "localhost" in safe:
                vite_ready.set()

    stream(frontend, "frontend", YL, filter_fn=_fe_filter)
    vite_ready.wait(timeout=20)

    if frontend.poll() is not None:
        log("frontend", RD, "Frontend failed to start.")
        stop_all()

    pub_url = ""
    if args.tunnel:
        pub_url = open_tunnel("http://localhost:5173", 5173)

    local_ip = get_local_ip()
    network_url = f"http://{local_ip}:5173" if local_ip else ""
    print_urls("http://localhost:5173", "http://localhost:8000", network_url, pub_url)

    if not args.no_browser:
        time.sleep(0.5)
        webbrowser.open(pub_url or "http://localhost:5173")

    try:
        while True:
            if backend.poll() is not None:
                log("backend", RD, f"Backend exited (code {backend.returncode}).")
                stop_all()
            if frontend.poll() is not None:
                log("frontend", RD, f"Frontend exited (code {frontend.returncode}).")
                stop_all()
            time.sleep(1)
    except KeyboardInterrupt:
        stop_all()


# ── Entry point ───────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="WanderAI unified launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python start.py               # Combined: build + single server (recommended)
  python start.py --rebuild     # Force rebuild frontend, then start combined
  python start.py --dev         # Dev: Vite HMR + FastAPI separately
  python start.py --tunnel      # Combined + public HTTPS URL
  python start.py --dev --tunnel  # Dev + public URL
        """
    )
    parser.add_argument("--dev",        action="store_true", help="Dev mode: Vite HMR + FastAPI")
    parser.add_argument("--rebuild",    action="store_true", help="Force rebuild the React frontend")
    parser.add_argument("--tunnel",     action="store_true", help="Create a public HTTPS URL")
    parser.add_argument("--no-browser", action="store_true", help="Don't auto-open browser")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, stop_all)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, stop_all)

    if args.dev:
        run_dev(args)
    else:
        run_combined(args)


if __name__ == "__main__":
    main()
