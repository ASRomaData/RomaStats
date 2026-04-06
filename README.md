# Roma Stats Bot 🔴🟡

Bot automatico che pubblica le statistiche delle partite della Roma su **Bluesky**.  
Gira su **GitHub Actions** (gratuito) e la dashboard è hostata su **Vercel** (gratuito).

---

## Setup in 5 passi

### 1. Crea il repository su GitHub
- Vai su github.com → **New repository**
- Nome: `roma-stats-bot` (o quello che vuoi)
- Visibilità: **Public** (necessaria per Vercel gratuito)
- Carica tutti i file di questa cartella

### 2. Aggiungi i GitHub Secrets
Vai su: **Settings → Secrets and variables → Actions → New repository secret**

| Nome secret     | Valore                              |
|-----------------|-------------------------------------|
| `BSKY_HANDLE`   | Il tuo handle Bluesky (es. `tuoaccount.bsky.social`) |
| `BSKY_PASSWORD` | La tua **App Password** di Bluesky (non la password principale) |

> Per creare un App Password su Bluesky: **Settings → Privacy and Security → App Passwords**

### 3. Abilita GitHub Actions
- Vai su **Actions** nel tuo repo
- Clicca **"I understand my workflows, go ahead and enable them"**
- Il bot partirà automaticamente ogni 15 minuti

### 4. Deploya la dashboard su Vercel
1. Vai su [vercel.com](https://vercel.com) → **New Project**
2. Importa il tuo repository GitHub
3. Vercel rileva automaticamente che è un sito statico
4. Clicca **Deploy** → la dashboard è online in 30 secondi

### 5. (Opzionale) Lancia il bot manualmente
Vai su **Actions → Roma Match Bot → Run workflow** per testare subito.

---

## Come funziona

```
GitHub Actions (ogni 15 min)
    → controlla se siamo nella finestra di partita (-1h / +3h dall'inizio)
    → se SÌ: cerca partita terminata su SofaScore
    → se trovata: pubblica su Bluesky
    → aggiorna dashboard_data.json nel repo

Vercel (dashboard statica)
    → legge dashboard_data.json
    → mostra stats, anteprima post, cronologia
    → accessibile da browser, iPhone, iPad
```

## Struttura file

```
├── bot.py                  # Script principale del bot
├── requirements.txt        # Dipendenze Python
├── index.html              # Dashboard web
├── dashboard_data.json     # Dati ultima partita (aggiornato dal bot)
├── last_posted.json        # ID ultima partita postata (anti-duplicati)
└── .github/
    └── workflows/
        └── bot.yml         # Configurazione GitHub Actions
```

## Personalizzazione

Per cambiare squadra, modifica in `bot.py`:
```python
TEAM_ID   = 2702      # ID SofaScore della Roma
TEAM_NAME = "roma"
HASHTAGS  = "#Roma #SerieA #ASRoma #ForzaRoma #SofaScore"
```

Trovi l'ID di qualsiasi squadra nell'URL di SofaScore:  
`sofascore.com/football/team/NOME-SQUADRA/ID`
