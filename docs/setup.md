# SynergyForge Setup Guide

This guide covers local setup and deployment, plus the Python data pipeline.

---

## Prerequisites

- Node.js 18+
- npm
- Firebase CLI: `npm i -g firebase-tools`
- Python 3.9+ and pip
- Git
- A Firebase project

---

## Clone and install

```bash
git clone https://github.com/<your-username>/synergyforge.git
cd synergyforge
npm install
```

---

## Frontend env vars

```bash
cp .env.example .env
# Fill with Firebase Web config from console
```

---

## Run locally

- Start functions + hosting emulators (optional):
  ```bash
  firebase emulators:start --only functions,hosting
  ```
- Start Vite dev server:
  ```bash
  npm run dev
  ```

App is at http://localhost:5173

---

## Build and deploy

```bash
npm run build
firebase deploy
```

---

## Data pipeline

```bash
cd data-pipeline
pip install -r requirements.txt
python main.py
# or
python main.py --testing 5
```

---

## MSF API parameters (functions)

Create `functions/.env` from `functions/.env.example` and set:

```
MSF_CLIENT_ID=...
MSF_CLIENT_SECRET=...
MSF_TOKEN_URL=https://hydra-prod-dot-pip-msf-prod.appspot.com/oauth2/token
MSF_API_BASE=https://api.marvelstrikeforce.com
MSF_X_API_KEY=...
```

The frontend hits `/api/oauth/client` then `/api/msf?path=game/v1/...`.
