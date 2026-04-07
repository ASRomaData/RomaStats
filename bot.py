import time
import json
import os
from datetime import datetime, timezone, timedelta
from curl_cffi import requests as curl_requests
from atproto import Client

# ==========================================================
# CONFIGURAZIONE DINAMICA (GitHub Actions / Secrets)
# ==========================================================
BSKY_HANDLE   = os.environ.get("BSKY_HANDLE", "")
BSKY_PASSWORD = os.environ.get("BSKY_PASSWORD", "")
# Se non specificato, il default è la Roma (2702)
TEAM_ID       = int(os.environ.get("TEAM_ID", 2702))
# Diventa True se lanciato manualmente con l'opzione "Force"
FORCE_RUN     = os.environ.get("FORCE_RUN", "false").lower() == "true"

DATA_FILE     = "last_posted.json"
DASHBOARD_FILE = "dashboard_data.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.sofascore.com/",
}

def safe_request(url):
    try:
        res = curl_requests.get(url, headers=HEADERS, impersonate="chrome110", timeout=20)
        return res if res.status_code == 200 else None
    except Exception as e:
        print(f"❌ Errore richiesta: {e}")
        return None

def load_last_posted():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f).get("last_event_id")
    return None

def save_last_posted(event_id):
    with open(DATA_FILE, "w") as f:
        json.dump({"last_event_id": str(event_id), "posted_at": datetime.now(timezone.utc).isoformat()}, f)

def get_team_events(team_id):
    events = []
    res = safe_request(f"https://api.sofascore.com/api/v1/team/{team_id}/events/last/0")
    if res: events += res.json().get("events", [])
    time.sleep(1)
    res = safe_request(f"https://api.sofascore.com/api/v1/team/{team_id}/events/next/0")
    if res: events += res.json().get("events", [])
    return events

def find_finished_match(events, last_posted_id):
    finished = [e for e in events if e.get("status", {}).get("type") == "finished"]
    if FORCE_RUN:
        # In modalità manuale prendiamo l'ultima conclusa a prescindere se già postata
        return finished[0] if finished else None
    
    # In automatico escludiamo quella già postata
    new_finished = [e for e in finished if str(e.get("id")) != str(last_posted_id)]
    return new_finished[0] if new_finished else None

def is_match_window(events):
    if FORCE_RUN: return True, None # Salta il controllo orario se forzato
    now_ts = datetime.now(timezone.utc).timestamp()
    for event in events:
        start_ts = event.get("startTimestamp", 0)
        if (start_ts - 3600) <= now_ts <= (start_ts + 10800):
            return True, event
    return False, None

def get_all_stats(event_id):
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/statistics"
    res = safe_request(url)
    if not res: return {}
    stats_all = next((p for p in res.json().get("statistics", []) if p.get("period") == "ALL"), None)
    full_map = {}
    if stats_all:
        for group in stats_all.get("groups", []):
            for item in group.get("statisticsItems", []):
                full_map[item["name"]] = {"home": item.get("home"), "away": item.get("away")}
    return full_map

def format_post(event, stats):
    home = event["homeTeam"]["name"]
    away = event["awayTeam"]["name"]
    h_s = event.get("homeScore", {}).get("display", 0)
    a_s = event.get("awayScore", {}).get("display", 0)
    
    def s(name): return stats.get(name, {"home": "-", "away": "-"})
    
    t_h, t_a = s("Total shots")["home"], s("Total shots")["away"]
    p_h, p_a = s("Shots on target")["home"], s("Shots on target")["away"]
    pos_h, pos_a = s("Ball possession")["home"], s("Ball possession")["away"]
    
    text = (f"⚽ Match Report: {home} {h_s}-{a_s} {away}\n\n"
            f"🎯 Tiri (Porta): {t_h}({p_h}) - {t_a}({p_a})\n"
            f"⏳ Possesso: {pos_h} - {pos_a}\n\n"
            f"#{home.replace(' ','')} #{away.replace(' ','')} #SerieA #SofaScore")
    return text[:300]

def post_to_bluesky(text):
    if not BSKY_HANDLE or not BSKY_PASSWORD: return False
    try:
        client = Client()
        client.login(BSKY_HANDLE.strip(), BSKY_PASSWORD.strip())
        client.send_post(text)
        return True
    except Exception as e:
        print(f"❌ Errore Bluesky: {e}"); return False

def save_dashboard_data(event, stats, post_text):
    data = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "match": {
            "id": event["id"], "home": event["homeTeam"]["name"], "away": event["awayTeam"]["name"],
            "score": f"{event['homeScore']['display']}-{event['awayScore']['display']}",
            "h_score": event['homeScore']['display'], "a_score": event['awayScore']['display'],
            "date": datetime.fromtimestamp(event["startTimestamp"], tz=timezone.utc).strftime("%d %b %Y"),
            "tournament": event.get("tournament", {}).get("name", "Serie A"),
        },
        "stats": stats,
        "post_text": post_text
    }
    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def main():
    print(f"🚀 Avvio per Team ID: {TEAM_ID} (Force: {FORCE_RUN})")
    events = get_team_events(TEAM_ID)
    if not events: return

    in_window, _ = is_match_window(events)
    if not in_window:
        print("⏰ Fuori finestra temporale."); return

    last_posted_id = load_last_posted()
    match = find_finished_match(events, last_posted_id)

    if match:
        stats = get_all_stats(match["id"])
        post_text = format_post(match, stats)
        if post_to_bluesky(post_text):
            save_last_posted(match["id"])
        save_dashboard_data(match, stats, post_text)
        print("✅ Operazione completata.")
    else:
        print("ℹ️ Nessuna nuova partita conclusa trovata.")

if __name__ == "__main__":
    main()
