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
    if not api_key: return None
    ctx = []
    if kp is not None: ctx.append(f"Kp: {kp:.1f} ({'quiet' if kp<2 else 'active' if kp<5 else 'stormy'})")
    ctx.append(f"Astrophotography score: {score}/10 ({score_label(score)})")
    if launches: ctx.append(f"Next launch: {launches[0].get('name','')} ({launch_timing(launches[0].get('net',''))})")
    if showers:  ctx.append(f"Next shower: {showers[0][1]} in {showers[0][0]} days")
    ctx.append(f"Moon: {moon_name}")
    if flares:   ctx.append(f"Solar: {flares[0].get('classType','')} flare recently")
    if neos:     ctx.append(f"NEO: {neos[0]['name']} at {neos[0]['ld']:.1f} lunar distances")
    if history:  ctx.append(f"Today in history ({history['year']}): {history['text'][:100]}")
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model":"claude-haiku-4-5-20251001","max_tokens":130,
                  "messages":[{"role":"user","content":
                    f"Today's space data:\n{chr(10).join(ctx)}\n\n"
                    "Write exactly 2 sentences about what makes today notable from a space perspective. "
                    "Weave the most interesting data points together. Specific and factual. "
                    "No 'Today is a great day' openings. Informed reader voice."}]},
            timeout=15
        )
        if r.status_code == 200:
            for block in r.json().get("content",[]):
                if block.get("type") == "text": return block["text"].strip()
    except Exception as e:
        print(f"  Editorial: {e}", file=sys.stderr)
    return None


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


# ── Buttondown email ───────────────────────────────────────────────────────────

