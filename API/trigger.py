"""
api/trigger.py — Vercel Serverless Function (Python runtime)

Quando la dashboard clicca "Genera ora", chiama questo endpoint.
Questo a sua volta triggera il workflow GitHub Actions via API.

Variabili d'ambiente da impostare su Vercel:
  GITHUB_TOKEN     → Personal Access Token con scope "repo" e "actions"
  GITHUB_OWNER     → il tuo username GitHub (es. "mariorossi")
  GITHUB_REPO      → nome del repo (es. "roma-stats-bot")
"""

import json
import os
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        """Gestisce preflight CORS."""
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_POST(self):
        """Triggera GitHub Actions workflow_dispatch."""
        # Leggi body
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}

        force = str(payload.get("force", "false")).lower()

        token = os.environ.get("GITHUB_TOKEN", "")
        owner = os.environ.get("GITHUB_OWNER", "")
        repo  = os.environ.get("GITHUB_REPO", "")

        if not token or not owner or not repo:
            self._respond(500, {
                "ok":    False,
                "error": "Variabili GITHUB_TOKEN / GITHUB_OWNER / GITHUB_REPO non configurate su Vercel."
            })
            return

        # Chiama l'API GitHub Actions workflow_dispatch
        url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/bot.yml/dispatches"
        gh_payload = json.dumps({
            "ref": "main",
            "inputs": {"force": force}
        }).encode()

        req = urllib.request.Request(
            url,
            data=gh_payload,
            headers={
                "Authorization":        f"Bearer {token}",
                "Accept":               "application/vnd.github+json",
                "Content-Type":         "application/json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req) as resp:
                # GitHub risponde 204 No Content se ok
                self._respond(200, {
                    "ok":      True,
                    "message": "Workflow avviato! Attendi 30-60 secondi e ricarica.",
                    "force":   force == "true"
                })
        except urllib.error.HTTPError as e:
            err_body = e.read().decode()
            self._respond(e.code, {
                "ok":    False,
                "error": f"GitHub API error {e.code}: {err_body}"
            })
        except Exception as e:
            self._respond(500, {"ok": False, "error": str(e)})

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _respond(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type",   "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # Silenzia i log di default
