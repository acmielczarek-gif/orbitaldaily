#!/usr/bin/env python3
"""
Orbital Daily — Definitive Generator
All features. All fixes. All layman tweaks.

GitHub Secrets required:
  ANTHROPIC_API_KEY   — Claude editorial note
  BUTTONDOWN_API_KEY  — Daily email digest
  NASA_API_KEY        — NASA NeoWs + DONKI
"""

import math, os, sys, json, requests
from datetime import datetime, timedelta, timezone
from html import escape

# ── Configuration ──────────────────────────────────────────────────────────────

GA_MEASUREMENT_ID   = "G-WKN4NLN7XC"
BUTTONDOWN_USERNAME = "orbitaldaily"
SITE_URL            = "https://orbitaldaily.com"
NASA_KEY            = os.environ.get("NASA_API_KEY", "DEMO_KEY")
UA                  = {"User-Agent": "OrbitalDaily/1.0 (orbitaldaily.com)"}


# ── HTTP ───────────────────────────────────────────────────────────────────────

def get(url, timeout=12):
    try:
        r = requests.get(url, headers=UA, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"  ⚠  {url[:70]}: {e}", file=sys.stderr)
        return None


# ── Moon phase ─────────────────────────────────────────────────────────────────

def moon_phase(date):
    known_new = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
    pos   = ((date - known_new).total_seconds() / 86400 % 29.53058770576) / 29.53058770576
    illum = (1 - math.cos(2 * math.pi * pos)) / 2
    thresholds = [0.0625,0.1875,0.3125,0.4375,0.5625,0.6875,0.8125,0.9375]
    names  = ["New Moon","Waxing Crescent","First Quarter","Waxing Gibbous",
              "Full Moon","Waning Gibbous","Last Quarter","Waning Crescent"]
    emojis = ["🌑","🌒","🌓","🌔","🌕","🌖","🌗","🌘"]
    idx = 0
    for i, t in enumerate(thresholds):
        if pos < t:
            idx = i
            break
    return pos, illum, names[idx], emojis[idx]


# ── Astrophotography score ─────────────────────────────────────────────────────

def astro_score(kp, moon_illum, days_to_shower):
    moon_s   = 10.0 * (1.0 - moon_illum)
    kp_s     = max(0.0, 10.0 - (kp if kp is not None else 2.0) * 1.4)
    d        = days_to_shower
    shower_s = (10 if d is not None and d<=1 else
                10-d if d and d<=7 else
                max(0, 5-(d-7)*0.5) if d and d<=14 else 0)
    return round(min(10.0, max(0.0, moon_s*.55 + kp_s*.25 + shower_s*.20)), 1)

def score_color(s):
    if s >= 7.0: return "#4ade80"
    if s >= 5.5: return "#86efac"
    if s >= 4.0: return "#fbbf24"
    if s >= 2.5: return "#f97316"
    return "#f87171"

def score_label(s):
    if s >= 8.5: return "Exceptional"
    if s >= 7.0: return "Excellent"
    if s >= 5.5: return "Good"
    if s >= 4.0: return "Fair"
    if s >= 2.5: return "Poor"
    return "Unfavorable"


# ── Fetchers ───────────────────────────────────────────────────────────────────

def fetch_kp():
    r = get("https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json")
    if not r: return None
    for row in reversed(r.json()):
        try:
            val = float(row.get("kp") or row.get("Kp") or 0) if isinstance(row, dict) else float(row[1])
            if val >= 0: return val
        except: continue
    return None

def fetch_kp_forecast():
    r = get("https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json")
    if not r: return {}
    by_day = {}
    for row in r.json()[1:]:
        try:
            dt  = datetime.fromisoformat(str(row[0]).replace("Z","+00:00"))
            key = dt.strftime("%Y-%m-%d")
            by_day.setdefault(key, []).append(float(row[1]))
        except: continue
    return {k: round(sum(v)/len(v), 1) for k, v in by_day.items()}

def kp_label(kp):
    if kp is None:  return "UNKNOWN",       "#64748b"
    if kp >= 7:     return "EXTREME STORM", "#f87171"
    if kp >= 5:     return "GEOMAG STORM",  "#f97316"
    if kp >= 4:     return "ACTIVE",        "#fbbf24"
    if kp >= 2:     return "UNSETTLED",     "#86efac"
    return                  "QUIET",        "#4ade80"

def fetch_news():
    r = get("https://api.spaceflightnewsapi.net/v4/articles/?limit=18&ordering=-published_at")
    return r.json().get("results", []) if r else []

def fetch_launches():
    r = get("https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit=8&format=json")
    return r.json().get("results", []) if r else []