def send_daily_email(kp, score, sai_status, launches, news, neos, flares,
                     moon_name, moon_illum, editorial, now):
    api_key = os.environ.get("BUTTONDOWN_API_KEY","")
    if not api_key:
        print("  Email: no BUTTONDOWN_API_KEY — skipping")
        return

    kp_text, _ = kp_label(kp)
    kp_display  = f"{kp:.1f}" if kp is not None else "N/A"
    moon_pct    = int(round(moon_illum * 100))
    day         = now.day
    date_str    = now.strftime(f"%B {day}, %Y")
    divider     = "-" * 48
    gps_status  = "Degraded" if kp and kp >= 4 else "Normal"

    if kp and kp >= 5:
        subject = f"Orbital Daily · {now.strftime('%b')} {day}: Aurora alert active, Kp {kp_display}"
    elif score >= 7.5:
        subject = f"Orbital Daily · {now.strftime('%b')} {day}: {score}/10 tonight, great conditions"
    elif neos and neos[0]["ld"] < 5:
        subject = f"Orbital Daily · {now.strftime('%b')} {day}: Asteroid {neos[0]['name']} passing Earth"
    elif launches:
        subject = f"Orbital Daily · {now.strftime('%b')} {day}: {launches[0].get('name','')} {launch_timing(launches[0].get('net',''))}"
    else:
        subject = f"Orbital Daily · {now.strftime('%b')} {day}: Space Activity {sai_status.title()}"

    if launches:
        launch_block = f"{launches[0].get('name','Unknown')} · {launch_timing(launches[0].get('net',''))}"
        if len(launches) > 1:
            launch_block += f"\n{launches[1].get('name','')} · {launch_timing(launches[1].get('net',''))}"
    else:
        launch_block = "No launches currently scheduled"

    solar_block = f"{flares[0].get('classType','')} flare detected · monitor for Kp rise" if flares else "No active solar events"
    neo_block   = f"{neos[0]['name']} · {neos[0]['ld']:.1f} lunar distances · {neos[0].get('date','this week')}" if neos and neos[0]["ld"] < 20 else "No notable close approaches this week"
    headlines   = "\n".join(f"* {a['title']}" for a in news[:5]) if news else "* No headlines available"
    editorial_text = editorial if editorial else "Visit orbitaldaily.com for today's full briefing."

    body = f"""Orbital Daily tracks space conditions daily: astrophotography scores, rocket launches, aurora alerts, and near-Earth objects, computed fresh every morning.

{divider}

{editorial_text}

{divider}

TONIGHT · {date_str}
Astrophotography Score: {score}/10 - {score_label(score)}
Moon: {moon_name} · {moon_pct}% illuminated

SPACE WEATHER
Kp Index: {kp_display} - {kp_text}
GPS Reliability: {gps_status}
Solar: {solar_block}

UPCOMING LAUNCHES
{launch_block}

NEAR-EARTH OBJECTS
{neo_block}

{divider}

TOP HEADLINES

{headlines}

{divider}

Read the full dashboard at orbitaldaily.com
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
            print(f"  Email failed: {r.status_code} — {r.text[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"  Email error: {e}", file=sys.stderr)



# ── Helpers ────────────────────────────────────────────────────────────────────

def esc(s): return escape(str(s))

# Global so editorial can access
moon_illum_global = 0.0

def score_band(s):
    if s >= 7.0: return "excellent"
    if s >= 5.0: return "good"
    if s >= 3.0: return "fair"
    return "poor"

def band_color(s):
    if s >= 5.0: return "#2f7d3e"
    if s >= 3.0: return "#a07508"
    if s >= 2.0: return "#c2610c"
    return "#b04a2f"

def band_bg(s):
    if s >= 5.0: return "rgba(47,125,62,0.05)"
    if s < 3.0:  return "rgba(176,74,47,0.04)"
    return "transparent"

def lede_headline(score):
    band = score_band(score)
    if band == "excellent": return "Get outside tonight."
    if band == "good":      return "Worth a look tonight."
    if band == "fair":      return "Wait for a better window."
    return "Stay in tonight."

def verdict_stamp(score):
    band = score_band(score)
    if band == "excellent": label, color = "EXCELLENT", "#2f7d3e"
    elif band == "good":    label, color = "GOOD",      "#2f7d3e"
    elif band == "fair":    label, color = "FAIR",      "#a07508"
    else:                   label, color = "UNFAVOURABLE", "#b04a2f"
    return label, color

def moon_svg(illum, size=104):
    lit_cx = round(50 - (1 - illum) * 48, 1)
    stroke = 1 if size > 50 else 0
    caption = "" if size < 50 else ""
    return (f'<svg viewBox="0 0 100 100" width="{size}" height="{size}" '
            f'style="display:block;" aria-hidden="true">'
            f'<circle cx="50" cy="50" r="48" fill="#c7cbd2"/>'
            f'<circle cx="{lit_cx}" cy="50" r="48" fill="#f3efe4" clip-path="url(#moonclip)"/>'
            f'<circle cx="50" cy="50" r="48" fill="none" stroke="#d8d4c8" stroke-width="{stroke}"/>'
            f'</svg>')

def issue_number(now):
    launch = datetime(2026, 1, 1, tzinfo=timezone.utc)
    delta  = (now - launch).days
    vol    = (delta // 90) + 1
    num    = delta % 90 + 1
    return f"Vol. {vol} · No. {num}"

def launch_when_color(timing):
    t = timing.upper()
    if t == "LAUNCHED": return "#a8a294"
    if t.startswith("T-"): return "#1b3a6b"
    return "#2a2f36"


# ── CSS ────────────────────────────────────────────────────────────────────────

CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body { background: #faf9f5; color: #14181d; }
body {
  font-family: 'Newsreader', Georgia, serif;
  font-size: 18px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}
a { color: inherit; text-decoration: none; }
a:hover { text-decoration: underline; }
::selection { background: #dfe6ee; }

/* Global clip for moon SVG */
.moonclip-defs { position: absolute; width: 0; height: 0; }

.page { max-width: 940px; margin: 0 auto; padding: 0 26px 90px; background: #faf9f5; }

/* Masthead */
.masthead { text-align: center; padding: 40px 0 0; }
.mast-kicker { font-family: 'IBM Plex Mono', monospace; font-size: 11px; letter-spacing: 0.32em; text-transform: uppercase; color: #8a8578; }
.mast-title { font-family: 'Newsreader', serif; font-weight: 600; font-size: clamp(42px,8vw,64px); line-height: 1; letter-spacing: -0.02em; margin: 10px 0 8px; color: #14181d; }
.mast-dateline { display: flex; align-items: center; justify-content: center; gap: 14px; font-family: 'IBM Plex Mono', monospace; font-size: 11px; letter-spacing: 0.14em; text-transform: uppercase; color: #6b6a62; padding-top: 6px; }
.mast-rule-line { flex: 1; height: 1px; background: #d8d4c8; max-width: 120px; }
.mast-tagline { font-family: 'Newsreader', serif; font-style: italic; font-size: 15px; color: #6b6a62; margin-top: 10px; padding-bottom: 22px; }
.mast-double-rule { height: 2px; background: #14181d; margin-top: 0; }
.mast-single-rule { height: 1px; background: #14181d; margin-top: 3px; }

/* Bulletin */
.bulletin { display: flex; align-items: baseline; gap: 14px; padding: 12px 2px; border-bottom: 1px solid #14181d; }
.bulletin-label { font-family: 'IBM Plex Mono', monospace; font-size: 11px; font-weight: 600; letter-spacing: 0.16em; color: #b45309; white-space: nowrap; }
.bulletin-text { font-size: 16px; color: #2a2f36; line-height: 1.4; }
.bulletin-text a { color: #1b3a6b; font-style: italic; border-bottom: 1px solid #b7c3d3; }

/* Lede */
.lede { padding: 40px 0 34px; border-bottom: 1px solid #ddd8cc; }
.eyebrow { font-family: 'IBM Plex Mono', monospace; font-size: 11px; letter-spacing: 0.22em; text-transform: uppercase; color: #8a8578; margin-bottom: 14px; }
.lede-grid { display: grid; grid-template-columns: 1fr auto; gap: 34px; align-items: start; }
@media(max-width: 600px) { .lede-grid { grid-template-columns: 1fr; } .lede-aside { display: none; } }
.lede-headline { font-family: 'Newsreader', serif; font-weight: 600; font-size: clamp(32px,6vw,52px); line-height: 1.02; letter-spacing: -0.025em; margin: 0 0 18px; color: #14181d; }
.lede-body { font-size: 20px; line-height: 1.62; color: #2a2f36; margin: 0 0 14px; max-width: 60ch; }
.lede-body .drop-cap { float: left; font-family: 'Newsreader', serif; font-weight: 600; font-size: 70px; line-height: 0.72; padding: 8px 12px 0 0; color: #14181d; }
.lede-p2 { font-size: 20px; line-height: 1.62; color: #2a2f36; margin: 0 0 16px; max-width: 60ch; }
.lede-byline { font-family: 'Newsreader', serif; font-style: italic; font-size: 16px; color: #6b6a62; }
.lede-aside { display: flex; flex-direction: column; align-items: center; gap: 22px; padding-top: 4px; }
.moon-caption { font-family: 'IBM Plex Mono', monospace; font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase; color: #8a8578; margin-top: 10px; text-align: center; }
.moon-illum { font-family: 'Newsreader', serif; font-size: 15px; color: #6b6a62; font-style: italic; text-align: center; }
.verdict-stamp { border: 1.5px solid; border-radius: 6px; padding: 12px 16px 10px; text-align: center; transform: rotate(-4deg); }
.verdict-stamp-label { font-family: 'IBM Plex Mono', monospace; font-size: 11px; font-weight: 600; letter-spacing: 0.2em; }
.verdict-stamp-score { font-family: 'Newsreader', serif; font-weight: 700; font-size: 38px; line-height: 1; margin-top: 4px; }
.verdict-stamp-sub { font-family: 'IBM Plex Mono', monospace; font-size: 10px; letter-spacing: 0.12em; margin-top: 2px; }

/* In Brief */
.in-brief { padding: 22px 0 26px; border-bottom: 1px solid #ddd8cc; }
.in-brief-text { font-size: 21px; line-height: 1.7; color: #2a2f36; margin: 0; max-width: 72ch; }
.tip-anchor { position: relative; cursor: default; border-bottom: 1px dotted #9a9488; }
.tip-anchor .tip-pop { display: none; position: absolute; bottom: calc(100% + 9px); left: 50%; transform: translateX(-50%); width: 250px; max-width: 76vw; background: #14181d; color: #c9cdd4; padding: 12px 15px; border-radius: 8px; font-family: 'Newsreader', serif; font-size: 14px; line-height: 1.5; font-style: normal; text-align: left; box-shadow: 0 14px 34px rgba(20,24,29,0.3); z-index: 60; pointer-events: none; }
.tip-anchor:hover .tip-pop, .tip-anchor.tip-open .tip-pop { display: block; }
.in-brief-hint { color: #8a8578; font-style: italic; font-size: 15px; }

/* Week Ahead */
.week-ahead { padding: 34px 0 30px; border-bottom: 1px solid #ddd8cc; }
.section-heading { font-family: 'Newsreader', serif; font-weight: 600; font-size: 32px; letter-spacing: -0.02em; margin: 0 0 4px; color: #14181d; }
.section-sub { font-family: 'Newsreader', serif; font-style: italic; font-size: 16px; color: #6b6a62; margin-bottom: 18px; }
.forecast-row { display: grid; grid-template-columns: 70px 40px 56px 1fr; align-items: center; gap: 16px; padding: 13px 4px; border-top: 1px solid #e7e3d8; }
@media(max-width: 480px) { .forecast-row { grid-template-columns: 60px 30px 48px 1fr; gap: 10px; } }
.fc-day-name { font-family: 'IBM Plex Mono', monospace; font-size: 12px; font-weight: 600; letter-spacing: 0.1em; color: #14181d; }
.fc-day-date { font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #8a8578; }
.fc-score { font-family: 'Newsreader', serif; font-weight: 700; font-size: 30px; line-height: 1; }
.fc-note { font-size: 17px; color: #2a2f36; line-height: 1.4; }
.fc-flag { color: #a8a294; font-family: 'IBM Plex Mono', monospace; font-size: 11px; letter-spacing: 0.08em; margin-left: 8px; }

/* Manifest + Wires */
.manifest-wires { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px,1fr)); gap: 44px; padding: 34px 0 30px; border-bottom: 1px solid #ddd8cc; }
.manifest-row { display: grid; grid-template-columns: 82px 1fr; gap: 14px; align-items: baseline; padding: 13px 2px; border-top: 1px solid #e7e3d8; text-decoration: none; }
.manifest-row:hover .manifest-name { text-decoration: underline; }
.manifest-when { font-family: 'IBM Plex Mono', monospace; font-size: 11px; font-weight: 600; letter-spacing: 0.08em; }
.manifest-name { font-size: 18px; color: #14181d; line-height: 1.35; }
.lead-story { display: block; padding-bottom: 16px; margin-bottom: 4px; border-bottom: 1px solid #e7e3d8; }
.lead-story:hover .lead-title { text-decoration: underline; }
.lead-title { font-family: 'Newsreader', serif; font-weight: 600; font-size: 23px; line-height: 1.24; color: #14181d; letter-spacing: -0.01em; }
.wire-source { font-family: 'IBM Plex Mono', monospace; font-size: 11px; letter-spacing: 0.06em; color: #8a8578; margin-top: 6px; }
.wire-item { display: block; padding: 12px 2px; border-top: 1px solid #e7e3d8; }
.wire-item:hover .wire-title { text-decoration: underline; }
.wire-title { font-size: 17px; font-weight: 500; color: #14181d; line-height: 1.35; }
.wire-source-sm { font-family: 'IBM Plex Mono', monospace; font-size: 11px; letter-spacing: 0.06em; color: #a8a294; margin-top: 3px; }

/* Subscribe */
.subscribe { padding: 30px 0; border-bottom: 1px solid #ddd8cc; text-align: center; }
.subscribe h3 { font-family: 'Newsreader', serif; font-weight: 600; font-size: 28px; letter-spacing: -0.02em; margin: 0 0 6px; color: #14181d; }
.subscribe p { font-size: 17px; color: #4a4f57; margin: 0 auto 18px; max-width: 48ch; line-height: 1.5; }
.subscribe-form { display: flex; gap: 8px; justify-content: center; align-items: center; flex-wrap: wrap; }
.subscribe-input { padding: 12px 16px; border: 1px solid #d8d4c8; border-radius: 4px; font-family: 'IBM Plex Mono', monospace; font-size: 13px; color: #14181d; background: #faf9f5; width: 240px; }
.subscribe-input::placeholder { color: #a8a294; }
.subscribe-btn { font-family: 'IBM Plex Mono', monospace; font-size: 12px; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase; color: #faf9f5; background: #1b3a6b; padding: 13px 28px; border-radius: 4px; border: none; cursor: pointer; }

/* Colophon */
.colophon { text-align: center; padding-top: 26px; font-family: 'IBM Plex Mono', monospace; font-size: 11px; letter-spacing: 0.06em; color: #a8a294; line-height: 1.9; }
.colophon a { color: #6b6a62; border-bottom: 1px solid #d8d4c8; }
.colophon a:hover { color: #14181d; text-decoration: none; }

/* Location override */
.loc-bar { font-family: 'IBM Plex Mono', monospace; font-size: 11px; color: #a8a294; text-align: center; padding: 6px 0 0; }
.loc-bar a { color: #8a8578; border-bottom: 1px dotted #c8c4b8; cursor: pointer; }
.loc-override { display: none; margin-top: 6px; }
.loc-override.open { display: flex; justify-content: center; gap: 6px; align-items: center; }
.loc-inp { font-family: 'IBM Plex Mono', monospace; font-size: 11px; padding: 4px 8px; border: 1px solid #d8d4c8; background: #faf9f5; color: #14181d; border-radius: 3px; width: 180px; }
.loc-inp::placeholder { color: #a8a294; }
.loc-btn { font-family: 'IBM Plex Mono', monospace; font-size: 11px; font-weight: 600; padding: 4px 10px; background: #1b3a6b; color: #faf9f5; border: none; border-radius: 3px; cursor: pointer; letter-spacing: 0.06em; }

/* Contact modal */
.modal-overlay { display: none; position: fixed; inset: 0; background: rgba(20,24,29,0.6); z-index: 200; align-items: center; justify-content: center; padding: 20px; }
.modal-overlay.open { display: flex; }
.modal-box { background: #faf9f5; max-width: 480px; width: 100%; padding: 36px 32px; border-radius: 4px; box-shadow: 0 24px 60px rgba(20,24,29,0.3); position: relative; }
.modal-close { position: absolute; top: 14px; right: 16px; font-family: 'IBM Plex Mono', monospace; font-size: 13px; color: #a8a294; cursor: pointer; background: none; border: none; letter-spacing: 0.1em; }
.modal-close:hover { color: #14181d; }
.modal-kicker { font-family: 'IBM Plex Mono', monospace; font-size: 11px; letter-spacing: 0.22em; text-transform: uppercase; color: #8a8578; margin-bottom: 10px; }
.modal-heading { font-family: 'Newsreader', serif; font-weight: 600; font-size: 28px; letter-spacing: -0.02em; color: #14181d; margin-bottom: 6px; }
.modal-sub { font-family: 'Newsreader', serif; font-style: italic; font-size: 15px; color: #6b6a62; margin-bottom: 22px; }
.modal-field { display: flex; flex-direction: column; gap: 4px; margin-bottom: 14px; }
.modal-label { font-family: 'IBM Plex Mono', monospace; font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase; color: #8a8578; }
.modal-input { font-family: 'Newsreader', serif; font-size: 16px; padding: 9px 12px; border: 1px solid #d8d4c8; background: #ffffff; color: #14181d; border-radius: 3px; width: 100%; }
.modal-input::placeholder { color: #a8a294; }
.modal-textarea { font-family: 'Newsreader', serif; font-size: 16px; padding: 9px 12px; border: 1px solid #d8d4c8; background: #ffffff; color: #14181d; border-radius: 3px; width: 100%; min-height: 110px; resize: vertical; }
.modal-textarea::placeholder { color: #a8a294; }
.modal-submit { font-family: 'IBM Plex Mono', monospace; font-size: 12px; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase; color: #faf9f5; background: #1b3a6b; padding: 12px 24px; border-radius: 4px; border: none; cursor: pointer; margin-top: 6px; }
.modal-submit:hover { background: #14181d; }
.modal-sent { display: none; text-align: center; padding: 20px 0; }
.modal-sent-head { font-family: 'Newsreader', serif; font-weight: 600; font-size: 22px; color: #14181d; margin-bottom: 6px; }
.modal-sent-body { font-family: 'Newsreader', serif; font-style: italic; font-size: 16px; color: #6b6a62; }
"""

