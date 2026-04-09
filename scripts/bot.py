import time
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from curl_cffi import requests as curl_requests
from atproto import Client

# ==========================================================
# CONFIGURAZIONE
# ==========================================================
BSKY_HANDLE   = os.environ.get("BSKY_HANDLE", "")
BSKY_PASSWORD = os.environ.get("BSKY_PASSWORD", "")
TEAM_ID       = 2702
TEAM_NAME     = "roma"
HASHTAGS      = "#Roma #SerieA #ASRoma #ForzaRoma #SofaScore"
DATA_FILE     = "dashboard_data.json"
POSTED_FILE   = "last_posted.json"
POST_WINDOW_HOURS = 3   # max ore dopo inizio partita per pubblicare
FORCE_MAX_DAYS    = 7   # giorni indietro in force mode
# ==========================================================

FORCE_MODE = "--force" in sys.argv

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.sofascore.com/",
}

def safe_request(url):
    try:
        res = curl_requests.get(url, headers=HEADERS, impersonate="chrome110", timeout=20)
        return res if res.status_code == 200 else None
    except Exception as e:
        print(f"Errore richiesta: {e}")
        return None

def load_last_posted():
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r") as f:
            return json.load(f).get("last_event_id")
    return None

def save_last_posted(event_id):
    with open(POSTED_FILE, "w") as f:
        json.dump({"last_event_id": event_id,
                   "posted_at": datetime.now(timezone.utc).isoformat()}, f)

def find_recent_roma_match(force=False):
    """
    Scansiona per data (oggi + giorni precedenti).
    Questo e' l'unico modo affidabile: last/0 di SofaScore
    restituisce la pagina PIU' VECCHIA, non la piu' recente.
    """
    now    = datetime.now(timezone.utc)
    now_ts = now.timestamp()
    team   = TEAM_NAME.lower()
    max_days = FORCE_MAX_DAYS if force else 3

    for days_ago in range(max_days):
        date_str = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"
        res = safe_request(url)
        if not res:
            time.sleep(1)
            continue

        for event in res.json().get("events", []):
            home   = event.get("homeTeam", {}).get("name", "").lower()
            away   = event.get("awayTeam", {}).get("name", "").lower()
            status = event.get("status", {}).get("type", "")
            if team not in home and team not in away:
                continue
            if status != "finished":
                continue
            start_ts = event.get("startTimestamp", 0)
            hours_ago = (now_ts - start_ts) / 3600

            # FIX 1: in auto mode pubblica solo entro POST_WINDOW_HOURS dall'inizio
            if not force and hours_ago > POST_WINDOW_HOURS:
                print(f"  Skip (troppo vecchia: {hours_ago:.1f}h fa): "
                      f"{event['homeTeam']['name']} vs {event['awayTeam']['name']}")
                continue

            print(f"  Trovata ({hours_ago:.1f}h fa): "
                  f"{event['homeTeam']['name']} "
                  f"{event.get('homeScore',{}).get('display','?')}-"
                  f"{event.get('awayScore',{}).get('display','?')} "
                  f"{event['awayTeam']['name']}")
            return event

        time.sleep(1.2)

    return None

def is_match_window_today():
    """Controlla se c'e' una partita Roma oggi nella finestra -1h/+3h."""
    now    = datetime.now(timezone.utc)
    now_ts = now.timestamp()
    team   = TEAM_NAME.lower()

    for delta in [0, 1, -1]:
        date_str = (now + timedelta(days=delta)).strftime("%Y-%m-%d")
        url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"
        res = safe_request(url)
        if not res:
            continue
        for event in res.json().get("events", []):
            home = event.get("homeTeam", {}).get("name", "").lower()
            away = event.get("awayTeam", {}).get("name", "").lower()
            if team not in home and team not in away:
                continue
            start_ts = event.get("startTimestamp", 0)
            if (start_ts - 3600) <= now_ts <= (start_ts + POST_WINDOW_HOURS * 3600):
                return True, event
        time.sleep(0.8)

    return False, None

def get_all_stats(event_id):
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/statistics"
    res = safe_request(url)
    if not res:
        return {}
    stats_all = next(
        (p for p in res.json().get("statistics", []) if p.get("period") == "ALL"), None)
    full_map = {}
    if stats_all:
        for group in stats_all.get("groups", []):
            for item in group.get("statisticsItems", []):
                full_map[item["name"]] = {"home": item.get("home"), "away": item.get("away")}
    return full_map

