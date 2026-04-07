import os, json, time
from datetime import datetime, timezone
from curl_cffi import requests as curl_requests
from atproto import Client

BSKY_HANDLE = os.environ.get("BSKY_HANDLE", "")
BSKY_PASSWORD = os.environ.get("BSKY_PASSWORD", "")
TEAM_ID = 2702 # Roma
FORCE_RUN = os.environ.get("FORCE_RUN", "false").lower() == "true"

def main():
    print(f"🚀 Bot avviato. Force Run: {FORCE_RUN}")
    
    # Prende l'ultima partita conclusa
    res = curl_requests.get(f"https://api.sofascore.com/api/v1/team/{TEAM_ID}/events/last/0", impersonate="chrome110")
    if res.status_code != 200: 
        print("Errore SofaScore"); return
    
    events = res.json().get("events", [])
    match = next((e for e in events if e["status"]["type"] == "finished"), None)
    
    if match:
        # Prende statistiche
        s_res = curl_requests.get(f"https://api.sofascore.com/api/v1/event/{match['id']}/statistics", impersonate="chrome110")
        stats_all = next((p for p in s_res.json().get("statistics", []) if p["period"] == "ALL"), None)
        
        full_stats = {}
        if stats_all:
            for g in stats_all["groups"]:
                for i in g["statisticsItems"]:
                    full_stats[i["name"]] = {"home": i["home"], "away": i["away"]}
        
        # Formattazione Post
        home, away = match['homeTeam']['name'], match['awayTeam']['name']
        h_s, a_s = match['homeScore']['display'], match['awayScore']['display']
        
        post = f"🟡🔴 Match Report: {home} {h_s}-{a_s} {away}\n\n"
        post += f"⚽ Tiri: {full_stats.get('Total shots',{}).get('home','-')} - {full_stats.get('Total shots',{}).get('away','-')}\n"
        post += f"⏳ Possesso: {full_stats.get('Ball possession',{}).get('home','-')} - {full_stats.get('Ball possession',{}).get('away','-')}\n\n"
        post += "#Roma #SerieA #ASRoma #SofaScore"

        # Pubblica su Bluesky
        if BSKY_HANDLE and BSKY_PASSWORD:
            client = Client()
            client.login(BSKY_HANDLE, BSKY_PASSWORD)
            client.send_post(post)
            print("✅ Postato su Bluesky")
        
        # Salva per la dashboard
        dashboard = {
            "last_updated": datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M:%S UTC"),
            "match": {"home": home, "away": away, "score": f"{h_s}-{a_s}"},
            "stats": full_stats,
            "post_text": post
        }
        with open("dashboard_data.json", "w") as f:
            json.dump(dashboard, f, indent=2)
        
        # Salva ultimo ID per evitare duplicati nei run automatici
        with open("last_posted.json", "w") as f:
            json.dump({"last_event_id": str(match['id'])}, f)

if __name__ == "__main__":
    main()