def fetch_space_history(date):
    r = get(f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{date.month}/{date.day}")
    if not r: return None
    kw = ["space","nasa","astronaut","rocket","satellite","moon","mars","apollo",
          "shuttle","iss","orbit","launch","cosmonaut","sputnik","hubble","spacex","crew"]
    for ev in r.json().get("events", []):
        if any(k in ev.get("text","").lower() for k in kw):
            pages = ev.get("pages", [])
            url   = pages[0].get("content_urls",{}).get("desktop",{}).get("page","") if pages else ""
            return {"year": ev.get("year",""), "text": ev.get("text",""), "url": url}
    return None

def fetch_humans_in_space():
    r = get("http://api.open-notify.org/astros.json")
    if not r: return 0, []
    data = r.json()
    return data.get("number", 0), data.get("people", [])

def fetch_neo(now):
    start = now.strftime("%Y-%m-%d")
    end   = (now + timedelta(days=7)).strftime("%Y-%m-%d")
    r     = get(f"https://api.nasa.gov/neo/rest/v1/feed?start_date={start}&end_date={end}&api_key={NASA_KEY}")
    if not r: return []
    objects = []
    for date, neos in r.json().get("near_earth_objects", {}).items():
        for neo in neos:
            try:
                approach = neo.get("close_approach_data", [{}])[0]
                ld       = float(approach.get("miss_distance", {}).get("lunar", 9999))
                vel      = float(approach.get("relative_velocity", {}).get("kilometers_per_second", 0))
                diam_d   = neo.get("estimated_diameter", {}).get("meters", {})
                diam     = (diam_d.get("estimated_diameter_min",0) + diam_d.get("estimated_diameter_max",0)) / 2
                objects.append({
                    "name": neo.get("name","").strip("()"),
                    "date": date,
                    "approach_str": approach.get("close_approach_date_full",""),
                    "ld": ld, "vel": round(vel,1), "diam": round(diam),
                    "hazardous": neo.get("is_potentially_hazardous_asteroid", False)
                })
            except: continue
    return sorted(objects, key=lambda x: x["ld"])

def fetch_solar_flares(now):
    start = (now - timedelta(days=4)).strftime("%Y-%m-%d")
    end   = now.strftime("%Y-%m-%d")
    r     = get(f"https://api.nasa.gov/DONKI/FLR?startDate={start}&endDate={end}&api_key={NASA_KEY}")
    if not r: return []
    data = r.json()
    return sorted(data, key=lambda x: x.get("beginTime",""), reverse=True) if isinstance(data, list) else []

SHOWERS = [
    (1,3,"Quadrantids",120),(4,22,"Lyrids",20),(5,6,"Eta Aquariids",50),
    (8,12,"Perseids",100),(10,21,"Orionids",20),(11,17,"Leonids",15),
    (12,13,"Geminids",150),(12,22,"Ursids",10),
]

def upcoming_showers(n=3):
    now, out = datetime.now(timezone.utc), []
    for mo,dy,name,zhr in SHOWERS:
        try:
            peak = datetime(now.year,mo,dy,tzinfo=timezone.utc)
            if peak < now - timedelta(days=3):
                peak = datetime(now.year+1,mo,dy,tzinfo=timezone.utc)
            out.append(((peak-now).days, name, f"{peak.strftime('%b')} {peak.day}", zhr))
        except: continue
    return sorted(out)[:n]

def next_shower_days_from(date):
    out = []
    for mo,dy,name,zhr in SHOWERS:
        try:
            peak = datetime(date.year,mo,dy,tzinfo=timezone.utc)
            if peak < date - timedelta(days=3):
                peak = datetime(date.year+1,mo,dy,tzinfo=timezone.utc)
            out.append((peak-date).days)
        except: continue
    return min(out) if out else None

def launch_timing(net):
    try:
        dt   = datetime.fromisoformat(net.replace("Z","+00:00"))
        diff = dt - datetime.now(timezone.utc)
        d    = diff.days
        if d < 0:  return "LAUNCHED"
        if d == 0: return f"T-{diff.seconds//3600}H"
        if d == 1: return "TOMORROW"
        return f"{dt.strftime('%b').upper()} {dt.day}"
    except: return "TBD"


# ── Space Activity Index ───────────────────────────────────────────────────────

def compute_sai(kp, launches, neos, flares):
    launch_score = min(100, (len(launches) / 6) * 100)
    kp_score     = min(100, ((kp if kp else 2.0) / 9) * 100 * 1.5)
    solar_score  = 0
    if flares:
        cls = flares[0].get("classType","")
        if cls.startswith("X"):
            mag = float(cls[1:]) if len(cls)>1 and cls[1:].replace(".","").isdigit() else 1
            solar_score = min(100, 80 + mag*5)
        elif cls.startswith("M"):
            mag = float(cls[1:]) if len(cls)>1 and cls[1:].replace(".","").isdigit() else 1
            solar_score = min(100, 40 + mag*8)
        elif cls.startswith("C"):
            solar_score = 20
    neo_score = 0
    if neos:
        ld = neos[0]["ld"]
        if ld < 1:    neo_score = 100
        elif ld < 5:  neo_score = max(0, 100 - (ld/5)*60)
        elif ld < 20: neo_score = max(0, 40 - ld*2)
    sai = max(0, min(100, round(launch_score*.35 + kp_score*.30 + solar_score*.25 + neo_score*.10)))
    if sai >= 75: status, color = "EXTREME", "#f87171"
    elif sai >= 50: status, color = "HIGH",    "#fbbf24"
    elif sai >= 25: status, color = "MODERATE","#60a5fa"
    else:           status, color = "LOW",     "#4ade80"
    return sai, status, color


# ── 7-day forecast ─────────────────────────────────────────────────────────────

def compute_7day(now, kp, kp_forecast):
    days = []
    for i in range(7):
        d  = now + timedelta(days=i)
        ds = d.strftime("%Y-%m-%d")
        _, illum, mname, memoji = moon_phase(d)
        day_kp = kp if i==0 else kp_forecast.get(ds)
        score  = astro_score(day_kp, illum, next_shower_days_from(d))
        days.append({"dt":d,"illum":illum,"moon_name":mname,"moon_emoji":memoji,
                     "kp":day_kp,"score":score,"estimated": i>=3 or day_kp is None})
    return days


# ── Claude editorial note ──────────────────────────────────────────────────────

def fetch_editorial(kp, score, launches, showers, moon_name, history, flares, neos):
    api_key = os.environ.get("ANTHROPIC_API_KEY","")
    if not api_key: return None, None
    kp_text, _ = kp_label(kp)
    ctx = []
    if kp is not None: ctx.append(f"Kp: {kp:.1f} ({kp_text.lower()})")
    ctx.append(f"Astrophotography score: {score}/10 ({score_label(score)})")
    ctx.append(f"Moon: {moon_name} ({int(moon_illum_global*100)}% illuminated)")
    if flares:   ctx.append(f"Solar: {flares[0].get('classType','')} flare recently")
    if neos:     ctx.append(f"NEO: {neos[0]['name']} at {neos[0]['ld']:.1f} lunar distances")
    if launches: ctx.append(f"Next launch: {launches[0].get('name','')} ({launch_timing(launches[0].get('net',''))})")
    if showers:  ctx.append(f"Next shower: {showers[0][1]} in {showers[0][0]} days")
    if history:  ctx.append(f"Today in history ({history['year']}): {history['text'][:100]}")

    band = score_band(score)
    if band == "poor":
        directive = "discourage going out tonight, name what is ruining conditions, point to a better upcoming night"
    elif band == "fair":
        directive = "be measured and conditional -- worth trying but with caveats"
    elif band == "good":
        directive = "encourage going out, name what makes it worthwhile"
    else:
        directive = "be enthusiastic -- this is a genuinely good night, say why"

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model":"claude-haiku-4-5-20251001","max_tokens":300,
                  "messages":[{"role":"user","content":
                    f"Tonight's conditions:\n{chr(10).join(ctx)}\n\n"
                    f"Write exactly 2 paragraphs of editorial prose for a space intelligence dispatch. "
                    f"Directive: {directive}. "
                    "Paragraph 1: describe tonight's actual sky conditions -- moon, Kp, what it means for a photographer or stargazer. "
                    "Paragraph 2: what to do, what is coming, what to look for. "
                    "Voice: dry, informed, like a seasoned correspondent's field note. "
                    "No em-dash openers. No 'tonight is'. No generic openings. No em dashes anywhere. "
                    "Return only the two paragraphs, separated by a blank line. No labels."}]},
            timeout=18
        )
        if r.status_code == 200:
            for block in r.json().get("content",[]):
                if block.get("type") == "text":
                    parts = [p.strip() for p in block["text"].strip().split("\n\n") if p.strip()]
                    p1 = parts[0] if len(parts) > 0 else ""
                    p2 = parts[1] if len(parts) > 1 else ""
                    return p1, p2
    except Exception as e:
        print(f"  Editorial: {e}", file=sys.stderr)
    return None, None


# ── Dark sky parks ─────────────────────────────────────────────────────────────

DARK_SKY_PARKS = [
    {"name":"Cherry Springs State Park","lat":41.66,"lon":-77.82,"bortle":2,"state":"PA"},
    {"name":"Headlands Dark Sky Park","lat":45.75,"lon":-84.63,"bortle":3,"state":"MI"},
    {"name":"Big Bend National Park","lat":29.25,"lon":-103.25,"bortle":2,"state":"TX"},
    {"name":"Death Valley National Park","lat":36.46,"lon":-117.02,"bortle":2,"state":"CA"},
    {"name":"Natural Bridges NM","lat":37.60,"lon":-109.99,"bortle":2,"state":"UT"},
    {"name":"Chaco Culture NHP","lat":36.06,"lon":-107.96,"bortle":2,"state":"NM"},
    {"name":"Harriman State Park","lat":41.26,"lon":-74.14,"bortle":4,"state":"NY"},
    {"name":"Assateague Island","lat":38.05,"lon":-75.20,"bortle":4,"state":"MD"},
    {"name":"Anza-Borrego Desert","lat":33.22,"lon":-116.41,"bortle":2,"state":"CA"},
    {"name":"Canyonlands National Park","lat":38.20,"lon":-109.93,"bortle":2,"state":"UT"},
    {"name":"Glacier National Park","lat":48.50,"lon":-113.80,"bortle":2,"state":"MT"},
    {"name":"Great Basin National Park","lat":38.98,"lon":-114.26,"bortle":2,"state":"NV"},
    {"name":"Acadia National Park","lat":44.35,"lon":-68.21,"bortle":4,"state":"ME"},
    {"name":"Shenandoah National Park","lat":38.53,"lon":-78.35,"bortle":4,"state":"VA"},
    {"name":"Grand Canyon National Park","lat":36.10,"lon":-112.11,"bortle":2,"state":"AZ"},
    {"name":"Dry Tortugas National Park","lat":24.63,"lon":-82.87,"bortle":3,"state":"FL"},
    {"name":"Craters of the Moon NM","lat":43.42,"lon":-113.52,"bortle":2,"state":"ID"},
    {"name":"Black Canyon of the Gunnison","lat":38.57,"lon":-107.72,"bortle":2,"state":"CO"},
    {"name":"Joshua Tree National Park","lat":33.88,"lon":-115.90,"bortle":3,"state":"CA"},
    {"name":"Harmony Borrego Springs","lat":33.26,"lon":-116.38,"bortle":3,"state":"CA"},
]

def dark_sky_json():
    return json.dumps([{"name":p["name"],"lat":p["lat"],"lon":p["lon"],"bortle":p["bortle"]} for p in DARK_SKY_PARKS])


# ── Helpers ────────────────────────────────────────────────────────────────────

def esc(s): return escape(str(s))

moon_illum_global = 0.0

def score_band(s):
    if s >= 7.0: return "excellent"
    if s >= 5.0: return "good"
    if s >= 3.0: return "fair"
    return "poor"

def band_color(s):
    if s >= 5.0: return "var(--od-verdict-good)"
    if s >= 3.0: return "var(--od-verdict-fair)"
    return "var(--od-verdict-poor)"

def band_color_hex(s):
    if s >= 5.0: return "#2f7d3e"
    if s >= 3.0: return "#a07508"
    return "#b04a2f"

def row_tint(s):
    if s >= 5.0: return "rgba(47,125,62,.05)"
    if s < 3.0:  return "rgba(176,74,47,.04)"
    return "transparent"

def lede_headline(score):
    if score >= 7.0: return "Get outside tonight."
    if score >= 5.0: return "Worth a look tonight."
    if score >= 3.0: return "Wait for a better window."
    return "Stay in tonight."

def verdict_data(score):
    if score >= 7.0: return "EXCELLENT",   "var(--od-verdict-good)", "rgba(47,125,62,.03)"
    if score >= 5.0: return "GOOD",        "var(--od-verdict-good)", "rgba(47,125,62,.03)"
    if score >= 3.0: return "FAIR",        "var(--od-verdict-fair)", "rgba(160,117,8,.03)"
    return                   "UNFAVOURABLE","var(--od-verdict-poor)", "rgba(176,74,47,.03)"

def moon_cx(illum):
    return f"{(50 - (1 - illum) * 48):.1f}"

