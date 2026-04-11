import time
import json
import os
import sys
import base64
from datetime import datetime, timezone, timedelta
from curl_cffi import requests as curl_requests
from atproto import Client

BSKY_HANDLE   = os.environ.get("BSKY_HANDLE", "")
BSKY_PASSWORD = os.environ.get("BSKY_PASSWORD", "")
IG_USER_ID    = os.environ.get("IG_USER_ID", "")
IG_TOKEN      = os.environ.get("IG_ACCESS_TOKEN", "")
GH_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "")
GH_TOKEN_BOT  = os.environ.get("GITHUB_TOKEN", "")
TEAM_NAME         = "roma"
HASHTAGS_BSKY     = "#Roma #SerieA #ASRoma #ForzaRoma #SofaScore"
HASHTAGS_IG       = "#Roma #SerieA #ASRoma #ForzaRoma #SofaScore #calcio #football #matchreport"
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
    team = TEAM_NAME.lower()
    max_days = FORCE_MAX_DAYS if force else 3
    for days_ago in range(max_days):
        date_str = (now - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"
        res = safe_request(url)
        if not res:
            time.sleep(1)
            continue
        for event in res.json().get("events", []):
            home = event.get("homeTeam", {}).get("name", "").lower()
            away = event.get("awayTeam", {}).get("name", "").lower()
            status = event.get("status", {}).get("type", "")
            if team not in home and team not in away:
                continue
            if status != "finished":
                continue
            start_ts = event.get("startTimestamp", 0)
            hours_ago = (now_ts - start_ts) / 3600
            if not force and hours_ago > POST_WINDOW_HOURS:
                continue
            print(f"  Trovata: {event['homeTeam']['name']} {event.get('homeScore',{}).get('display','?')}-{event.get('awayScore',{}).get('display','?')} {event['awayTeam']['name']}")
            return event
        time.sleep(1.2)
    return None

def find_halftime_roma_match():
    now = datetime.now(timezone.utc)
    team = TEAM_NAME.lower()
    date_str = now.strftime("%Y-%m-%d")
    url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}"
    res = safe_request(url)
    if not res:
        return None
    for event in res.json().get("events", []):
        home = event.get("homeTeam", {}).get("name", "").lower()
        away = event.get("awayTeam", {}).get("name", "").lower()
        status = event.get("status", {})
        s_type = status.get("type", "")
        s_desc = status.get("description", "").lower()
        if team not in home and team not in away:
            continue
        if s_type == "inprogress" and any(k in s_desc for k in ["ht", "half", "interval"]):
            print(f"  Partita all'intervallo: {event['homeTeam']['name']} {event.get('homeScore',{}).get('display','?')}-{event.get('awayScore',{}).get('display','?')} {event['awayTeam']['name']}")
            return event
    return None

def is_match_window_today():
    now = datetime.now(timezone.utc)
    now_ts = now.timestamp()
    team = TEAM_NAME.lower()
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

def get_stats_for_period(event_id, period="ALL"):
    url = f"https://api.sofascore.com/api/v1/event/{event_id}/statistics"
    res = safe_request(url)
    if not res:
        return {}
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

# --- Stats helpers ---

def sv(stats, name, side):
    v = stats.get(name, {}).get(side)
    return str(v) if v not in (None, "", "-") else "-"

def calc_precision(stats, side):
    try:
        acc_raw = stats.get("Accurate passes", {}).get(side, "")
        tot_raw = stats.get("Total passes", {}).get(side, "")
        # SofaScore sometimes returns "387/450 (86%)" in acc_raw
        if "/" in str(acc_raw):
            parts = str(acc_raw).split("/")
            acc = float(parts[0].strip())
            tot = float(parts[1].strip().split()[0])
            return f"{round(acc/tot*100)}%"
        if tot_raw not in (None, "", "-"):
            acc = float(str(acc_raw).replace("%","").strip())
            tot = float(str(tot_raw).replace("%","").strip())
            if tot > 0:
                return f"{round(acc/tot*100)}%"
    except Exception:
        pass
    return sv(stats, "Accurate passes", side)  # fallback: show raw value

def calc_xgot(stats, side, event):
    try:
        if side == "home":
            goals = int(event.get("homeScore", {}).get("display", 0) or 0)
            saves_opp = stats.get("Goalkeeper saves", {}).get("away")
        else:
            goals = int(event.get("awayScore", {}).get("display", 0) or 0)
            saves_opp = stats.get("Goalkeeper saves", {}).get("home")
        saves = int(saves_opp) if saves_opp not in (None, "-", "") else 0
        return str(goals + saves)
    except Exception:
        return "-"

