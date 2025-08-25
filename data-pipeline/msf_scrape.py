
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

import argparse, json, os, time, re
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Tuple

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
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
    traits: list[str] = field(default_factory=list)
    abilities: list[dict] = field(default_factory=list)

# Canonical forms for common spaced-caps / collapsed tokens
CANON_MAP = {
    "HELLFIRECLUB": "Hellfire Club",
    "IMMORTALXMEN": "Immortal X Men",
    "CRUCIBLE": "Crucible",
    "CRUCIBLEOFFENSE": "Crucible Offense",
    "WAROFFENSE": "War Offense",
    "WARDEFENSE": "War Defense",
    "ARENA": "Arena",
    "RAIDS": "Raids",

    # Roles / factions often appear letter-spaced in yellow spans
    "PROTECTOR": "Protector",
    "SUPPORT": "Support",
    "CONTROLLER": "Controller",
    "BLASTER": "Blaster",
    "BRAWLER": "Brawler",
    "ACCURSED": "Accursed",

    # Common status effects / mechanics
    "DEFENSEUP": "Defense Up",
    "DEFENSEDOWN": "Defense Down",
    "OFFENSEUP": "Offense Up",
    "OFFENSEDOWN": "Offense Down",
    "HEALBLOCK": "Heal Block",
    "ABILITYBLOCK": "Ability Block",
    "IMMUNITY": "Immunity",
    "SAFEGUARD": "Safeguard",
    "SLOW": "Slow",
    "STUN": "Stun",
    "TAUNT": "Taunt",
    "TRAUMA": "Trauma",
    "BLEED": "Bleed",
    "BLIND": "Blind",
    "SILENCE": "Silence",
    "SPEEDUP": "Speed Up",
    "SPEEDBAR": "Speed Bar",
}

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
    return href.rstrip("/").split("/")[-1].strip().lower()

def _get_meta_content(driver, selector: str) -> str:
    try:
        el = driver.find_element(By.CSS_SELECTOR, selector)
        return (el.get_attribute("content") or "").strip()
    except Exception:
        return ""
    
def _clean_title(name: str) -> str:
    s = (name or "").strip()
    # remove everything from ' | MARVEL Strike Force...' onward (case-insensitive)
    s = re.sub(r"\s*\|\s*MARVEL Strike Force.*$", "", s, flags=re.I).strip()
    return s

def _split_camel(s: str) -> str:
    # "HellfireClub" -> "Hellfire Club"
    return re.sub(r"(?<!^)(?=[A-Z])", " ", s)

def _normalize_token(raw: str) -> str:
    """
    Normalize tokens extracted from ability-yellow spans.

    Handles:
    - NBSP / narrow NBSP / zero-width chars
    - Fully letter-spaced tokens (collapse to canonical)
    - Mixed cases like 'Defense UP' (treat 'UP' as 'Up', keep real acronyms)
    """
    if not raw:
        return ""

    # Normalize weird whitespace / invisible chars
    s = (raw
         .replace("\u00A0", " ")   # NBSP
         .replace("\u202F", " ")   # narrow NBSP
         .replace("\u2007", " ")   # figure space
         .replace("\u200B", "")    # zero-width space
         .replace("\u200C", "")    # ZWNJ
         .replace("\u200D", "")    # ZWJ
         )
    s = re.sub(r"\s+", " ", s).strip()

    # --- CASE A: Entire token is letter+space pattern (e.g., 'H E L L F I R E C L U B')
    # Collapse all spaces, then canonicalize if we know it.
    if re.fullmatch(r"(?:[A-Za-z]\s+)+[A-Za-z]", s):
        collapsed = re.sub(r"\s+", "", s).upper()  # 'HELLFIRECLUB'
        if collapsed in CANON_MAP:
            return CANON_MAP[collapsed]
        # Fallback: title the collapsed string ('Crucibleoffense' → 'Crucibleoffense')
        out = collapsed.title()
        # Small touch-ups
        out = out.replace("Xmen", "X Men")
        return out

    # --- CASE B: The token may contain smaller letter-spaced fragments inside
    # Collapse any *sub-strings* that match the spaced-caps pattern.
    def _collapse_fragment(m: re.Match) -> str:
        return m.group(0).replace(" ", "")
    s = re.sub(r"(?<!\w)(?:[A-Za-z]\s){1,}[A-Za-z](?!\w)", _collapse_fragment, s)

    # Unify separators & cleanup
    s = s.replace("-", " ").replace("_", " ")
    s = re.sub(r"\s+", " ", s).strip()

    # Word-level normalization
    KEEP_UPPER = {"AI", "ISO", "X"}   # keep true acronyms upper; treat 'UP' as 'Up'
    words = s.split(" ")
    out_words = []
    for w in words:
        uw = w.upper()
        # If this whole word matches a canonical collapsed form, use it
        if uw in CANON_MAP and " " not in CANON_MAP[uw]:
            out_words.append(CANON_MAP[uw])
            continue
        if uw in KEEP_UPPER:
            out_words.append(uw)
        elif uw == "UP":
            out_words.append("Up")
        else:
            out_words.append(w.title())

    out = " ".join(out_words)

    # Final canonicalization pass for multi-word collapsed combos (e.g., 'DefenseUp' assembled earlier)
    collapsed_again = re.sub(r"\s+", "", out).upper()
    if collapsed_again in CANON_MAP:
        return CANON_MAP[collapsed_again]

    return out

def _extract_traits_from_page(driver) -> list[str]:
    """
    Prefer href slugs for canonical trait names, fallback to text.
    Targets DOM like: ul.filter-group a.traits (your snippet).
    """
    els = driver.find_elements(
        By.CSS_SELECTOR,
        "ul.filter-group a.traits, a[href*='/characters/trait/'], a[href*='/en/characters/trait/']"
    )

    tokens = []
    for el in els:
        token = ""
        href = el.get_attribute("href") or ""
        text = (el.get_attribute("innerText") or el.text or "").strip()

        # 1) Prefer the slug in the href: .../trait/HellfireClub -> "Hellfire Club"
        if "/trait/" in href:
            last = href.rstrip("/").split("/")[-1]
            token = _normalize_token(last)

        # 2) Fallback to text (handles spaced-caps)
        if not token and text:
            token = _normalize_token(text)

        if token:
            tokens.append(token)

    # De-dup, preserve order (case-insensitive)
    seen = set()
    out = []
    for t in tokens:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            out.append(t)
    return out

def _get_text(el) -> str:
    # preserve newlines from <pre>, and decode any HTML entities
    try:
        txt = el.get_attribute("innerText")
        return (txt or "").strip()
    except Exception:
        return (el.text or "").strip()

def _extract_abilities_from_page(driver) -> tuple[list[dict], list[str]]:
    """
    Returns (abilities, yellowKeyTerms)
    abilities item shape:
      {
        "name": str,
        "imageUrl": str,
        "description": str,   # multi-line
        "energyCost": int|None
      }
    yellowKeyTerms: normalized unique list from <span class="ability-yellow">…</span>
    """
    abilities: list[dict] = []
    yellow_terms: list[str] = []

    # One "panel-content" per ability
    sections = driver.find_elements(
        By.CSS_SELECTOR,
        "div.hero-abilities .panel-content"
    )

    for sec in sections:
        try:
            # name
            try:
                name = sec.find_element(By.CSS_SELECTOR, ".ability-description h4").text.strip()
            except Exception:
                name = ""

            # icon
            try:
                img = sec.find_element(By.CSS_SELECTOR, ".ability-icon img").get_attribute("src") or ""
            except Exception:
                img = ""

            # description (the <pre> with class 'ability-text')
            try:
                pre = sec.find_element(By.CSS_SELECTOR, ".ability-description pre.ability-text")
                description = _get_text(pre)
            except Exception:
                description = ""

            # energy cost: count filled nodes if present
            try:
                full_nodes = sec.find_elements(By.CSS_SELECTOR, ".ability-description .ability-energy i.full")
                energyCost = len(full_nodes) if full_nodes else None
            except Exception:
                energyCost = None

            # yellow key terms inside the description
            try:
                spans = sec.find_elements(By.CSS_SELECTOR, ".ability-description pre.ability-text span.ability-yellow")
                for sp in spans:
                    token = _normalize_token(sp.text)
                    if token:
                        yellow_terms.append(token)
            except Exception:
                pass

            # add ability if we have at least a name or description
            if name or description:
                abilities.append({
                    "name": name,
                    "imageUrl": img,
                    "description": description,
                    "energyCost": energyCost
                })
        except Exception as e:
            print(f"[abilities] skip section: {e}")

    # De-dup yellow terms, keep order (case-insensitive)
    seen = set()
    dedup = []
    for t in yellow_terms:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            dedup.append(t)
    return abilities, dedup

def enrich_from_detail(driver, c: MiniCharacter, throttle: float = 1.0) -> List[str]:
    driver.get(c.url)
    WebDriverWait(driver, 12).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "meta[property='og:title'], h1"))
    )
    time.sleep(throttle)

    # Name (cleaned from og:title; fallback h1)
    name_meta = _get_meta_content(driver, "meta[property='og:title']")
    clean_name = _clean_title(name_meta)
    if not clean_name:
        try:
            clean_name = driver.find_element(By.CSS_SELECTOR, "h1").text.strip()
        except NoSuchElementException:
            clean_name = c.name

    # Image
    image = _get_meta_content(driver, "meta[property='og:image']")

    # Traits
    traits = _extract_traits_from_page(driver)

    # Abilities + yellow terms from ability text
    abilities, yellow_terms = _extract_abilities_from_page(driver)

    # Apply to object
    c.name = clean_name or c.name
    if image:
        c.imageUrl = image
    c.traits = traits or c.traits
    c.abilities = abilities or c.abilities

    # Return per-page keywords so caller can aggregate globally
    return yellow_terms

def scrape_character_list(
    index_url: str,
    limit: Optional[int] = None,
    headless: bool = True,
    throttle: float = 1.0
) -> Tuple[List[MiniCharacter], List[str]]:
    driver = setup_driver(headless=headless)
    global_terms: List[str] = []
    try:
        driver.get(index_url)
        WebDriverWait(driver, 20).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a[href*='/characters/']"))
        )
        time.sleep(throttle)

        anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='/characters/']")
        seen_paths = set()
        results: List[MiniCharacter] = []

        for a in anchors:
            href = a.get_attribute("href") or ""
            if not href:
                continue
            # Skip index links, trait links, or non-character links
            if href.rstrip("/").endswith("/characters"):
                continue
            if "/trait/" in href:
                continue
            if "/characters/" not in href:
                continue

            slug = slug_from_url(href)
            if not slug or slug in seen_paths:
                continue

            text = (a.text or "").strip()
            name_guess = text if text else slug.replace("-", " ").title()

            # Try to grab a nearby image (best-effort on index)
            img_url = ""
            try:
                img_el = a.find_element(By.TAG_NAME, "img")
                img_url = img_el.get_attribute("src") or ""
            except Exception:
                pass

            results.append(MiniCharacter(name=name_guess, path=slug, url=href, imageUrl=img_url))
            seen_paths.add(slug)
            if limit and len(results) >= limit:
                break

        # Enrich each character and aggregate yellow terms globally
        terms_seen = set()
        for c in results:
            try:
                page_terms = enrich_from_detail(driver, c, throttle=throttle)
                for t in page_terms:
                    k = t.lower()
                    if k not in terms_seen:
                        terms_seen.add(k)
                        global_terms.append(t)
            except Exception as e:
                print(f"[enrich] {c.path}: {e}")

        return results, global_terms

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

def write_keywords_json(keywords: list[str], output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sorted(keywords), f, ensure_ascii=False, indent=2)
    print(f"Wrote JSON: {output_path} ({len(keywords)} terms)")

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
    p = argparse.ArgumentParser(description="SynergyForge minimal scraper (characters, traits, abilities, keywords)")
    p.add_argument("--index-url", type=str, default="https://marvelstrikeforce.com/en/characters",
                   help="Character index page to start from")
    p.add_argument("--limit", type=int, default=10, help="Limit number of characters to scrape")
    p.add_argument("--headless", action="store_true", help="Run Chrome headless")
    p.add_argument("--no-headless", dest="headless", action="store_false")
    p.add_argument("--throttle", type=float, default=1.0, help="Seconds to sleep between actions")
    p.add_argument("--output", type=str, default="data-pipeline/output/characters_min.json", help="Path to write frontend JSON")
    p.add_argument("--keywords-out", type=str, default="", help="Path to write global ability keywords JSON (optional)")
    p.add_argument("--firestore", action="store_true", help="Also write results to Firestore")
    p.add_argument("--project-id", type=str, default=None, help="Your Firebase project id (required with --firestore)")
    p.add_argument("--service-account", type=str, default=None, help="Path to service account JSON (optional)")
    p.set_defaults(headless=True)
    args = p.parse_args()

    chars, terms = scrape_character_list(
        index_url=args.index_url,
        limit=args.limit,
        headless=args.headless,
        throttle=args.throttle
    )

    print(f"Scraped {len(chars)} characters")
    for c in chars[:3]:
        print(f" - {c.name} ({c.path}) → {c.url}")

    write_frontend_json(chars, args.output)

    # Keywords file path (default next to output)
    if args.keywords_out:
        kw_path = args.keywords_out
    else:
        out_dir = os.path.dirname(args.output) or "."
        kw_path = os.path.join(out_dir, "ability_keywords.json")

    write_keywords_json(terms, kw_path)

    if args.firestore:
        if not args.project_id:
            raise SystemExit("--project-id is required when using --firestore")
        write_firestore(chars, project_id=args.project_id, service_account=args.service_account)


if __name__ == "__main__":
    main()