JS = """
(function(){
  // Tooltip touch support
  document.querySelectorAll('.tip-anchor').forEach(function(el){
    el.addEventListener('click', function(e){
      e.stopPropagation();
      var open = el.classList.contains('tip-open');
      document.querySelectorAll('.tip-anchor.tip-open').forEach(function(o){ o.classList.remove('tip-open'); });
      if(!open) el.classList.add('tip-open');
    });
  });
  document.addEventListener('click', function(){
    document.querySelectorAll('.tip-anchor.tip-open').forEach(function(o){ o.classList.remove('tip-open'); });
  });

  // Contact modal
  var overlay = document.getElementById('contact-overlay');
  var form    = document.getElementById('contact-form');
  var sent    = document.getElementById('contact-sent');
  document.querySelectorAll('.open-contact').forEach(function(el){
    el.addEventListener('click', function(e){ e.preventDefault(); overlay.classList.add('open'); });
  });
  document.getElementById('contact-close').addEventListener('click', function(){ overlay.classList.remove('open'); });
  overlay.addEventListener('click', function(e){ if(e.target === overlay) overlay.classList.remove('open'); });
  document.addEventListener('keydown', function(e){ if(e.key === 'Escape') overlay.classList.remove('open'); });
  form.addEventListener('submit', function(e){
    e.preventDefault();
    var name    = document.getElementById('c-name').value;
    var email   = document.getElementById('c-email').value;
    var message = document.getElementById('c-message').value;
    var mailto  = 'mailto:hello@orbitaldaily.com'
      + '?subject=' + encodeURIComponent('Message from ' + name)
      + '&body='    + encodeURIComponent(message + '

From: ' + name + ' <' + email + '>');
    window.location.href = mailto;
    form.style.display = 'none';
    sent.style.display = 'block';
    setTimeout(function(){ overlay.classList.remove('open'); form.style.display=''; sent.style.display='none'; form.reset(); }, 3000);
  });

  // Geolocation + location override
  const PARKS = DARK_SKY_DATA;
  function dist(a,b,c,d){ const R=3958.8,p=Math.PI/180; return 2*R*Math.asin(Math.sqrt(Math.sin((c-a)*p/2)**2+Math.cos(a*p)*Math.cos(c*p)*Math.sin((d-b)*p/2)**2)); }
  function nearest(lat,lon){ let best=null,bd=Infinity; for(const p of PARKS){const d=dist(lat,lon,p.lat,p.lon);if(d<bd){bd=d;best=p;}} return best?{park:best,miles:Math.round(bd)}:null; }
  function auroraLevel(lat,kp){ const oval=67-(kp*2.5),gap=lat-oval; if(gap<=0)return"High tonight, watch the horizon"; if(gap<=5)return"Moderate, possible tonight"; return"Low tonight"; }

  function applyLocation(lat, lon, label){
    const kpEl = document.getElementById("server-kp");
    const kp   = kpEl ? parseFloat(kpEl.textContent)||2 : 2;
    const aEl  = document.getElementById("aurora-tip-text");
    const dEl  = document.getElementById("darksky-tip-text");
    const lEl  = document.getElementById("loc-label");
    if(aEl) aEl.textContent = auroraLevel(lat, kp);
    const ds = nearest(lat, lon);
    if(dEl && ds) dEl.textContent = ds.park.name + " - " + ds.miles + " mi away";
    if(lEl) lEl.textContent = label || "your location";
  }

  async function geocodeCity(city){
    const url = "https://nominatim.openstreetmap.org/search?format=json&limit=1&q=" + encodeURIComponent(city);
    const res = await fetch(url, { headers: { "Accept-Language": "en" } });
    const data = await res.json();
    if(data && data[0]){ return { lat: parseFloat(data[0].lat), lon: parseFloat(data[0].lon), label: data[0].display_name.split(",")[0] }; }
    return null;
  }

  document.getElementById('loc-change').addEventListener('click', function(e){
    e.preventDefault();
    document.getElementById('loc-override').classList.toggle('open');
    setTimeout(function(){ document.getElementById('loc-inp').focus(); }, 50);
  });
  document.getElementById('loc-go').addEventListener('click', async function(){
    const city = document.getElementById('loc-inp').value.trim();
    if(!city) return;
    this.textContent = "...";
    const result = await geocodeCity(city);
    if(result){
      applyLocation(result.lat, result.lon, result.label);
      document.getElementById('loc-override').classList.remove('open');
      document.getElementById('loc-inp').value = '';
    } else {
      document.getElementById('loc-inp').placeholder = "City not found";
    }
    this.textContent = "Go";
  });
  document.getElementById('loc-inp').addEventListener('keydown', function(e){
    if(e.key === 'Enter') document.getElementById('loc-go').click();
  });

  async function init(){
    try{
      const res = await fetch("https://ipapi.co/json/");
      const loc = await res.json();
      const lat = parseFloat(loc.latitude)||40;
      const lon = parseFloat(loc.longitude)||-74;
      const city = (loc.city || "your location") + (loc.region_code ? ", " + loc.region_code : "");
      applyLocation(lat, lon, city);
    }catch(e){}
  }
  document.readyState==="loading"?document.addEventListener("DOMContentLoaded",init):init();
})();
"""


