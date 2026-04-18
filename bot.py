import time
import json
import os
import sys
import base64
import uuid
import urllib.request
from datetime import datetime, timezone, timedelta
from curl_cffi import requests as curl_requests
from atproto import Client

BSKY_HANDLE   = os.environ.get("BSKY_HANDLE", "")
BSKY_PASSWORD = os.environ.get("BSKY_PASSWORD", "")
IG_USER_ID    = os.environ.get("IG_USER_ID", "")
IG_TOKEN      = os.environ.get("IG_ACCESS_TOKEN", "")
GH_REPOSITORY = os.environ.get("GH_REPOSITORY", "") # e.g. "username/repo"
GH_TOKEN_BOT  = os.environ.get("GH_TOKEN", "")      # Needed to push the image
VERCEL_DOMAIN = os.environ.get("VERCEL_DOMAIN", "") 
TEAM_NAME         = "roma"
TEAM_ID           = 2702   
HASHTAGS_BSKY     = "#Roma #SerieA #ASRoma #ForzaRoma"
HASHTAGS_IG       = "#Roma #SerieA #ASRoma #ForzaRoma #calcio #football #matchreport"
DATA_FILE         = "dashboard_data.json"
POSTED_FILE       = "last_posted.json"
CARD_FILE         = "match_card.png"
POST_WINDOW_HOURS = 3
FORCE_MAX_DAYS    = 7
FORCE_MODE    = "--force"    in sys.argv
HALFTIME_MODE = "--halftime" in sys.argv

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
        print(f"Errore richiesta: {e}")
        return None

def load_last_posted():
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r") as f:
            d = json.load(f)
            return d.get("last_event_id"), d.get("last_halftime_id")
    return None, None

def save_last_posted(event_id=None, halftime_id=None):
    existing = {}
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r") as f:
            existing = json.load(f)
    if event_id:
        existing["last_event_id"] = event_id
        existing["posted_at"] = datetime.now(timezone.utc).isoformat()
    if halftime_id:
        existing["last_halftime_id"] = halftime_id
    with open(POSTED_FILE, "w") as f:
        json.dump(existing, f)

def find_recent_roma_match(force=False):
    now = datetime.now(timezone.utc)
    now_ts = now.timestamp()
    max_days = FORCE_MAX_DAYS if force else 3
    for days_ago in range(max_days):
        date_str = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"
        res = safe_request(url)
        if not res:
            time.sleep(1)
            continue
        for event in res.json().get("events", []):
            if event.get("homeTeam", {}).get("id") == TEAM_ID or event.get("awayTeam", {}).get("id") == TEAM_ID:
                if event.get("status", {}).get("type", "") == "finished":
                    start_ts = event.get("startTimestamp", 0)
                    hours_ago = (now_ts - start_ts) / 3600
                    if force or hours_ago <= POST_WINDOW_HOURS:
                        print(f"  Trovata: {event['homeTeam']['name']} {event.get('homeScore',{}).get('display','?')}-{event.get('awayScore',{}).get('display','?')} {event['awayTeam']['name']}")
                        return event
        time.sleep(1.2)
    return None

def find_halftime_roma_match():
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"
    res = safe_request(url)
    if not res: return None
    for event in res.json().get("events", []):
        home = event.get("homeTeam", {}).get("name", "").lower()
        away = event.get("awayTeam", {}).get("name", "").lower()
        status = event.get("status", {})
        if "roma" in home or "roma" in away:
            if status.get("type") == "inprogress" and "ht" in status.get("description", "").lower():
                return event
    return None

def is_match_window_today():
    now = datetime.now(timezone.utc)
    now_ts = now.timestamp()
    for delta in [0, 1, -1]:
        date_str = (now + timedelta(days=delta)).strftime("%Y-%m-%d")
        url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"
        res = safe_request(url)
        if not res: continue
        for event in res.json().get("events", []):
            if event.get("homeTeam", {}).get("id") == TEAM_ID or event.get("awayTeam", {}).get("id") == TEAM_ID:
                start_ts = event.get("startTimestamp", 0)
                if (start_ts - 3600) <= now_ts <= (start_ts + POST_WINDOW_HOURS * 3600):
                    return True, event
        time.sleep(0.8)
    return False, None

def get_stats_for_period(event_id, period="ALL"):
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/statistics"
    res = safe_request(url)
    if not res: return {}
    target = next((p for p in res.json().get("statistics", []) if p.get("period") == period), None)
    if not target:
        target = next((p for p in res.json().get("statistics", []) if p.get("period") == "ALL"), None)
    full_map = {}
    if target:
        for group in target.get("groups", []):
            for item in group.get("statisticsItems", []):
                full_map[item["name"]] = {"home": item.get("home"), "away": item.get("away")}
    return full_map

def get_all_stats(event_id):
    return get_stats_for_period(event_id, "ALL")

def sv(stats, name, side):
    v = stats.get(name, {}).get(side)
    return str(v) if v not in (None, "", "-") else "-"

def calc_precision(stats, side):
    try:
        acc_raw = stats.get("Accurate passes", {}).get(side, "")
        if "/" in str(acc_raw):
            parts = str(acc_raw).split("/")
            acc = float(parts[0].strip())
            tot = float(parts[1].strip().split()[0])
            if tot > 0: return f"{round(acc/tot*100)}%"
    except: pass
    return "-"

