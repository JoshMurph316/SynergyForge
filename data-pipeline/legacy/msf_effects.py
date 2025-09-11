import json, time, re, os
from dataclasses import dataclass, asdict
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager

EFFECTS_URLS = [
    "https://marvelstrikeforce.com/en/effects",
    # Fallback: localized (renders server-side)
    "https://marvelstrikeforce.com/it/effects",
]

CANON_KIND = {
    "buff": "buff",
    "debuff": "debuff",
    "altro": "other", "other": "other", "effetto": "other"
}

# optional: additional canon overrides (spelling/new effects)
CANON_OVERRIDES = {
    "Exhausted": {"id": "EXHAUSTED", "kind": "debuff"},
    "Exposed": {"id": "EXPOSED", "kind": "debuff"},
    "Safeguard": {"id": "SAFEGUARD", "kind": "buff"},
    "Trauma": {"id": "TRAUMA", "kind": "debuff"},
    "Vulnerable": {"id": "VULNERABLE", "kind": "other"},
}

ALIAS_MAP = {
    "Defense Down": ["defense down", "def down", "def-"],
    "Defense Up": ["defense up", "def up", "def+"],
    "Offense Down": ["offense down", "off-"],
    "Offense Up": ["offense up", "off+"],
    "Speed Up": ["speed up"],
    "Slow": ["speed down", "slow"],
    "Heal Block": ["healing blocked", "no heal"],
    "Ability Block": ["ability blocked"],
    "Deathproof": ["dp"],
    "Evade": ["dodge"],
    "Disrupted": ["buffs blocked", "no new buffs"],
    "Immunity": ["immune"],
    "Safeguard": ["unflippable", "unclearable"],
    "Trauma": ["healing prevention persistence"],
    "Bleed": ["bleed"],
    "Minor Bleed": ["minor bleed"],
    "Regeneration": ["regen"],
    "Minor Regeneration": ["minor regen"],
    "Deflect": ["block next attack"],
    "Counterattack": ["counter"],
    "Stealth": ["stealth"],
    "Taunt": ["taunt"],
    "Stun": ["stun"],
    "Blind": ["blind"],
    "Charged": ["charged"],
    "Assist Now": ["assist now"],
    "Vulnerable": ["iso vulnerable"],
    "Exposed": ["exposed"],
    "Exhausted": ["exhausted"]
}

SECTION_HEADING_RE = re.compile(r"^\s*(POSITIVE|NEGATIVE|OTHER)\s+EFFECTS\s*$", re.I)
JUNK_TITLE_RE = re.compile(r"^\s*(Expires:|Opposite:|Duration:)\b", re.I)

def canon_id(name: str) -> str:
    return re.sub(r"[^A-Z0-9_]", "", name.upper().replace(" ", "_"))

@dataclass
class Effect:
    id: str
    name: str
    kind: str
    summary: str
    opposite: str | None = None
    flip_to: str | None = None
    clearable: bool | None = None
    stacking: bool | None = None
    duration_hint: str | None = None
    aliases: list[str] | None = None
    keywords: list[str] | None = None

def accept_cookies(driver):
    try:
        # Common cookie buttons
        for sel in ["button[title='Accept All']", "button#onetrust-accept-btn-handler",
                    "button[aria-label*='Accept']", "button:contains('Accept')"]:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            if elems:
                elems[0].click()
                time.sleep(0.5)
                return
    except Exception:
        pass

def _clean_lines(s: str) -> list[str]:
    # collapse multiple newlines, strip bullets, trim whitespace
    lines = [ln.strip(" \t•-") for ln in re.split(r"\n+", s) if ln.strip()]
    return lines

def _extract_title_and_body(card) -> tuple[str, str]:
    # Prefer a true heading inside the card; fall back to first line of text
    for sel in [".//h1", ".//h2", ".//h3", ".//h4", ".//strong", ".//b"]:
        els = card.find_elements(By.XPATH, sel)
        if els and els[0].text.strip():
            title = els[0].text.strip()
            body = card.text.replace(title, "", 1).strip()
            return title, body
    txt = card.text.strip()
    lines = _clean_lines(txt)
    if not lines:
        return "", ""
    title = lines[0]
    body = "\n".join(lines[1:]).strip()
    return title, body

