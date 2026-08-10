"""
patent_agent.py — Orbital Daily Layer 1 Specialist: Patent Agent

Purpose: monitor USPTO filings from a baseline list of space companies +
CPC B64G (spacecraft), apply a taste-driven pick/reject judgment (calibrated
against real examples from a live session), and write results to a flat-file
history — extending the existing sai_history.json / editorial_history.json
pattern.

Definition of done (tonight): runs once, hits real USPTO data, produces one
real entry in patent_history.json.

NOTE FOR CLAUDE CODE: the two fetch_* functions below are stubbed with
NotImplementedError. Fill them in using the EXACT request pattern/query
syntax that already worked in tonight's session (api.uspto.gov Patent File
Wrapper Search API, applicantNameText phrase match for assignee search,
cpcClassificationBag wildcard for CPC search — client-side date filtering
if the API's own date param proves unreliable, same as the gov-contracts
feed already does). Do not guess at new syntax — reuse what already ran
successfully tonight. Everything else in this file is complete.
"""

import os
import sys
import json
import hashlib
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("WARNING: python-dotenv not installed — relying on ambient env vars.", file=sys.stderr)

try:
    import anthropic
except ImportError:
    print("ERROR: anthropic package not installed. Run: pip install anthropic", file=sys.stderr)
    sys.exit(1)

import requests


# ---------------------------------------------------------------------------
# CONFIG — baseline categories (hardcoded fallback; dynamic-from-trends is a
# future hook, not built yet since the Trends agent doesn't exist).
# ---------------------------------------------------------------------------

BASELINE_COMPANIES = [
    "SpaceX",
    "Blue Origin",
    "Rocket Lab",
    "ispace",
    "Sierra Space",
    "Axiom Space",
    "Astroscale",
    "Firefly Aerospace",
    "Varda Space",
]

CPC_CLASSES = ["B64G"]

# Daily production default. For TONIGHT'S FIRST RUN, temporarily set this
# higher (e.g. 180) so there's something in range to judge — seen-memory
# starts empty, so a 14-day window on a fresh repo will likely find nothing.
# Flip back to 14 once this has run successfully at least once.
LOOKBACK_DAYS = 180

USPTO_SEARCH_URL = "https://api.uspto.gov/api/v1/patent/applications/search"