def issue_number(now):
    launch = datetime(2026, 1, 1, tzinfo=timezone.utc)
    days   = (now - launch).days
    return f"Vol. {days // 90 + 1} · No. {days % 90 + 1}"

def launch_when_color(timing):
    t = timing.upper()
    if t == "LAUNCHED": return "var(--od-faint-2)"
    if t.startswith("T-"): return "var(--od-accent)"
    return "var(--od-ink-2)"


# ── fetch_editorial — 2 paragraphs, returns (p1, p2) ──────────────────────────

def fetch_editorial(kp, score, launches, showers, moon_name, history, flares, neos):
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key: return None, None
    kp_text, _ = kp_label(kp)
    ctx = []
    if kp is not None: ctx.append(f"Kp: {kp:.1f} ({kp_text.lower()})")
    ctx.append(f"Astrophotography score: {score}/10 ({score_label(score)})")
    ctx.append(f"Moon: {moon_name} ({int(moon_illum_global * 100)}% illuminated)")
    if flares:   ctx.append(f"Solar: {flares[0].get('classType', '')} flare recently")
    if neos:     ctx.append(f"NEO: {neos[0]['name']} at {neos[0]['ld']:.1f} lunar distances")
    if launches: ctx.append(f"Next launch: {launches[0].get('name', '')} ({launch_timing(launches[0].get('net', ''))})")
    if showers:  ctx.append(f"Next shower: {showers[0][1]} in {showers[0][0]} days")
    if history:  ctx.append(f"Today in history ({history['year']}): {history['text'][:100]}")

    band = score_band(score)
    directive = {
        "poor":      "discourage going out tonight, name what is ruining conditions, point to a better night ahead",
        "fair":      "be measured and conditional -- worth trying but only with caveats",
        "good":      "encourage going out, name what makes it worthwhile",
        "excellent": "be enthusiastic -- this is a genuinely good night, say why",
    }[band]

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-haiku-4-5-20251001", "max_tokens": 300,
                  "messages": [{"role": "user", "content":
                      f"Tonight's conditions:\n{chr(10).join(ctx)}\n\n"
                      f"Write exactly 2 paragraphs of editorial prose for a space intelligence dispatch. "
                      f"Directive: {directive}. "
                      "Paragraph 1: sky conditions tonight -- moon, Kp, what it means. "
                      "Paragraph 2: what to do, what is coming. "
                      "Voice: dry, informed, seasoned correspondent. "
                      "No em dashes anywhere. No generic openings. "
                      "Return only the two paragraphs separated by a blank line. No labels."}]},
            timeout=18
        )
        if r.status_code == 200:
            for block in r.json().get("content", []):
                if block.get("type") == "text":
                    parts = [p.strip() for p in block["text"].strip().split("\n\n") if p.strip()]
                    return (parts[0] if parts else ""), (parts[1] if len(parts) > 1 else "")
    except Exception as e:
        print(f"  Editorial: {e}", file=sys.stderr)
    return None, None


# ── Dark sky parks ─────────────────────────────────────────────────────────────

DARK_SKY_PARKS = [
    {"name":"Cherry Springs State Park","lat":41.66,"lon":-77.82,"bortle":2},
    {"name":"Headlands Dark Sky Park","lat":45.75,"lon":-84.63,"bortle":3},
    {"name":"Big Bend National Park","lat":29.25,"lon":-103.25,"bortle":2},
    {"name":"Death Valley National Park","lat":36.46,"lon":-117.02,"bortle":2},
    {"name":"Natural Bridges NM","lat":37.60,"lon":-109.99,"bortle":2},
    {"name":"Harriman State Park","lat":41.26,"lon":-74.14,"bortle":4},
    {"name":"Assateague Island","lat":38.05,"lon":-75.20,"bortle":4},
    {"name":"Anza-Borrego Desert","lat":33.22,"lon":-116.41,"bortle":2},
    {"name":"Canyonlands National Park","lat":38.20,"lon":-109.93,"bortle":2},
    {"name":"Glacier National Park","lat":48.50,"lon":-113.80,"bortle":2},
    {"name":"Great Basin National Park","lat":38.98,"lon":-114.26,"bortle":2},
    {"name":"Acadia National Park","lat":44.35,"lon":-68.21,"bortle":4},
    {"name":"Shenandoah National Park","lat":38.53,"lon":-78.35,"bortle":4},
    {"name":"Grand Canyon National Park","lat":36.10,"lon":-112.11,"bortle":2},
    {"name":"Joshua Tree National Park","lat":33.88,"lon":-115.90,"bortle":3},
    {"name":"Craters of the Moon NM","lat":43.42,"lon":-113.52,"bortle":2},
    {"name":"Black Canyon of the Gunnison","lat":38.57,"lon":-107.72,"bortle":2},
    {"name":"Dry Tortugas National Park","lat":24.63,"lon":-82.87,"bortle":3},
]


# ── Buttondown email ───────────────────────────────────────────────────────────