def _parse_extras(body_text: str) -> tuple[str|None, str|None, str]:
    """Pull out Opposite: …  and Expires: …  from body; return (opposite, duration_hint, summary_wo_labels)"""
    # normalize spacing
    body = re.sub(r"[ \t]+", " ", body_text).strip()

    # capture Opposite:
    opp = None
    m_opp = re.search(r"\bOpposite:\s*([A-Za-z +\-]+)\b", body, flags=re.I)
    if m_opp:
        opp = m_opp.group(1).strip()

    # capture Expires: …
    dur = None
    m_exp = re.search(r"\bExpires:\s*(.*?)\b(?=(Opposite:|$))", body, flags=re.I)
    if m_exp:
        raw = m_exp.group(1).strip().lower()
        if "start of turn" in raw:
            dur = "start_of_turn"
        elif "end of turn" in raw:
            dur = "end_of_turn"
        elif "never" in raw:
            dur = "never"
        elif "on " in raw:   # e.g., On Counter, On Evade, On Block
            dur = "on_trigger"

    # remove label fragments from summary
    body = re.sub(r"\bExpires:\s*.*?(?=(Opposite:|$))", "", body, flags=re.I).strip()
    body = re.sub(r"\bOpposite:\s*[A-Za-z +\-]+\b", "", body, flags=re.I).strip()
    body = re.sub(r"\s{2,}", " ", body)

    return opp, dur, body

def _infer_kind(name: str, body: str) -> str:
    txt = f"{name} {body}".lower()
    # Minimal heuristics; avoids relying on DOM badges
    buff_hits = ["defense up", "offense up", "speed up", "immunity", "safeguard",
                 "deflect", "evade", "regeneration", "counterattack", "taunt", "stealth",
                 "minor defense up", "minor offense up", "minor regeneration"]
    debuff_hits = ["defense down", "offense down", "slow", "heal block", "ability block",
                   "blind", "disrupted", "bleed", "stun", "trauma", "exhausted", "exposed",
                   "minor defense down", "minor offense down", "minor bleed", "silence"]
    if any(k in txt for k in buff_hits):   return "buff"
    if any(k in txt for k in debuff_hits): return "debuff"
    return "other"

