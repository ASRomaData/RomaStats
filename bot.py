import time
import json
import os
from datetime import datetime, timezone, timedelta
from curl_cffi import requests as curl_requests
from atproto import Client

# ==========================================================
# CONFIGURAZIONE DINAMICA
# ==========================================================
BSKY_HANDLE   = os.environ.get("BSKY_HANDLE", "")
BSKY_PASSWORD = os.environ.get("BSKY_PASSWORD", "")
# Prende il Team ID dall'ambiente (default Roma 2702)
TEAM_ID       = int(os.environ.get("TEAM_ID", 2702))
# Forza l'esecuzione anche fuori dalla finestra temporale
FORCE_RUN     = os.environ.get("FORCE_RUN", "false").lower() == "true"

DATA_FILE     = "last_posted.json"
DASHBOARD_FILE = "dashboard_data.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
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
            return json.load(f).get("last_id")
    return None

def save_last_posted(match_id):
    with open(DATA_FILE, "w") as f:
        json.dump({"last_id": match_id, "date": datetime.now().isoformat()}, f)

def get_all_stats(match_id):
    url = f"https://api.sofascore.com/api/v1/event/{match_id}/statistics"
    res = safe_request(url)
    if not res: return None
    return res.json().get("statistics", [])

def format_post(match, stats_data):
    home = match["homeTeam"]["name"]
    away = match["awayTeam"]["name"]
    res_h = match["homeScore"]["display"]
    res_a = match["awayScore"]["display"]
    
    # Trova le statistiche nel JSON
    s = {}
    for period in stats_data:
        if period["period"] == "ALL":
            for group in period["groups"]:
                for item in group["statisticsItems"]:
                    s[item["name"]] = (item["home"], item["away"])

    post = f"⚽ {home} {res_h}-{res_a} {away}\n\n"
    post += f"📊 Statistiche Match:\n"
    post += f"Possesso: {s.get('Ball possession', ('?','?'))[0]} - {s.get('Ball possession', ('?','?'))[1]}\n"
    post += f"Tiri (in porta): {s.get('Total shots', ('?','?'))[0]}({s.get('Shots on target', ('?','?'))[0]}) - {s.get('Total shots', ('?','?'))[1]}({s.get('Shots on target', ('?','?'))[1]})\n"
    post += f"Corner: {s.get('Corner kicks', ('0','0'))[0]} - {s.get('Corner kicks', ('0','0'))[1]}\n"
    post += f"Falli: {s.get('Fouls', ('0','0'))[0]} - {s.get('Fouls', ('0','0'))[1]}\n\n"
    post += f"#{home.replace(' ','')} #{away.replace(' ','')} #SerieA #SofaScore"
    return post

def post_to_bluesky(text):
    if not BSKY_HANDLE or not BSKY_PASSWORD:
        print("⚠️ Credenziali Bluesky mancanti.")
        return False
    try:
        client = Client()
        client.login(BSKY_HANDLE, BSKY_PASSWORD)
        client.send_post(text=text)
        print("✅ Post inviato su Bluesky!")
        return True
    except Exception as e:
        print(f"❌ Errore Bluesky: {e}")
        return False

def main():
    print(f"🔍 Controllo Team ID: {TEAM_ID}")
    url = f"https://api.sofascore.com/api/v1/team/{TEAM_ID}/events/last/0"
    res = safe_request(url)
    if not res: return
    
    events = res.json().get("events", [])
    if not events: return

    # Se FORCE_RUN è true, prendiamo l'ultima partita a prescindere dall'orario
    match = None
    last_posted_id = load_last_posted()

    if FORCE_RUN:
        for e in events:
            if e["status"]["type"] == "finished":
                match = e
                break
    else:
        # Controllo standard (finestra temporale)
        now = datetime.now(timezone.utc)
        for e in events:
            start_dt = datetime.fromtimestamp(e["startTimestamp"], tz=timezone.utc)
            if start_dt - timedelta(hours=1) <= now <= start_dt + timedelta(hours=5):
                if e["status"]["type"] == "finished" and e["id"] != last_posted_id:
                    match = e
                    break

    if match:
        stats = get_all_stats(match["id"])
        if stats:
            post_text = format_post(match, stats)
            if post_to_bluesky(post_text):
                save_last_posted(match["id"])
                # Aggiorna dashboard
                db_data = {"last_updated": datetime.now().isoformat(), "match": match, "stats": stats, "post_text": post_text}
                with open(DASHBOARD_FILE, "w") as f: json.dump(db_data, f)
    else:
        print("ℹ️ Nessuna nuova partita terminata trovata.")

if __name__ == "__main__":
    main()
