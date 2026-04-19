import time
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from curl_cffi import requests as curl_requests

# --- CONFIGURAZIONE ---
IG_USER_ID    = os.environ.get("IG_USER_ID", "")
IG_TOKEN      = os.environ.get("IG_ACCESS_TOKEN", "")
GH_REPOSITORY = os.environ.get("GH_REPOSITORY", "ASRomaData/RomaStats") 
TEAM_ID       = 2702   
POSTED_FILE   = "last_posted.json"
CARD_FILE     = "match_card.png"
FORCE_MODE    = "--force" in sys.argv

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Referer": "https://www.sofascore.com/",
}

# --- GESTIONE DUPLICATI ---
def load_last_posted():
    if os.path.exists(POSTED_FILE):
        try:
            with open(POSTED_FILE, "r") as f:
                return json.load(f).get("last_event_id")
        except: return None
    return None

def save_last_posted(event_id):
    with open(POSTED_FILE, "w") as f:
        json.dump({"last_event_id": str(event_id), "date": datetime.now().isoformat()}, f)

# --- LOGICA DATI ---
def safe_request(url):
    try:
        res = curl_requests.get(url, headers=HEADERS, impersonate="chrome110", timeout=20)
        return res if res.status_code == 200 else None
    except: return None

def find_recent_roma_match():
    now = datetime.now(timezone.utc)
    for days_ago in range(7 if FORCE_MODE else 3):
        date_str = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"
        res = safe_request(url)
        if not res: continue
        for event in res.json().get("events", []):
            if (event.get("homeTeam", {}).get("id") == TEAM_ID or event.get("awayTeam", {}).get("id") == TEAM_ID) and \
               event.get("status", {}).get("type") == "finished":
                return event
    return None

def get_all_stats(event_id):
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/statistics"
    res = safe_request(url)
    if not res: return {}
    target = next((p for p in res.json().get("statistics", []) if p.get("period") == "ALL"), None)
    full_map = {}
    if target:
        for group in target.get("groups", []):
            for item in group.get("statisticsItems", []):
                full_map[item["name"]] = {"home": item.get("home"), "away": item.get("away")}
    return full_map

# --- GRAFICA MIGLIORATA ---
def generate_match_card(event, stats):
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (1080, 1080), "#1a1a2e")
        draw = ImageDraw.Draw(img)
        
        # Caricamento Font (Linux path per GitHub Actions)
        def get_font(size):
            paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 
                     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
            for p in paths:
                if os.path.exists(p): return ImageFont.truetype(p, size)
            return ImageFont.load_default()

        f_big = get_font(80)
        f_mid = get_font(45)
        f_small = get_font(35)

        # Header
        draw.rectangle([0, 0, 1080, 300], fill="#8E1F2F")
        res_text = f"{event['homeTeam']['name']}  {event['homeScore']['display']} - {event['awayScore']['display']}  {event['awayTeam']['name']}"
        draw.text((540, 150), res_text, fill="white", anchor="mm", font=f_big)

        # Stats
        y = 400
        items = [("Possesso", "Ball possession"), ("Tiri Totali", "Total shots"), 
                 ("In Porta", "Shots on target"), ("Passaggi", "Accurate passes")]
        
        for label, key in items:
            h = str(stats.get(key, {}).get("home", "0"))
            a = str(stats.get(key, {}).get("away", "0"))
            
            draw.text((540, y), label, fill="#F1B041", anchor="mm", font=f_small)
            draw.text((200, y), h, fill="white", anchor="mm", font=f_mid)
            draw.text((880, y), a, fill="white", anchor="mm", font=f_mid)
            draw.line([150, y+50, 930, y+50], fill="#333355", width=2)
            y += 150

        img.save(CARD_FILE)
        return True
    except Exception as e:
        print(f"Errore grafica: {e}"); return False

# --- INSTAGRAM ---
def post_to_instagram(img_url, event):
    if not IG_USER_ID or not IG_TOKEN: return False
    full_url = f"{img_url}?t={int(time.time())}"
    caption = f"Match Report: {event['homeTeam']['name']} vs {event['awayTeam']['name']} #ASRoma #SerieA"
    
    base = "https://graph.facebook.com/v19.0"
    r = curl_requests.post(f"{base}/{IG_USER_ID}/media", data={"image_url": full_url, "caption": caption, "access_token": IG_TOKEN})
    if "id" not in r.json(): return False
    
    time.sleep(10)
    curl_requests.post(f"{base}/{IG_USER_ID}/media_publish", data={"creation_id": r.json()["id"], "access_token": IG_TOKEN})
    return True

def main():
    match = find_recent_roma_match()
    if not match: return

    # Controllo Duplicato
    last_id = load_last_posted()
    if not FORCE_MODE and str(match["id"]) == last_id:
        print(f"Partita {match['id']} già postata. Uso --force per ignorare."); return

    stats = get_all_stats(match["id"])
    if generate_match_card(match, stats):
        user, repo = GH_REPOSITORY.split("/")
        img_url = f"https://{user}.github.io/{repo}/{CARD_FILE}"
        
        print(f"Pubblicazione partita {match['id']}...")
        if post_to_instagram(img_url, match):
            save_last_posted(match["id"]) #
            print("Successo!")

if __name__ == "__main__":
    main()
