import time
import json
import os
import sys
import base64
from datetime import datetime, timezone, timedelta
from curl_cffi import requests as curl_requests
from atproto import Client

# ==========================================================
# CONFIGURAZIONE
# ==========================================================
BSKY_HANDLE   = os.environ.get("BSKY_HANDLE", "")
BSKY_PASSWORD = os.environ.get("BSKY_PASSWORD", "")
IG_USER_ID    = os.environ.get("IG_USER_ID", "")
IG_TOKEN      = os.environ.get("IG_ACCESS_TOKEN", "")
GH_REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "")   # auto in Actions: "owner/repo"
GH_TOKEN_BOT  = os.environ.get("GITHUB_TOKEN", "")        # auto in Actions

TEAM_ID       = 2702
TEAM_NAME     = "roma"
HASHTAGS_BSKY = "#Roma #SerieA #ASRoma #ForzaRoma #SofaScore"
HASHTAGS_IG   = "#Roma #SerieA #ASRoma #ForzaRoma #SofaScore #calcio #football #matchreport"
DATA_FILE     = "dashboard_data.json"
POSTED_FILE   = "last_posted.json"
CARD_FILE     = "match_card.png"
POST_WINDOW_HOURS = 3
FORCE_MAX_DAYS    = 7
# ==========================================================

FORCE_MODE = "--force" in sys.argv

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.sofascore.com/",
}

# ----------------------------------------------------------
# SOFASCORE HELPERS
# ----------------------------------------------------------

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
            start_ts  = event.get("startTimestamp", 0)
            hours_ago = (now_ts - start_ts) / 3600
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

# ----------------------------------------------------------
# TEXT FORMATTERS
# ----------------------------------------------------------

def format_post_bluesky(event, stats):
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
             f"{HASHTAGS_BSKY}")
    return text[:300] if len(text) > 300 else text

def format_caption_instagram(event, stats):
    """Longer caption for Instagram (2200 char limit)."""
    home    = event["homeTeam"]["name"]
    away    = event["awayTeam"]["name"]
    h_score = event.get("homeScore", {}).get("display", 0)
    a_score = event.get("awayScore", {}).get("display", 0)
    tourney = event.get("tournament", {}).get("name", "")

    def s(name):
        return stats.get(name, {"home": "-", "away": "-"})

    lines = [
        f"🟡🔴 Match Report: {home} {h_score}-{a_score} {away}",
        f"🏆 {tourney}" if tourney else "",
        "",
        f"⚽ Tiri (Porta): {s('Total shots')['home']} ({s('Shots on target')['home']}) "
        f"— {s('Total shots')['away']} ({s('Shots on target')['away']})",
    ]
    xg_h = s("Expected goals")["home"]
    if xg_h not in (None, "-"):
        lines.append(f"📊 xG: {xg_h} — {s('Expected goals')['away']}")
    lines += [
        f"⏳ Possesso: {s('Ball possession')['home']} — {s('Ball possession')['away']}",
        f"🎯 Passaggi acc.: {s('Accurate passes')['home']} — {s('Accurate passes')['away']}",
        f"🟨 Gialli: {s('Yellow cards')['home']} — {s('Yellow cards')['away']}",
        f"🔴 Rossi: {s('Red cards')['home']} — {s('Red cards')['away']}",
        f"📐 Corner: {s('Corner kicks')['home']} — {s('Corner kicks')['away']}",
        f"🚫 Falli: {s('Fouls')['home']} — {s('Fouls')['away']}",
        "",
        HASHTAGS_IG,
    ]
    return "\n".join(l for l in lines if l is not None)

# ----------------------------------------------------------
# MATCH CARD IMAGE (for Instagram)
# ----------------------------------------------------------