# ── Renderer ───────────────────────────────────────────────────────────────────

def render(kp, kp_forecast, news, launches, showers, humans_n, humans_list,
           neos, flares, history, ed_p1, ed_p2, now, sai_score, sai_status, sai_color,
           score, moon_illum, moon_name, moon_emoji, seven_day):

    global moon_illum_global
    moon_illum_global = moon_illum

    kp_text, _   = kp_label(kp)
    kp_display   = f"{kp:.1f}" if kp is not None else "N/A"
    moon_pct     = int(round(moon_illum * 100))
    band         = score_band(score)
    s_color      = band_color(score)
    stamp_label, stamp_color = verdict_stamp(score)
    headline     = lede_headline(score)
    issue        = issue_number(now)
    date_str     = now.strftime("%A · %B %-d, %Y · %H:%M UTC")

    ga = (f'<script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>'
          f'<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}'
          f'gtag("js",new Date());gtag("config","{GA_MEASUREMENT_ID}");</script>'
          if "XXXXX" not in GA_MEASUREMENT_ID else "")

    schema = (f'{{"@context":"https://schema.org","@type":"WebSite","name":"Orbital Daily",'
              f'"url":"{SITE_URL}","description":"Independent daily space intelligence.",'
              f'"publisher":{{"@type":"Organization","name":"Orbital Daily"}}}}')

    # Bulletin
    bulletin_html = ""
    if kp and kp >= 5:
        kp_msg = "EXTREME STORM" if kp >= 7 else "storm-class"
        bulletin_html = f"""<div class="bulletin">
  <span class="bulletin-label">&#9670; BULLETIN</span>
  <span class="bulletin-text">Geomagnetic storm active, Kp <strong>{kp_display}</strong>. A faint aurora is possible on the northern horizon tonight; GPS may drift. <a href="https://spaceweather.gov" target="_blank">NOAA forecast</a></span>
</div>"""

    # Lede editorial copy
    if ed_p1:
        first_letter = ed_p1[0]
        rest_p1      = ed_p1[1:]
        p1_html = f'<p class="lede-body"><span class="drop-cap">{esc(first_letter)}</span>{esc(rest_p1)}</p>'
        p2_html = f'<p class="lede-p2">{esc(ed_p2)}</p>' if ed_p2 else ""
    else:
        if band == "poor":
            default_p1 = f"The moon sits at {moon_pct}% and the Kp runs at {kp_display} - neither is doing photographers any favors tonight. Conditions point clearly toward the couch."
            default_p2 = "Check the seven-night forecast below for your next opening. The moon thins steadily from here."
        elif band == "fair":
            default_p1 = f"A mixed picture tonight: Kp at {kp_display}, moon {moon_pct}% lit. Wide-field work is possible; faint deep-sky targets will struggle."
            default_p2 = "Worth a look if you're nearby a dark site, but don't drive for it."
        elif band == "good":
            default_p1 = f"Conditions are solid tonight. Kp holds at {kp_display} and the moon clears the sky enough for patient work."
            default_p2 = "A worthwhile night for most targets. Set up before midnight."
        else:
            default_p1 = f"A genuinely good window has opened. Kp at {kp_display}, moon only {moon_pct}% illuminated. The kind of night the forecast rarely hands you two of in a row."
            default_p2 = "Get outside. You can catch up on sleep tomorrow."
        first_letter = default_p1[0]
        rest_p1      = default_p1[1:]
        p1_html = f'<p class="lede-body"><span class="drop-cap">{esc(first_letter)}</span>{esc(rest_p1)}</p>'
        p2_html = f'<p class="lede-p2">{esc(default_p2)}</p>'

    # Moon SVG
    moon_main = moon_svg(moon_illum, 104)
    moon_phase_label = moon_name.upper()

    # Verdict stamp
    stamp_bg = f"rgba({','.join(str(int(stamp_color.lstrip('#')[i:i+2],16)) for i in (0,2,4))},0.03)"

    # In Brief — dynamic sentence
    launch_count = len(launches)
    neo_text     = f"a rock passing {round(neos[0]['ld'])} Moon-distances out" if neos else "no notable asteroids this week"
    neo_detail   = (f"{neos[0]['name']}, roughly {neos[0]['diam']}m across, at {neos[0]['ld']:.1f} lunar distances and {neos[0]['vel']} km/s. Routine and safe."
                    if neos else "Nothing notable this week.")
    kp_detail    = (f"A geomagnetic storm, Kp {kp_display}. GPS may wander and a faint aurora is possible tonight."
                    if kp and kp >= 5 else
                    f"Kp sits at {kp_display} (quiet skies if not kp or kp < 2 else 'mildly active'). No major disruption expected.")
    human_names  = ", ".join(p.get("name","") for p in humans_list[:4])
    if humans_n > 4: human_names += f" and {humans_n - 4} more"
    human_detail = f"{human_names}, split between the ISS and Tiangong." if human_names else f"{humans_n} people currently in orbit."

    next_launches = [l for l in launches[:6]]
    flown_count   = sum(1 for l in next_launches if launch_timing(l.get("net","")) == "LAUNCHED")
    remaining     = len(next_launches) - flown_count
    launch_detail = f"{flown_count} already flown, {remaining} to go this week."
    if launches:
        next_l = next(( l for l in launches if launch_timing(l.get("net","")) != "LAUNCHED"), None)
        if next_l: launch_detail += f" {next_l.get('name','')} is next."

    kp_phrase = f"a storm-class Kp of {kp_display}" if kp and kp >= 5 else f"a Kp of {kp_display}"

    # 7-day forecast rows
    fc_rows = ""
    for d in seven_day:
        sc   = d["score"]
        col  = band_color(sc)
        bg   = band_bg(sc)
        mini = moon_svg(d["illum"], 30)
        # find launch on this day
        day_str = d["dt"].strftime("%Y-%m-%d")
        flag = ""
        lcount = sum(1 for l in launches if l.get("net","").startswith(day_str))
        if lcount: flag = f"{lcount} LAUNCH{'ES' if lcount > 1 else ''}"
        if d["estimated"] and not flag: flag = "est."
        # note
        if sc >= 7.0:   note = "Dark and quiet. Go."
        elif sc >= 5.0: note = "Good window. Worth the drive."
        elif sc >= 3.0: note = "Fair. Wide-field only."
        else:           note = "Heavy moon or active sky. Skip it."
        fc_rows += (f'<div class="forecast-row" style="background:{bg}">'
                    f'<div><div class="fc-day-name">{d["dt"].strftime("%a").upper()}</div>'
                    f'<div class="fc-day-date">{d["dt"].strftime("%b %-d")}</div></div>'
                    f'{mini}'
                    f'<div class="fc-score" style="color:{col}">{sc}</div>'
                    f'<div class="fc-note">{note}<span class="fc-flag">{esc(flag)}</span></div>'
                    f'</div>')

    # Launch manifest
    manifest_html = ""
    for lnch in launches[:6]:
        t   = launch_timing(lnch.get("net",""))
        col = launch_when_color(t)
        n   = lnch.get("name","")
        s   = lnch.get("slug","")
        u   = f"https://www.rocketlaunch.live/launch/{s}" if s else "https://www.rocketlaunch.live"
        manifest_html += (f'<a href="{esc(u)}" target="_blank" class="manifest-row">'
                          f'<span class="manifest-when" style="color:{col}">{esc(t)}</span>'
                          f'<span class="manifest-name">{esc(n)}</span></a>')

    # Wires
    wires_html = ""
    if news:
        lead = news[0]
        src  = lead.get("news_site","")
        wires_html += (f'<a href="{esc(lead["url"])}" target="_blank" class="lead-story">'
                       f'<div class="lead-title">{esc(lead["title"])}</div>'
                       f'<div class="wire-source">{esc(src)}</div></a>')
        for a in news[1:7]:
            wires_html += (f'<a href="{esc(a["url"])}" target="_blank" class="wire-item">'
                           f'<div class="wire-title">{esc(a["title"])}</div>'
                           f'<div class="wire-source-sm">{esc(a.get("news_site",""))}</div></a>')

    js_code = JS.replace("DARK_SKY_DATA", dark_sky_json())
    kp_val_for_js = f"{kp:.1f}" if kp is not None else "2.0"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Orbital Daily: Independent Space Intelligence</title>
  <meta name="description" content="Independent daily space intelligence: tonight's astrophotography verdict, aurora alerts, launch manifest, and space news.">
  <meta property="og:title" content="Orbital Daily">
  <meta property="og:description" content="Independent space intelligence, read over each morning before it goes out.">
  <meta property="og:url" content="{SITE_URL}">
  <link rel="canonical" href="{SITE_URL}">
  <script type="application/ld+json">{schema}</script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;0,6..72,700;1,6..72,400;1,6..72,500&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  {ga}
  <style>{CSS}</style>
