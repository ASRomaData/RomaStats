# Roma Stats Bot ⚽🔴

Bot automatico che pubblica le statistiche delle partite della Roma su **Bluesky**.
Gira su **GitHub Actions** (gratuito) con dashboard su **Vercel** (gratuito).

## Funzionalità

- ✅ Pubblica automaticamente dopo ogni partita della Roma
- ✅ Attivo solo nella finestra -1h / +3h dall'inizio partita
- ✅ Override manuale dalla dashboard (bottone "Genera ora")
- ✅ Dashboard responsive (computer, iPhone, iPad)
- ✅ Cronologia post pubblicati
- ✅ Anteprima del post prima della pubblicazione

---

## Setup completo

### 1. Crea il repository su GitHub

```bash
git clone https://github.com/TUO-USERNAME/roma-stats-bot.git
cd roma-stats-bot
# copia tutti i file qui dentro
git add .
git commit -m "Initial commit"
git push
```

Oppure su github.com → **New repository** → carica i file via interfaccia web.

> ⚠️ Il file `.github/workflows/bot.yml` deve trovarsi esattamente in quel percorso.
> Se carichi manualmente, crea il file su GitHub con **Add file → Create new file**
> e scrivi `.github/workflows/bot.yml` nel campo nome.

---

### 2. GitHub Secrets

**Settings → Secrets and variables → Actions → New repository secret**

| Secret          | Valore                                      |
|-----------------|---------------------------------------------|
| `BSKY_HANDLE`   | Il tuo handle Bluesky (es. `nome.bsky.social`) |
| `BSKY_PASSWORD` | App Password Bluesky (non la password principale) |

> Crea App Password su Bluesky: **Settings → Privacy and Security → App Passwords**

---

### 3. GitHub Personal Access Token (per il trigger manuale)

1. github.com → **Settings → Developer settings**
2. **Personal access tokens → Tokens (classic)**
3. **Generate new token (classic)**
4. Spunta: `repo` e `workflow`
5. Copia il token → servirà nel passo successivo

---

### 4. Deploy su Vercel

1. Vai su [vercel.com](https://vercel.com) → **New Project**
2. Importa il repository GitHub
3. Clicca **Deploy**
4. Dopo il deploy vai su **Settings → Environment Variables** e aggiungi:

| Variable         | Valore                          |
|------------------|---------------------------------|
| `GITHUB_TOKEN`   | Il token generato al passo 3    |
| `GITHUB_OWNER`   | Il tuo username GitHub          |
| `GITHUB_REPO`    | Nome del repository             |

5. **Redeploy** dall'interfaccia Vercel per applicare le variabili

---

### 5. Abilita GitHub Actions

- Tab **Actions** nel repo → clicca **"I understand my workflows, enable them"**
- Il bot parte automaticamente ogni 15 minuti

---

### 6. Test manuale

Dalla dashboard Vercel → tab **"Genera"** → clicca **"Genera ora (forza)"**

Oppure da GitHub: **Actions → Roma Match Bot → Run workflow → force: true**

---

## Struttura file

```
├── bot.py                        # Script principale bot
├── requirements.txt              # Dipendenze Python
├── index.html                    # Dashboard web
├── dashboard_data.json           # Dati ultima partita (aggiornato dal bot)
├── last_posted.json              # Anti-duplicati
├── vercel.json                   # Config Vercel + routing API
├── api/
│   └── trigger.py                # Serverless function trigger GitHub Actions
└── .github/
    └── workflows/
        └── bot.yml               # GitHub Actions workflow
```

## Come funziona

```
GitHub Actions (ogni 15 min, gratis)
    → controlla finestra partita Roma (-1h/+3h)
    → se partita finita: pubblica su Bluesky
    → aggiorna dashboard_data.json nel repo
    → commit automatico

Vercel (dashboard statica + API)
    → legge dashboard_data.json dal repo
    → mostra stats, anteprima, cronologia
    → bottone "Genera" → chiama /api/trigger
        → GitHub API workflow_dispatch
            → bot.py --force
```

## Personalizzazione

Per cambiare squadra, modifica in `bot.py`:
```python
TEAM_ID  = 2702   # ID SofaScore
HASHTAGS = "#Roma #SerieA #ASRoma #ForzaRoma #SofaScore"
```

ID di qualsiasi squadra nell'URL SofaScore:
`sofascore.com/football/team/NOME/ID`
