import json
import os
import urllib.request
import urllib.error


def handler(request):
    # CORS preflight
    if request.method == "OPTIONS":
        return _response(200, {})

    if request.method != "POST":
        return _response(405, {"ok": False, "error": "Method not allowed"})

    try:
        payload = request.json() or {}
    except Exception:
        payload = {}

    force = str(payload.get("force", "false")).lower()

    token = os.environ.get("GITHUB_TOKEN", "")
    owner = os.environ.get("GITHUB_OWNER", "")
    repo  = os.environ.get("GITHUB_REPO", "")

    if not token or not owner or not repo:
        return _response(500, {
            "ok": False,
            "error": "Missing GitHub environment variables"
        })

    url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/bot.yml/dispatches"

    gh_payload = json.dumps({
        "ref": "main",
        "inputs": {"force": force}
    }).encode()

    req = urllib.request.Request(
        url,
        data=gh_payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST"
    )

    try:
        urllib.request.urlopen(req)

        return _response(200, {
            "ok": True,
            "message": "Workflow triggered",
            "force": force == "true"
        })

    except urllib.error.HTTPError as e:
        return _response(e.code, {
            "ok": False,
            "error": f"GitHub API error {e.code}: {e.read().decode()}"
        })

    except Exception as e:
        return _response(500, {"ok": False, "error": str(e)})


def _response(status, data):
    return {
        "statusCode": status,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Content-Type": "application/json"
        },
        "body": json.dumps(data)
    }
