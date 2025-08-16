# SynergyForge
*Data-driven team building for strategy gamers.*

**SynergyForge** is a tactical team analysis tool designed for strategy games like *Marvel Strike Force*.  
It calculates **team synergy scores**, visualizes **turn order speed tuning**, and maps **counter strategies** — making it an invaluable tool for both casual players and competitive strategists.

This version has been rebuilt from the ground up to serve two purposes:
1. **Portfolio Showcase** – A polished, professional-grade application to demonstrate data analysis, UI design, and full-stack development skills.
2. **Monetizable Product** – Donation links and potential subscription features for revenue generation.

---

## 📌 Features

### Current Development Focus
- **Synergy Score** (0–100) based on:
  - Tag cohesion
  - Role balance
  - Buff/Debuff coverage
  - Energy synergies
  - Ally passives
- **Turn Order Speed Tuner** with:
  - Base speed calculations
  - Pre-turn Turn Meter (TM) gains
  - Speed Up effects
  - Timeline visualization
- **Counter Matrix** with Evidence Tags:
  - Known counters for defense teams
  - Punch-up ratios
  - Confidence levels
  - Verified sources

### Planned Enhancements
- ROI Optimizer – Compare upgrade efficiency for Gear, ISO, and Stars
- Patch Diff Viewer – Show before/after stat & ability changes per game patch
- Premium analytics dashboard for subscribers

---

## 🛠 Tech Stack

**Frontend:**  
- React (Vite or CRA)
- Firebase Hosting & Firestore
- MUI (Material UI) for UI components
- Recharts for radar/timeline charts

**Backend & Data Processing:**  
- Python for data scraping and normalization
- Firestore for structured storage
- Custom APIs (optional future expansion)

**Hosting:**  
- Firebase Hosting
- Firestore (NoSQL database)

---

## 📂 Project Structure

```
synergyforge/
│
├── src/                      # React frontend
│   ├── components/           # UI components
│   ├── pages/                # Page components
│   ├── services/             # Firestore & API calls
│   ├── utils/                # Helper functions
│   ├── assets/               # Images, icons
│   └── styles/               # CSS/SCSS files
│
├── data-pipeline/            # Python scrapers & processors
│   ├── scrapers/
│   ├── processors/
│   ├── config/
│   └── output/
│
├── docs/                     # Documentation
│   ├── setup.md
│   ├── data-models.md
│   ├── firebase.md
│   └── monetization.md
│
├── .env.example              # Example environment variables
├── firebase.json             # Firebase config
├── firestore.rules           # Firestore security rules
├── firestore.indexes.json    # Firestore indexes
├── package.json
└── README.md
```

---

## 🚀 Getting Started

### 1. Clone the Repository
```bash
git clone https://github.com/<your-username>/synergyforge.git
cd synergyforge
```

### 2. Install Dependencies
```bash
npm install
```

### 3. Configure Environment Variables
Copy the example environment file:
```bash
cp .env.example .env
```
Edit `.env` with your Firebase project configuration:
```env
VITE_FIREBASE_API_KEY=your-api-key
VITE_FIREBASE_AUTH_DOMAIN=your-auth-domain
VITE_FIREBASE_PROJECT_ID=your-project-id
VITE_FIREBASE_STORAGE_BUCKET=your-storage-bucket
VITE_FIREBASE_MESSAGING_SENDER_ID=your-sender-id
VITE_FIREBASE_APP_ID=your-app-id
```

---

## 🖥 Running Locally
```bash
npm run dev
```
This starts the development server. The app will be available at:
```
http://localhost:5173
```
*(URL may differ depending on your dev setup.)*

---

## 📦 Deployment

1. **Login to Firebase**
```bash
firebase login
```

2. **Build the App**
```bash
npm run build
```

3. **Deploy to Firebase Hosting**
```bash
firebase deploy
```

---

## 📊 Data Pipeline (Python)

The `data-pipeline/` folder contains scrapers and processors that:
- Fetch raw character/game data
- Clean & normalize stats
- Push data to Firestore

To run the pipeline:
```bash
cd data-pipeline
pip install -r requirements.txt
python main.py
```

---

## 💰 Monetization

Planned monetization features:
- **Donation Links:** Ko-Fi / PayPal / Buy Me a Coffee integrated in UI
- **Premium Analytics:** Lock advanced analytics (ROI optimizer, advanced counters) behind Firebase Auth
- **Subscriptions:** Optional monthly plan via Stripe integration

---

## 📅 Development Roadmap

**Sprint A – Synergy + Turn Order**
- Synergy scoring algorithm
- Speed tuner visualizations

**Sprint B – Counter Matrix**
- Counter tracking system
- Verified evidence tagging

**Sprint C – Monetization & Portfolio Polish**
- Donation links
- Premium features
- Screenshots, landing page, and demo video

---

## 📜 License
MIT License – free to use, modify, and distribute.

---

## 📧 Contact
Created by **Joshua Murphy** – *Army Veteran & Web Developer*  
Email: [joshmurph316@gmail.com]  
Portfolio: [tbd]