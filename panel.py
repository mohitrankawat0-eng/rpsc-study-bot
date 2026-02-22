"""
panel.py - RPSC Study Bot Control Panel
Run: python panel.py
Opens: http://localhost:8888

No extra packages needed — uses only Python built-ins.
"""
import subprocess
import threading
import time
import os
import sys
import signal
from http.server import BaseHTTPRequestHandler, HTTPServer
from collections import deque
from datetime import datetime

# ── State ─────────────────────────────────────────────────────────────────────
bot_process: subprocess.Popen | None = None
log_lines   = deque(maxlen=80)     # last 80 log lines
start_time: str = "–"
lock = threading.Lock()

BOT_SCRIPT = os.path.join(os.path.dirname(__file__), "bot.py")
PYTHON     = sys.executable
PANEL_PORT = 8888


def add_log(line: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    with lock:
        log_lines.append(f"[{ts}] {line}")


def start_bot() -> None:
    global bot_process, start_time
    if bot_process and bot_process.poll() is None:
        add_log("Bot already running — stop it first.")
        return
    add_log(">>> Starting bot...")
    start_time = datetime.now().strftime("%d %b %Y %H:%M:%S")
    bot_process = subprocess.Popen(
        [PYTHON, BOT_SCRIPT],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=os.path.dirname(BOT_SCRIPT),
    )
    threading.Thread(target=_read_output, daemon=True).start()
    add_log(f"Bot PID: {bot_process.pid}")


def stop_bot() -> None:
    global bot_process
    if bot_process and bot_process.poll() is None:
        add_log(f">>> Stopping bot (PID {bot_process.pid})...")
        try:
            bot_process.terminate()
            bot_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            bot_process.kill()
        add_log("Bot stopped.")
    else:
        add_log("Bot is not running.")
    bot_process = None


def restart_bot() -> None:
    add_log(">>> Restarting bot...")
    stop_bot()
    time.sleep(1)
    start_bot()


def _read_output() -> None:
    """Stream subprocess output into log_lines."""
    if not bot_process:
        return
    for line in bot_process.stdout:
        add_log(line.rstrip())
    ret = bot_process.wait()
    add_log(f"<<< Bot process exited (code {ret})")


def _bot_status() -> tuple[str, str]:
    """Returns (label, css-class)"""
    if bot_process and bot_process.poll() is None:
        return "🟢 RUNNING", "running"
    return "🔴 STOPPED", "stopped"


# ── HTML ──────────────────────────────────────────────────────────────────────
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="5">
<title>RPSC Study Bot — Control Panel</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Segoe UI', sans-serif;
    background: #0f1117;
    color: #e0e0e0;
    padding: 24px;
  }}
  h1 {{ color: #7c83fd; font-size: 1.6rem; margin-bottom: 4px; }}
  .sub {{ color: #888; font-size: 0.85rem; margin-bottom: 24px; }}

  .card {{
    background: #1a1d2e;
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 20px;
    border: 1px solid #2a2d40;
  }}
  .status-row {{
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
  }}
  .badge {{
    font-size: 1.1rem;
    font-weight: 700;
    padding: 6px 16px;
    border-radius: 20px;
  }}
  .badge.running {{ background: #1a3a1a; color: #4caf50; border: 1px solid #4caf50; }}
  .badge.stopped {{ background: #3a1a1a; color: #f44336; border: 1px solid #f44336; }}

  .info {{ color: #aaa; font-size: 0.85rem; }}
  .info span {{ color: #ccc; font-weight: 600; }}

  .btn-row {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 18px; }}
  .btn {{
    padding: 10px 26px;
    border: none;
    border-radius: 8px;
    font-size: 0.95rem;
    font-weight: 600;
    cursor: pointer;
    transition: opacity .15s;
  }}
  .btn:hover {{ opacity: 0.85; }}
  .btn-start   {{ background: #4caf50; color: #fff; }}
  .btn-stop    {{ background: #f44336; color: #fff; }}
  .btn-restart {{ background: #7c83fd; color: #fff; }}

  .log-box {{
    background: #0d0f1a;
    border: 1px solid #2a2d40;
    border-radius: 8px;
    padding: 14px;
    height: 420px;
    overflow-y: auto;
    font-family: 'Consolas', monospace;
    font-size: 0.78rem;
    line-height: 1.6;
    color: #b0bec5;
  }}
  .log-box .ok  {{ color: #4caf50; }}
  .log-box .err {{ color: #f44336; }}
  .log-box .inf {{ color: #81d4fa; }}
  .log-box .warn{{ color: #ffb74d; }}

  h2 {{ font-size: 1rem; color: #7c83fd; margin-bottom: 12px; }}
  footer {{ text-align:center; color:#555; font-size:0.75rem; margin-top:16px; }}
</style>
</head>
<body>
<h1>🎓 RPSC Study Bot</h1>
<p class="sub">Control Panel &nbsp;·&nbsp; Auto-refreshes every 5s &nbsp;·&nbsp; 
   <a href="/" style="color:#7c83fd">Refresh now</a></p>

<div class="card">
  <div class="status-row">
    <div class="badge {cls}">{status}</div>
    <div class="info">
      PID: <span>{pid}</span> &nbsp;|&nbsp;
      Started: <span>{started}</span> &nbsp;|&nbsp;
      Uptime: <span>{uptime}</span>
    </div>
  </div>
  <div class="btn-row">
    <form method="post" action="/start"  style="display:inline">
      <button class="btn btn-start">▶ Start</button>
    </form>
    <form method="post" action="/stop"   style="display:inline">
      <button class="btn btn-stop">■ Stop</button>
    </form>
    <form method="post" action="/restart" style="display:inline">
      <button class="btn btn-restart">↺ Restart</button>
    </form>
  </div>
</div>

<div class="card">
  <h2>📋 Live Logs (last 80 lines)</h2>
  <div class="log-box" id="log">
{log_html}
  </div>
</div>

<footer>RPSC Study Bot Panel &nbsp;·&nbsp; @RPSCstudy_bot &nbsp;·&nbsp; 
Adaptive Intelligence v2</footer>
<script>
  // Auto-scroll log to bottom
  var d = document.getElementById('log');
  if(d) d.scrollTop = d.scrollHeight;
</script>
</body>
</html>"""


def _make_log_html() -> str:
    with lock:
        lines = list(log_lines)
    rows = []
    for ln in lines:
        if "ERROR" in ln or "error" in ln or "Traceback" in ln:
            rows.append(f'<div class="err">{ln}</div>')
        elif "WARNING" in ln or "WARN" in ln or "warn" in ln:
            rows.append(f'<div class="warn">{ln}</div>')
        elif "[INFO]" in ln or "OK" in ln or "started" in ln.lower() or "running" in ln.lower():
            rows.append(f'<div class="inf">{ln}</div>')
        elif ">>>" in ln or "<<<" in ln:
            rows.append(f'<div class="ok">{ln}</div>')
        else:
            rows.append(f'<div>{ln}</div>')
    return "\n".join(rows) if rows else '<div class="inf">-- No log output yet --</div>'


def _make_page() -> str:
    status, cls    = _bot_status()
    pid            = bot_process.pid if (bot_process and bot_process.poll() is None) else "–"
    uptime_str     = "–"

    return HTML_TEMPLATE.format(
        status  = status,
        cls     = cls,
        pid     = pid,
        started = start_time,
        uptime  = uptime_str,
        log_html= _make_log_html(),
    )


# ── HTTP Handler ──────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):   # silence access log spam
        pass

    def _respond(self, body: str, code: int = 200) -> None:
        enc = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(enc)))
        self.end_headers()
        self.wfile.write(enc)

    def do_GET(self):
        self._respond(_make_page())

    def do_POST(self):
        path = self.path.rstrip("/")
        if path == "/start":
            threading.Thread(target=start_bot, daemon=True).start()
        elif path == "/stop":
            threading.Thread(target=stop_bot, daemon=True).start()
        elif path == "/restart":
            threading.Thread(target=restart_bot, daemon=True).start()
        # Redirect back to GET
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    add_log("Panel started — auto-launching bot...")
    start_bot()

    server = HTTPServer(("0.0.0.0", PANEL_PORT), Handler)
    url    = f"http://localhost:{PANEL_PORT}"
    print(f"\n{'='*50}")
    print(f"  RPSC Study Bot — Control Panel")
    print(f"  Open in browser: {url}")
    print(f"  Press Ctrl+C to stop everything.")
    print(f"{'='*50}\n")

    # Auto-open browser
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        stop_bot()


if __name__ == "__main__":
    main()
