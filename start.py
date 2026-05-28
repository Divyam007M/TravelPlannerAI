"""
WanderAI — Dev Launcher
========================
Run:  python start.py
Run with public URL:  python start.py --tunnel

What it does:
  • Starts FastAPI backend silently in the background (:8000)
  • Starts Vite frontend exposed on your local network (:5173)
  • (Optional) Creates a public HTTPS URL via cloudflared or localtunnel
  • Opens your browser automatically
  • One Ctrl+C kills everything cleanly

Press Ctrl+C to stop all servers.
"""

import subprocess
import threading
import sys
import os
import signal
import time
import argparse
import shutil
import webbrowser

# ── ANSI colours ──────────────────────────────────────────────────
R  = "\033[0m"
B  = "\033[1m"
CY = "\033[96m"
YL = "\033[93m"
GR = "\033[92m"
RD = "\033[91m"
MG = "\033[95m"
DM = "\033[2m"

ROOT     = os.path.dirname(os.path.abspath(__file__))
BACKEND  = os.path.join(ROOT, "backend")
FRONTEND = os.path.join(ROOT, "frontend")
NPM      = "npm.cmd" if sys.platform == "win32" else "npm"
PYTHON   = sys.executable

processes: list[subprocess.Popen] = []
tunnel_url: str = ""


# ── Helpers ───────────────────────────────────────────────────────
def log(tag: str, colour: str, msg: str):
    print(f"{colour}{B}[{tag}]{R} {msg}", flush=True)


def prefix_stream(stream, tag: str, colour: str, capture_fn=None):
    """Forward subprocess output lines with a coloured tag prefix."""
    try:
        for raw in iter(stream.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip()
            if not line:
                continue
            if capture_fn:
                capture_fn(line)
            print(f"{colour}{B}[{tag}]{R} {DM}{line}{R}", flush=True)
    except Exception:
        pass


def attach_streams(proc: subprocess.Popen, tag: str, colour: str, capture_fn=None):
    for s in (proc.stdout, proc.stderr):
        threading.Thread(
            target=prefix_stream,
            args=(s, tag, colour, capture_fn),
            daemon=True,
        ).start()


def stop_all(signum=None, frame=None):
    print(f"\n{RD}{B}Stopping all servers...{R}")
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
    print(f"{DM}All stopped. Goodbye! ✈️{R}\n")
    sys.exit(0)


def check_env():
    env_path = os.path.join(BACKEND, ".env")
    if not os.path.exists(env_path):
        print(f"\n{RD}{B}[ERROR]{R} backend/.env not found!")
        print(f"{YL}  Create it from the template:{R}")
        print(f"    copy backend\\.env.example backend\\.env")
        print(f"    (then add your GROQ_API_KEY)\n")
        sys.exit(1)


def print_banner(tunnel_mode: bool):
    if sys.platform == "win32":
        os.system("color")  # enable ANSI on Windows
    print(f"\n{CY}{'═'*54}{R}")
    print(f"{CY}{B}  ✈️  WanderAI Dev Launcher{R}")
    if tunnel_mode:
        print(f"{MG}{B}  🌐 Public URL mode enabled{R}")
    print(f"{CY}{'═'*54}{R}")


def print_urls(local_ip: str = "", pub_url: str = ""):
    print(f"\n{GR}{'─'*54}{R}")
    print(f"{GR}{B}  App is running!{R}")
    print(f"  {B}Local:  {R}   http://localhost:5173")
    if local_ip:
        print(f"  {B}Network:{R}   http://{local_ip}:5173")
    if pub_url:
        print(f"  {MG}{B}Public: {R}   {pub_url}{R}")
    print(f"  {B}API:    {R}   http://localhost:8000")
    print(f"{GR}{'─'*54}{R}")
    print(f"{DM}  Press Ctrl+C to stop all servers{R}\n")


# ── Tunnel: cloudflared (preferred — no install needed on Windows) ─
def try_cloudflared(frontend_url: str) -> str:
    """Try to open a cloudflared quick tunnel. Returns public URL or ''."""
    if not shutil.which("cloudflared"):
        return ""
    log("tunnel", MG, "Opening cloudflared tunnel...")
    try:
        proc = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", frontend_url],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        processes.append(proc)
        # cloudflared prints the URL to stdout within ~5s
        for _ in range(30):
            line = proc.stdout.readline().decode("utf-8", errors="replace").strip()
            if "trycloudflare.com" in line or ".cloudflare.com" in line:
                # Extract the URL
                for part in line.split():
                    if part.startswith("https://"):
                        log("tunnel", MG, f"Public URL → {B}{part}{R}")
                        return part
            time.sleep(0.3)
    except Exception as e:
        log("tunnel", RD, f"cloudflared failed: {e}")
    return ""


# ── Tunnel: localtunnel (npm-based, no account needed) ────────────
def try_localtunnel(port: int) -> str:
    """Try localtunnel via npx. Returns public URL or ''."""
    log("tunnel", MG, "Trying localtunnel (npx lt)...")
    url = ""
    try:
        proc = subprocess.Popen(
            [NPM, "exec", "--yes", "--", "localtunnel", "--port", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        processes.append(proc)
        # lt prints: "your url is: https://..."
        for _ in range(40):
            raw = proc.stdout.readline()
            line = raw.decode("utf-8", errors="replace").strip()
            if "your url is" in line.lower():
                for part in line.split():
                    if part.startswith("https://"):
                        url = part
                        log("tunnel", MG, f"Public URL → {B}{url}{R}")
                        return url
            if proc.poll() is not None:
                break
            time.sleep(0.3)
    except Exception as e:
        log("tunnel", RD, f"localtunnel failed: {e}")
    return ""


def get_local_ip() -> str:
    """Best-effort: get the machine's LAN IP address."""
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return ""


# ── Main ──────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="WanderAI dev launcher — starts backend + frontend together"
    )
    parser.add_argument(
        "--tunnel", action="store_true",
        help="Generate a public HTTPS URL (tries cloudflared then localtunnel)"
    )
    parser.add_argument(
        "--no-browser", action="store_true",
        help="Don't auto-open the browser"
    )
    args = parser.parse_args()

    print_banner(tunnel_mode=args.tunnel)
    check_env()

    signal.signal(signal.SIGINT, stop_all)
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, stop_all)

    # ── 1. Start backend (suppress most output — runs quietly in BG) ─
    log("backend", CY, "Starting FastAPI on http://localhost:8000 ...")
    backend_proc = subprocess.Popen(
        [PYTHON, "main.py"],
        cwd=BACKEND,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    processes.append(backend_proc)

    # Only surface backend errors (warnings/errors), suppress INFO spam
    def backend_filter(line: str):
        lowered = line.lower()
        if any(k in lowered for k in ("error", "exception", "traceback", "warning", "critical")):
            log("backend", CY, line)

    for s in (backend_proc.stdout, backend_proc.stderr):
        threading.Thread(
            target=prefix_stream,
            args=(s, "backend", CY, backend_filter),
            daemon=True,
        ).start()

    # Wait for backend to be ready
    log("backend", CY, "Waiting for backend to be ready...")
    time.sleep(2.5)
    if backend_proc.poll() is not None:
        log("backend", RD, f"Backend crashed! (exit {backend_proc.returncode})")
        log("backend", RD, "Check backend/.env — is GROQ_API_KEY set?")
        sys.exit(1)
    log("backend", GR, "Backend is up ✓")

    # ── 2. Start Vite frontend with --host (network exposure) ────────
    log("frontend", YL, "Starting Vite on http://localhost:5173 (network-exposed) ...")
    vite_ready = threading.Event()

    frontend_proc = subprocess.Popen(
        [NPM, "run", "dev", "--", "--host"],
        cwd=FRONTEND,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    processes.append(frontend_proc)

    def frontend_filter(line: str):
        if "ready in" in line or "localhost" in line or "➜" in line:
            log("frontend", YL, line)
            if "ready" in line or "localhost" in line:
                vite_ready.set()

    for s in (frontend_proc.stdout, frontend_proc.stderr):
        threading.Thread(
            target=prefix_stream,
            args=(s, "frontend", YL, frontend_filter),
            daemon=True,
        ).start()

    # Wait for Vite to signal it's ready
    vite_ready.wait(timeout=20)
    if frontend_proc.poll() is not None:
        log("frontend", RD, f"Frontend crashed! (exit {frontend_proc.returncode})")
        stop_all()

    # ── 3. Optional tunnel ────────────────────────────────────────────
    pub_url = ""
    if args.tunnel:
        pub_url = try_cloudflared("http://localhost:5173")
        if not pub_url:
            pub_url = try_localtunnel(5173)
        if not pub_url:
            log("tunnel", RD,
                "No tunnel tool found. Install cloudflared: "
                "https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/")

    # ── 4. Print summary URLs ─────────────────────────────────────────
    local_ip = get_local_ip()
    print_urls(local_ip=local_ip, pub_url=pub_url)

    # ── 5. Auto-open browser ──────────────────────────────────────────
    if not args.no_browser:
        open_url = pub_url if pub_url else "http://localhost:5173"
        time.sleep(0.5)
        try:
            webbrowser.open(open_url)
        except Exception:
            pass

    # ── 6. Monitor — exit if either server dies ───────────────────────
    try:
        while True:
            if backend_proc.poll() is not None:
                log("backend", RD, f"Backend exited unexpectedly (code {backend_proc.returncode}).")
                stop_all()
            if frontend_proc.poll() is not None:
                log("frontend", RD, f"Frontend exited unexpectedly (code {frontend_proc.returncode}).")
                stop_all()
            time.sleep(1)
    except KeyboardInterrupt:
        stop_all()


if __name__ == "__main__":
    main()