def parse_effect_tiles(driver):
    effects = []

    # 1) Try to collect “cards” that actually represent single effects.
    candidates = []
    # common patterns on the page; broaden carefully but DO NOT include generic <li> or big section wrappers
    selectors = [
        "[class*='effect-card']",
        "[class*='EffectCard']",
        "[data-testid*='effect']",
        "article",
        "section [role='article']",
    ]
    for sel in selectors:
        candidates.extend(driver.find_elements(By.CSS_SELECTOR, sel))

    # De-duplicate WebElements
    seen_ids = set()
    uniq = []
    for el in candidates:
        try:
            key = el.id  # Selenium webelement id
        except Exception:
            key = str(hash(el))
        if key not in seen_ids:
            uniq.append(el); seen_ids.add(key)

    # 2) Parse candidates -> Effects, ignore section headers and junk titles
    for card in uniq:
        title, body = _extract_title_and_body(card)
        if not title or SECTION_HEADING_RE.match(title) or JUNK_TITLE_RE.match(title):
            continue
        # Filter out obvious aggregators like “POSITIVE EFFECTS ... (huge wall of text)”
        if len(body) > 1200 and title.upper().endswith("EFFECTS"):
            continue

        lines = _clean_lines(f"{title}\n{body}")
        # Rebuild a clean text: sometimes inner headings repeat the name
        name = lines[0].strip()
        if SECTION_HEADING_RE.match(name) or JUNK_TITLE_RE.match(name):
            continue

        # Disqualify pseudo-cards like “Expires: On Counter”, “Opposite: Bleed”
        if name.lower().startswith(("expires:", "opposite:", "duration:")):
            continue

        opposite_name, duration_hint, summary_clean = _parse_extras("\n".join(lines[1:]) or body)

        eff_id = re.sub(r"[^A-Z0-9_]", "", name.upper().replace(" ", "_"))
        kind = _infer_kind(name, summary_clean)

        effects.append({
            "id": eff_id,
            "name": name,
            "kind": kind,
            "summary": summary_clean or body.strip(),
            "opposite": None if not opposite_name else re.sub(r"[^A-Z0-9_]", "", opposite_name.upper().replace(" ", "_")),
            "flip_to": None,
            "clearable": None,   # set later in post-process
            "stacking": bool(re.search(r"\bstack|\bstacks|\bper stack\b|\bminor\b", summary_clean, re.I)),
            "duration_hint": duration_hint,
            "aliases": [],
            "keywords": [],
        })

    # 3) If the page structure changed and we captured almost nothing, fall back to text segmentation:
    if len(effects) < 10:
        page_text = driver.find_element(By.TAG_NAME, "body").text
        blocks = re.split(r"\b(POSITIVE EFFECTS|NEGATIVE EFFECTS|OTHER EFFECTS)\b", page_text, flags=re.I)
        # Identify effect names by a controlled vocabulary (minimal list; add more if needed)
        VOCAB = [
            "Counterattack","Deathproof","Immunity","Defense Up","Deflect","Evade","Regeneration",
            "Safeguard","Minor Defense Up","Minor Deflect","Minor Regeneration","Minor Offense Up",
            "Offense Up","Speed Up","Stealth","Taunt",
            "Ability Block","Blind","Disrupted","Defense Down","Bleed","Heal Block","Minor Bleed",
            "Trauma","Minor Defense Down","Minor Offense Down","Offense Down","Silence","Slow","Stun",
            "Assist Now","Charged","Exhausted","Exposed","Iso-8 Vulnerable","Revive Once","Overpower Effects"
        ]
        # Build regex that splits on effect names (as headings)
        rx = re.compile(r"(?<=\n)(%s)\b" % "|".join(re.escape(v) for v in VOCAB))
        for part in blocks:
            if not isinstance(part, str): continue
            # segment this block by known names
            segs = rx.split(part)
            # segs like ["", "Counterattack", "...desc...", "Deathproof", "...desc...", ...]
            for i in range(1, len(segs), 2):
                nm = segs[i].strip()
                desc = segs[i+1].strip() if i+1 < len(segs) else ""
                if not nm: continue
                if nm.lower().startswith(("expires:", "opposite:", "duration:")): continue
                opp, dur, summary = _parse_extras(desc)
                eff_id = re.sub(r"[^A-Z0-9_]", "", nm.upper().replace(" ", "_"))
                kind = _infer_kind(nm, summary)
                effects.append({
                    "id": eff_id,
                    "name": nm,
                    "kind": kind,
                    "summary": summary,
                    "opposite": None if not opp else re.sub(r"[^A-Z0-9_]", "", opp.upper().replace(" ", "_")),
                    "flip_to": None,
                    "clearable": None,
                    "stacking": bool(re.search(r"\bstack|\bstacks|\bper stack\b|\bminor\b", summary, re.I)),
                    "duration_hint": dur,
                    "aliases": [],
                    "keywords": [],
                })

    # 4) Deduplicate by id; keep the longest summary; combine fields
    dedup: dict[str, dict] = {}
    for e in effects:
        cur = dedup.get(e["id"])
        if cur is None:
            dedup[e["id"]] = e
        else:
            # prefer longer summary and keep any discovered opposite/duration
            if len((e["summary"] or "")) > len((cur["summary"] or "")):
                cur["summary"] = e["summary"]
            cur["opposite"] = cur["opposite"] or e["opposite"]
            cur["duration_hint"] = cur["duration_hint"] or e["duration_hint"]
            cur["stacking"] = cur["stacking"] or e["stacking"]

    # 5) Final cleanups: infer clearable, set known opposites/flip
    by_id = dedup
    def set_oppo(a, b):
        if a in by_id and b in by_id:
            by_id[a]["opposite"] = b
            by_id[b]["opposite"] = a

    set_oppo("DEFENSE_UP", "DEFENSE_DOWN")
    set_oppo("OFFENSE_UP", "OFFENSE_DOWN")
    set_oppo("SPEED_UP", "SLOW")
    set_oppo("IMMUNITY", "DISRUPTED")
    set_oppo("BLEED", "REGENERATION")
    set_oppo("MINOR_DEFENSE_UP", "MINOR_DEFENSE_DOWN")
    set_oppo("MINOR_OFFENSE_UP", "MINOR_OFFENSE_DOWN")

    for e in by_id.values():
        txt = f"{e['name']} {e['summary']}".lower()
        if "cannot be cleared or flipped" in txt or "unclearable" in txt or "unflippable" in txt:
            e["clearable"] = False
        elif e["name"].upper() in ("SAFEGUARD", "TRAUMA"):
            e["clearable"] = False
        else:
            e["clearable"] = True

    return list(by_id.values())