def build_stats_lines(event, stats, halftime=False):
    h_score = event.get("homeScore", {}).get("display", "?")
    a_score = event.get("awayScore", {}).get("display", "?")
    home    = event["homeTeam"]["name"]
    away    = event["awayTeam"]["name"]
    tourney = event.get("tournament", {}).get("name", "")
    label   = "Statistiche 1° Tempo" if halftime else "Match Report"

    xgoth = calc_xgot(stats, "home", event)
    xgota = calc_xgot(stats, "away", event)
    prech = calc_precision(stats, "home")
    preca = calc_precision(stats, "away")
    xgh   = sv(stats, "Expected goals", "home")
    xga   = sv(stats, "Expected goals", "away")
    bch   = sv(stats, "Big chances",    "home")
    bca   = sv(stats, "Big chances",    "away")

    lines = [
        f"\U0001f7e1\U0001f534 {label}: {home} {h_score}-{a_score} {away}",
        f"\U0001f3c6 {tourney}" if tourney else "",
        "",
        f"\u26bd Tiri (nello specchio): {sv(stats,'Total shots','home')} ({sv(stats,'Shots on target','home')}) - {sv(stats,'Total shots','away')} ({sv(stats,'Shots on target','away')})",
    ]
    if xgh != "-":
        lines.append(f"\U0001f4ca xG: {xgh} - {xga}  |  xG in porta: {xgoth} - {xgota}")
    else:
        lines.append(f"\U0001f4ca xG in porta: {xgoth} - {xgota}")
    lines += [
        f"\u23f3 Possesso: {sv(stats,'Ball possession','home')} - {sv(stats,'Ball possession','away')}",
        f"\U0001f3af Precisione: {prech} - {preca}",
    ]
    if bch != "-":
        lines.append(f"\U0001f525 Grandi Occasioni: {bch} - {bca}")
    return [l for l in lines if l is not None]

def format_post_bluesky(event, stats, halftime=False):
    lines = build_stats_lines(event, stats, halftime) + ["", HASHTAGS_BSKY]
    text = "\n".join(lines)
    return text[:300] if len(text) > 300 else text

def format_caption_instagram(event, stats, halftime=False):
    lines = build_stats_lines(event, stats, halftime)
    lines += [
        "",
        f"\U0001f7e8 Gialli: {sv(stats,'Yellow cards','home')} - {sv(stats,'Yellow cards','away')}",
        f"\U0001f4d0 Corner: {sv(stats,'Corner kicks','home')} - {sv(stats,'Corner kicks','away')}",
        "",
        HASHTAGS_IG,
    ]
    return "\n".join(l for l in lines if l is not None)

# --- Match card image ---

