# SynergyForge Setup Guide

This document walks you through setting up **SynergyForge** from a fresh `git pull` to a live deployment on Firebase Hosting, including running the Python data pipeline.

---

## 1️⃣ Prerequisites

Before starting, ensure you have the following installed:

- **Node.js** (v18 or later) – [Download](https://nodejs.org/)
- **npm** (comes with Node.js)
- **Firebase CLI** – Install globally:
  ```bash
  npm install -g firebase-tools
  ```
- **Python** (v3.9 or later) – [Download](https://www.python.org/downloads/)
- **pip** (comes with Python)
- **Git** – [Download](https://git-scm.com/downloads)
- A Firebase project set up in the [Firebase Console](https://console.firebase.google.com/)

---

## 2️⃣ Clone the Repository

```bash
git clone https://github.com/<your-username>/synergyforge.git
cd synergyforge
```

---

## 3️⃣ Install JavaScript Dependencies

```bash
npm install
```

---

## 4️⃣ Environment Variables

Copy the example environment file and edit it:

```bash
cp .env.example .env
```

Fill in the `.env` file with your Firebase configuration values:

```env
VITE_FIREBASE_API_KEY=your-api-key
VITE_FIREBASE_AUTH_DOMAIN=your-auth-domain
VITE_FIREBASE_PROJECT_ID=your-project-id
VITE_FIREBASE_STORAGE_BUCKET=your-storage-bucket
VITE_FIREBASE_MESSAGING_SENDER_ID=your-sender-id
VITE_FIREBASE_APP_ID=your-app-id
```

You can find these values in your Firebase Console → Project Settings.

---

## 5️⃣ Firebase Initialization (First Time Only)

Login to Firebase:

```bash
firebase login
```

Initialize hosting (if not already done):

```bash
firebase init hosting
```

When prompted:
- **Select your Firebase project**
- Public directory: `dist` (if using Vite) or `build` (if using CRA)
- Configure as SPA: **Yes**
- Overwrite `index.html`: **No**

---

## 6️⃣ Running Locally

```bash
npm run dev
```

Your app should be available at:
```
http://localhost:5173
```
*(Port may differ based on setup)*

---

## 7️⃣ Building for Production

```bash
npm run build
```

This generates the production-ready files in `/dist` (or `/build`).

---

## 8️⃣ Deploying to Firebase

```bash
firebase deploy
```

After a few moments, Firebase will return your **live app URL**.

---

## 9️⃣ Data Pipeline Setup (Python)

The `data-pipeline/` folder contains Python scripts for:
- Scraping raw game data
- Cleaning and normalizing character stats
- Uploading data to Firestore

### Install Python Dependencies

```bash
cd data-pipeline
pip install -r requirements.txt
```

### Running the Data Pipeline

```bash
python main.py
```

Options may include:
- `--testing <n>` → Scrape only `<n>` characters for quick testing

Example:
```bash
python main.py --testing 5
```

---

## 🔄 Recommended Workflow

1. Pull the latest code:
   ```bash
   git pull
   ```
2. Update dependencies:
   ```bash
   npm install
   pip install -r data-pipeline/requirements.txt
   ```
3. Run the data pipeline to refresh data:
   ```bash
   python data-pipeline/main.py
   ```
4. Start local dev:
   ```bash
   npm run dev
   ```
5. Build & deploy:
   ```bash
   npm run build && firebase deploy
   ```

---

## ✅ You’re Ready!

You now have **SynergyForge** running locally and deployed to Firebase, with fresh game data pulled from the pipeline.