def calc_xgot(stats, side, event, all_stats=None):
    try:
        goals = int(event.get("homeScore" if side=="home" else "awayScore", {}).get("display", 0) or 0)
        opp_side = "away" if side=="home" else "home"
        prevented = 0
        for src in ([stats, all_stats] if all_stats else [stats]):
            if src:
                for key in ("Goals prevented", "goalsPrevented"):
                    raw = src.get(key, {}).get(opp_side)
                    if raw not in (None, "", "-"):
                        prevented = float(str(raw).replace("+", ""))
                        break
            if prevented: break
        return "{:.2f}".format(round(float(goals) + prevented, 2))
    except: return "0.00"

def build_stats_lines(event, stats, halftime=False):
    h_score = event.get("homeScore", {}).get("display", "?")
    a_score = event.get("awayScore", {}).get("display", "?")
    home, away = event["homeTeam"]["name"], event["awayTeam"]["name"]
    label = "Statistiche 1° Tempo" if halftime else "Match Report"
    lines = [
        f"\U0001f7e1\U0001f534 {label}: {home} {h_score}-{a_score} {away}",
        f"\u26bd Tiri (nello specchio): {sv(stats,'Total shots','home')} ({sv(stats,'Shots on target','home')}) - {sv(stats,'Total shots','away')} ({sv(stats,'Shots on target','away')})",
        f"\U0001f4ca xG in porta: {calc_xgot(stats, 'home', event)} - {calc_xgot(stats, 'away', event)}",
        f"\u23f3 Possesso: {sv(stats,'Ball possession','home')} - {sv(stats,'Ball possession','away')}",
        f"\U0001f3af Precisione: {calc_precision(stats, 'home')} - {calc_precision(stats, 'away')}"
    ]
    return lines

def format_post_bluesky(event, stats, halftime=False):
    h_score = event.get("homeScore", {}).get("display", "?")
    a_score = event.get("awayScore", {}).get("display", "?")
    prefix = f"#{event['homeTeam']['name'].replace(' ','')}{event['awayTeam']['name'].replace(' ','')} {h_score}:{a_score}"
    if halftime: prefix += " (1T)"
    lines = [prefix, f"xG in porta {calc_xgot(stats,'home',event)}-{calc_xgot(stats,'away',event)}", HASHTAGS_BSKY]
    return "\n".join(lines)

def format_caption_instagram(event, stats, halftime=False):
    lines = build_stats_lines(event, stats, halftime)
    lines += ["", f"\U0001f7e8 Gialli: {sv(stats,'Yellow cards','home')} - {sv(stats,'Yellow cards','away')}", HASHTAGS_IG]
    return "\n".join(lines)

def generate_match_card(event, stats, output_path=CARD_FILE, halftime=False):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError: return False
    img = Image.new("RGB", (1080, 1080), "#1a1a2e")
    draw = ImageDraw.Draw(img)
    # [Logica semplificata per brevità, usa quella esistente nel tuo file]
    draw.text((540, 540), "MATCH DATA", fill="white", anchor="mm")
    img.save(output_path); return True

def get_github_image_url():
    """
    Constructs the raw GitHub Pages URL for the uploaded image.
    Assumes your repo is 'username/repo' and Pages is active.
    """
    if not GH_REPOSITORY: return None
    user, repo = GH_REPOSITORY.split("/")
    return f"https://{user}.github.io/{repo}/{CARD_FILE}"

def post_to_instagram(image_url, caption):
    if not IG_USER_ID or not IG_TOKEN: return False
    base = "https://graph.facebook.com/v19.0"
    # Instagram requires a fresh URL. We append a timestamp to bypass caching.
    final_url = f"{image_url}?t={int(time.time())}"
    print(f"  Invio URL a Instagram: {final_url}")
    
    cr = curl_requests.post(f"{base}/{IG_USER_ID}/media", data={"image_url": final_url, "caption": caption, "access_token": IG_TOKEN}, timeout=30)
    cd = cr.json()
    if "error" in cd:
        print(f"  Errore IG: {cd['error'].get('message')}"); return False
    
    creation_id = cd.get("id")
    time.sleep(10) # Wait for Instagram to process the image
    pr = curl_requests.post(f"{base}/{IG_USER_ID}/media_publish", data={"creation_id": creation_id, "access_token": IG_TOKEN}, timeout=30)
    return "id" in pr.json()

def post_to_bluesky(text):
    if not BSKY_HANDLE or not BSKY_PASSWORD: return False
    try:
        client = Client(); client.login(BSKY_HANDLE, BSKY_PASSWORD)
        client.send_post(text); return True
    except: return False

def save_dashboard_data(event, stats, post_text, published_bsky, published_ig, force_mode, halftime=False):
    data = {"match": event["id"], "posted": datetime.now().isoformat()}
    with open(DATA_FILE, "w") as f: json.dump(data, f)

def publish_to_instagram(match, stats, halftime=False):
    print("\n--- INSTAGRAM ---")
    if not generate_match_card(match, stats, halftime=halftime): return False
    
    # In GitHub Actions, the file 'match_card.png' is saved to the workspace.
    # The workflow then commits it to the repo. We use the resulting GitHub URL.
    image_url = get_github_image_url()
    if not image_url:
        print("  GH_REPOSITORY non configurato."); return False
        
    caption = format_caption_instagram(match, stats, halftime)
    return post_to_instagram(image_url, caption)

def main():
    if HALFTIME_MODE:
        match = find_halftime_roma_match()
        if not match: return
        stats = get_stats_for_period(match["id"], "1ST")
        publish_to_instagram(match, stats, halftime=True)
    else:
        match = find_recent_roma_match(force=FORCE_MODE)
        if not match: return
        stats = get_all_stats(match["id"])
        publish_to_instagram(match, stats)

if __name__ == "__main__":
    main()
