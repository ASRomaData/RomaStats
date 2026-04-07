import os, json, time
from datetime import datetime, timezone
from curl_cffi import requests as curl_requests
from atproto import Client

# Configurazione ambiente
BSKY_HANDLE = os.environ.get("BSKY_HANDLE", "")
BSKY_PASSWORD = os.environ.get("BSKY_PASSWORD", "")
TEAM_ID = 2702 # Roma
FORCE_RUN = os.environ.get("FORCE_RUN", "false").lower() == "true"

def main():
    print(f"🚀 Bot avviato. Force Run: {FORCE_RUN}")
    
    # Prende l'ultima partita conclusa
    res = curl_requests.get(f"https://api.sofascore.com/api/v1/team/{TEAM_ID}/events/last/0", impersonate="chrome110")
    if res.status_code != 200: return
    
    events = res.json().get("events", [])
    match = next((e for e in events if e["status"]["type"] == "finished"), None)
    
    if match:
        # Prende statistiche
        s_res = curl_requests.get(f"https://api.sofascore.com/api/v1/event/{match['id']}/statistics", impersonate="chrome110")
        stats_data = s_res.json().get("statistics", [])
        stats_all = next((p for p in stats_data if p["period"] == "ALL"), None)
        
        full_stats = {}
        if stats_all:
            for g in stats_all["groups"]:
                for i in g["statisticsItems"]:
                    full_stats[i["name"]] = {"home": i["home"], "away": i["away"]}
        
        # Format post
        post = f"⚽ {match['homeTeam']['name']} {match['homeScore']['display']}-{match['awayScore']['display']} {match['awayTeam']['name']}\n\n"
        post += f"📊 Statistiche:\nPossesso: {full_stats.get('Ball possession',{}).get('home','?')} - {full_stats.get('Ball possession',{}).get('away','?')}\n"
        post += f"Tiri: {full_stats.get('Total shots',{}).get('home','?')} - {full_stats.get('Total shots',{}).get('away','?')}\n\n"
        post += "#Roma #SerieA #SofaScore"

        # Pubblica
        client = Client()
        client.login(BSKY_HANDLE, BSKY_PASSWORD)
        client.send_post(post)
        
        # Salva per Vercel
        dashboard = {
            "last_updated": datetime.now().strftime("%H:%M:%S"),
            "match": {"home": match['homeTeam']['name'], "away": match['awayTeam']['name'], "score": f"{match['homeScore']['display']}-{match['awayScore']['display']}"},
            "stats": full_stats,
            "post_text": post
        }
        with open("dashboard_data.json", "w") as f: json.dump(dashboard, f)
        print("✅ Completato!")

if __name__ == "__main__":
    main()
