# SynergyForge
Data-driven team building for strategy gamers.

SynergyForge is a tactical team analysis tool for games like Marvel Strike Force. It calculates team synergy, visualizes turn order/speed tuning, and maps counter strategies.

Goals:
1. Portfolio-quality showcase of full-stack skills.
2. Foundation for a monetizable product.

---

## Features

Current focus
- Synergy Score (0–100)
- Turn Order Speed Tuner
- Counter Matrix with evidence tags

Planned enhancements
- ROI Optimizer — Gear/ISO/Stars efficiency
- Patch Diff Viewer — Before/after per game patch

---

## Tech stack

Frontend
- React (Vite)
- Firebase Hosting & Firestore

Backend & data
- Python for data scraping/normalization
- Firestore for structured storage

Hosting
- Firebase Hosting
- Firestore (NoSQL)

---

## Project structure

```
synergyforge/
  src/                    # React frontend
    services/             # Firebase & API
    lib/                  # API helpers
    types/                # TypeScript types
  data-pipeline/          # Python scrapers/processors
  docs/                   # Documentation
  .env.example            # Frontend env vars
  firebase.json           # Firebase config
  firestore.rules         # Firestore rules
  firestore.indexes.json  # Firestore indexes
  package.json
  README.md
```

---

## Getting started

1) Install dependencies
```
npm install
```

2) Configure environment variables (frontend)
```
cp .env.example .env
# Fill with Firebase Web config from project settings
```

3) Run locally
```
npm run dev
```

---

## MSF API (local dev)

Cloud Functions expose:
- POST /api/oauth/client — obtains client-credential token and sets msf_at cookie
- GET  /api/msf?path=game/v1/... — proxies to MSF API using cookie token
- GET  /api/whoami — debug endpoint

To run against emulators in dev:
1. Create `functions/.env` from `functions/.env.example` and fill values:
```
MSF_CLIENT_ID=...
MSF_CLIENT_SECRET=...
MSF_TOKEN_URL=https://hydra-prod-dot-pip-msf-prod.appspot.com/oauth2/token
MSF_API_BASE=https://api.marvelstrikeforce.com
MSF_X_API_KEY=...
```
2. Start emulators: `firebase emulators:start --only functions,hosting`
3. Start Vite: `npm run dev`

The frontend calls `ensureAppToken()` then requests traits/characters and renders a small preview.

---

## Deployment

```
npm run build
firebase deploy
```

Security headers are applied via `firebase.json`.

---

## License
MIT License

---

## Contact
Created by Joshua Murphy — Army Veteran & Web Developer
Email: joshmurph316@gmail.com
Portfolio: tbd