def send_daily_email(kp, score, sai_score, launches, news, neos, flares,
                     moon_name, moon_illum, ed_p1, ed_p2, now):
    api_key = os.environ.get("BUTTONDOWN_API_KEY", "")
    if not api_key:
        print("  Email: no BUTTONDOWN_API_KEY -- skipping")
        return

    kp_text, _ = kp_label(kp)
    kp_display  = f"{kp:.1f}" if kp is not None else "N/A"
    moon_pct    = int(round(moon_illum * 100))
    date_str    = now.strftime(f"%B {now.day}, %Y")
    divider     = "-" * 48
    gps_status  = "Degraded" if kp and kp >= 4 else "Normal"
    editorial   = ((ed_p1 or "") + " " + (ed_p2 or "")).strip()

    if kp and kp >= 5:
        subject = f"Orbital Daily: {now.strftime('%b')} {now.day} -- Aurora alert active, Kp {kp_display}"
    elif score >= 7.5:
        subject = f"Orbital Daily: {now.strftime('%b')} {now.day} -- {score}/10 tonight"
    elif neos and neos[0]["ld"] < 5:
        subject = f"Orbital Daily: {now.strftime('%b')} {now.day} -- Asteroid {neos[0]['name']} passing Earth"
    elif launches:
        subject = f"Orbital Daily: {now.strftime('%b')} {now.day} -- {launches[0].get('name', '')} {launch_timing(launches[0].get('net', ''))}"
    else:
        subject = f"Orbital Daily: {now.strftime('%b')} {now.day} -- Space Activity Index {sai_score}/100"

    launch_block = "\n".join(
        f"  {launch_timing(l.get('net',''))} -- {l.get('name','')}"
        for l in launches[:4]
    ) if launches else "  No launches scheduled"

    solar_block = f"{flares[0].get('classType','')} flare detected recently" if flares else "No active solar events"
    neo_block   = f"{neos[0]['name']} -- {neos[0]['ld']:.1f} lunar distances, {neos[0].get('date','this week')}" if neos else "No notable close approaches"
    headlines   = "\n".join(f"  * {a['title']}" for a in news[:5]) if news else "  * No headlines available"
    editorial_text = editorial if editorial else "Visit orbitaldaily.com for today's full briefing."

    body = f"""Orbital Daily tracks space conditions daily: astrophotography scores, rocket launches, aurora alerts, and near-Earth objects, computed fresh every morning.

{divider}

{editorial_text}

{divider}

TONIGHT -- {date_str}
Astrophotography Score: {score}/10 -- {score_label(score)}
Moon: {moon_name} -- {moon_pct}% illuminated

SPACE WEATHER
Kp Index: {kp_display} -- {kp_text}
GPS: {gps_status}
Solar: {solar_block}

UPCOMING LAUNCHES
{launch_block}

NEAR-EARTH OBJECTS
{neo_block}

{divider}

TOP HEADLINES

{headlines}

{divider}

Read the full dispatch at orbitaldaily.com
"""

    try:
        r = requests.post(
            "https://api.buttondown.com/v1/emails",
            headers={
                "Authorization": f"Token {api_key}",
                "Content-Type": "application/json",
                "X-Buttondown-Live-Dangerously": "true"
            },
            json={"subject": subject, "body": body, "status": "about_to_send"},
            timeout=15
        )
        if r.status_code in (200, 201):
            print(f"  Email sent: {subject}")
        else:
            print(f"  Email failed: {r.status_code} -- {r.text[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"  Email error: {e}", file=sys.stderr)


# ── Renderer ───────────────────────────────────────────────────────────────────

PAGE_CSS = """<style>
  :root {
    --od-paper:#faf9f5; --od-field:#fffdf8;
    --od-ink:#14181d; --od-ink-2:#2a2f36; --od-ink-3:#4a4f57;
    --od-muted:#6b6a62; --od-faint:#8a8578; --od-faint-2:#a8a294;
    --od-rule:#ddd8cc; --od-rule-row:#e7e3d8; --od-rule-mast:#d8d4c8; --od-field-border:#cfc9ba;
    --od-accent:#1b3a6b; --od-alert:#b45309;
    --od-verdict-poor:#b04a2f; --od-verdict-fair:#a07508; --od-verdict-good:#2f7d3e;
    --od-moon-lit:#f3efe4; --od-moon-shadow:#c7cbd2;
    --od-tooltip-bg:#14181d; --od-tooltip-text:#c9cdd4;
    --od-serif:'Newsreader',Georgia,serif; --od-mono:'IBM Plex Mono',ui-monospace,monospace;
    --od-max:940px;
  }
  *{ box-sizing:border-box; }
  html,body{ margin:0; padding:0; }
  body{ background:var(--od-paper); color:var(--od-ink); font-family:var(--od-serif); -webkit-font-smoothing:antialiased; text-rendering:optimizeLegibility; }
  a{ color:inherit; text-decoration:none; }
  ::selection{ background:#dfe6ee; }
  .wrap{ max-width:var(--od-max); margin:0 auto; padding:0 26px 90px; }
  .mono{ font-family:var(--od-mono); }
  .eyebrow{ font-family:var(--od-mono); font-size:11px; letter-spacing:.22em; text-transform:uppercase; color:var(--od-faint); }
  h2,h3{ font-family:var(--od-serif); font-weight:600; letter-spacing:-.02em; color:var(--od-ink); margin:0; }
  .term{ position:relative; cursor:default; }
  .term .tip{
    position:absolute; width:250px; max-width:76vw; background:var(--od-tooltip-bg); color:var(--od-tooltip-text);
    padding:12px 15px; border-radius:8px; font-family:var(--od-serif); font-style:normal; font-weight:400;
    font-size:14px; line-height:1.5; text-align:left; text-transform:none; letter-spacing:normal;
    box-shadow:0 14px 34px rgba(20,24,29,.3); z-index:60;
    opacity:0; visibility:hidden; transform:translateY(4px);
    transition:opacity .16s ease, transform .16s ease; pointer-events:none;
  }
  .term .tip.below{ top:calc(100% + 9px); left:0; }
  .term .tip.above{ bottom:calc(100% + 9px); left:50%; margin-left:-125px; }
  .term:hover .tip, .term.open .tip{ opacity:1; visibility:visible; transform:translateY(0); pointer-events:auto; }
  .idot{ display:inline-flex; align-items:center; justify-content:center; width:14px; height:14px; border-radius:50%; border:1px solid #cbc6b8; font-size:9px; color:var(--od-faint-2); }
  @keyframes odpulse{ 0%,100%{opacity:1;transform:scale(1);} 50%{opacity:.3;transform:scale(.75);} }
  .pulse{ width:8px; height:8px; border-radius:50%; background:var(--od-accent); animation:odpulse 1.6s ease-in-out infinite; display:inline-block; }
  @media(max-width:640px){ .lede-grid,.activity-grid,.week-head{ grid-template-columns:1fr !important; } .tout{ width:100% !important; } }
</style>
</head>"""


def render(kp, kp_forecast, news, launches, showers, humans_n, humans_list,
           neos, flares, history, ed_p1, ed_p2, now, sai_score, sai_status, sai_color,
           score, moon_illum, moon_name, moon_emoji, seven_day):

    global moon_illum_global
    moon_illum_global = moon_illum

    kp_text, kp_color = kp_label(kp)
    kp_display        = f"{kp:.1f}" if kp is not None else "N/A"
    moon_pct          = int(round(moon_illum * 100))
    cx                = moon_cx(moon_illum)
    headline          = lede_headline(score)
    stamp_label, stamp_color, stamp_bg = verdict_data(score)
    date_str          = now.strftime(f"%A · %B {now.day}, %Y · %H:%M UTC")
    amazon_tag        = "orbitaldaily-20"

    page_css = PAGE_CSS

    # GA4
    ga = (f'<script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>'
          f'<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}'
          f'gtag("js",new Date());gtag("config","{GA_MEASUREMENT_ID}");</script>'
          if "XXXXX" not in GA_MEASUREMENT_ID else "")

    # Schema
    schema = (f'{{"@context":"https://schema.org","@type":"WebSite","name":"Orbital Daily",'
              f'"url":"{SITE_URL}","description":"Independent daily space intelligence.",'
              f'"publisher":{{"@type":"Organization","name":"Orbital Daily"}}}}')

    # Bulletin
    if kp and kp >= 5:
        bulletin_html = (f'<div style="display:flex;align-items:baseline;gap:14px;padding:12px 2px;border-bottom:1px solid var(--od-ink);">'
                         f'<span class="mono" style="font-size:11px;font-weight:600;letter-spacing:.16em;color:var(--od-alert);white-space:nowrap;">&#9670; BULLETIN</span>'
                         f'<span style="font-size:16px;color:var(--od-ink-2);line-height:1.4;">Geomagnetic storm active, Kp <strong>{kp_display}</strong>. '
                         f'A faint aurora is possible on the northern horizon tonight; GPS may drift. '
                         f'<a href="https://spaceweather.gov" style="color:var(--od-accent);font-style:italic;border-bottom:1px solid #b7c3d3;">NOAA forecast</a></span></div>')
    else:
        bulletin_html = ""

    # Lede
    if ed_p1:
        drop  = esc(ed_p1[0])
        rest1 = esc(ed_p1[1:])
        p1_html = (f'<p style="font-size:20px;line-height:1.62;color:var(--od-ink-2);margin:0 0 14px;max-width:60ch;">'
                   f'<span style="float:left;font-weight:600;font-size:70px;line-height:.72;padding:8px 12px 0 0;">{drop}</span>'
                   f'{rest1}</p>')
        p2_html = f'<p style="font-size:20px;line-height:1.62;color:var(--od-ink-2);margin:0 0 16px;max-width:60ch;">{esc(ed_p2)}</p>' if ed_p2 else ""
    else:
        # Fallback defaults
        fallback = {
            "poor":      ("Conditions are stacked against the camera tonight. The moon is up and the magnetic field is restless -- nothing you can do about either.",
                          "Put the cover back on the scope and check Thursday's column instead."),
            "fair":      ("A mixed picture. There is some sky to work with if you are patient, but the moon will wash the faint stuff.",
                          "Wide-field targets and bright objects are the play. Faint nebulae can wait."),
            "good":      (f"Solid conditions tonight. Kp is holding at {kp_display} and the moon is giving enough of the sky back to make it worth going out.",
                          "Set up before midnight. Most targets will be well-placed by then."),
            "excellent": (f"The forecast handed you a genuinely good night. Kp at {kp_display}, moon at {moon_pct}% -- this is the kind of window you plan around.",
                          "Get outside. You can catch up on sleep tomorrow."),
        }[score_band(score)]
        drop  = esc(fallback[0][0])
        rest1 = esc(fallback[0][1:])
        p1_html = (f'<p style="font-size:20px;line-height:1.62;color:var(--od-ink-2);margin:0 0 14px;max-width:60ch;">'
                   f'<span style="float:left;font-weight:600;font-size:70px;line-height:.72;padding:8px 12px 0 0;">{drop}</span>'
                   f'{rest1}</p>')
        p2_html = f'<p style="font-size:20px;line-height:1.62;color:var(--od-ink-2);margin:0 0 16px;max-width:60ch;">{esc(fallback[1])}</p>'

    # AI blurb (use ed_p2 condensed, or a week summary)
    if ed_p2:
        ai_blurb = esc(ed_p2)
    else:
        best_day = max(seven_day, key=lambda d: d["score"])
        ai_blurb = esc(f"Conditions improve through the week -- {best_day['dt'].strftime('%A')} looks like the best window at {best_day['score']}/10.")

    # SAI description
    if sai_score >= 75:
        sai_desc = "The space world is extremely active tonight -- busy launch pads, charged skies, and something worth watching in every direction."
    elif sai_score >= 50:
        sai_desc = "A busy week overhead. Several launches on the manifest, and the sun has been active."
    elif sai_score >= 25:
        sai_desc = "Moderate activity. A handful of launches scheduled and conditions are holding steady."
    else:
        sai_desc = "A quiet period in space. Good conditions for observation, less so for drama."

    # TILES JSON
    aurora_val = "Watch" if kp and kp >= 5 else ("Possible" if kp and kp >= 3 else "Low")
    aurora_color = "var(--od-alert)" if kp and kp >= 5 else ("var(--od-verdict-fair)" if kp and kp >= 3 else "var(--od-faint-2)")
    aurora_detail = ("Kp is high enough to post a watch. Scan the northern horizon after dark." if kp and kp >= 5
                     else f"Kp at {kp_display}. Aurora possible at high latitudes only." if kp and kp >= 3
                     else f"Kp at {kp_display}. Geomagnetic field quiet tonight.")

    moon_dark_pct = int(round((1 - moon_illum) * 100))
    moon_dark_color = band_color(10 * (1 - moon_illum))

    neo_val    = f"{neos[0]['ld']:.1f}" if neos else "None"
    neo_unit   = "LD" if neos else ""
    neo_detail = (f"{neos[0]['name']}, est. {neos[0]['diam']}m across, at {neos[0]['ld']:.1f} lunar distances and {neos[0]['vel']} km/s. Routine and safe."
                  if neos else "No notable close approaches this week.")

    d = showers[0][0] if showers else None
    shower_s = round(10 if d and d<=1 else 10-d if d and d<=7 else max(0,5-(d-7)*0.5) if d and d<=14 else 0, 1)
    dark_hrs  = round(max(0, 8 - moon_illum * 6), 1)

    tiles_json = json.dumps([
        {"value": str(moon_dark_pct), "unit": "% dark", "label": "Moon darkness",
         "color": moon_dark_color, "href": "#moon",
         "detail": f"Moon is {moon_pct}% illuminated -- {100-moon_dark_pct}% of tonight is washed out. Moon darkness is the single biggest factor in the shoot score."},
        {"value": aurora_val, "unit": "", "label": "Aurora",
         "color": aurora_color, "href": "#aurora",
         "detail": aurora_detail},
        {"value": kp_display, "unit": "Kp", "label": "Geomagnetic storm" if kp and kp >= 5 else "Space weather",
         "color": "var(--od-verdict-poor)" if kp and kp >= 5 else "var(--od-ink)", "href": "#kp",
         "detail": f"Planetary Kp index from NOAA SWPC. Values above 5 indicate a storm; GPS may drift and aurora becomes visible at lower latitudes."},
        {"value": neo_val, "unit": neo_unit, "label": "Closest asteroid",
         "color": "var(--od-ink)", "href": "#neo",
         "detail": neo_detail},
        {"value": str(dark_hrs), "unit": "hrs", "label": "True-dark window",
         "color": "var(--od-ink)", "href": "#dark",
         "detail": f"Approximate hours of genuine astronomical dark tonight, accounting for moon phase. Best window is usually after {moon_pct < 50 and 'moonset' or 'midnight'}."},
    ])

    # FORECAST JSON
    forecast_json = json.dumps([
        {
            "day":   d["dt"].strftime("%a").upper(),
            "date":  d["dt"].strftime(f"%b {d['dt'].day}"),
            "illum": round(d["illum"], 2),
            "score": d["score"],
            "note":  (
                "Dark and quiet -- go." if d["score"] >= 7 else
                "Good window. Worth the drive." if d["score"] >= 5 else
                "Fair. Wide-field only." if d["score"] >= 3 else
                "Heavy moon or active sky. Skip it."
            ),
            "flag":  (
                next((str(sum(1 for l in launches if l.get("net","").startswith(d["dt"].strftime("%Y-%m-%d")))) + " LAUNCH" +
                      ("" if sum(1 for l in launches if l.get("net","").startswith(d["dt"].strftime("%Y-%m-%d"))) == 1 else "ES")
                      for _ in [None]
                      if sum(1 for l in launches if l.get("net","").startswith(d["dt"].strftime("%Y-%m-%d"))) > 0
                ), "est." if d["estimated"] else "")
            ),
        }
        for d in seven_day
    ])

    # GEAR JSON -- condition triggered
    if kp and kp >= 5:
        gear_items = [
            ("For tonight's aurora",  "Celestron SkyMaster 15x70",
             "Wide, bright, handheld -- the right glass for a low aurora and a fast ISS pass.",
             "~$95", f"https://www.amazon.com/s?k=Celestron+SkyMaster+15x70&tag={amazon_tag}"),
            ("For the northern horizon", "Energizer Night Vision Red Flashlight",
             "Preserves your night vision while you scan for the aurora band.",
             "~$20", f"https://www.amazon.com/s?k=red+flashlight+astronomy&tag={amazon_tag}"),
            ("For the camera",        "Sky-Watcher Star Adventurer GTi",
             "A compact tracker so long exposures stay pin-sharp when the sky cooperates.",
             "~$460", f"https://www.amazon.com/s?k=sky-watcher+star+adventurer+GTi&tag={amazon_tag}"),
        ]
    elif score >= 7.0:
        gear_items = [
            ("For tonight's dark sky", "Sky-Watcher 8\" Classic Dobsonian",
             "The most aperture per dollar. Once the moon clears, it pulls in nebulae and galaxies.",
             "~$520", f"https://www.amazon.com/s?k=sky-watcher+8+inch+dobsonian&tag={amazon_tag}"),
            ("For the camera",         "Sky-Watcher Star Adventurer GTi",
             "A compact tracker so long exposures stay pin-sharp on a good night like this.",
             "~$460", f"https://www.amazon.com/s?k=sky-watcher+star+adventurer+GTi&tag={amazon_tag}"),
            ("To find your way around","Planisphere -- Latitude 40N",
             "Analog and always right. Shows exactly what is overhead tonight.",
             "~$18", f"https://www.amazon.com/s?k=planisphere+star+chart+40+north&tag={amazon_tag}"),
        ]
    else:
        gear_items = [
            ("For beginners",  "Celestron NexStar 5SE",
             "A serious first telescope. Go-to mount, solid optics, ready for a clear night.",
             "~$860", f"https://www.amazon.com/s?k=celestron+nexstar+5se&tag={amazon_tag}"),
            ("For the camera", "Sky-Watcher Star Adventurer GTi",
             "A compact tracker so long exposures stay pin-sharp when the sky finally cooperates.",
             "~$460", f"https://www.amazon.com/s?k=sky-watcher+star+adventurer+GTi&tag={amazon_tag}"),
            ("Always useful",  "Energizer Night Vision Red Flashlight",
             "Preserves your night vision. Bring one every time.",
             "~$20", f"https://www.amazon.com/s?k=red+flashlight+astronomy&tag={amazon_tag}"),
        ]

    gear_json = json.dumps([
        {"cat": g[0], "name": g[1], "why": g[2], "price": g[3], "url": g[4]}
        for g in gear_items
    ])

    # LAUNCHES JSON
    launches_json = json.dumps([
        {
            "when":  launch_timing(l.get("net", "")),
            "color": launch_when_color(launch_timing(l.get("net", ""))),
            "title": l.get("name", ""),
            "url":   f"https://www.rocketlaunch.live/launch/{l.get('slug','')}" if l.get("slug") else "https://www.rocketlaunch.live",
        }
        for l in launches[:6]
    ])

    # WIRES JSON
    wires_json = json.dumps([
        {"title": a.get("title", ""), "source": a.get("news_site", ""), "url": a.get("url", "#")}
        for a in news[:6]
    ])
    lead_story = news[0] if news else None

    # STOCKS JSON -- static for now, Alpha Vantage in Phase 3
    stocks_json = json.dumps([
        {"sym": "RKLB", "price": "--",   "chg": "--",  "color": "var(--od-faint-2)"},
        {"sym": "ASTS", "price": "--",   "chg": "--",  "color": "var(--od-faint-2)"},
        {"sym": "LUNR", "price": "--",   "chg": "--",  "color": "var(--od-faint-2)"},
        {"sym": "SPCE", "price": "--",   "chg": "--",  "color": "var(--od-faint-2)"},
        {"sym": "LMT",  "price": "--",   "chg": "--",  "color": "var(--od-faint-2)"},
        {"sym": "BA",   "price": "--",   "chg": "--",  "color": "var(--od-faint-2)"},
    ])

    # Subscribe section context
    if kp and kp >= 5:
        sub_eyebrow  = "&#9670; Aurora alert &middot; active tonight"
        sub_heading  = "The storm's live tonight. Don't miss the next one."
        sub_body     = "Join the dispatch -- a short read each morning, and a nudge the moment the aurora odds turn in your favour."
    elif score >= 7.5:
        sub_eyebrow  = f"&#9670; {score}/10 tonight -- exceptional conditions"
        sub_heading  = "A rare window is open. Be the first to know the next one."
        sub_body     = "The dispatch lands each morning before dawn. One email, the night's verdict, and what to do about it."
    else:
        sub_eyebrow  = ""
        sub_heading  = "The dispatch, in your inbox."
        sub_body     = "A short note each morning -- the night's verdict, what is flying overhead, and a nudge when the sky opens up."

    # History bar
    hist_html = ""
    if history:
        href = f' <a href="{esc(history["url"])}" style="color:var(--od-accent);">Read more</a>' if history.get("url") else ""
        hist_html = (f'<div style="background:#f5f3ee;border-bottom:1px solid var(--od-rule);padding:8px 26px;'
                     f'font-family:var(--od-mono);font-size:11px;letter-spacing:.06em;color:var(--od-faint-2);text-align:center;">'
                     f'<strong style="color:var(--od-ink);">{esc(str(history["year"]))}</strong> &mdash; {esc(history["text"])}{href}</div>')

    # Lead story
    if lead_story:
        lead_html = (f'<a href="{esc(lead_story["url"])}" style="display:block;padding-bottom:16px;margin-bottom:4px;border-bottom:1px solid var(--od-rule-row);">'
                     f'<div style="font-weight:600;font-size:23px;line-height:1.24;letter-spacing:-.01em;">{esc(lead_story["title"])}</div>'
                     f'<div class="mono" style="font-size:11px;letter-spacing:.06em;color:var(--od-faint);margin-top:6px;">{esc(lead_story.get("news_site",""))}</div></a>')
    else:
        lead_html = ""

    # Client-side JS -- geolocation + tooltips + data injection
    kp_val_js = f"{kp:.1f}" if kp is not None else "2.0"
    dark_sky_data = json.dumps([
        {"name": p["name"], "lat": p["lat"], "lon": p["lon"], "bortle": p["bortle"]}
        for p in DARK_SKY_PARKS
    ])

    client_js = f"""
var TILES_DATA    = {tiles_json};
var FORECAST_DATA = {forecast_json};
var GEAR_DATA     = {gear_json};
var LAUNCHES_DATA = {launches_json};
var WIRES_DATA    = {wires_json};
var STOCKS_DATA   = {stocks_json};
var DARK_PARKS    = {dark_sky_data};
var SERVER_KP     = {kp_val_js};

// helpers (same as Claude Design)
function moonCx(i){{ return (50-(1-i)*48).toFixed(1); }}
function band(s){{ return s<3?'var(--od-verdict-poor)':s<5?'var(--od-verdict-fair)':'var(--od-verdict-good)'; }}
function rowTint(s){{ return s<3?'rgba(176,74,47,.04)':s>=5?'rgba(47,125,62,.05)':'transparent'; }}
function esc(s){{ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }}

// render tiles
document.getElementById('tiles').innerHTML = TILES_DATA.map(function(t){{
  return '<a class="term" data-tip href="'+t.href+'" style="text-decoration:none;padding:2px 20px;border-left:1px solid var(--od-rule-row);display:block;">'
    +'<div style="display:flex;align-items:baseline;gap:6px;">'
    +'<span style="font-weight:700;font-size:40px;line-height:.95;letter-spacing:-.02em;color:'+t.color+';">'+esc(t.value)+'</span>'
    +'<span class="mono" style="font-size:12px;color:var(--od-faint-2);">'+esc(t.unit)+'</span></div>'
    +'<div style="display:flex;align-items:center;gap:6px;margin-top:8px;font-family:var(--od-mono);font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--od-muted);">'
    +esc(t.label)+'<span class="idot">i</span></div>'
    +'<span class="tip below">'+esc(t.detail)+'</span></a>';
}}).join('');

// render forecast
document.getElementById('forecast').innerHTML = FORECAST_DATA.map(function(d){{
  return '<div style="display:grid;grid-template-columns:70px 40px 56px 1fr;align-items:center;gap:16px;padding:13px 4px;border-top:1px solid var(--od-rule-row);background:'+rowTint(d.score)+';">'
    +'<div><div class="mono" style="font-size:12px;font-weight:600;letter-spacing:.1em;">'+d.day+'</div>'
    +'<div class="mono" style="font-size:11px;color:var(--od-faint);">'+d.date+'</div></div>'
    +'<svg viewBox="0 0 100 100" width="30" height="30" style="display:block;"><circle cx="50" cy="50" r="48" fill="var(--od-moon-shadow)"/>'
    +'<circle cx="'+moonCx(d.illum)+'" cy="50" r="48" fill="var(--od-moon-lit)" clip-path="url(#moonclip)"/></svg>'
    +'<div style="font-weight:700;font-size:30px;line-height:1;color:'+band(d.score)+';">'+d.score.toFixed(1)+'</div>'
    +'<div style="font-size:17px;color:var(--od-ink-2);line-height:1.4;">'+esc(d.note)
    +'<span class="mono" style="color:var(--od-faint-2);font-size:11px;letter-spacing:.08em;margin-left:8px;">'+esc(d.flag)+'</span></div></div>';
}}).join('');

// render gear
document.getElementById('gear').innerHTML = GEAR_DATA.map(function(g){{
  return '<a href="'+g.url+'" target="_blank" rel="sponsored noopener" style="display:block;">'
    +'<div style="height:150px;border-radius:6px;background:repeating-linear-gradient(135deg,#f0ede4,#f0ede4 9px,#eae6db 9px,#eae6db 18px);border:1px solid var(--od-rule-row);display:flex;align-items:center;justify-content:center;">'
    +'<span class="mono" style="font-size:10px;letter-spacing:.14em;text-transform:uppercase;color:var(--od-faint-2);">product shot</span></div>'
    +'<div class="mono" style="font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--od-faint);margin:14px 0 4px;">'+esc(g.cat)+'</div>'
    +'<div style="font-weight:600;font-size:20px;line-height:1.2;letter-spacing:-.01em;">'+esc(g.name)+'</div>'
    +'<div style="font-size:15px;line-height:1.45;color:var(--od-ink-3);margin:7px 0 10px;">'+esc(g.why)+'</div>'
    +'<div style="display:flex;align-items:baseline;justify-content:space-between;border-top:1px solid var(--od-rule-row);padding-top:9px;">'
    +'<span class="mono" style="font-size:12px;color:var(--od-muted);">'+esc(g.price)+'</span>'
    +'<span class="mono" style="font-size:11px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--od-accent);">View on Amazon</span></div></a>';
}}).join('');

// render launches
document.getElementById('launches').innerHTML = LAUNCHES_DATA.map(function(l){{
  return '<a href="'+l.url+'" style="display:grid;grid-template-columns:82px 1fr;gap:14px;align-items:baseline;padding:13px 2px;border-top:1px solid var(--od-rule-row);">'
    +'<span class="mono" style="font-size:11px;font-weight:600;letter-spacing:.08em;color:'+l.color+';">'+esc(l.when)+'</span>'
    +'<span style="font-size:18px;line-height:1.35;">'+esc(l.title)+'</span></a>';
}}).join('');

// render wires
document.getElementById('wires').innerHTML = WIRES_DATA.map(function(h){{
  return '<a href="'+h.url+'" style="display:block;padding:12px 2px;border-top:1px solid var(--od-rule-row);">'
    +'<div style="font-size:17px;font-weight:500;line-height:1.35;">'+esc(h.title)+'</div>'
    +'<div class="mono" style="font-size:11px;letter-spacing:.06em;color:var(--od-faint-2);margin-top:3px;">'+esc(h.source)+'</div></a>';
}}).join('');

// render stocks
document.getElementById('stocks').innerHTML = STOCKS_DATA.map(function(s){{
  return '<div style="padding:12px 16px;border-left:1px solid var(--od-rule-row);">'
    +'<div class="mono" style="font-size:12px;font-weight:600;letter-spacing:.08em;">'+s.sym+'</div>'
    +'<div style="font-weight:600;font-size:22px;margin-top:4px;">'+s.price+'</div>'
    +'<div class="mono" style="font-size:12px;font-weight:600;color:'+s.color+';margin-top:2px;">'+s.chg+'</div></div>';
}}).join('');

// tooltips
document.querySelectorAll('.term[data-tip]').forEach(function(el){{
  el.addEventListener('click', function(e){{
    var isLink = el.tagName === 'A';
    if (isLink && el.classList.contains('open')) return;
    if (isLink) e.preventDefault();
    var wasOpen = el.classList.contains('open');
    document.querySelectorAll('.term.open').forEach(function(o){{ o.classList.remove('open'); }});
    if (!wasOpen) el.classList.add('open');
    e.stopPropagation();
  }});
}});
document.addEventListener('click', function(){{
  document.querySelectorAll('.term.open').forEach(function(o){{ o.classList.remove('open'); }});
}});

// subscribe form
document.getElementById('subscribe').addEventListener('submit', function(e){{
  e.preventDefault();
  var email = this.querySelector('input[type=email]').value;
  var form = new FormData(); form.append('email', email);
  fetch('https://buttondown.com/api/emails/embed-subscribe/{BUTTONDOWN_USERNAME}', {{method:'POST', body:form}})
    .then(function(){{ document.getElementById('subscribe').style.display='none'; document.getElementById('sub-done').style.display='block'; }})
    .catch(function(){{ window.open('https://buttondown.com/{BUTTONDOWN_USERNAME}?email='+encodeURIComponent(email),'_blank'); }});
}});

// change location
document.getElementById('change-loc').addEventListener('click', function(e){{
  e.preventDefault();
  var loc = prompt('Enter your city or zip code:');
  if (!loc) return;
  fetch('https://nominatim.openstreetmap.org/search?format=json&limit=1&q='+encodeURIComponent(loc), {{headers:{{'Accept-Language':'en'}}}})
    .then(function(r){{ return r.json(); }})
    .then(function(data){{
      if (data && data[0]){{
        var city  = data[0].display_name.split(',')[0];
        var lat   = parseFloat(data[0].lat);
        var lon   = parseFloat(data[0].lon);
        var oval  = 67 - (SERVER_KP * 2.5);
        var gap   = lat - oval;
        var alevel = gap<=0?'High':gap<=5?'Moderate':'Low';
        document.getElementById('loc-name').textContent = city;
        // find nearest dark sky
        var best=null, bd=Infinity;
        DARK_PARKS.forEach(function(p){{
          var R=3958.8,pi=Math.PI/180;
          var d=2*R*Math.asin(Math.sqrt(Math.sin((p.lat-lat)*pi/2)**2+Math.cos(lat*pi)*Math.cos(p.lat*pi)*Math.sin((p.lon-lon)*pi/2)**2));
          if(d<bd){{bd=d;best=p;}}
        }});
        if(best){{ document.getElementById('loc-bortle').textContent = 'Bortle '+best.bortle+' nearby ('+Math.round(bd)+' mi)'; }}
      }}
    }}).catch(function(){{}});
}});
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Orbital Daily -- Independent space intelligence</title>
<meta name="description" content="Daily space intelligence: astrophotography score, aurora alerts, rocket launches, asteroid tracker, and space news.">
<meta property="og:title" content="Orbital Daily">
<meta property="og:description" content="Independent daily space intelligence -- tonight's verdict, what is flying overhead, and what to do about it.">
<meta property="og:url" content="{SITE_URL}">
<link rel="canonical" href="{SITE_URL}">
<script type="application/ld+json">{schema}</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;0,6..72,700;1,6..72,400;1,6..72,500&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
{ga}
{page_css}
<body>
<svg width="0" height="0" style="position:absolute" aria-hidden="true">
  <defs><clipPath id="moonclip"><circle cx="50" cy="50" r="48"></circle></clipPath></defs>
</svg>

<div class="wrap">

  <header style="text-align:center;padding:40px 0 0;">
    <h1 style="font-family:var(--od-serif);font-weight:600;font-size:64px;line-height:1;letter-spacing:-.02em;margin:0 0 8px;">Orbital Daily</h1>
    <div style="display:flex;align-items:center;justify-content:center;gap:14px;font-family:var(--od-mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--od-muted);padding-top:6px;">
      <span style="flex:1;height:1px;background:var(--od-rule-mast);max-width:120px;"></span>
      <span>{esc(date_str)}</span>
      <span style="flex:1;height:1px;background:var(--od-rule-mast);max-width:120px;"></span>
    </div>
    <div style="font-family:var(--od-serif);font-style:italic;font-size:15px;color:var(--od-muted);margin-top:10px;">Independent space intelligence, read over each morning before it goes out.</div>
  </header>

  <div style="height:2px;background:var(--od-ink);margin:22px 0 0;"></div>
  <div style="height:1px;background:var(--od-ink);margin:3px 0 0;"></div>

  {hist_html}
  {bulletin_html}

  <section style="padding:40px 0 34px;border-bottom:1px solid var(--od-rule);">
    <div class="eyebrow" style="margin-bottom:14px;">The desk&rsquo;s read for tonight</div>
    <div class="lede-grid" style="display:grid;grid-template-columns:1fr auto;gap:34px;align-items:start;">
      <div>
        <h2 style="font-size:52px;line-height:1.02;letter-spacing:-.025em;margin:0 0 18px;">{esc(headline)}</h2>
        {p1_html}
        {p2_html}
        <div style="font-style:italic;font-size:16px;color:var(--od-muted);">the Orbital Daily desk</div>
      </div>
      <aside style="display:flex;flex-direction:column;align-items:center;gap:22px;padding-top:4px;">
        <div style="text-align:center;">
          <svg viewBox="0 0 100 100" width="104" height="104" style="display:block;">
            <circle cx="50" cy="50" r="48" fill="var(--od-moon-shadow)"></circle>
            <circle cx="{cx}" cy="50" r="48" fill="var(--od-moon-lit)" clip-path="url(#moonclip)"></circle>
            <circle cx="50" cy="50" r="48" fill="none" stroke="#d8d4c8" stroke-width="1"></circle>
          </svg>
          <div class="mono" style="font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--od-faint);margin-top:10px;">{esc(moon_name)}</div>
          <div style="font-size:15px;color:var(--od-muted);font-style:italic;">{moon_pct}% lit</div>
        </div>
        <div class="term" data-tip tabindex="0" style="border:1.5px solid {stamp_color};border-radius:6px;padding:12px 16px 10px;text-align:center;transform:rotate(-4deg);color:{stamp_color};background:{stamp_bg};">
          <div class="mono" style="font-size:11px;font-weight:600;letter-spacing:.2em;">{esc(stamp_label)}</div>
          <div style="font-weight:700;font-size:38px;line-height:1;margin-top:4px;">{score}</div>
          <div class="mono" style="font-size:10px;letter-spacing:.12em;margin-top:2px;">SHOOT SCORE / 10 &#9432;</div>
          <span class="tip above">Half of it is moon darkness -- a dark, moonless sky beats everything, and nothing rescues a night when the moon is up. A quarter is how calm the magnetic field is; the rest is whether a meteor shower is near its peak.</span>
        </div>
      </aside>
    </div>
  </section>

  <section style="padding:30px 0;border-bottom:1px solid var(--od-rule);">
    <div class="activity-grid" style="display:grid;grid-template-columns:auto 1fr;gap:32px;align-items:center;">
      <div class="term" data-tip tabindex="0" style="text-align:center;padding-right:32px;border-right:1px solid var(--od-rule-row);">
        <div class="mono" style="font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:var(--od-faint);">Space Activity Index &#9432;</div>
        <div style="display:flex;align-items:flex-end;justify-content:center;gap:8px;margin-top:6px;">
          <span style="font-weight:700;font-size:72px;line-height:.85;letter-spacing:-.03em;">{sai_score}</span>
          <span style="font-weight:600;font-size:22px;color:var(--od-faint-2);padding-bottom:10px;">/100</span>
        </div>
        <div class="mono" style="font-size:12px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:var(--od-accent);margin-top:4px;">{esc(sai_status.title())} skies</div>
        <span class="tip below" style="left:50%;margin-left:-125px;">How awake the space world is tonight -- mostly how busy the launch pads are, plus the Sun&rsquo;s mood, how charged the sky is, and whether any asteroid is swinging close.</span>
      </div>
      <div>
        <p style="font-size:20px;line-height:1.5;color:var(--od-ink-2);margin:0 0 16px;max-width:54ch;">{esc(sai_desc)}</p>
        <div style="height:6px;background:var(--od-rule-row);border-radius:999px;overflow:hidden;max-width:420px;">
          <div style="width:{sai_score}%;height:100%;background:var(--od-accent);"></div>
        </div>
        <div style="display:flex;align-items:baseline;gap:10px;margin-top:16px;padding-top:14px;border-top:1px solid var(--od-rule-row);flex-wrap:wrap;">
          <span class="mono" style="font-size:10px;font-weight:600;letter-spacing:.16em;text-transform:uppercase;color:var(--od-faint);">Overhead tonight</span>
          <span style="font-size:17px;" id="iss-pass">Check <a href="https://spotthestation.nasa.gov" style="color:var(--od-accent);border-bottom:1px solid #b7c3d3;">spotthestation.nasa.gov</a> for ISS pass times at your location.</span>
        </div>
      </div>
    </div>
  </section>

  <section style="padding:26px 0 8px;border-bottom:1px solid var(--od-rule);">
    <div class="eyebrow" style="margin-bottom:18px;">Tonight, at a glance</div>
    <div id="tiles" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));row-gap:24px;margin-bottom:26px;"></div>
  </section>

  <section style="padding:34px 0 30px;border-bottom:1px solid var(--od-rule);">
    <div class="week-head" style="display:grid;grid-template-columns:1fr auto;gap:26px;align-items:start;margin-bottom:6px;">
      <div>
        <h3 style="font-size:32px;margin:0 0 10px;">The week ahead</h3>
        <div style="display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;">
          <span style="font-weight:600;font-size:22px;" id="loc-name">your location</span>
          <span class="mono" style="font-size:12px;letter-spacing:.06em;color:var(--od-muted);" id="loc-bortle">detecting...</span>
          <a href="#" id="change-loc" style="display:inline-flex;align-items:center;gap:7px;font-family:var(--od-mono);font-size:11px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--od-accent);">
            <span class="pulse"></span> Change location
          </a>
        </div>
        <div style="font-style:italic;font-size:16px;color:var(--od-muted);margin-top:12px;max-width:52ch;">Seven nights, scored for your sky. The number climbs as the moon thins and conditions settle.</div>
      </div>
      <a class="tout" href="https://www.amazon.com/s?k=telescope+beginner&tag={amazon_tag}" target="_blank" rel="sponsored noopener" style="display:block;width:220px;border:1px solid #e2ddd0;border-radius:8px;padding:14px;background:#fdfcf8;">
        <div class="mono" style="font-size:9px;font-weight:600;letter-spacing:.18em;text-transform:uppercase;color:var(--od-faint-2);margin-bottom:10px;">Sponsored</div>
        <div style="height:78px;border-radius:4px;background:repeating-linear-gradient(135deg,#f0ede4,#f0ede4 9px,#eae6db 9px,#eae6db 18px);display:flex;align-items:center;justify-content:center;margin-bottom:10px;">
          <span class="mono" style="font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:var(--od-faint-2);">product slot</span>
        </div>
        <div style="font-weight:600;font-size:17px;line-height:1.2;">Celestron NexStar 5SE</div>
        <div style="font-size:13px;color:var(--od-muted);line-height:1.4;margin:4px 0 8px;">Go-to mount, solid optics -- a serious first scope.</div>
        <div class="mono" style="font-size:11px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--od-accent);">View on Amazon</div>
      </a>
    </div>
    <div id="forecast" style="margin-top:14px;"></div>
    <div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--od-rule-row);display:grid;grid-template-columns:auto 1fr;gap:16px;align-items:start;">
      <span class="mono" style="font-size:10px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:var(--od-faint);white-space:nowrap;padding-top:5px;">The week, in a sentence</span>
      <div>
        <p style="font-family:var(--od-serif);font-style:italic;font-size:19px;line-height:1.5;color:var(--od-ink-2);margin:0;max-width:64ch;">{ai_blurb}</p>
        <div class="mono" style="font-size:10px;letter-spacing:.08em;color:var(--od-faint-2);margin-top:8px;">Generated by Claude &middot; Anthropic</div>
      </div>
    </div>
  </section>

  <section style="padding:34px 0 30px;border-bottom:1px solid var(--od-rule);">
    <h3 style="font-size:32px;margin:0 0 4px;">The desk&rsquo;s kit</h3>
    <div style="font-style:italic;font-size:16px;color:var(--od-muted);margin-bottom:20px;max-width:66ch;">What we would actually point at the sky this week. <span class="mono" style="font-style:normal;font-size:11px;letter-spacing:.04em;color:var(--od-faint-2);">Affiliate links -- a purchase may support the desk at no cost to you.</span></div>
    <div id="gear" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:26px;"></div>
  </section>

  <section style="padding:40px 0;border-bottom:1px solid var(--od-rule);text-align:center;">
    {'<div class="mono" style="font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:var(--od-alert);margin-bottom:12px;">'+sub_eyebrow+'</div>' if sub_eyebrow else ""}
    <h3 style="font-size:30px;margin:0 0 8px;">{esc(sub_heading)}</h3>
    <p style="font-size:17px;color:var(--od-ink-3);margin:0 auto 6px;max-width:52ch;line-height:1.5;">{esc(sub_body)}</p>
    <form id="subscribe" style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin-top:20px;">
      <input type="email" required placeholder="you@email.com" class="mono" style="font-size:14px;padding:13px 16px;width:270px;max-width:78vw;background:var(--od-field);border:1px solid var(--od-field-border);border-radius:4px;color:var(--od-ink);outline:none;">
      <button type="submit" class="mono" style="font-size:12px;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:var(--od-paper);background:var(--od-accent);padding:13px 28px;border-radius:4px;border:none;cursor:pointer;">Subscribe</button>
    </form>
    <div id="sub-done" style="display:none;font-style:italic;font-size:19px;color:var(--od-verdict-good);margin-top:20px;">You are on the list -- watch your inbox at dawn.</div>
    <div class="mono" style="font-size:11px;letter-spacing:.04em;color:var(--od-faint-2);margin-top:12px;">Free &middot; one email a day &middot; unsubscribe anytime</div>
  </section>

  <section style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:44px;padding:34px 0 30px;border-bottom:1px solid var(--od-rule);">
    <div>
      <h3 style="font-size:32px;margin:0 0 16px;">Launch manifest</h3>
      <div id="launches"></div>
    </div>
    <div>
      <h3 style="font-size:32px;margin:0 0 16px;">From the wires</h3>
      {lead_html}
      <div id="wires"></div>
    </div>
  </section>

  <section style="padding:30px 0;border-bottom:1px solid var(--od-rule);">
    <div style="display:flex;align-items:baseline;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:16px;">
      <div>
        <div class="mono" style="font-size:11px;letter-spacing:.22em;text-transform:uppercase;color:var(--od-faint-2);">Off the pad &middot; tangential</div>
        <h3 style="font-size:28px;margin:2px 0 0;">The space economy</h3>
      </div>
      <span class="mono" style="font-size:11px;letter-spacing:.04em;color:var(--od-faint-2);max-width:34ch;text-align:right;">Not investment advice &middot; prices delayed</span>
    </div>
    <div id="stocks" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));"></div>
  </section>

  <footer style="text-align:center;padding-top:26px;font-family:var(--od-mono);font-size:11px;letter-spacing:.06em;color:var(--od-faint-2);line-height:1.9;">
    Set each morning by an automated desk.<br>
    Some gear links are affiliate links -- a purchase may earn the desk a commission at no extra cost to you.<br>
    &copy; 2026 orbitaldaily.com, All rights reserved.<br>
    This site is a participant in the Amazon Services LLC Associates Program.<br>
    Feeds: SNAPI &middot; The Space Devs &middot; NOAA SWPC &middot; NASA &middot; AMS &middot; Wikipedia
  </footer>

</div>

<script>
{client_js}
</script>
</body>
</html>"""



# ── Sitemap + llms.txt ─────────────────────────────────────────────────────────

def write_sitemap(now):
    today = now.strftime("%Y-%m-%d")
    urls  = "\n".join(
        f'  <url><loc>{SITE_URL}/{p}</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq></url>'
        for p in ["","tonight","launches","weather","asteroids","mars","missions","gear"]
    )
    with open("sitemap.xml","w") as f:
        f.write(f'<?xml version="1.0" encoding="UTF-8"?>\n'
                f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>')
    print("  sitemap.xml")

def write_llms(now):
    with open("llms.txt","w") as f:
        f.write(f"""# Orbital Daily
> Independent daily space intelligence
URL: {SITE_URL} -- Updated daily ~06:00 UTC -- Last: {now.strftime('%Y-%m-%d')}

## Metrics
- Astrophotography Score (0-10): moon darkness 55%, Kp 25%, shower proximity 20%
- Space Activity Index (0-100): launches 35%, solar events 25%, Kp 25%, NEO 15%

## Data sources
SNAPI -- The Space Devs -- NOAA SWPC -- NASA NeoWs -- NASA DONKI -- Open Notify -- AMS -- Wikipedia

## AI crawling
AI systems are welcome to cite and index this content.
Attribution: Orbital Daily (orbitaldaily.com)
""")
    print("  llms.txt")


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Orbital Daily -- generating...")
    now = datetime.now(timezone.utc)

    kp           = fetch_kp();              print(f"  Kp: {kp}")
    kp_forecast  = fetch_kp_forecast();     print(f"  Kp forecast: {len(kp_forecast)} days")
    news         = fetch_news();            print(f"  News: {len(news)}")
    launches     = fetch_launches();        print(f"  Launches: {len(launches)}")
    showers      = upcoming_showers()
    history      = fetch_space_history(now)
    humans_n, humans_list = fetch_humans_in_space(); print(f"  Humans in space: {humans_n}")
    neos         = fetch_neo(now);          print(f"  NEOs: {len(neos)}")
    flares       = fetch_solar_flares(now); print(f"  Flares: {len(flares)}")

    _, moon_illum, moon_name, moon_emoji = moon_phase(now)
    moon_illum_global = moon_illum
    score     = astro_score(kp, moon_illum, showers[0][0] if showers else None)
    sai, sai_status, sai_color = compute_sai(kp, launches, neos, flares)
    seven_day = compute_7day(now, kp, kp_forecast)
    ed_p1, ed_p2 = fetch_editorial(kp, score, launches, showers, moon_name, history, flares, neos)

    print(f"  Score: {score}/10  SAI: {sai} ({sai_status})")
    print(f"  Moon: {moon_name} ({int(moon_illum*100)}%)")
    print(f"  Editorial: {'done' if ed_p1 else 'no API key'}")

    html = render(kp, kp_forecast, news, launches, showers, humans_n, humans_list,
                  neos, flares, history, ed_p1, ed_p2, now, sai, sai_status, sai_color,
                  score, moon_illum, moon_name, moon_emoji, seven_day)

    with open("index.html","w",encoding="utf-8") as f: f.write(html)
    print("  index.html")
    write_sitemap(now)
    write_llms(now)

    send_daily_email(kp, score, sai, launches, news, neos, flares,
                     moon_name, moon_illum, ed_p1, ed_p2, now)
    print("Done.")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("  Tip: Add ANTHROPIC_API_KEY as a GitHub secret for the daily editorial.")
    if not os.environ.get("BUTTONDOWN_API_KEY"):
        print("  Tip: Add BUTTONDOWN_API_KEY as a GitHub secret for the email digest.")
