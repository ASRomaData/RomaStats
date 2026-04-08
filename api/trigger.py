import json
import os
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        length  = int(self.headers.get("Content-Length", 0))
        body    = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}

        force = "true" if str(payload.get("force", "false")).lower() == "true" else "false"

        token = os.environ.get("GITHUB_TOKEN", "")
        owner = os.environ.get("GITHUB_OWNER", "")
        repo  = os.environ.get("GITHUB_REPO", "")

        if not all([token, owner, repo]):
            self._respond(500, {
                "ok": False,
                "error": "Variabili mancanti: configura GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO su Vercel."
            })
            return

        url  = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/bot.yml/dispatches"
        data = json.dumps({"ref": "main", "inputs": {"force": force}}).encode()
        req  = urllib.request.Request(url, data=data, method="POST", headers={
            "Authorization":        f"Bearer {token}",
            "Accept":               "application/vnd.github+json",
            "Content-Type":         "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

        try:
            urllib.request.urlopen(req)
            self._respond(200, {
                "ok":      True,
                "message": "Workflow avviato! Attendi 30-60 secondi e ricarica.",
                "force":   force == "true"
            })
        except urllib.error.HTTPError as e:
            self._respond(e.code, {"ok": False, "error": f"GitHub {e.code}: {e.read().decode()}"})
        except Exception as e:
            self._respond(500, {"ok": False, "error": str(e)})

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _respond(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type",   "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass
