# data-pipeline/msf_scrape.py
# SynergyForge scraper (characters → traits, abilities, keywords + global stats merge via CSV/DOM)
#
# Key updates in this version:
# - CSV-first enrichment from /hero-total-stats (then DOM fallback)
# - Robust CSV header normalization (handles 'CHARACTERS\xa0', 'RESIST\xa0', etc.)
# - Name column detection via 'CHARACTERS'/'CHARACTER'/'NAME'/'HERO' (NBSP tolerant)
# - Header mapping: RESIST -> RESISTANCE + extra stats included (CRIT_DAMAGE, etc.)
# - Cookie banner click on both stats page and character detail pages
# - Debug prints: headers, sample rows, sample names, and per-character merges
#
# Usage (tiny sample):
#   python data-pipeline/msf_scrape.py \
#     --limit 5 \
#     --output data-pipeline/output/characters_min.json \
#     --no-headless \
#     --throttle 1.0

import argparse
import csv
import glob
import json
import os
import re
import string
import time
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Tuple

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException

# Canonical map (split into utils/canon_map.py)
from utils.canon_map import CANON_MAP as DEFAULT_CANON_MAP, KEEP_UPPER, load_canon_map

# Firestore (optional)
try:
    from firebase_admin import credentials, initialize_app
    from google.cloud import firestore
except Exception:
    credentials = None
    initialize_app = None
    firestore = None

# ---------------------------
# Canonical map (mutable copy)
# ---------------------------
CANON = DEFAULT_CANON_MAP.copy()

# ---------------------------
# Data shape
# ---------------------------
@dataclass
class MiniCharacter:
    name: str
    path: str                 # stable slug (lowercase)
    url: str
    imageUrl: str = ""
    traits: List[str] = field(default_factory=list)
    abilities: List[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)        # merged stat dictionary
    power: Optional[int] = None                      # top-level POWER

# ---------------------------
# Browser setup
# ---------------------------
def setup_driver(headless: bool = True, download_dir: Optional[str] = None) -> webdriver.Chrome:
    """Create a Chrome WebDriver with sensible defaults + optional download dir."""
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1366,900")

    if download_dir:
        os.makedirs(download_dir, exist_ok=True)
        prefs = {
            "download.default_directory": os.path.abspath(download_dir),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            "safebrowsing.disable_download_protection": True,
        }
        opts.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

    # allow downloads in headless where supported
    if download_dir:
        try:
            driver.execute_cdp_cmd(
                "Page.setDownloadBehavior",
                {"behavior": "allow", "downloadPath": os.path.abspath(download_dir)}
            )
        except Exception:
            pass
    return driver

def slug_from_url(href: str) -> str:
    """Take the last URL path segment and lowercase it for stable doc IDs."""
    return href.rstrip("/").split("/")[-1].strip().lower()

def _get_meta_content(driver, selector: str) -> str:
    try:
        el = driver.find_element(By.CSS_SELECTOR, selector)
        return (el.get_attribute("content") or "").strip()
    except Exception:
        return ""

def _clean_title(name: str) -> str:
    """'Azazel | MARVEL Strike Force | Scopely' → 'Azazel'."""
    s = (name or "").strip()
    return re.sub(r"\s*\|\s*MARVEL Strike Force.*$", "", s, flags=re.I).strip()

def _split_camel(s: str) -> str:
    """'HellfireClub' → 'Hellfire Club'."""
    return re.sub(r"(?<!^)(?=[A-Z])", " ", s)

def _normalize_token(raw: str) -> str:
    """
    Normalize tokens extracted from ability-yellow spans.
    - Handle spaced-caps, NBSP/zero-width chars, 'UP' casing, and canonical combos via CANON.
    """
    if not raw:
        return ""
    s = (raw
         .replace("\u00A0", " ")
         .replace("\u202F", " ")
         .replace("\u2007", " ")
         .replace("\u200B", "")
         .replace("\u200C", "")
         .replace("\u200D", "")
         )
    s = re.sub(r"\s+", " ", s).strip()

    # CASE A: whole token letter-spaced
    if re.fullmatch(r"(?:[A-Za-z]\s+)+[A-Za-z]", s):
        collapsed = re.sub(r"\s+", "", s).upper()
        if collapsed in CANON:
            return CANON[collapsed]
        return collapsed.title().replace("Xmen", "X Men")

    # CASE B: collapse letter-spaced fragments
    def _collapse_fragment(m: re.Match) -> str:
        return m.group(0).replace(" ", "")
    s = re.sub(r"(?<!\w)(?:[A-Za-z]\s){1,}[A-Za-z](?!\w)", _collapse_fragment, s)

    s = s.replace("-", " ").replace("_", " ")
    s = re.sub(r"\s+", " ", s).strip()

    words = s.split(" ")
    out_words = []
    for w in words:
        uw = w.upper()
        if uw in CANON and " " not in CANON[uw]:
            out_words.append(CANON[uw])
        elif uw in KEEP_UPPER:
            out_words.append(uw)
        elif uw == "UP":
            out_words.append("Up")
        else:
            out_words.append(w.title())

    out = " ".join(out_words)
    collapsed_again = re.sub(r"\s+", "", out).upper()
    if collapsed_again in CANON:
        return CANON[collapsed_again]
    return out

# ---------------------------
# Traits extraction
# ---------------------------
def _extract_traits_from_page(driver) -> List[str]:
    els = driver.find_elements(
        By.CSS_SELECTOR,
        "ul.filter-group a.traits, a[href*='/characters/trait/'], a[href*='/en/characters/trait/']"
    )
    tokens: List[str] = []
    for el in els:
        token = ""
        href = el.get_attribute("href") or ""
        text = (el.get_attribute("innerText") or el.text or "").strip()
        if "/trait/" in href:
            last = href.rstrip("/").split("/")[-1]
            token = _normalize_token(last)
        if not token and text:
            token = _normalize_token(text)
        if token:
            tokens.append(token)

    seen, out = set(), []
    for t in tokens:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            out.append(t)
    return out

# ---------------------------
# Abilities extraction (+ yellow terms)
# ---------------------------
def _get_text(el) -> str:
    try:
        txt = el.get_attribute("innerText")
        return (txt or "").strip()
    except Exception:
        return (el.text or "").strip()

def _extract_abilities_from_page(driver) -> Tuple[List[dict], List[str]]:
    abilities: List[dict] = []
    yellow_terms: List[str] = []
    sections = driver.find_elements(By.CSS_SELECTOR, "div.hero-abilities .panel-content")

    for sec in sections:
        try:
            try:
                name = sec.find_element(By.CSS_SELECTOR, ".ability-description h4").text.strip()
            except Exception:
                name = ""
            try:
                img = sec.find_element(By.CSS_SELECTOR, ".ability-icon img").get_attribute("src") or ""
            except Exception:
                img = ""
            try:
                pre = sec.find_element(By.CSS_SELECTOR, ".ability-description pre.ability-text")
                description = _get_text(pre)
            except Exception:
                description = ""
            try:
                full_nodes = sec.find_elements(By.CSS_SELECTOR, ".ability-description .ability-energy i.full")
                energyCost = len(full_nodes) if full_nodes else None
            except Exception:
                energyCost = None
            try:
                spans = sec.find_elements(By.CSS_SELECTOR, ".ability-description pre.ability-text span.ability-yellow")
                for sp in spans:
                    raw = sp.get_attribute("innerText") or sp.text
                    token = _normalize_token(raw)
                    if token:
                        yellow_terms.append(token)
            except Exception:
                pass

            if name or description:
                abilities.append({
                    "name": name,
                    "imageUrl": img,
                    "description": description,
                    "energyCost": energyCost
                })
        except Exception as e:
            print(f"[abilities] skip section: {e}")

    # de-dup keywords
    seen, dedup = set(), []
    for t in yellow_terms:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            dedup.append(t)
    return abilities, dedup

# ---------------------------
# Total-stats table enrichment
# ---------------------------

# Canonical stats + extras we’ll carry through
_HEADER_MAP = {
    "power": "POWER", "total power": "POWER",
    "health": "HEALTH", "total health": "HEALTH", "hp": "HEALTH",
    "damage": "DAMAGE", "total damage": "DAMAGE",
    "armor": "ARMOR", "armour": "ARMOR", "total armor": "ARMOR", "total armour": "ARMOR",
    "focus": "FOCUS", "total focus": "FOCUS",
    "resist": "RESISTANCE", "resistance": "RESISTANCE", "total resistance": "RESISTANCE",
    "speed": "SPEED", "total speed": "SPEED",
    # extras available in CSV
    "crit damage": "CRIT_DAMAGE",
    "crit chance": "CRIT_CHANCE",
    "dodge chance": "DODGE_CHANCE",
    "block chance": "BLOCK_CHANCE",
    "block amount": "BLOCK_AMOUNT",
    "accuracy": "ACCURACY",
}

def _norm_header(h: str) -> str:
    """Normalize CSV/DOM header: strip NBSPs, collapse spaces, lower-case."""
    s = (h or "").replace("\u00A0", " ").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def _name_key(s: str) -> str:
    """
    Normalize names to a stable join key:
    - lowercase
    - replace curly apostrophes with straight
    - drop EVERYTHING except [a-z0-9]
    (lets 'Rachel Summers' match 'RachelSummers')
    """
    s = (s or "").lower().replace("’", "'")
    s = re.sub(r"\s*\([^)]*\)\s*", "", s)        # remove parentheticals
    return re.sub(r"[^a-z0-9]", "", s)

def _click_cookie_banner(driver):
    """Try to accept common consent banners so dynamic content renders."""
    possible_texts = ["Accept", "I Agree", "Allow All", "Got it", "Accept All", "AGREE"]
    try:
        # specific OneTrust id first
        btns = driver.find_elements(By.CSS_SELECTOR, "#onetrust-accept-btn-handler")
        for b in btns:
            try:
                if b.is_displayed():
                    b.click()
                    time.sleep(0.5)
                    return
            except Exception:
                pass
        # generic buttons by text
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for b in buttons:
            try:
                t = (b.get_attribute("innerText") or b.text or "").strip()
                if any(p.lower() in t.lower() for p in possible_texts):
                    if b.is_displayed():
                        b.click()
                        time.sleep(0.5)
                        return
            except Exception:
                pass
    except Exception:
        pass

def _coerce_num(val: str):
    num = re.sub(r"[^\d\.,-]", "", (val or "")).replace(",", "")
    if not num:
        return val
    if re.fullmatch(r"-?\d+", num):
        try:
            return int(num)
        except Exception:
            return val
    if re.fullmatch(r"-?\d+\.\d+", num):
        try:
            return float(num)
        except Exception:
            return val
    return val

def _try_download_stats_csv(driver, url: str, download_dir: str, throttle: float = 1.0) -> Optional[str]:
    """
    Navigate to stats page, click a CSV/Export control if present, and return the downloaded CSV filepath.
    Returns None if not found.
    """
    driver.get(url)
    _click_cookie_banner(driver)
    time.sleep(throttle)

    before = set(glob.glob(os.path.join(download_dir, "*.csv")))

    # Sometimes the export is off-screen; try a quick scroll sweep
    for y in (0, 500, 1200, 2400):
        try:
            driver.execute_script(f"window.scrollTo(0,{y});")
            time.sleep(0.3)
        except Exception:
            pass

        # hunt for export controls
        candidates = []
        try:
            candidates.extend(driver.find_elements(By.CSS_SELECTOR, "a[href$='.csv']"))
        except Exception:
            pass
        try:
            candidates.extend(driver.find_elements(By.CSS_SELECTOR, "a[download]"))
        except Exception:
            pass

        # buttons/links containing CSV text
        try:
            candidates.extend(driver.find_elements(By.TAG_NAME, "a"))
            candidates.extend(driver.find_elements(By.TAG_NAME, "button"))
        except Exception:
            pass

        clicked = False
        for el in candidates:
            try:
                text = (el.get_attribute("innerText") or el.text or "").strip()
                href = el.get_attribute("href") or ""
                if ("csv" in text.lower()) or ("export" in text.lower()) or href.endswith(".csv"):
                    if el.is_displayed():
                        el.click()
                        clicked = True
                        break
            except Exception:
                continue

        if clicked:
            # wait for a new CSV to appear
            for _ in range(30):  # ~15s
                time.sleep(0.5)
                after = set(glob.glob(os.path.join(download_dir, "*.csv")))
                new = list(after - before)
                if new:
                    newest = max(new, key=os.path.getmtime)
                    print(f"[total-stats] CSV download detected: {os.path.basename(newest)}")
                    return newest
            break  # clicked but no file → bail

    print("[total-stats] CSV export not found; will try DOM table.")
    return None

def _parse_stats_csv(csv_path: str) -> List[dict]:
    """
    Parse the roster CSV into row dicts with normalized headers + nameKey.
    Handles NBSPs and header variants like 'CHARACTERS', 'RESIST', etc.
    """
    rows: List[dict] = []
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        raw_headers = reader.fieldnames or []
        norm_headers = [_norm_header(h) for h in raw_headers]
        print(f"[total-stats] CSV headers (raw): {raw_headers}")
        print(f"[total-stats] CSV headers (norm): {norm_headers}")

        # Identify the name column
        NAME_CANDS = {"hero", "name", "character", "characters", "unit"}
        name_idx = -1
        for i, nh in enumerate(norm_headers):
            if nh in NAME_CANDS:
                name_idx = i
                break
        if name_idx < 0 and raw_headers:
            # fallback: pick the first column that isn't just a '#'/index
            for i, nh in enumerate(norm_headers):
                if nh not in {"#", "rank", "index"}:
                    name_idx = i
                    break
        if name_idx < 0:
            raise RuntimeError("Could not detect name column in CSV")

        name_col = raw_headers[name_idx]

        # Build a header mapping for stats
        stat_cols = []
        for i, (raw_h, nh) in enumerate(zip(raw_headers, norm_headers)):
            if i == name_idx:
                continue
            canon = _HEADER_MAP.get(nh, raw_h.strip().upper().replace(" ", "_"))
            stat_cols.append((raw_h, canon))

        for r in reader:
            name = (r.get(name_col) or "").replace("\u00A0", " ").strip()
            if not name:
                continue
            row = {"name": name, "nameKey": _name_key(name)}
            for raw_h, canon in stat_cols:
                val = _coerce_num(r.get(raw_h))
                row[canon] = val
            rows.append(row)

    print(f"[total-stats] CSV parsed rows: {len(rows)}")
    # sample: names + a couple of stats
    print("[total-stats] CSV names sample (first 5): " + str([r.get('name') for r in rows[:5]]))
    print("[total-stats] CSV row sample (first 3): " +
          str([{ "name": r.get("name"), "POWER": r.get("POWER"), "SPEED": r.get("SPEED") } for r in rows[:3]]))
    return rows

def _scrape_total_stats_table_dom(driver, url: str, throttle: float = 1.0) -> List[dict]:
    """
    Fallback: visit the total-stats page and scrape a rendered table.
    Returns rows: { "name": "...", "nameKey": "...", "POWER": ..., "SPEED": ..., ... }
    """
    driver.get(url)
    _click_cookie_banner(driver)
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "table, [role='table'], .table, .table-wrapper"))
        )
    except Exception:
        pass
    time.sleep(throttle)

    tables = driver.find_elements(By.CSS_SELECTOR, "table")
    if not tables:
        tables = driver.find_elements(By.CSS_SELECTOR, "[role='table'], .table-wrapper")

    best = None
    best_cols = 0
    for t in tables:
        try:
            headers_el = t.find_elements(By.CSS_SELECTOR, "thead tr th")
            if not headers_el:
                headers_el = t.find_elements(By.CSS_SELECTOR, "tr:first-child th, tr:first-child td")
            headers = [ (h.get_attribute("innerText") or h.text or "").strip() for h in headers_el ]
            if not headers or len(headers) < 5:
                continue
            hdr_lower = [_norm_header(h) for h in headers]
            score = sum(1 for k in ["name","character","hero","health","damage","armor","armour","focus","resist","resistance","speed","power"] if any(k == x for x in hdr_lower))
            if score >= 3 and len(headers) > best_cols:
                best = (t, headers)
                best_cols = len(headers)
        except Exception:
            continue

    if not best:
        print("[total-stats] No suitable table found in DOM")
        return []

    t, headers = best
    # Canonicalize header names
    canon_headers = []
    for h in headers:
        nh = _norm_header(h)
        if nh in ("character", "name", "characters", "hero"):
            canon_headers.append("name")
        else:
            canon_headers.append(_HEADER_MAP.get(nh, h.strip().upper()))

    trs = t.find_elements(By.CSS_SELECTOR, "tbody tr") or t.find_elements(By.CSS_SELECTOR, "tr")[1:]
    print(f"[total-stats] Using DOM table with {len(canon_headers)} columns and {len(trs)} rows")
    print(f"[total-stats] Headers (canon): {canon_headers}")

    rows: List[dict] = []
    for tr in trs:
        cells = tr.find_elements(By.CSS_SELECTOR, "td")
        if not cells or len(cells) < 2:
            continue
        raw_vals = []
        for c in cells[:len(canon_headers)]:
            txt = (c.get_attribute("innerText") or c.text or "").replace("\u00A0", " ").strip()
            raw_vals.append(txt)

        row = {}
        for hdr, val in zip(canon_headers, raw_vals):
            if hdr == "name":
                txt = val
                # Try to find a link (rare on this page)
                try:
                    a = tr.find_element(By.CSS_SELECTOR, "a[href*='/characters/']")
                    txt = (a.get_attribute("innerText") or a.text or txt).strip()
                    row["slug"] = slug_from_url(a.get_attribute("href") or "")
                except Exception:
                    pass
                row["name"] = txt
            else:
                row[hdr] = _coerce_num(val)

        if row.get("name"):
            row["nameKey"] = _name_key(row["name"])
            rows.append(row)

    print("[total-stats] DOM names sample (first 5): " + str([r.get('name') for r in rows[:5]]))
    print("[total-stats] DOM row sample (first 3): " +
          str([{ "name": r.get("name"), "POWER": r.get("POWER"), "SPEED": r.get("SPEED") } for r in rows[:3]]))
    return rows

def _get_total_stats_rows(driver, url: str, download_dir: str, throttle: float = 1.0) -> List[dict]:
    """
    Try CSV-first, then fall back to DOM scraping. Always returns a list of row dicts.
    Also writes a debug JSON so we can inspect the parsed result.
    """
    # CSV-first
    csv_path = _try_download_stats_csv(driver, url, download_dir, throttle=throttle)
    rows: List[dict] = []
    if csv_path and os.path.isfile(csv_path):
        try:
            rows = _parse_stats_csv(csv_path)
        except Exception as e:
            print(f"[total-stats] CSV parse failed: {e}")

    # DOM fallback
    if not rows:
        rows = _scrape_total_stats_table_dom(driver, url, throttle=throttle)

    # Debug dump
    try:
        os.makedirs("data-pipeline/output", exist_ok=True)
        debug_json = "data-pipeline/output/hero_total_stats_rows.json"
        with open(debug_json, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        print(f"[total-stats] Wrote parsed table to {debug_json}")
    except Exception as e:
        print(f"[total-stats] Failed to write debug JSON: {e}")

    return rows

# ---------------------------
# Enrichment: detail page (no stats here)
# ---------------------------
def enrich_from_detail(driver, c: MiniCharacter, throttle: float = 1.0) -> List[str]:
    driver.get(c.url)
    _click_cookie_banner(driver)  # accept cookies here too (prevents "Loading..." names)
    WebDriverWait(driver, 12).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "meta[property='og:title'], h1"))
    )
    time.sleep(throttle)

    name_meta = _get_meta_content(driver, "meta[property='og:title']")
    clean_name = _clean_title(name_meta) or c.name
    try:
        if not clean_name:
            clean_name = driver.find_element(By.CSS_SELECTOR, "h1").text.strip()
    except NoSuchElementException:
        pass

    image = _get_meta_content(driver, "meta[property='og:image']")
    traits = _extract_traits_from_page(driver)
    abilities, yellow_terms = _extract_abilities_from_page(driver)

    c.name = clean_name or c.name
    if image:
        c.imageUrl = image
    c.traits = traits or c.traits
    c.abilities = abilities or c.abilities

    return yellow_terms