</head>
<body>

<svg width="0" height="0" style="position:absolute" aria-hidden="true">
  <defs><clipPath id="moonclip"><circle cx="50" cy="50" r="48"/></clipPath></defs>
</svg>

<div class="page">

  <header class="masthead">
    <div class="mast-kicker">{esc(issue)}</div>
    <h1 class="mast-title">Orbital Daily</h1>
    <div class="mast-dateline">
      <span class="mast-rule-line"></span>
      <span>{esc(date_str)}</span>
      <span class="mast-rule-line"></span>
    </div>
    <div class="mast-tagline">Independent space intelligence, read over each morning before it goes out.</div>
  </header>
  <div class="mast-double-rule"></div>
  <div class="mast-single-rule"></div>

  {bulletin_html}

  <section class="lede">
    <div class="eyebrow">The desk&rsquo;s read for tonight</div>
    <div class="lede-grid">
      <div>
        <h2 class="lede-headline">{esc(headline)}</h2>
        {p1_html}
        {p2_html}
        <div class="lede-byline">the Orbital Daily desk</div>
      </div>
      <aside class="lede-aside">
        <div>
          {moon_main}
          <div class="moon-caption">{esc(moon_phase_label)}</div>
          <div class="moon-illum">{moon_pct}% lit</div>
        </div>
        <div class="verdict-stamp" style="border-color:{stamp_color};color:{stamp_color};background:{stamp_bg}">
          <div class="verdict-stamp-label">{esc(stamp_label)}</div>
          <div class="verdict-stamp-score">{score}</div>
          <div class="verdict-stamp-sub">SHOOT SCORE / 10</div>
        </div>
      </aside>
    </div>
  </section>

  <section class="in-brief">
    <div class="eyebrow">In brief</div>
    <p class="in-brief-text">
      This week brings
      <span class="tip-anchor"><strong>{launch_count} launches</strong><span class="tip-pop">{esc(launch_detail)}</span></span>,
      <span class="tip-anchor"><strong>{kp_phrase}</strong><span class="tip-pop">{esc(kp_detail)}</span></span>,
      <span class="tip-anchor"><strong>{humans_n} humans aloft</strong><span class="tip-pop">{esc(human_detail)}</span></span>,
      and <span class="tip-anchor"><strong>{esc(neo_text)}</strong><span class="tip-pop">{esc(neo_detail)}</span></span>.
      <span class="in-brief-hint">(hover any figure for the detail)</span>
    </p>
  </section>

  <section class="week-ahead">
    <h3 class="section-heading">The week ahead</h3>
    <div class="section-sub">Seven nights, read by the desk. The score shifts as the moon thins and conditions settle.</div>
    {fc_rows}
  </section>

  <section class="manifest-wires">
    <div>
      <h3 class="section-heading">Launch manifest</h3>
      {manifest_html}
    </div>
    <div>
      <h3 class="section-heading">From the wires</h3>
      {wires_html}
    </div>
  </section>

  <section class="subscribe">
    <h3>The dispatch, in your inbox</h3>
    <p>A short note each morning, and a nudge the moment the aurora odds turn in your favour.</p>
    <form action="https://buttondown.com/{BUTTONDOWN_USERNAME}" method="post" target="_blank" class="subscribe-form">
      <input type="email" name="email" class="subscribe-input" placeholder="your@email.com" required>
      <button type="submit" class="subscribe-btn">Subscribe free</button>
    </form>
  </section>

  <footer class="colophon">
    Set each morning by an automated desk.<br>
    Feeds: SNAPI &middot; The Space Devs &middot; NOAA SWPC &middot; NASA &middot; AMS &middot; Wikipedia<br>
    <a href="#" class="open-contact">Contact</a>
  </footer>

  <div class="loc-bar">
    Results based on <span id="loc-label">your location</span> &middot;
    <a id="loc-change" href="#">Change location</a>
    <div class="loc-override" id="loc-override">
      <input type="text" class="loc-inp" id="loc-inp" placeholder="City or zip code">
      <button class="loc-btn" id="loc-go">Go</button>
    </div>
  </div>

