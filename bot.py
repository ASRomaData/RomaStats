import time
import json
import os
import sys
import base64
import uuid
import urllib.request
import random
from datetime import datetime, timezone, timedelta
from curl_cffi import requests as curl_requests
from atproto import Client

# --- CONFIGURAZIONE ---
BSKY_HANDLE   = os.environ.get("BSKY_HANDLE", "")
BSKY_PASSWORD = os.environ.get("BSKY_PASSWORD", "")
IG_USER_ID    = os.environ.get("IG_USER_ID", "")
IG_TOKEN      = os.environ.get("IG_ACCESS_TOKEN", "")
GH_REPOSITORY = os.environ.get("GH_REPOSITORY", "ASRomaData/RomaStats") 

TEAM_ID           = 2702   
HASHTAGS_IG       = "#Roma #SerieA #ASRoma #ForzaRoma #calcio #football #matchreport"
POSTED_FILE       = "last_posted.json"
CARD_FILE         = "match_card.png"
FORCE_MODE        = "--force" in sys.argv

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.sofascore.com/",
}

def safe_request(url):
    try:
        res = curl_requests.get(url, headers=HEADERS, impersonate="chrome110", timeout=20)
        return res if res.status_code == 200 else None
    except: return None

# --- LOGICA DATI ---

def find_recent_roma_match(force=False):
    now = datetime.now(timezone.utc)
    for days_ago in range(7 if force else 3):
        date_str = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"
        res = safe_request(url)
        if not res: continue
        for event in res.json().get("events", []):
            if event.get("homeTeam", {}).get("id") == TEAM_ID or event.get("awayTeam", {}).get("id") == TEAM_ID:
                if event.get("status", {}).get("type", "") == "finished":
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

# --- UTILS GRAFICA ---

def sv(stats, name, side):
    v = stats.get(name, {}).get(side)
    return str(v) if v not in (None, "", "-") else "0"

def generate_match_card(event, stats, output_path=CARD_FILE):
    try:
        from PIL import Image, ImageDraw, ImageFont
        # Canvas 1080x1080 (Instagram Square)
        img = Image.new("RGB", (1080, 1080), "#1a1a2e") # Sfondo Blu Notte
        draw = ImageDraw.Draw(img)
        
        # Colori
        ROMA_RED = "#8E1F2F"
        ROMA_GOLD = "#F1B041"
        
        # Header - Risultato
        h_name = event['homeTeam']['name']
        a_name = event['awayTeam']['name']
        h_score = event.get('homeScore', {}).get('display', '0')
        a_score = event.get('awayScore', {}).get('display', '0')
        
        draw.rectangle([0, 0, 1080, 250], fill=ROMA_RED)
        draw.text((540, 100), f"{h_name}  {h_score} - {a_score}  {a_name}", fill="white", anchor="mm", font=None) # Usa font se disponibile
        
        # Corpo - Statistiche
        y_offset = 350
        stats_to_show = [
            ("Possesso Palla", "Ball possession"),
            ("Tiri Totali", "Total shots"),
            ("Tiri in Porta", "Shots on target"),
            ("Passaggi Accurati", "Accurate passes"),
            ("Calci d'angolo", "Corner kicks"),
            ("Falli commessi", "Fouls")
        ]
        
        for label, key in stats_to_show:
            h_val = sv(stats, key, 'home')
            a_val = sv(stats, key, 'away')
            
            # Label centrale
            draw.text((540, y_offset), label, fill=ROMA_GOLD, anchor="mm")
            # Valori laterali
            draw.text((200, y_offset), h_val, fill="white", anchor="mm")
            draw.text((880, y_offset), a_val, fill="white", anchor="mm")
            
            # Linea separatrice
            draw.line([150, y_offset+40, 930, y_offset+40], fill="#333355", width=2)
            y_offset += 110

        img.save(output_path)
        print(f"  Immagine {output_path} generata con successo.")
        return True
    except Exception as e:
        print(f"  Errore generazione card: {e}")
        return False

# --- PUBBLICAZIONE ---

def check_url_is_image(url):
    try:
        req = urllib.request.Request(url, method='HEAD')
        with urllib.request.urlopen(req) as response:
            return "image" in response.info().get_content_type()
    except: return False

def post_to_instagram(image_url, caption):
    if not IG_USER_ID or not IG_TOKEN: return False
    full_url = f"{image_url}?t={int(time.time())}"
    
    if not check_url_is_image(full_url):
        print(f"  URL non ancora pronto: {full_url}")
        return False

    base = "https://graph.facebook.com/v19.0"
    r = curl_requests.post(f"{base}/{IG_USER_ID}/media", data={
        "image_url": full_url, "caption": caption, "access_token": IG_TOKEN
    })
    res = r.json()
    if "id" not in res: return False
    
    creation_id = res["id"]
    time.sleep(10)
    r_pub = curl_requests.post(f"{base}/{IG_USER_ID}/media_publish", data={
        "creation_id": creation_id, "access_token": IG_TOKEN
    })
    return "id" in r_pub.json()

def main():
    match = find_recent_roma_match(force=FORCE_MODE)
    if not match: return
    
    stats = get_all_stats(match["id"])
    if not generate_match_card(match, stats): return

    user, repo = GH_REPOSITORY.split("/")
    img_url = f"https://{user}.github.io/{repo}/{CARD_FILE}"
    
    h_name = match['homeTeam']['name']
    a_name = match['awayTeam']['name']
    caption = f"🏁 Finita! {h_name} {match.get('homeScore',{}).get('display')} - {match.get('awayScore',{}).get('display')} {a_name}\n\n📊 Ecco le statistiche del match.\n\n{HASHTAGS_IG}"
    
    print("\n--- INSTAGRAM ---")
    if post_to_instagram(img_url, caption):
        print("  Post Instagram pubblicato!")
    else:
        print("  Pubblicazione fallita. Verifica GitHub Pages e visibilità Repo.")

if __name__ == "__main__":
    main()