def scrape_effects(no_headless: bool = False, throttle: float = 0.5) -> list[dict]:
    """
    Scrape Effects from the MSF Effects page(s) and return a clean list of dicts:
    [
      {
        "id": "DEFENSE_DOWN",
        "name": "Defense Down",
        "kind": "debuff",
        "summary": "...",
        "opposite": "DEFENSE_UP",      # id of opposite effect, if known
        "flip_to": "DEFENSE_UP",       # id of flip target, if known
        "clearable": True | False,
        "stacking": bool,
        "duration_hint": "start_of_turn"|"end_of_turn"|"on_trigger"|"never"|None,
        "aliases": [...],
        "keywords": [...]
      },
      ...
    ]
    """
    # --- webdriver setup ---
    opts = webdriver.ChromeOptions()
    if not no_headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--window-size=1400,1000")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

    try:
        collected: list[dict] = []

        # hit primary EN page; fall back to localized (often more server-rendered)
        for url in EFFECTS_URLS:
            driver.get(url)
            time.sleep(throttle)
            accept_cookies(driver)
            time.sleep(throttle)

            # parse into list[dict] (each with id/name/summary/etc.)
            parsed = parse_effect_tiles(driver)
            if parsed:
                collected = parsed
                break

        # If still empty, nothing to do
        if not collected:
            return []

        # --- Sanity filter: remove aggregate headers / junk labels / obvious noise ---
        BAD_PREFIXES = (
            "EXPIRES_", "OPPOSITE_", "POSITIVE_EFFECTS",
            "NEGATIVE_EFFECTS", "OTHER_EFFECTS"
        )
        collected = [
            e for e in collected
            if isinstance(e, dict)
            and e.get("id") and e.get("name")
            and not any(str(e["id"]).startswith(p) for p in BAD_PREFIXES)
            and not str(e["name"]).upper().endswith(" EFFECTS")
            and not str(e["name"]).lower().startswith(("expires:", "opposite:", "duration:"))
        ]

        # Build index by display name (used for linking)
        by_name: dict[str, dict] = {e["name"]: e for e in collected}

        def link_mutual(a_name: str, b_name: str):
            """Set opposite both ways if both exist."""
            a = by_name.get(a_name); b = by_name.get(b_name)
            if a and b:
                a["opposite"] = b["id"]
                b["opposite"] = a["id"]

        def link_flip(src_name: str, dst_name: str):
            """Set flip_to from src -> dst if both exist."""
            s = by_name.get(src_name); d = by_name.get(dst_name)
            if s and d:
                s["flip_to"] = d["id"]

        # --- Known opposite/flip pairs (safe canonical links) ---
        link_mutual("Defense Up", "Defense Down")
        link_mutual("Offense Up", "Offense Down")
        link_mutual("Speed Up", "Slow")
        link_mutual("Immunity", "Disrupted")
        link_mutual("Bleed", "Regeneration")
        link_mutual("Minor Defense Up", "Minor Defense Down")
        link_mutual("Minor Offense Up", "Minor Offense Down")

        link_flip("Defense Down", "Defense Up")
        link_flip("Offense Down", "Offense Up")

        # --- Enrichment: clearable, aliases, keywords ---
        base_aliases = {
            "Defense Down": ["defense down", "def down", "def-"],
            "Defense Up": ["defense up", "def up", "def+"],
            "Offense Down": ["offense down", "off-"],
            "Offense Up": ["offense up", "off+"],
            "Speed Up": ["speed up", "fill speed bar"],
            "Slow": ["slow", "reduce speed bar"],
            "Heal Block": ["heal block", "cannot be healed"],
            "Ability Block": ["ability block"],
            "Safeguard": ["unclearable", "unflippable"],
            "Trauma": ["healing prevention persists", "cannot gain positive effects from heal"],
            "Bleed": ["bleed"],
            "Regeneration": ["regeneration", "regen"],
            "Counterattack": ["counter", "counterattack"],
            "Disrupted": ["disrupted", "no new buffs"],
            "Immunity": ["immunity", "immune"],
            "Exposed": ["exposed"],
            "Exhausted": ["exhausted"],
            "Iso-8 Vulnerable": ["iso vulnerable", "vulnerable"],
        }

        for e in collected:
            name = str(e.get("name", ""))
            summary = str(e.get("summary", ""))
            txt = f"{name} {summary}".lower()

            # clearable
            if any(k in txt for k in ["cannot be cleared or flipped", "unclearable", "unflippable"]):
                e["clearable"] = False
            elif name.upper() in ("SAFEGUARD", "TRAUMA"):
                e["clearable"] = False
            elif e.get("clearable") is None:
                e["clearable"] = True

            # ensure aliases/keywords exist
            aliases = set(e.get("aliases") or [])
            aliases.update(base_aliases.get(name, []))
            aliases.add(name.lower())
            e["aliases"] = sorted(aliases)

            if not e.get("keywords"):
                e["keywords"] = e["aliases"]

            # normalize kind if missing
            k = (e.get("kind") or "").lower()
            if k not in ("buff", "debuff", "other"):
                # light inference if parse didn't supply it
                if any(t in txt for t in [
                    "defense up", "offense up", "speed up", "immunity", "safeguard",
                    "deflect", "evade", "regeneration", "counterattack", "taunt", "stealth",
                    "minor defense up", "minor offense up", "minor regeneration"
                ]):
                    e["kind"] = "buff"
                elif any(t in txt for t in [
                    "defense down", "offense down", "slow", "heal block", "ability block",
                    "blind", "disrupted", "bleed", "stun", "trauma", "exhausted", "exposed",
                    "minor defense down", "minor offense down", "minor bleed", "silence"
                ]):
                    e["kind"] = "debuff"
                else:
                    e["kind"] = "other"

            # light boolean for stacking
            if e.get("stacking") is None:
                e["stacking"] = bool(re.search(r"\bstack|\bstacks|\bper stack\b|\bminor\b", summary, re.I))

            # normalize duration_hint string
            dh = e.get("duration_hint")
            if dh is not None:
                dh = str(dh)
                if dh not in ("start_of_turn", "end_of_turn", "on_trigger", "never"):
                    e["duration_hint"] = None

        return collected

    finally:
        driver.quit()

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="data-pipeline/output/effect_data.json")
    ap.add_argument("--no-headless", action="store_true")
    ap.add_argument("--throttle", type=float, default=0.5)
    args = ap.parse_args()

    data = scrape_effects(no_headless=args.no_headless, throttle=args.throttle)
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump({"effects": data, "source": "msf_effects", "ts": int(time.time())}, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(data)} effects → {args.output}")