def format_post(event, stats):
    home    = event["homeTeam"]["name"]
    away    = event["awayTeam"]["name"]
    h_score = event.get("homeScore", {}).get("display", 0)
    a_score = event.get("awayScore", {}).get("display", 0)

    def s(name):
        return stats.get(name, {"home": "-", "away": "-"})

    text = (f"🟡🔴 Match Report: {home} {h_score}-{a_score} {away}\n\n"
            f"⚽ Tiri (Porta): {s('Total shots')['home']}({s('Shots on target')['home']}) "
            f"- {s('Total shots')['away']}({s('Shots on target')['away']})\n")
    xg_h = s("Expected goals")["home"]
    if xg_h not in (None, "-"):
        text += f"📊 xG: {xg_h} - {s('Expected goals')['away']}\n"
    text += (f"⏳ Possesso: {s('Ball possession')['home']} - {s('Ball possession')['away']}\n"
             f"🎯 Passaggi: {s('Accurate passes')['home']} - {s('Accurate passes')['away']}\n\n"
             f"{HASHTAGS}")
    return text[:300] if len(text) > 300 else text

def post_to_bluesky(text):
    if not BSKY_HANDLE or not BSKY_PASSWORD:
        print("Credenziali Bluesky non configurate, skip.")
        return False
    try:
        client = Client()
        client.login(BSKY_HANDLE.strip(), BSKY_PASSWORD.strip())
        post = client.send_post(text)
        post_id = post.uri.split("/")[-1]
        print(f"Bluesky OK: https://bsky.app/profile/{BSKY_HANDLE}/post/{post_id}")
        return True
    except Exception as e:
        print(f"Errore Bluesky: {e}")
        return False

def save_dashboard_data(event, stats, post_text, published, force_mode):
    home     = event["homeTeam"]["name"]
    away     = event["awayTeam"]["name"]
    h_score  = event.get("homeScore", {}).get("display", 0)
    a_score  = event.get("awayScore", {}).get("display", 0)
    start_ts = event.get("startTimestamp", 0)

    def s(name):
        return stats.get(name, {"home": "-", "away": "-"})

    data = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "force_mode":   force_mode,
        "published":    published,
        "match": {
            "id":         event["id"],
            "home":       home,
            "away":       away,
            "score":      f"{h_score}-{a_score}",
            "h_score":    h_score,
            "a_score":    a_score,
            "date":       datetime.fromtimestamp(start_ts, tz=timezone.utc)
                          .strftime("%d %b %Y %H:%M"),
            "tournament": event.get("tournament", {}).get("name", ""),
        },
        "stats": {
            "total_shots":     s("Total shots"),
            "shots_on_target": s("Shots on target"),
            "expected_goals":  s("Expected goals"),
            "ball_possession": s("Ball possession"),
            "accurate_passes": s("Accurate passes"),
            "fouls":           s("Fouls"),
            "corner_kicks":    s("Corner kicks"),
            "yellow_cards":    s("Yellow cards"),
            "red_cards":       s("Red cards"),
        },
        "post_text": post_text,
    }

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"dashboard_data.json aggiornato")

def main():
    print(f"Roma Bot — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Modalita: {'FORCE (manuale)' if FORCE_MODE else 'AUTO'}")

    if not FORCE_MODE:
        in_window, upcoming = is_match_window_today()
        if not in_window:
            if upcoming:
                start = datetime.fromtimestamp(
                    upcoming.get("startTimestamp", 0), tz=timezone.utc)
                print(f"Fuori finestra. Prossima Roma: "
                      f"{upcoming['homeTeam']['name']} vs {upcoming['awayTeam']['name']} "
                      f"— {start.strftime('%d %b %H:%M UTC')}")
            else:
                print("Nessuna partita Roma in finestra oggi.")
            return
        print("Nella finestra di partita, procedo...")

    match = find_recent_roma_match(force=FORCE_MODE)
    if not match:
        msg = (f"Nessuna partita negli ultimi {FORCE_MAX_DAYS}gg."
               if FORCE_MODE else "Nessuna partita terminata nella finestra.")
        print(msg)
        return

    last_posted_id = load_last_posted()
    if not FORCE_MODE and str(match.get("id")) == str(last_posted_id):
        print("Partita gia' postata, skip.")
        return

    stats = get_all_stats(match["id"])
    if not stats:
        print("Statistiche non ancora disponibili, riprovo al prossimo run.")
        return

    post_text = format_post(match, stats)
    print(f"\n--- POST ({len(post_text)} chars) ---\n{post_text}\n")

    published = post_to_bluesky(post_text)

    if published and not FORCE_MODE:
        save_last_posted(str(match["id"]))

    save_dashboard_data(match, stats, post_text, published, FORCE_MODE)
    print("Done.")

if __name__ == "__main__":
    main()
