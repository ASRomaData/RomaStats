import time
import json
import os
from datetime import datetime, timezone, timedelta
from curl_cffi import requests as curl_requests
from atproto import Client

# ==========================================================
# CONFIGURAZIONE — imposta queste variabili nei GitHub Secrets
# ==========================================================
BSKY_HANDLE   = os.environ.get("BSKY_HANDLE", "")        # es. tuoaccount.bsky.social
BSKY_PASSWORD = os.environ.get("BSKY_PASSWORD", "")      # App Password di Bluesky
TEAM_ID       = 2702                                      # Roma su SofaScore
TEAM_NAME     = "roma"
HASHTAGS      = "#Roma #SerieA #ASRoma #ForzaRoma #SofaScore"
DATA_FILE     = "last_posted.json"                        # traccia ultima partita postata
# ==========================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.sofascore.com/",
}

# ----------------------------------------------------------
# UTILITÀ
# ----------------------------------------------------------

def safe_request(url):
    try:
        res = curl_requests.get(url, headers=HEADERS, impersonate="chrome110", timeout=20)
        return res if res.status_code == 200 else None
    except Exception as e:
        print(f"❌ Errore richiesta: {e}")
        return None

def load_last_posted():
    """Carica l'ID dell'ultima partita postata dal file JSON."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f).get("last_event_id")
    return None

def save_last_posted(event_id):
    """Salva l'ID dell'ultima partita postata."""
    with open(DATA_FILE, "w") as f:
        json.dump({"last_event_id": event_id, "posted_at": datetime.now(timezone.utc).isoformat()}, f)

# ----------------------------------------------------------
# CALENDARIO — recupera le prossime/ultime partite della Roma
# ----------------------------------------------------------

def get_team_events(team_id):
    """
    Recupera le ultime partite + le prossime dalla API SofaScore.
    Endpoint: /api/v1/team/{id}/events/last/0 e /next/0
    Ogni pagina restituisce max 10 eventi, la pagina 0 è la più recente.
    """
    events = []

    # Ultime partite (pagina 0 = le più recenti)
    res = safe_request(f"https://api.sofascore.com/api/v1/team/{team_id}/events/last/0")
    if res:
        events += res.json().get("events", [])

    time.sleep(1)

    # Prossime partite
    res = safe_request(f"https://api.sofascore.com/api/v1/team/{team_id}/events/next/0")
    if res:
        events += res.json().get("events", [])

    return events

def find_finished_match(events, last_posted_id):
    """
    Cerca la partita più recente già terminata che non sia già stata postata.
    """
    finished = [
        e for e in events
        if e.get("status", {}).get("type") == "finished"
        and str(e.get("id")) != str(last_posted_id)
    ]
    if not finished:
        return None
    # Ordina per startTimestamp decrescente, prendi la più recente
    finished.sort(key=lambda e: e.get("startTimestamp", 0), reverse=True)
    return finished[0]

def is_match_window(events):
    """
    Controlla se siamo nella finestra temporale di una partita:
    da 1 ora prima dell'inizio a 3 ore dopo l'inizio.
    Restituisce (True/False, prossima_partita_o_None).
    """
    now_ts = datetime.now(timezone.utc).timestamp()

    for event in events:
        start_ts = event.get("startTimestamp", 0)
        window_start = start_ts - 3600      # 1 ora prima
        window_end   = start_ts + 10800     # 3 ore dopo

        if window_start <= now_ts <= window_end:
            return True, event

    return False, None

# ----------------------------------------------------------
# STATISTICHE
# ----------------------------------------------------------

def get_all_stats(event_id):
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/statistics"
    res = safe_request(url)
    if not res:
        return {}
    stats_all = next(
        (p for p in res.json().get("statistics", []) if p.get("period") == "ALL"),
        None
    )
    full_map = {}
    if stats_all:
        for group in stats_all.get("groups", []):
            for item in group.get("statisticsItems", []):
                full_map[item["name"]] = {
                    "home": item.get("home"),
                    "away": item.get("away")
                }
    return full_map

# ----------------------------------------------------------
# FORMATTAZIONE POST
# ----------------------------------------------------------

def format_post(event, stats):
    home    = event["homeTeam"]["name"]
    away    = event["awayTeam"]["name"]
    h_score = event.get("homeScore", {}).get("display", 0)
    a_score = event.get("awayScore", {}).get("display", 0)

    def s(name):
        return stats.get(name, {"home": "-", "away": "-"})

    t_h,    t_a    = s("Total shots")["home"],     s("Total shots")["away"]
    p_h,    p_a    = s("Shots on target")["home"], s("Shots on target")["away"]
    xg_h,   xg_a   = s("Expected goals")["home"],  s("Expected goals")["away"]
    pos_h,  pos_a  = s("Ball possession")["home"],  s("Ball possession")["away"]
    pass_h, pass_a = s("Accurate passes")["home"],  s("Accurate passes")["away"]

    text = (
        f"🟡🔴 Match Report: {home} {h_score}-{a_score} {away}\n\n"
        f"⚽ Tiri (Porta): {t_h}({p_h}) - {t_a}({p_a})\n"
    )
    if xg_h not in (None, "-"):
        text += f"📊 xG: {xg_h} - {xg_a}\n"

    text += (
        f"⏳ Possesso: {pos_h} - {pos_a}\n"
        f"🎯 Passaggi Precisi: {pass_h} - {pass_a}\n\n"
        f"{HASHTAGS}"
    )
    # Bluesky: max 300 caratteri
    if len(text) > 300:
        text = text[:297] + "..."
    return text

# ----------------------------------------------------------
# PUBBLICA SU BLUESKY
# ----------------------------------------------------------

def post_to_bluesky(text):
    if not BSKY_HANDLE or not BSKY_PASSWORD:
        print("⚠️  Credenziali Bluesky non configurate, skip.")
        return False
    try:
        client = Client()
        client.login(BSKY_HANDLE.strip(), BSKY_PASSWORD.strip())
        post = client.send_post(text)
        post_id = post.uri.split("/")[-1]
        print(f"✅ Bluesky: https://bsky.app/profile/{BSKY_HANDLE}/post/{post_id}")
        return True
    except Exception as e:
        print(f"❌ Errore Bluesky: {e}")
        return False

# ----------------------------------------------------------
# SALVA DATI PER LA DASHBOARD
# ----------------------------------------------------------

def save_dashboard_data(event, stats, post_text):
    """
    Salva i dati dell'ultima partita in un JSON che la dashboard web leggerà.
    Su GitHub Actions questo file viene committato nel repo.
    """
    home    = event["homeTeam"]["name"]
    away    = event["awayTeam"]["name"]
    h_score = event.get("homeScore", {}).get("display", 0)
    a_score = event.get("awayScore", {}).get("display", 0)

    def s(name):
        return stats.get(name, {"home": "-", "away": "-"})

    data = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "match": {
            "id":      event["id"],
            "home":    home,
            "away":    away,
            "score":   f"{h_score}-{a_score}",
            "h_score": h_score,
            "a_score": a_score,
            "date":    datetime.fromtimestamp(
                event.get("startTimestamp", 0), tz=timezone.utc
            ).strftime("%d %b %Y"),
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

    with open("dashboard_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("✅ dashboard_data.json aggiornato")

# ----------------------------------------------------------
# MAIN
# ----------------------------------------------------------

def main():
    print(f"🚀 Roma Bot avviato — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

    # 1. Recupera tutte le partite (ultime + prossime)
    events = get_team_events(TEAM_ID)
    if not events:
        print("❌ Nessun evento trovato da SofaScore.")
        return

    # 2. Controlla se siamo nella finestra temporale di una partita
    in_window, current_event = is_match_window(events)
    if not in_window:
        print("⏰ Fuori dalla finestra di partita. Nessuna azione.")
        # Mostra prossima partita
        upcoming = [
            e for e in events
            if e.get("status", {}).get("type") not in ("finished", "canceled")
            and e.get("startTimestamp", 0) > datetime.now(timezone.utc).timestamp()
        ]
        if upcoming:
            upcoming.sort(key=lambda e: e.get("startTimestamp", 0))
            next_match = upcoming[0]
            next_dt = datetime.fromtimestamp(next_match["startTimestamp"], tz=timezone.utc)
            print(f"📅 Prossima partita: {next_match['homeTeam']['name']} vs "
                  f"{next_match['awayTeam']['name']} — {next_dt.strftime('%d %b %Y %H:%M UTC')}")
        return

    print(f"✅ Siamo nella finestra di partita!")

    # 3. Cerca partita terminata non ancora postata
    last_posted_id = load_last_posted()
    finished_match = find_finished_match(events, last_posted_id)

    if not finished_match:
        print("⏳ Partita non ancora terminata o già postata. Aspetto...")
        return

    print(f"🎯 Partita terminata trovata: "
          f"{finished_match['homeTeam']['name']} "
          f"{finished_match['homeScore']['display']}-"
          f"{finished_match['awayScore']['display']} "
          f"{finished_match['awayTeam']['name']}")

    # 4. Recupera statistiche
    stats = get_all_stats(finished_match["id"])
    if not stats:
        print("⚠️ Statistiche non disponibili, riprovo al prossimo run.")
        return

    # 5. Formatta e pubblica
    post_text = format_post(finished_match, stats)
    print(f"\n--- POST ({len(post_text)} chars) ---\n{post_text}\n")

    posted = post_to_bluesky(post_text)

    if posted:
        # 6. Salva ID partita postata (evita duplicati)
        save_last_posted(str(finished_match["id"]))

    # 7. Aggiorna sempre i dati della dashboard
    save_dashboard_data(finished_match, stats, post_text)

if __name__ == "__main__":
    main()
