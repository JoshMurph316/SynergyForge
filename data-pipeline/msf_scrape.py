
# msf_scrape_min.py
# Minimal, step-by-step scraper for SynergyForge
#
# What it does (small, safe start):
# 1) Opens https://msf.gg/characters with Selenium (headless by default)
# 2) Grabs links that look like character pages (anchor href contains '/characters/')
# 3) Builds a tiny record: { name, path, url, imageUrl? }
# 4) Writes JSON for the frontend
# 5) (Optional) Writes to Firestore if --firestore is passed
#
# Run examples:
#   python msf_scrape_min.py --limit 5 --output output/characters_min.json
#   python msf_scrape_min.py --limit 5 --output output/characters_min.json --firestore --project-id synergyforge-XXXX --service-account path/to/sa.json
#
# Notes:
# - This is intentionally simple so you can extend it as you learn the DOM.
# - Adjust CSS selectors if the site structure changes.
# - Be respectful: throttle requests and don't hammer the site.

import argparse, json, os, time
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Set

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Firestore (optional)
try:
    from firebase_admin import credentials, initialize_app
    from google.cloud import firestore
except Exception:
    credentials = None
    initialize_app = None
    firestore = None

@dataclass
class MiniCharacter:
    name: str
    path: str
    url: str
    imageUrl: str = ""

def setup_driver(headless: bool = True) -> webdriver.Chrome:
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    return driver

def slug_from_url(href: str) -> str:
    # last segment after /characters/<slug>
    return href.rstrip("/").split("/")[-1]

def scrape_character_list(limit: Optional[int] = None, headless: bool = True, throttle: float = 1.0) -> List[MiniCharacter]:
    base = "https://msf.gg/characters"
    driver = setup_driver(headless=headless)
    try:
        driver.get(base)
        # Wait until links to character pages appear. Adjust selector if needed.
        WebDriverWait(driver, 20).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[href*='/characters/']"))
        )
        time.sleep(throttle)

        anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='/characters/']")

        seen_paths: Set[str] = set()
        results: List[MiniCharacter] = []

        for a in anchors:
            href = a.get_attribute("href") or ""
            text = (a.text or "").strip()
            if not href or href.rstrip("/").endswith("/characters"):
                continue  # skip the index link itself
            slug = slug_from_url(href)
            if not slug or slug in seen_paths:
                continue

            # Try to find an image under/near the link (best-effort)
            img_url = ""
            try:
                img_el = a.find_element(By.TAG_NAME, "img")
                img_url = img_el.get_attribute("src") or ""
            except Exception:
                pass

            # Fallback for name: use slug if anchor text is empty
            name = text if text else slug.replace("-", " ").title()

            results.append(MiniCharacter(name=name, path=slug, url=href, imageUrl=img_url))
            seen_paths.add(slug)

            if limit and len(results) >= limit:
                break

        return results
    finally:
        try:
            driver.quit()
        except Exception:
            pass

def write_frontend_json(characters: List[MiniCharacter], output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    payload = [asdict(c) for c in characters]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Wrote JSON: {output_path} ({len(payload)} records)")

def write_firestore(characters: List[MiniCharacter], project_id: str, service_account: Optional[str] = None, collection: str = "characters_min"):
    if firestore is None:
        raise RuntimeError("Firestore libraries not installed. Run: pip install firebase-admin google-cloud-firestore")

    # Prefer Application Default Credentials (GOOGLE_APPLICATION_CREDENTIALS)
    client = None
    if service_account:
        if not os.path.isfile(service_account):
            raise FileNotFoundError(f"Service account JSON not found: {service_account}")
        cred = credentials.Certificate(service_account)
        initialize_app(cred, {"projectId": project_id})
        client = firestore.Client(project=project_id)
    else:
        client = firestore.Client(project=project_id)

    batch = client.batch()
    count = 0
    for c in characters:
        doc_id = c.path  # stable slug
        ref = client.collection(collection).document(doc_id)
        batch.set(ref, asdict(c))
        count += 1
        if count % 400 == 0:
            batch.commit()
            print(f"Committed {count} docs")
            batch = client.batch()
    if count % 400 != 0:
        batch.commit()
    print(f"Firestore write complete: {count} docs → collection '{collection}'")

def main():
    ap = argparse.ArgumentParser(description="SynergyForge minimal scraper")
    ap.add_argument("--limit", type=int, default=10, help="Limit number of characters to scrape (default 10)")
    ap.add_argument("--headless", action="store_true", help="Run Chrome headless")
    ap.add_argument("--no-headless", dest="headless", action="store_false")
    ap.add_argument("--throttle", type=float, default=1.0, help="Seconds to sleep between actions")
    ap.add_argument("--output", type=str, default="output/characters_min.json", help="Path to write frontend JSON")
    ap.add_argument("--firestore", action="store_true", help="Also write results to Firestore")
    ap.add_argument("--project-id", type=str, default=None, help="Your Firebase project id")
    ap.add_argument("--service-account", type=str, default=None, help="Path to service account JSON (optional)")
    ap.set_defaults(headless=True)
    args = ap.parse_args()

    chars = scrape_character_list(limit=args.limit, headless=args.headless, throttle=args.throttle)
    print(f"Scraped {len(chars)} characters")
    for c in chars[:3]:
        print(f" - {c.name} ({c.path}) → {c.url}")

    write_frontend_json(chars, args.output)

    if args.firestore:
        if not args.project_id:
            raise SystemExit("--project-id is required when using --firestore")
        write_firestore(chars, project_id=args.project_id, service_account=args.service_account)

if __name__ == "__main__":
    main()