def generate_match_card(event, stats, output_path=CARD_FILE):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Pillow non installato, skip generazione immagine.")
        return False

    W, H   = 1080, 1080
    BG     = "#1a1a2e"
    RED    = "#e8003d"
    YELLOW = "#f5d800"
    WHITE  = "#ffffff"
    MUTED  = "#9999bb"
    SURF   = "#252545"

    home    = event["homeTeam"]["name"]
    away    = event["awayTeam"]["name"]
    h_score = str(event.get("homeScore", {}).get("display", "?"))
    a_score = str(event.get("awayScore", {}).get("display", "?"))
    tourney = event.get("tournament", {}).get("name", "")
    date_s  = ""
    ts      = event.get("startTimestamp", 0)
    if ts:
        date_s = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%d %b %Y")

    def s(name):
        v = stats.get(name, {"home": "-", "away": "-"})
        return str(v.get("home") or "-"), str(v.get("away") or "-")

    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    def font(size, bold=True):
        faces = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        ] if bold else [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ]
        for f in faces:
            try:
                return ImageFont.truetype(f, size)
            except:
                pass
        return ImageFont.load_default()

    f_score  = font(80)
    f_header = font(40)
    f_stat   = font(36)
    f_label  = font(30, bold=False)
    f_tiny   = font(26, bold=False)

    # Top bar
    draw.rectangle([0, 0, W, 14], fill=RED)
    draw.rectangle([0, 14, W, 20], fill=YELLOW)

    # "MATCH REPORT" header
    draw.text((W//2, 68), "MATCH REPORT", font=f_header, fill=YELLOW, anchor="mm")

    # Score box
    draw.rounded_rectangle([80, 110, W-80, 350], radius=28, fill=SURF)
    score_text = f"{home}  {h_score} - {a_score}  {away}"
    # If names are long, shorten
    if len(score_text) > 28:
        h_short = home.split()[-1] if " " in home else home
        a_short = away.split()[-1] if " " in away else away
        score_text = f"{h_short}  {h_score} - {a_score}  {a_short}"
    draw.text((W//2, 215), score_text, font=f_score, fill=WHITE, anchor="mm")
    sub = f"{tourney}  ·  {date_s}" if tourney else date_s
    draw.text((W//2, 318), sub, font=f_tiny, fill=MUTED, anchor="mm")

    # Stats rows
    stat_rows = [
        ("Tiri (Porta)",    f"{s('Total shots')[0]} ({s('Shots on target')[0]})",
                            f"{s('Total shots')[1]} ({s('Shots on target')[1]})"),
        ("xG",              *s("Expected goals")),
        ("Possesso",        *s("Ball possession")),
        ("Passaggi acc.",   *s("Accurate passes")),
        ("Falli",           *s("Fouls")),
        ("Corner",          *s("Corner kicks")),
        ("Gialli / Rossi",
            f"{s('Yellow cards')[0]} / {s('Red cards')[0]}",
            f"{s('Yellow cards')[1]} / {s('Red cards')[1]}"),
    ]

    # Filter out rows where both values are "-"
    stat_rows = [(l, h, a) for l, h, a in stat_rows
                 if not (h.strip("-/ ") == "" and a.strip("-/ ") == "")]

    row_h = min(78, (H - 420) // max(len(stat_rows), 1))
    y0    = 390

    for i, (label, hv, av) in enumerate(stat_rows):
        y    = y0 + i * row_h
        fill = SURF if i % 2 == 0 else BG
        draw.rectangle([60, y, W-60, y+row_h-3], fill=fill)
        draw.text((W//2,   y + row_h//2), label, font=f_label, fill=MUTED, anchor="mm")
        draw.text((175,    y + row_h//2), hv,    font=f_stat,  fill=RED,   anchor="mm")
        draw.text((W-175,  y + row_h//2), av,    font=f_stat,  fill=WHITE, anchor="mm")

    # Footer
    draw.rectangle([0, H-20, W, H-13], fill=YELLOW)
    draw.rectangle([0, H-13, W, H],    fill=RED)
    draw.text((W//2, H-52), "#ASRoma  #SerieA  #ForzaRoma  #SofaScore",
              font=f_tiny, fill=MUTED, anchor="mm")

    img.save(output_path, "PNG", optimize=True)
    print(f"Match card generata: {output_path}")
    return True

# ----------------------------------------------------------
# GITHUB: commit image so it's publicly accessible
# ----------------------------------------------------------

def commit_image_to_github(image_path):
    """Push match_card.png to the repo via GitHub API. Returns public raw URL."""
    if not GH_TOKEN_BOT or not GH_REPOSITORY:
        print("GITHUB_TOKEN / GITHUB_REPOSITORY non disponibili, skip commit immagine.")
        return None

    owner, repo = GH_REPOSITORY.split("/", 1)
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{image_path}"
    headers = {
        "Authorization": f"Bearer {GH_TOKEN_BOT}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    with open(image_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()

    # Get existing SHA (required for update)
    get_res = curl_requests.get(api_url, headers=headers, timeout=15)
    sha     = get_res.json().get("sha") if get_res.status_code == 200 else None

    body = {
        "message": "📸 Update match card [skip ci]",
        "content": content_b64,
        "branch":  "main",
    }
    if sha:
        body["sha"] = sha

    put_res = curl_requests.put(api_url, headers=headers, json=body, timeout=30)
    if put_res.status_code in (200, 201):
        raw_url = (f"https://raw.githubusercontent.com/{owner}/{repo}/main/{image_path}"
                   f"?t={int(time.time())}")
        print(f"Immagine committata su GitHub: {raw_url}")
        return raw_url

    print(f"Errore commit immagine: {put_res.status_code} — {put_res.text[:200]}")
    return None

# ----------------------------------------------------------
# INSTAGRAM GRAPH API
# ----------------------------------------------------------

def post_to_instagram(image_url, caption):
    if not IG_USER_ID or not IG_TOKEN:
        print("Credenziali Instagram non configurate, skip.")
        return False

    base = "https://graph.facebook.com/v19.0"

    # Step 1 — create media container
    create_res = curl_requests.post(
        f"{base}/{IG_USER_ID}/media",
        params={
            "image_url":  image_url,
            "caption":    caption,
            "access_token": IG_TOKEN,
        },
        timeout=30,
    )
    create_data = create_res.json()
    if "error" in create_data:
        print(f"Instagram errore container: {create_data['error'].get('message')}")
        return False

    creation_id = create_data.get("id")
    if not creation_id:
        print(f"Instagram: creation_id mancante — {create_data}")
        return False
    print(f"Instagram container creato: {creation_id}")

    # Step 2 — wait for the container to be ready
    time.sleep(5)

    # Step 3 — publish
    publish_res = curl_requests.post(
        f"{base}/{IG_USER_ID}/media_publish",
        params={
            "creation_id":  creation_id,
            "access_token": IG_TOKEN,
        },
        timeout=30,
    )
    publish_data = publish_res.json()
    if "error" in publish_data:
        print(f"Instagram errore publish: {publish_data['error'].get('message')}")
        return False

    media_id = publish_data.get("id")
    print(f"Instagram OK: media_id={media_id}")
    return True

# ----------------------------------------------------------
# BLUESKY
# ----------------------------------------------------------

def post_to_bluesky(text):
    if not BSKY_HANDLE or not BSKY_PASSWORD:
        print("Credenziali Bluesky non configurate, skip.")
        return False
    try:
        client = Client()
        client.login(BSKY_HANDLE.strip(), BSKY_PASSWORD.strip())
        post    = client.send_post(text)
        post_id = post.uri.split("/")[-1]
        print(f"Bluesky OK: https://bsky.app/profile/{BSKY_HANDLE}/post/{post_id}")
        return True
    except Exception as e:
        print(f"Errore Bluesky: {e}")
        return False

# ----------------------------------------------------------
# DASHBOARD DATA
# ----------------------------------------------------------

def save_dashboard_data(event, stats, post_text, published_bsky,
                        published_ig, force_mode):
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
        "published":    published_bsky,
        "published_ig": published_ig,
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
    print("dashboard_data.json aggiornato")

# ----------------------------------------------------------
# MAIN
# ----------------------------------------------------------

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

    # --- Bluesky ---
    bsky_text  = format_post_bluesky(match, stats)
    print(f"\n--- BLUESKY ({len(bsky_text)} chars) ---\n{bsky_text}\n")
    published_bsky = post_to_bluesky(bsky_text)

    # --- Instagram ---
    published_ig = False
    if IG_USER_ID and IG_TOKEN:
        print("\n--- INSTAGRAM ---")
        card_ok  = generate_match_card(match, stats)
        image_url = None
        if card_ok:
            # Commit the image to GitHub so it's publicly accessible via raw URL
            image_url = commit_image_to_github(CARD_FILE)
            if image_url:
                # Brief wait for GitHub CDN to propagate
                print("Attendo propagazione CDN GitHub (8s)...")
                time.sleep(8)
                ig_caption = format_caption_instagram(match, stats)
                print(f"Caption Instagram ({len(ig_caption)} chars):\n{ig_caption}\n")
                published_ig = post_to_instagram(image_url, ig_caption)
    else:
        print("Instagram non configurato (IG_USER_ID / IG_ACCESS_TOKEN mancanti), skip.")

    # --- Save anti-duplicate marker ---
    if (published_bsky or published_ig) and not FORCE_MODE:
        save_last_posted(str(match["id"]))

    save_dashboard_data(match, stats, bsky_text, published_bsky, published_ig, FORCE_MODE)
    print("Done.")

if __name__ == "__main__":
    main()