def generate_match_card(event, stats, output_path=CARD_FILE, halftime=False):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Pillow non installato.")
        return False
    W, H = 1080, 1080
    BG = "#1a1a2e"; RED = "#e8003d"; YELLOW = "#f5d800"
    WHITE = "#ffffff"; MUTED = "#9999bb"; SURF = "#252545"
    home = event["homeTeam"]["name"]; away = event["awayTeam"]["name"]
    h_score = str(event.get("homeScore",{}).get("display","?")); a_score = str(event.get("awayScore",{}).get("display","?"))
    tourney = event.get("tournament",{}).get("name","")
    ts = event.get("startTimestamp",0)
    date_s = datetime.fromtimestamp(ts,tz=timezone.utc).strftime("%d %b %Y") if ts else ""
    header = "STATISTICHE 1 TEMPO" if halftime else "MATCH REPORT"
    xgoth = calc_xgot(stats,"home",event); xgota = calc_xgot(stats,"away",event)
    prech = calc_precision(stats,"home");  preca = calc_precision(stats,"away")
    img = Image.new("RGB",(W,H),BG); draw = ImageDraw.Draw(img)
    def font(size,bold=True):
        faces = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf","/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"] if bold else ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf","/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]
        for f in faces:
            try: return ImageFont.truetype(f,size)
            except: pass
        return ImageFont.load_default()
    f_score=font(76);f_hdr=font(36);f_stat=font(32);f_lbl=font(26,bold=False);f_tiny=font(22,bold=False)
    draw.rectangle([0,0,W,14],fill=RED); draw.rectangle([0,14,W,20],fill=YELLOW)
    draw.text((W//2,62),header,font=f_hdr,fill=YELLOW,anchor="mm")
    draw.rounded_rectangle([80,105,W-80,335],radius=26,fill=SURF)
    h_s=home.split()[-1] if len(home)>12 else home; a_s=away.split()[-1] if len(away)>12 else away
    draw.text((W//2,200),f"{h_s}  {h_score} - {a_score}  {a_s}",font=f_score,fill=WHITE,anchor="mm")
    sub=f"{tourney}  .  {date_s}" if tourney else date_s
    draw.text((W//2,300),sub,font=f_tiny,fill=MUTED,anchor="mm")
    stat_rows=[
        ("Tiri (nello specchio)",f"{sv(stats,'Total shots','home')} ({sv(stats,'Shots on target','home')})",f"{sv(stats,'Total shots','away')} ({sv(stats,'Shots on target','away')})"),
        ("xG  |  xG in porta",f"{sv(stats,'Expected goals','home')}  |  {xgoth}",f"{sv(stats,'Expected goals','away')}  |  {xgota}"),
        ("Possesso",sv(stats,"Ball possession","home"),sv(stats,"Ball possession","away")),
        ("Precisione",prech,preca),
        ("Grandi Occasioni",sv(stats,"Big chances","home"),sv(stats,"Big chances","away")),
        ("Gialli / Rossi",f"{sv(stats,'Yellow cards','home')} / {sv(stats,'Red cards','home')}",f"{sv(stats,'Yellow cards','away')} / {sv(stats,'Red cards','away')}"),
    ]
    stat_rows=[(l,h,a) for l,h,a in stat_rows if not(h.strip("-/ |")==""and a.strip("-/ |")=="")]
    row_h=min(74,(H-418)//max(len(stat_rows),1)); y0=370
    for i,(label,hv,av) in enumerate(stat_rows):
        y=y0+i*row_h
        draw.rectangle([60,y,W-60,y+row_h-3],fill=SURF if i%2==0 else BG)
        draw.text((W//2,y+row_h//2),label,font=f_lbl,fill=MUTED,anchor="mm")
        draw.text((165,y+row_h//2),hv,font=f_stat,fill=RED,anchor="mm")
        draw.text((W-165,y+row_h//2),av,font=f_stat,fill=WHITE,anchor="mm")
    draw.rectangle([0,H-20,W,H-13],fill=YELLOW); draw.rectangle([0,H-13,W,H],fill=RED)
    draw.text((W//2,H-48),"#ASRoma  #SerieA  #ForzaRoma  #SofaScore",font=f_tiny,fill=MUTED,anchor="mm")
    img.save(output_path,"PNG",optimize=True); print(f"Match card generata: {output_path}"); return True

# --- GitHub image commit ---

def commit_image_to_github(image_path):
    if not GH_TOKEN_BOT or not GH_REPOSITORY:
        print("GITHUB_TOKEN/GITHUB_REPOSITORY mancanti."); return None
    owner,repo = GH_REPOSITORY.split("/",1)
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{image_path}"
    gh_h = {"Authorization":f"Bearer {GH_TOKEN_BOT}","Accept":"application/vnd.github+json","Content-Type":"application/json","X-GitHub-Api-Version":"2022-11-28"}
    with open(image_path,"rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()
    get_res = curl_requests.get(api_url,headers=gh_h,timeout=15)
    sha = get_res.json().get("sha") if get_res.status_code==200 else None
    body = json.dumps({"message":"update match card [skip ci]","content":content_b64,"branch":"main",**({"sha":sha} if sha else {})}).encode()
    put_res = curl_requests.put(api_url,headers=gh_h,data=body,timeout=30)
    if put_res.status_code in(200,201):
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/main/{image_path}"
        print(f"Immagine su GitHub: {raw_url}"); return raw_url
    print(f"Errore commit: {put_res.status_code} — {put_res.text[:200]}"); return None

def verify_url_accessible(url,retries=3,wait=8):
    for attempt in range(retries):
        try:
            r = curl_requests.head(url,timeout=10)
            if r.status_code==200:
                print(f"  URL accessibile (tentativo {attempt+1})"); return True
        except Exception: pass
        if attempt<retries-1:
            print(f"  URL non pronto, attendo {wait}s..."); time.sleep(wait)
    print("  WARN: URL non verificato, provo comunque."); return False

# --- @officialasroma photo ---

def get_officialasroma_latest_photo():
    ig_h = {
        "User-Agent":"Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "Accept":"application/json, text/plain, */*","Accept-Language":"it-IT,it;q=0.9,en;q=0.8",
        "x-ig-app-id":"936619743392459","Referer":"https://www.instagram.com/",
    }
    try:
        res = curl_requests.get("https://www.instagram.com/api/v1/users/web_profile_info/?username=officialasroma",headers=ig_h,impersonate="safari_ios17_2",timeout=20)
        if res.status_code!=200:
            print(f"  @officialasroma: status {res.status_code}"); return None
        edges=(res.json().get("data",{}).get("user",{}).get("edge_owner_to_timeline_media",{}).get("edges",[]))
        for edge in edges:
            node=edge.get("node",{})
            if node.get("is_video"): continue
            url=node.get("display_url")
            if url: print("  @officialasroma foto OK."); return url
    except Exception as e:
        print(f"  Errore scraping @officialasroma: {e}")
    return None

# --- Instagram Graph API ---

def post_to_instagram(image_url,caption):
    if not IG_USER_ID or not IG_TOKEN:
        print("Credenziali Instagram mancanti, skip."); return False
    base="https://graph.facebook.com/v19.0"
    print(f"  Container con URL: {image_url[:80]}...")
    cr = curl_requests.post(f"{base}/{IG_USER_ID}/media",data={"image_url":image_url,"caption":caption,"access_token":IG_TOKEN},timeout=30)
    cd = cr.json()
    print(f"  Container response: {cd}")
    if "error" in cd:
        e=cd["error"]; print(f"  IG errore container [{e.get('code')}]: {e.get('message')}"); return False
    creation_id=cd.get("id")
    if not creation_id:
        print(f"  IG: creation_id mancante"); return False
    print(f"  Container OK: {creation_id}, attendo 8s...")
    time.sleep(8)
    pr = curl_requests.post(f"{base}/{IG_USER_ID}/media_publish",data={"creation_id":creation_id,"access_token":IG_TOKEN},timeout=30)
    pd = pr.json()
    print(f"  Publish response: {pd}")
    if "error" in pd:
        e=pd["error"]; print(f"  IG errore publish [{e.get('code')}]: {e.get('message')}"); return False
    print(f"  Instagram OK: media_id={pd.get('id')}"); return True

# --- Bluesky ---

def post_to_bluesky(text):
    if not BSKY_HANDLE or not BSKY_PASSWORD:
        print("Credenziali Bluesky mancanti, skip."); return False
    try:
        client=Client(); client.login(BSKY_HANDLE.strip(),BSKY_PASSWORD.strip())
        post=client.send_post(text); post_id=post.uri.split("/")[-1]
        print(f"Bluesky OK: https://bsky.app/profile/{BSKY_HANDLE}/post/{post_id}"); return True
    except Exception as e:
        print(f"Errore Bluesky: {e}"); return False

# --- Dashboard ---

def save_dashboard_data(event,stats,post_text,published_bsky,published_ig,force_mode,halftime=False):
    h_score=event.get("homeScore",{}).get("display",0); a_score=event.get("awayScore",{}).get("display",0)
    start_ts=event.get("startTimestamp",0)
    data={
        "last_updated":datetime.now(timezone.utc).isoformat(),"force_mode":force_mode,
        "halftime_mode":halftime,"published":published_bsky,"published_ig":published_ig,
        "match":{"id":event["id"],"home":event["homeTeam"]["name"],"away":event["awayTeam"]["name"],
            "score":f"{h_score}-{a_score}","h_score":h_score,"a_score":a_score,
            "date":datetime.fromtimestamp(start_ts,tz=timezone.utc).strftime("%d %b %Y %H:%M") if start_ts else "",
            "tournament":event.get("tournament",{}).get("name","")},
        "stats":{
            "total_shots":{"home":sv(stats,"Total shots","home"),"away":sv(stats,"Total shots","away")},
            "shots_on_target":{"home":sv(stats,"Shots on target","home"),"away":sv(stats,"Shots on target","away")},
            "expected_goals":{"home":sv(stats,"Expected goals","home"),"away":sv(stats,"Expected goals","away")},
            "xg_on_target":{"home":calc_xgot(stats,"home",event),"away":calc_xgot(stats,"away",event)},
            "ball_possession":{"home":sv(stats,"Ball possession","home"),"away":sv(stats,"Ball possession","away")},
            "passing_precision":{"home":calc_precision(stats,"home"),"away":calc_precision(stats,"away")},
            "big_chances":{"home":sv(stats,"Big chances","home"),"away":sv(stats,"Big chances","away")},
            "accurate_passes":{"home":sv(stats,"Accurate passes","home"),"away":sv(stats,"Accurate passes","away")},
            "fouls":{"home":sv(stats,"Fouls","home"),"away":sv(stats,"Fouls","away")},
            "corner_kicks":{"home":sv(stats,"Corner kicks","home"),"away":sv(stats,"Corner kicks","away")},
            "yellow_cards":{"home":sv(stats,"Yellow cards","home"),"away":sv(stats,"Yellow cards","away")},
            "red_cards":{"home":sv(stats,"Red cards","home"),"away":sv(stats,"Red cards","away")},
        },
        "post_text":post_text,
    }
    with open(DATA_FILE,"w",encoding="utf-8") as f:
        json.dump(data,f,ensure_ascii=False,indent=2)
    print("dashboard_data.json aggiornato")

# --- IG flow ---

def publish_to_instagram(match,stats,halftime=False):
    print("\n--- INSTAGRAM ---")
    ig_caption=format_caption_instagram(match,stats,halftime=halftime)
    print(f"Caption ({len(ig_caption)} chars):\n{ig_caption}\n")
    image_url=get_officialasroma_latest_photo()
    if not image_url:
        print("  Genero match card...")
        if generate_match_card(match,stats,halftime=halftime):
            image_url=commit_image_to_github(CARD_FILE)
            if image_url:
                verify_url_accessible(image_url,retries=3,wait=8)
    if not image_url:
        print("  Nessuna image_url, skip Instagram."); return False
    return post_to_instagram(image_url,ig_caption)

# --- Main ---

def main():
    print(f"Roma Bot — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    mode_str="HALFTIME" if HALFTIME_MODE else("FORCE" if FORCE_MODE else "AUTO")
    print(f"Modalita: {mode_str}")

    if HALFTIME_MODE:
        match=find_halftime_roma_match()
        if not match:
            print("Nessuna partita Roma all'intervallo."); return
        stats=get_stats_for_period(match["id"],"1ST")
        if not stats:
            print("Statistiche 1° tempo non disponibili."); return
        _,last_ht_id=load_last_posted()
        ht_key=f"ht_{match['id']}"
        if last_ht_id==ht_key:
            print("Statistiche intervallo già postate, skip."); return
        bsky_text=format_post_bluesky(match,stats,halftime=True)
        print(f"\n--- BLUESKY ---\n{bsky_text}\n")
        published_bsky=post_to_bluesky(bsky_text)
        published_ig=False
        if IG_USER_ID and IG_TOKEN:
            published_ig=publish_to_instagram(match,stats,halftime=True)
        if published_bsky or published_ig:
            save_last_posted(halftime_id=ht_key)
        save_dashboard_data(match,stats,bsky_text,published_bsky,published_ig,False,halftime=True)
        print("Done."); return

    if not FORCE_MODE:
        in_window,upcoming=is_match_window_today()
        if not in_window:
            if upcoming:
                start=datetime.fromtimestamp(upcoming.get("startTimestamp",0),tz=timezone.utc)
                print(f"Fuori finestra. Prossima: {upcoming['homeTeam']['name']} vs {upcoming['awayTeam']['name']} — {start.strftime('%d %b %H:%M UTC')}")
            else:
                print("Nessuna partita Roma in finestra oggi.")
            return
        print("Nella finestra di partita, procedo...")

    match=find_recent_roma_match(force=FORCE_MODE)
    if not match:
        print(f"Nessuna partita negli ultimi {FORCE_MAX_DAYS}gg." if FORCE_MODE else "Nessuna partita terminata nella finestra."); return
    last_id,_=load_last_posted()
    if not FORCE_MODE and str(match.get("id"))==str(last_id):
        print("Partita già postata, skip."); return
    stats=get_all_stats(match["id"])
    if not stats:
        print("Statistiche non ancora disponibili."); return
    bsky_text=format_post_bluesky(match,stats)
    print(f"\n--- BLUESKY ---\n{bsky_text}\n")
    published_bsky=post_to_bluesky(bsky_text)
    published_ig=False
    if IG_USER_ID and IG_TOKEN:
        published_ig=publish_to_instagram(match,stats,halftime=False)
    else:
        print("Instagram non configurato, skip.")
    if(published_bsky or published_ig) and not FORCE_MODE:
        save_last_posted(event_id=str(match["id"]))
    save_dashboard_data(match,stats,bsky_text,published_bsky,published_ig,FORCE_MODE)
    print("Done.")

if __name__=="__main__":
    main()