# ---------------------------
# Index scrape + enrichment + stats merge
# ---------------------------
def scrape_character_list(
    index_url: str,
    limit: Optional[int] = None,
    headless: bool = True,
    throttle: float = 1.0,
    include_total_stats: bool = True,
    total_stats_url: str = "https://marvelstrikeforce.com/en/hero-total-stats",
) -> Tuple[List[MiniCharacter], List[str]]:
    download_dir = "data-pipeline/output/tmp_downloads"
    driver = setup_driver(headless=headless, download_dir=download_dir)
    global_terms: List[str] = []
    try:
        # 1) Index → candidate characters
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
            if href.rstrip("/").endswith("/characters"):  # index root
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

        # 2) Enrich each character (detail page)
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

        # 3) Merge global total stats (CSV-first, DOM fallback)
        if include_total_stats:
            table_rows = _get_total_stats_rows(driver, total_stats_url, download_dir, throttle=throttle)
            print(f"[total-stats] Parsed {len(table_rows)} roster rows")

            by_key = { (r.get("nameKey") or ""): r for r in table_rows if r.get("nameKey") }
            by_slug = { (r.get("slug") or ""): r for r in table_rows if r.get("slug") }

            print(f"[total-stats] Sample nameKeys: {list(by_key.keys())[:5]}")

            unmatched, merged, show = [], 0, 0
            for c in results:
                k_name = _name_key(c.name)
                k_slugname = _name_key(c.path.replace("-", " "))

                row = by_key.get(k_name) or by_key.get(k_slugname) or by_slug.get(c.path)

                if row:
                    p = row.get("POWER")
                    if isinstance(p, (int, float)):
                        c.power = int(p)
                    stats = {kk: vv for kk, vv in row.items() if kk not in ("name","nameKey","slug") and isinstance(kk, str) and kk.isupper()}
                    if stats:
                        c.stats.update(stats)
                    merged += 1
                    if show < 20:
                        print(f"[merge] matched '{c.name}'  key='{k_name}'  POWER={c.power}  SPEED={c.stats.get('SPEED')}")
                        show += 1
                else:
                    unmatched.append(c.name)

            print(f"[total-stats] Merged stats into {merged}/{len(results)} characters")
            if unmatched:
                print(f"[total-stats] Unmatched {len(unmatched)} names (first 10): {unmatched[:10]}")

        return results, global_terms

    finally:
        try:
            driver.quit()
        except Exception:
            pass

# ---------------------------
# Writers
# ---------------------------
def write_frontend_json(characters: List[MiniCharacter], output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    payload = [asdict(c) for c in characters]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Wrote JSON: {output_path} ({len(payload)} records)")

def write_keywords_json(keywords: List[str], output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sorted(set(keywords), key=lambda x: x.lower()), f, ensure_ascii=False, indent=2)
    print(f"Wrote JSON: {output_path} ({len(keywords)} terms)")

def write_firestore(characters: List[MiniCharacter], project_id: str, service_account: Optional[str] = None, collection: str = "characters_min"):
    if firestore is None:
        raise RuntimeError("Firestore libraries not installed. Run: pip install firebase-admin google-cloud-firestore")
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
        doc_id = c.path
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

# ---------------------------
# CLI
# ---------------------------
def main():
    p = argparse.ArgumentParser(description="SynergyForge scraper (traits, abilities, keywords + global stats merge)")
    p.add_argument("--index-url", type=str, default="https://marvelstrikeforce.com/en/characters",
                   help="Character index page to start from")
    p.add_argument("--limit", type=int, default=10, help="Limit number of characters to scrape")
    p.add_argument("--headless", action="store_true", help="Run Chrome headless")
    p.add_argument("--no-headless", dest="headless", action="store_false")
    p.add_argument("--throttle", type=float, default=1.0, help="Seconds to sleep between actions")
    p.add_argument("--output", type=str, default="data-pipeline/output/characters_min.json", help="Path to write frontend JSON")
    p.add_argument("--keywords-out", type=str, default="", help="Path to write global ability keywords JSON (optional)")
    p.add_argument("--no-total-stats", action="store_true", help="Skip the global total-stats merge (debug)")
    p.add_argument("--canon-map-json", type=str, default="", help="Path to JSON file to extend/override the canonical keyword map")
    p.add_argument("--firestore", action="store_true", help="Also write results to Firestore")
    p.add_argument("--project-id", type=str, default=None, help="Your Firebase project id (required with --firestore)")
    p.add_argument("--service-account", type=str, default=None, help="Path to service account JSON (optional)")
    p.set_defaults(headless=True)
    args = p.parse_args()

    if args.canon_map_json:
        try:
            CANON.update(load_canon_map(args.canon_map_json))
            print(f"Loaded canon overrides: {args.canon_map_json}")
        except Exception as e:
            print(f"Failed to load canon map '{args.canon_map_json}': {e}")

    chars, terms = scrape_character_list(
        index_url=args.index_url,
        limit=args.limit,
        headless=args.headless,
        throttle=args.throttle,
        include_total_stats=not args.no_total_stats,
        total_stats_url="https://marvelstrikeforce.com/en/hero-total-stats",
    )

    print(f"Scraped {len(chars)} characters")
    for c in chars[:3]:
        print(f" - {c.name} ({c.path}) → {c.url}")

    write_frontend_json(chars, args.output)

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