USPTO_API_KEY = os.environ.get("USPTO_API_KEY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

REPO_ROOT = Path(__file__).resolve().parent
HISTORY_PATH = REPO_ROOT / "patent_history.json"
SEEN_MEMORY_PATH = REPO_ROOT / "patent_agent_seen.json"

HAIKU_MODEL = "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# TASTE CALIBRATION — real judgments from a live pick/reject session.
# This is the actual "judgment baked in via Aleks's own examples" the
# roadmap calls for. Edit this list directly to retune the agent's taste —
# don't touch the fetch or plumbing code to change what it likes.
# ---------------------------------------------------------------------------

PICK_EXAMPLES = [
    {"company": "BWXT Advanced Technologies", "title": "Fuel Bundle with Twisted Ribbon Fuel Rodlets for Nuclear Thermal Propulsion",
     "why": "Nuclear thermal propulsion is the 'get to Mars faster' story — sparks imagination."},
    {"company": "HGP Intelligent Energy", "title": "GPU-Accelerated Digital Twin System for Space Nuclear Reactors",
     "why": "Companion infrastructure to nuclear propulsion — same reason as above."},
    {"company": "Mitsubishi Electric", "title": "Satellite Constellation Forming System",
     "why": "Space telecom infrastructure — feels close to reality, not speculative."},
    {"company": "Blue Origin", "title": "Low Earth Orbit with Electric Propulsion",
     "why": "Maneuverability matters for debris clearing, satellite servicing, and defense implications."},
    {"company": "L'Garde", "title": "Solar Sail for Orbital Maneuvers",
     "why": "Sci-fi angle — plausible path to meaningful fractions of light speed over distance."},
    {"company": "Digital Global Systems", "title": "Systems and Methods of Sensor Data Fusion",
     "why": "Detection/tracking capability — same reasoning as maneuverability picks."},
    {"company": "Honeybee Robotics", "title": "System for In Situ Resource Utilization in Extraterrestrial Environments",
     "why": "Moon/Mars colonization — high imagination-spark value."},
    {"company": "Fremen Space", "title": "Devices, Systems, and Processes for Water Collection and Filtration",
     "why": "On-brand sci-fi reference (Dune), and life-support basics for habitats."},
    {"company": "Blue Origin", "title": "Integrated Thermionic Diode and Molten Oxide Electrolysis Cell",
     "why": "ISRU / lunar resource extraction — same reasoning as Honeybee pick."},
    {"company": "Blue Origin", "title": "Laser Material Fusion Under Vacuum",
     "why": "In-space manufacturing/assembly — building things in orbit instead of launching pre-built."},
    {"company": "SpaceX", "title": "System and Method of Providing Access to Compute Resources Distributed Across a Group of Satellites",
     "why": "Space-based computing/data infrastructure — near-term and imagination-sparking."},
    {"company": "The Charles Stark Draper Laboratory", "title": "Microthruster Array",
     "why": "Precision maneuvering — same near-Earth maneuverability story as other picks."},
]

REJECT_EXAMPLES = [
    {"company": "Xplore", "title": "Artificial Satellite with Onboard Georectification of Image Data",
     "why": "Useful but not a story — internal image-processing efficiency, not a capability leap."},
    {"company": "Blue Origin", "title": "Gallium Nitride-Based Active Current Flowback Prevention",
     "why": "Internal component engineering, no mission-level story."},
    {"company": "Blue Origin", "title": "Wire-Feed Friction Stir Additive Manufacturing",
     "why": "Internal manufacturing process, not a capability the reader can picture."},
    {"company": "Blue Origin", "title": "Silicon Carbide Coatings and Methods of Fabricating and Repairing",
     "why": "Durability engineering — low story value on its own."},
    {"company": "The Charles Stark Draper Laboratory", "title": "Dynamic Security Fabric Interposers in Heterogeneously Integrated Systems",
     "why": "Off-topic false positive — semiconductor security, not spacecraft."},
    {"company": "Lockheed Martin", "title": "Hybrid Pitch Bearing for Rigid Rotor",
     "why": "Off-topic false positive — helicopter/rotorcraft part (CPC B64C), not spacecraft (B64G)."},
]


def build_system_prompt() -> str:
    picks_text = "\n".join(f"- {p['company']} — \"{p['title']}\": PICK. {p['why']}" for p in PICK_EXAMPLES)
    rejects_text = "\n".join(f"- {r['company']} — \"{r['title']}\": REJECT. {r['why']}" for r in REJECT_EXAMPLES)

    return f"""You are the patent specialist for Orbital Daily, a space newsletter whose \
North Star is getting a general-audience reader excited about where the space \
economy is heading — not technical significance for its own sake.

Your job: look at a batch of real US patent filings and judge each one PICK or \
REJECT using this rubric:

PICK if the filing reads as a capability leap for what humans/machines can DO in \
space — a new mission type, a new place we can go or build, a new way to move, \
survive, or connect. This is an imagination test for a layperson, not a technical \
significance test. A useful-but-unglamorous internal improvement can still be a \
REJECT even if it's a legitimately good patent.

REJECT if it's a component-level or manufacturing-process improvement internal to \
making existing hardware slightly better, cheaper, or more durable — no new "we can \
now do X" claim a general reader would find exciting. Also REJECT anything that is \
an off-topic false positive (matched a search term but isn't actually about \
spacecraft/space capability).

Real examples of this taste, from the person whose judgment you're modeling:

PICKS:
{picks_text}

REJECTS:
{rejects_text}

For each filing in the batch you're given, decide PICK or REJECT, and if PICK, \
write a one-sentence plain-language summary (no jargon) and a one-sentence "why it \
matters" in the same voice as the examples above — direct, enthusiastic about real \
capability, allergic to hype about internal engineering.

Respond with ONLY a JSON array, no other text, no markdown code fences. Each element:
{{"index": <int>, "pick": <bool>, "plain_summary": <string or null>, "why_it_matters": <string or null>}}
"""


# ---------------------------------------------------------------------------
# FETCH — USPTO Open Data Portal (Patent File Wrapper Search API)
# ---------------------------------------------------------------------------

def _uspto_search(query: str, limit: int = 100) -> list[dict]:
    """Shared GET against the ODP Patent File Wrapper Search API — the exact
    pattern verified working tonight: X-Api-Key header auth, `q` as a
    query-string-syntax expression, results sorted by filing date descending
    so a single page covers the most recent filings first. A 404 from this
    API means "zero matches" (its normal empty-result response), not a real
    error, so it's returned as [] rather than raised. One retry on 429
    (rate-limited once tonight under back-to-back requests)."""
    headers = {"X-Api-Key": USPTO_API_KEY, "Accept": "application/json"}
    params = {
        "q": query,
        "limit": limit,
        "sort": "applicationMetaData.filingDate desc",
    }

    for attempt in range(2):
        resp = requests.get(USPTO_SEARCH_URL, headers=headers, params=params, timeout=20)
        if resp.status_code == 404:
            return []
        if resp.status_code == 429 and attempt == 0:
            time.sleep(3)
            continue
        resp.raise_for_status()
        return resp.json().get("patentFileWrapperDataBag", [])
    return []


def _extract_filing(record: dict) -> dict | None:
    """Pull the fields we care about out of one patentFileWrapperDataBag
    record. Returns None if the record is missing a title or filing date
    (can't judge or date-filter it). `applicationNumberText` is a top-level
    field on the record (sibling of applicationMetaData, not nested inside
    it) — confirmed against a raw API response — and is the actual unique
    identifier USPTO assigns per application, unlike assignee+title+date
    which two same-day continuation filings can share verbatim."""
    amd = record.get("applicationMetaData") or {}
    filing_date = amd.get("filingDate")
    title = amd.get("inventionTitle")
    if not filing_date or not title:
        return None
    applicants = [
        a.get("applicantNameText")
        for a in amd.get("applicantBag", [])
        if a.get("applicantNameText")
    ]
    return {
        "assignee": "; ".join(applicants) if applicants else "Unknown",
        "title": title,
        "filing_date": filing_date,
        "application_number": record.get("applicationNumberText"),
        "cpc": amd.get("cpcClassificationBag") or [],
    }


def fetch_by_assignee(company_name: str, lookback_days: int) -> list[dict]:
    """applicantNameText phrase match — verified tonight to match on
    substring/adjacent-token phrases within the full legal entity name
    (e.g. "Blue Origin" matches "Blue Origin Manufacturing, LLC"). Date
    filtering is done client-side rather than via the API's own range-query
    param: combining a quoted phrase clause with a filingDate range clause
    in the same `q` string proved fragile earlier tonight (worked sometimes,
    silently mis-parsed other times), so it's safer to fetch broad + sorted,
    then filter here."""
    query = f'applicationMetaData.applicantBag.applicantNameText:"{company_name}"'
    records = _uspto_search(query)

    cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    results = []
    for record in records:
        filing = _extract_filing(record)
        if filing is None or filing["filing_date"] < cutoff:
            continue
        filing.pop("cpc", None)
        results.append(filing)
    return results


def fetch_by_cpc(cpc_class: str, lookback_days: int) -> list[dict]:
    """CPC search. An unquoted single-token wildcard on the bare class code
    (e.g. `B64G*`) works reliably server-side — verified tonight. It stops
    being reliable the moment the target gets more specific than a bare
    class (e.g. a subgroup like "B64G 6"): cpcClassificationBag values
    contain internal whitespace ("B64G   6/00"), and the query-string parser
    splits on whitespace *before* the field scope applies, so neither a
    quoted phrase nor a quoted wildcard actually matches — confirmed
    tonight. Fix (same one used tonight): search broad with just the class
    wildcard, then verify/narrow client-side by stripping whitespace from
    both sides and comparing prefixes directly."""
    class_prefix = cpc_class.split()[0]
    query = f"applicationMetaData.cpcClassificationBag:{class_prefix}*"
    records = _uspto_search(query)

    cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    normalized_target = cpc_class.replace(" ", "").upper()

    results = []
    for record in records:
        filing = _extract_filing(record)
        if filing is None or filing["filing_date"] < cutoff:
            continue
        cpc_codes = filing.pop("cpc", [])
        if not any(code.replace(" ", "").upper().startswith(normalized_target) for code in cpc_codes):
            continue
        results.append(filing)
    return results


# ---------------------------------------------------------------------------
# MEMORY — avoid re-judging the same filing on every run
# ---------------------------------------------------------------------------

def filing_key(filing: dict) -> str:
    """Prefer the application's real USPTO identifier (applicationNumberText)
    — it's unique per application, unlike assignee+title+date, which two
    same-day continuation/divisional filings can share verbatim (confirmed:
    two Digital Global Systems filings on 2026-02-18 had identical assignee,
    title, and date, and collided under the old hash). Fall back to the old
    hash only if the application number is somehow missing from the record."""
    app_num = filing.get("application_number")
    if app_num:
        return f"appnum:{app_num}"
    raw = f"{filing.get('assignee','')}|{filing.get('title','')}|{filing.get('filing_date','')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def load_seen_memory() -> set:
    if not SEEN_MEMORY_PATH.exists():
        return set()
    try:
        with open(SEEN_MEMORY_PATH, "r") as f:
            return set(json.load(f))
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARNING: could not read seen-memory file, starting fresh: {e}", file=sys.stderr)
        return set()


def save_seen_memory(seen: set) -> None:
    try:
        with open(SEEN_MEMORY_PATH, "w") as f:
            json.dump(sorted(seen), f, indent=2)
    except OSError as e:
        print(f"ERROR: could not write seen-memory file: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# HISTORY — extends the existing flat-file pattern
# ---------------------------------------------------------------------------

def load_history() -> list:
    if not HISTORY_PATH.exists():
        return []
    try:
        with open(HISTORY_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARNING: could not read history file, starting fresh: {e}", file=sys.stderr)
        return []


def save_history(history: list) -> None:
    try:
        with open(HISTORY_PATH, "w") as f:
            json.dump(history, f, indent=2)
    except OSError as e:
        print(f"ERROR: could not write history file: {e}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# JUDGMENT
# ---------------------------------------------------------------------------

def judge_filings(candidates: list) -> list:
    """Send unseen candidates to Haiku in one batched call, get back
    pick/reject + summaries. Returns [] if candidates is empty (no API
    call made — no reason to spend tokens on a quiet day)."""
    if not candidates:
        return []

    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    numbered = "\n".join(
        f"{i}. {c['assignee']} — \"{c['title']}\" (filed {c['filing_date']})"
        for i, c in enumerate(candidates)
    )

    try:
        response = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=2000,
            system=build_system_prompt(),
            messages=[{"role": "user", "content": f"Judge this batch:\n\n{numbered}"}],
        )
        raw_text = response.content[0].text.strip()
        raw_text = raw_text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        judgments = json.loads(raw_text)
    except (anthropic.APIError, json.JSONDecodeError, IndexError, KeyError) as e:
        print(f"ERROR: judgment call failed, skipping this run's picks: {e}", file=sys.stderr)
        return []

    results = []
    for j in judgments:
        idx = j.get("index")
        if idx is None or not (0 <= idx < len(candidates)):
            continue
        if j.get("pick"):
            candidate = candidates[idx]
            results.append({
                "assignee": candidate["assignee"],
                "title": candidate["title"],
                "filing_date": candidate["filing_date"],
                "plain_summary": j.get("plain_summary"),
                "why_it_matters": j.get("why_it_matters"),
            })
    return results


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    if not USPTO_API_KEY:
        print("ERROR: USPTO_API_KEY not set (check .env).", file=sys.stderr)
        sys.exit(1)

    seen = load_seen_memory()
    all_candidates = []

    for company in BASELINE_COMPANIES:
        try:
            filings = fetch_by_assignee(company, LOOKBACK_DAYS)
            all_candidates.extend(filings)
        except Exception as e:
            print(f"WARNING: assignee fetch failed for {company!r}, skipping: {e}", file=sys.stderr)

    for cpc in CPC_CLASSES:
        try:
            filings = fetch_by_cpc(cpc, LOOKBACK_DAYS)
            all_candidates.extend(filings)
        except Exception as e:
            print(f"WARNING: CPC fetch failed for {cpc!r}, skipping: {e}", file=sys.stderr)

    # De-dup against memory, and de-dup within this run's own results
    # (assignee search and CPC search can both surface the same filing).
    unseen = []
    run_keys = set()
    for f in all_candidates:
        k = filing_key(f)
        if k in seen or k in run_keys:
            continue
        run_keys.add(k)
        unseen.append(f)

    print(f"Fetched {len(all_candidates)} total candidates, {len(unseen)} unseen after dedup.")

    picks = judge_filings(unseen)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    history = load_history()
    history.append({
        "date": today,
        "candidates_checked": len(unseen),
        "picks": picks,
    })
    save_history(history)

    seen.update(run_keys)
    save_seen_memory(seen)

    if picks:
        print(f"Wrote {len(picks)} pick(s) to {HISTORY_PATH.name}:")
        for p in picks:
            print(f"  - {p['assignee']}: {p['title']}")
    else:
        print(f"Quiet day — 0 picks. Logged a checked-but-empty entry to {HISTORY_PATH.name}.")


if __name__ == "__main__":
    main()