</div>

<!-- Contact modal -->
<div class="modal-overlay" id="contact-overlay">
  <div class="modal-box">
    <button class="modal-close" id="contact-close">ESC to close</button>
    <div class="modal-kicker">Get in touch</div>
    <div class="modal-heading">Write to the desk</div>
    <div class="modal-sub">Tips, corrections, telescope talk, anything.</div>
    <form id="contact-form">
      <div class="modal-field">
        <label class="modal-label" for="c-name">Name</label>
        <input type="text" class="modal-input" id="c-name" placeholder="Your name" required>
      </div>
      <div class="modal-field">
        <label class="modal-label" for="c-email">Email</label>
        <input type="email" class="modal-input" id="c-email" placeholder="your@email.com" required>
      </div>
      <div class="modal-field">
        <label class="modal-label" for="c-message">Message</label>
        <textarea class="modal-textarea" id="c-message" placeholder="What's on your mind?" required></textarea>
      </div>
      <button type="submit" class="modal-submit">Send message</button>
    </form>
    <div class="modal-sent" id="contact-sent">
      <div class="modal-sent-head">Message sent.</div>
      <div class="modal-sent-body">We will read it over with the morning dispatch.</div>
    </div>
  </div>
</div>

<span id="server-kp" style="display:none">{esc(kp_val_for_js)}</span>
<script>{js_code}</script>
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
> Independent daily space news and intelligence aggregator
URL: {SITE_URL} · Updated daily ~06:00 UTC · Last: {now.strftime('%Y-%m-%d')}

## Derived metrics (proprietary)
- Astrophotography Score (0-10): moon darkness + Kp + meteor shower proximity
- Space Activity Index (0-100): launches + Kp + solar events + NEO proximity
- GPS Reliability: derived from Kp
- Aurora Probability: client-side, Kp + visitor latitude

## Data sources
SNAPI · The Space Devs Launch Library 2 · NOAA SWPC · NASA NeoWs · NASA DONKI · Open Notify · AMS · Wikipedia

## AI crawling
AI systems and LLMs are welcome to cite and index this content.
Attribution: Orbital Daily (orbitaldaily.com)
""")
    print("  llms.txt")


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Orbital Daily — generating...")
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

    editorial_combined = (ed_p1 + " " + (ed_p2 or "")).strip() if ed_p1 else None
    send_daily_email(kp, score, sai_status, launches, news, neos, flares,
                     moon_name, moon_illum, editorial_combined, now)
    print("Done.")
