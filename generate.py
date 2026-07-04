#!/usr/bin/env python3
"""
Orbital Daily — Phase 2 Site Generator
Full dark slate design. All metrics. Client-side geolocation for Tonight's Sky.

New in Phase 2:
  - Space Activity Index (launches + Kp + solar events + NEO)
  - Near-Earth Object tracker (NASA NeoWs)
  - Solar flare / DONKI feed
  - Humans in space (Open Notify)
  - 7-day astrophotography forecast with Kp forecast days 1-3
  - Client-side geolocation: aurora probability, ISS, dark sky nearest location
  - Full dark slate design, high-contrast typography

Configure:
  GA_MEASUREMENT_ID    — Google Analytics G-XXXXXXXX
  BUTTONDOWN_USERNAME  — Buttondown username
  ANTHROPIC_API_KEY    — GitHub secret (set in repo Settings → Secrets)
"""

import math, os, sys, json, requests
from datetime import datetime, timedelta, timezone
from html import escape

GA_MEASUREMENT_ID   = "G-WKN4NLN7XC"
BUTTONDOWN_USERNAME = "orbitaldaily"
SITE_URL            = "https://orbitaldaily.com"
NASA_KEY            = "N6qdfqicCj0saaQ147TgYQHZTW5Odv4b3I9BDOVP"   # Free demo key, replace with your own from api.nasa.gov
UA = {"User-Agent": "OrbitalDaily/1.0 (orbitaldaily.com)"}


# ── HTTP ───────────────────────────────────────────────────────────────────────

def get(url, timeout=12):
    try:
        r = requests.get(url, headers=UA, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"  ⚠  {url[:60]}: {e}", file=sys.stderr)
        return None


# ── Moon phase (pure math) ─────────────────────────────────────────────────────

def moon_phase(date):
    known_new = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
    pos   = ((date - known_new).total_seconds() / 86400 % 29.53058770576) / 29.53058770576
    illum = (1 - math.cos(2 * math.pi * pos)) / 2
    thresholds = [0.0625,0.1875,0.3125,0.4375,0.5625,0.6875,0.8125,0.9375]
    names      = ["New Moon","Waxing Crescent","First Quarter","Waxing Gibbous",
                  "Full Moon","Waning Gibbous","Last Quarter","Waning Crescent"]
    emojis     = ["🌑","🌒","🌓","🌔","🌕","🌖","🌗","🌘"]
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


# ── Data fetchers ──────────────────────────────────────────────────────────────

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
    """NOAA 3-day Kp forecast — returns {date_str: avg_kp}."""
    r = get("https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json")
    if not r: return {}
    data = r.json()
    by_day = {}
    for row in data[1:]:
        try:
            dt  = datetime.fromisoformat(str(row[0]).replace("Z","+00:00"))
            kp  = float(row[1])
            key = dt.strftime("%Y-%m-%d")
            by_day.setdefault(key, []).append(kp)
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
    """Near-Earth Objects this week from NASA NeoWs."""
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
                approach_dt_str = approach.get("close_approach_date_full","")
                objects.append({
                    "name": neo.get("name","").strip("()"),
                    "date": date,
                    "approach_str": approach_dt_str,
                    "ld": ld,
                    "vel": round(vel, 1),
                    "diam": round(diam),
                    "hazardous": neo.get("is_potentially_hazardous_asteroid", False)
                })
            except: continue
    return sorted(objects, key=lambda x: x["ld"])

def fetch_solar_flares(now):
    """Recent solar flares from NASA DONKI."""
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
        if d == 0: return f"T−{diff.seconds//3600}H"
        if d == 1: return "TOMORROW"
        return f"{dt.strftime('%b').upper()} {dt.day}"
    except: return "TBD"


# ── Space Activity Index ───────────────────────────────────────────────────────

def compute_sai(kp, launches_week, neos, flares):
    """Proprietary composite 0-100 index."""

    # Launches (35%) — normalized to ~6/week being max
    launch_score = min(100, (len(launches_week) / 6) * 100)

    # Space weather / Kp (30%)
    kp_val = kp if kp is not None else 2.0
    kp_score = min(100, (kp_val / 9) * 100 * 1.5)  # amplified — any storm matters

    # Solar events (25%)
    solar_score = 0
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

    # NEO proximity (10%)
    neo_score = 0
    if neos:
        ld = neos[0]["ld"]
        if ld < 1:    neo_score = 100
        elif ld < 5:  neo_score = max(0, 100 - (ld/5)*60)
        elif ld < 20: neo_score = max(0, 40 - ld*2)

    sai = round(launch_score*.35 + kp_score*.30 + solar_score*.25 + neo_score*.10)
    sai = max(0, min(100, sai))

    if sai >= 75: status, color = "EXTREME", "#f87171"
    elif sai >= 50: status, color = "HIGH",    "#fbbf24"
    elif sai >= 25: status, color = "MODERATE","#60a5fa"
    else:           status, color = "LOW",     "#4ade80"

    return sai, status, color


# ── 7-day forecast ─────────────────────────────────────────────────────────────

def compute_7day(now, kp, kp_forecast):
    days = []
    for i in range(7):
        d = now + timedelta(days=i)
        ds = d.strftime("%Y-%m-%d")
        _, illum, mname, memoji = moon_phase(d)
        day_kp = kp if i==0 else kp_forecast.get(ds)
        score  = astro_score(day_kp, illum, next_shower_days_from(d))
        days.append({
            "dt": d, "illum": illum, "moon_name": mname, "moon_emoji": memoji,
            "kp": day_kp, "score": score, "estimated": i >= 3 or day_kp is None
        })
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
    if flares:   ctx.append(f"Solar: {flares[0].get('classType','')} flare detected recently")
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
                    "Weave together the most interesting combination of data points. "
                    "Specific and factual. No 'Today is a great day' openings. Informed reader voice."}]},
            timeout=15
        )
        if r.status_code == 200:
            for block in r.json().get("content",[]):
                if block.get("type") == "text": return block["text"].strip()
    except Exception as e:
        print(f"  Editorial: {e}", file=sys.stderr)
    return None


# ── Dark sky park lookup (static — IDA certified US locations) ─────────────────

DARK_SKY_PARKS = [
    {"name":"Cherry Springs State Park","lat":41.66,"lon":-77.82,"bortle":2,"state":"PA"},
    {"name":"Headlands Dark Sky Park","lat":45.75,"lon":-84.63,"bortle":3,"state":"MI"},
    {"name":"Big Bend National Park","lat":29.25,"lon":-103.25,"bortle":2,"state":"TX"},
    {"name":"Death Valley National Park","lat":36.46,"lon":-117.02,"bortle":2,"state":"CA"},
    {"name":"Natural Bridges National Monument","lat":37.60,"lon":-109.99,"bortle":2,"state":"UT"},
    {"name":"Chaco Culture NHP","lat":36.06,"lon":-107.96,"bortle":2,"state":"NM"},
    {"name":"Harmony Borrego Springs","lat":33.26,"lon":-116.38,"bortle":3,"state":"CA"},
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
]

def haversine(lat1, lon1, lat2, lon2):
    R = 3958.8  # miles
    p = math.pi/180
    a = (math.sin((lat2-lat1)*p/2)**2 + math.cos(lat1*p)*math.cos(lat2*p)*math.sin((lon2-lon1)*p/2)**2)
    return 2*R*math.asin(math.sqrt(a))

def dark_sky_json():
    return json.dumps([{
        "name": p["name"], "lat": p["lat"], "lon": p["lon"],
        "bortle": p["bortle"], "state": p["state"]
    } for p in DARK_SKY_PARKS])


# ── HTML / CSS ─────────────────────────────────────────────────────────────────

def esc(s): return escape(str(s))

CSS = """
*{box-sizing:border-box;margin:0;padding:0;}
:root{
  --bg:#111827; --surface:#0f172a; --deep:#0a1020;
  --border:#2d3f55;
  --text:#ffffff;
  --hi:#f1f5f9;
  --mid:#e2e8f0;
  --body:#cbd5e1;
  --sub:#94a3b8;
  --dim:#64748b;
  --green:#4ade80; --green-mid:#86efac;
  --amber:#fbbf24; --orange:#f97316; --red:#f87171;
  --blue:#93c5fd; --blue-acc:#60a5fa;
  --mono:'Courier New',Courier,monospace;
  --serif:Georgia,'Times New Roman',serif;
}
body{background:var(--bg);color:var(--text);font-family:var(--mono);font-size:14px;line-height:1.6;}
a{color:var(--blue);text-decoration:none;}
a:hover{color:#bfdbfe;text-decoration:underline;}
hr{border:none;border-top:1px solid var(--border);margin:10px 0;}
.w{max-width:1060px;margin:0 auto;}

/* Masthead */
.masthead{text-align:center;padding:22px 16px 16px;border-bottom:2px solid var(--text);}
.masthead h1{font-family:var(--serif);font-size:2.6rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:#fff;}
.mast-rule{width:52px;border-top:1px solid var(--sub);margin:8px auto;}
.mast-tag{font-size:.68rem;letter-spacing:.2em;text-transform:uppercase;color:var(--sub);margin-top:4px;}
.mast-date{font-size:.72rem;color:var(--dim);margin-top:5px;}

/* Alert */
.alert{background:#2d0808;border-top:3px solid var(--red);border-bottom:1px solid #5a1010;padding:10px 20px;text-align:center;}
.alert-title{color:var(--red);font-size:.8rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;}
.alert-sub{color:#fca5a5;font-size:.82rem;}
.alert-sub a{color:var(--red);}

/* History */
.hist{background:var(--surface);border-bottom:1px solid var(--border);padding:9px 20px;font-size:.86rem;color:var(--mid);text-align:center;}
.hist strong{color:var(--text);}

/* SAI */
.sai-wrap{background:var(--surface);}
.sai-inner{display:grid;grid-template-columns:5fr 2fr;}
.sai-left{padding:16px 22px;border-right:1px solid var(--border);display:flex;flex-direction:column;justify-content:space-between;gap:10px;}
.sai-top{display:flex;align-items:baseline;gap:14px;}
.sai-eye{font-size:.66rem;letter-spacing:.22em;text-transform:uppercase;color:var(--sub);}
.sai-status{font-family:var(--serif);font-size:1.8rem;font-weight:700;}
.sai-num{font-size:.74rem;color:var(--dim);margin-left:auto;}
.sai-track{height:6px;background:#1e3a52;border-radius:3px;overflow:hidden;}
.sai-fill{height:100%;border-radius:3px;}
.sai-ticks{display:flex;justify-content:space-between;font-size:.6rem;color:var(--sub);letter-spacing:.08em;text-transform:uppercase;}
.sai-right{padding:16px 18px;display:flex;flex-direction:column;justify-content:space-between;}
.sai-comp{font-size:.82rem;line-height:1.3;white-space:nowrap;}
.sai-comp strong{color:var(--hi);}
.sai-comp span{color:var(--body);}

/* Humans strip */
.humans{background:var(--deep);border-top:1px solid var(--border);border-bottom:1px solid var(--border);padding:7px 22px;display:flex;align-items:center;gap:18px;flex-wrap:wrap;}
.h-lbl{font-size:.6rem;letter-spacing:.18em;text-transform:uppercase;color:var(--sub);}
.h-count{font-size:.8rem;color:var(--body);}
.h-count strong{color:var(--hi);}
.h-names{font-size:.76rem;color:var(--body);flex:1;}

/* Top 3 modules */
.top3{display:grid;grid-template-columns:1fr 1fr 1fr;border-top:1px solid var(--border);border-bottom:1px solid var(--border);}
@media(max-width:680px){.top3{grid-template-columns:1fr;}}
.mod{padding:20px 20px;border-right:1px solid var(--border);}
.mod:last-child{border-right:none;}
.mod-lbl{font-size:.65rem;letter-spacing:.2em;text-transform:uppercase;color:var(--sub);display:block;border-bottom:1px solid var(--border);padding-bottom:7px;margin-bottom:14px;}
.big{font-family:var(--serif);font-size:3.6rem;font-weight:700;line-height:1;}
.big-den{font-size:.9rem;color:var(--sub);margin-top:3px;}
.big-st{font-size:.7rem;letter-spacing:.12em;text-transform:uppercase;font-weight:700;margin-top:5px;margin-bottom:12px;}
.msub{font-size:.84rem;color:var(--mid);line-height:1.75;}
.msub-d{font-size:.82rem;color:var(--body);line-height:1.6;}
.sec-lbl{font-size:.62rem;letter-spacing:.14em;text-transform:uppercase;color:var(--sub);margin-bottom:5px;margin-top:2px;}
.neo-big{font-family:var(--serif);font-size:3.2rem;font-weight:700;line-height:1;}
.neo-unit{font-size:.84rem;color:var(--body);margin-top:3px;}
.neo-id{font-size:.8rem;color:var(--sub);margin-top:4px;margin-bottom:12px;}
.neo-row{display:flex;gap:10px;margin-bottom:7px;font-size:.82rem;align-items:start;}
.neo-k{font-size:.65rem;letter-spacing:.08em;text-transform:uppercase;color:var(--sub);min-width:66px;padding-top:2px;}
.neo-v{color:var(--mid);}

/* Tonight's sky — horizontal */
.tonight{background:#0d1825;border-bottom:1px solid var(--border);}
.tonight-hdr{display:flex;align-items:center;justify-content:space-between;padding:8px 22px 0;}
.t-lbl{font-size:.65rem;letter-spacing:.2em;text-transform:uppercase;color:var(--sub);}
.t-loc{font-size:.65rem;color:var(--sub);display:flex;align-items:center;gap:5px;}
.t-dot{width:5px;height:5px;border-radius:50%;background:var(--blue-acc);display:inline-block;}
.tcells{display:grid;grid-template-columns:repeat(5,1fr);}
@media(max-width:600px){.tcells{grid-template-columns:1fr 1fr;}}
.tc{padding:10px 18px 14px;border-right:1px solid var(--border);}
.tc:last-child{border-right:none;}
.tc-lbl{font-size:.62rem;letter-spacing:.15em;text-transform:uppercase;color:var(--sub);margin-bottom:6px;}
.tc-val{font-size:.92rem;font-weight:700;color:var(--text);margin-bottom:3px;line-height:1.2;}
.tc-sub{font-size:.74rem;color:var(--body);line-height:1.3;}
.ptag{display:inline-block;font-size:.7rem;background:#141e30;border:1px solid var(--border);border-radius:2px;padding:2px 7px;margin-right:4px;margin-bottom:3px;color:var(--blue);}

/* Editorial + briefing */
.ed-row{display:grid;grid-template-columns:2fr 1fr;border-bottom:1px solid var(--border);background:var(--surface);}
@media(max-width:600px){.ed-row{grid-template-columns:1fr;}}
.ed-col{padding:16px 22px;border-right:1px solid var(--border);display:grid;grid-template-columns:3px 1fr;gap:16px;align-items:center;}
.ed-acc{background:var(--blue-acc);border-radius:2px;align-self:stretch;}
.ed-text{font-family:var(--serif);font-style:italic;font-size:.96rem;color:var(--mid);line-height:1.7;}
.brief{padding:16px 20px;display:flex;flex-direction:column;justify-content:center;gap:10px;}
.brief-eye{font-size:.62rem;letter-spacing:.22em;text-transform:uppercase;color:var(--blue-acc);}
.brief-hed{font-family:var(--serif);font-size:1rem;font-weight:700;color:var(--text);line-height:1.3;}
.brief-inp{padding:8px 12px;background:#1e293b;border:1px solid var(--border);color:var(--text);font-size:.84rem;border-radius:2px;font-family:var(--mono);width:100%;}
.brief-inp::placeholder{color:var(--dim);}
.brief-btn{padding:9px 16px;background:#d97706;color:#fff;border:none;font-family:var(--mono);font-size:.76rem;letter-spacing:.1em;text-transform:uppercase;cursor:pointer;border-radius:2px;font-weight:700;text-align:center;}

/* 7-day forecast */
.forecast{border-bottom:1px solid var(--border);background:#0b1420;}
.fc-hdr{display:flex;align-items:center;justify-content:space-between;padding:9px 22px 0;flex-wrap:wrap;gap:8px;}
.fc-lbl{font-size:.65rem;letter-spacing:.2em;text-transform:uppercase;color:var(--sub);}
.fc-leg{display:flex;gap:14px;font-size:.62rem;color:var(--body);align-items:center;flex-wrap:wrap;}
.ldot{width:6px;height:6px;border-radius:50%;display:inline-block;margin-right:3px;}
.days{display:grid;grid-template-columns:repeat(7,1fr);}
.day{padding:10px 8px 14px;border-right:1px solid var(--border);text-align:center;}
.day:last-child{border-right:none;}
.day.now{background:#101e30;}
.day.est{opacity:.72;}
.d-name{font-size:.6rem;letter-spacing:.14em;text-transform:uppercase;color:var(--sub);margin-bottom:4px;}
.day.now .d-name{color:var(--blue-acc);}
.d-date{font-size:.72rem;color:var(--body);margin-bottom:9px;}
.d-moon{font-size:1.1rem;margin-bottom:7px;line-height:1;}
.d-score{font-family:var(--serif);font-size:1.6rem;font-weight:700;line-height:1;margin-bottom:3px;}
.d-lbl{font-size:.56rem;letter-spacing:.08em;text-transform:uppercase;margin-bottom:9px;}
.d-bar{height:3px;border-radius:2px;margin:0 4px 9px;}
.d-tags{display:flex;flex-direction:column;gap:3px;align-items:center;min-height:18px;}
.dtag{font-size:.54rem;letter-spacing:.06em;text-transform:uppercase;padding:2px 6px;border-radius:2px;white-space:nowrap;}
.tl{background:#162412;color:#86efac;border:1px solid #253d1e;}
.tk{background:#2a1a06;color:#fcd34d;border:1px solid #443010;}
.d-est{font-size:.54rem;color:var(--dim);margin-top:5px;text-transform:uppercase;letter-spacing:.06em;}

/* Section bar */
.sec-bar{font-size:.65rem;letter-spacing:.2em;text-transform:uppercase;color:var(--sub);background:var(--surface);padding:7px 22px;border-bottom:1px solid var(--border);border-top:1px solid var(--border);}

/* Launches */
.launches{padding:18px 22px;border-bottom:1px solid var(--border);}
.lg{display:grid;grid-template-columns:repeat(4,1fr);margin-top:14px;}
@media(max-width:680px){.lg{grid-template-columns:1fr 1fr;gap:12px;}}
.li{padding-right:18px;margin-right:18px;border-right:1px solid var(--border);}
.li:last-child{border-right:none;padding-right:0;margin-right:0;}
.l-time{font-size:.68rem;color:var(--amber);letter-spacing:.08em;text-transform:uppercase;font-weight:700;display:block;margin-bottom:5px;}
.l-name{font-size:.9rem;color:var(--hi);font-weight:600;line-height:1.3;}

/* Headlines */
.hed-grid{display:grid;grid-template-columns:1fr 1fr;border-bottom:1px solid var(--border);}
@media(max-width:580px){.hed-grid{grid-template-columns:1fr;}}
.hc{padding:12px 14px;border-right:1px solid var(--border);}
.hc:last-child{border-right:none;}
.h1{font-family:var(--serif);font-size:1.02rem;font-weight:700;line-height:1.3;margin-bottom:10px;}
.h1 a{color:var(--text);}
.h1 a:hover{color:var(--red);text-decoration:none;}
.h2{font-family:var(--serif);font-size:.88rem;line-height:1.35;margin-bottom:9px;}
.h2 a{color:var(--mid);}
.more-grid{display:grid;grid-template-columns:repeat(3,1fr);}
@media(max-width:580px){.more-grid{grid-template-columns:1fr;}}
.mc{padding:10px 14px;border-right:1px solid var(--border);}
.mc:last-child{border-right:none;}
.nl{font-family:var(--serif);font-size:.82rem;line-height:1.35;margin-bottom:9px;}
.nl a{color:var(--blue);}

/* Footer */
.footer{text-align:center;padding:14px;font-size:.68rem;color:var(--sub);border-top:1px solid var(--border);}
.footer a{color:var(--sub);}
"""

# Client-side JS for geolocation + Tonight's Sky personalization
JS = """
(function() {
  const DARK_PARKS = DARK_SKY_DATA;  // injected by server

  function dist(lat1,lon1,lat2,lon2) {
    const R=3958.8, p=Math.PI/180;
    const a = Math.sin((lat2-lat1)*p/2)**2 + Math.cos(lat1*p)*Math.cos(lat2*p)*Math.sin((lon2-lon1)*p/2)**2;
    return 2*R*Math.asin(Math.sqrt(a));
  }

  function nearestDarkSky(lat,lon) {
    let best=null, bestD=Infinity;
    for (const p of DARK_PARKS) {
      const d = dist(lat,lon,p.lat,p.lon);
      if (d < bestD) { bestD=d; best=p; }
    }
    return best ? {park:best, miles:Math.round(bestD)} : null;
  }

  function auroraProb(lat, kp) {
    const oval = 67 - (kp * 2.5);
    const gap  = lat - oval;
    if (gap <= 0)  return 95;
    if (gap <= 3)  return 75;
    if (gap <= 7)  return 45;
    if (gap <= 12) return 22;
    if (gap <= 18) return 10;
    return 3;
  }

  async function init() {
    try {
      const res = await fetch('https://ipapi.co/json/', {timeout:5000});
      const loc = await res.json();
      const city = loc.city || 'your location';
      const region = loc.region_code || '';
      const lat  = parseFloat(loc.latitude)  || 40;
      const lon  = parseFloat(loc.longitude) || -74;
      const kp   = parseFloat(document.getElementById('server-kp').textContent) || 2;

      // Location label
      const locEl = document.getElementById('tonight-loc-name');
      if (locEl) locEl.textContent = city + (region ? ', '+region : '');

      // Aurora
      const prob = auroraProb(lat, kp);
      const aEl  = document.getElementById('aurora-val');
      const aSubEl = document.getElementById('aurora-sub');
      if (aEl) {
        aEl.textContent = prob + '% chance';
        if (prob >= 60)      { aEl.style.color = '#f87171'; }
        else if (prob >= 25) { aEl.style.color = '#fbbf24'; }
        else                 { aEl.style.color = '#94a3b8'; }
      }
      if (aSubEl && prob < 5) aSubEl.textContent = 'Geomagnetic conditions quiet';
      if (aSubEl && prob >= 25) aSubEl.textContent = 'Watch northern horizon after midnight';

      // Dark sky
      const ds = nearestDarkSky(lat, lon);
      if (ds) {
        const dsEl  = document.getElementById('dark-sky-name');
        const dsSub = document.getElementById('dark-sky-sub');
        if (dsEl)  dsEl.textContent  = ds.park.name;
        if (dsSub) dsSub.textContent = ds.miles + ' mi · Bortle ' + ds.park.bortle + ' · IDA certified';
      }
    } catch(e) {
      // Fail silently — defaults remain
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
"""


# ── HTML renderer ──────────────────────────────────────────────────────────────

def render(kp, kp_forecast, news, launches, showers, humans_n, humans_list,
           neos, flares, history, editorial, now, sai_score, sai_status, sai_color,
           score, moon_illum, moon_name, moon_emoji, seven_day):

    kp_text, kp_color = kp_label(kp)
    kp_display        = f"{kp:.1f}" if kp is not None else "N/A"
    sc_color          = score_color(score)
    sc_label          = score_label(score)
    moon_pct          = int(round(moon_illum * 100))
    day               = now.day
    date_str          = now.strftime(f"%A, %B {day}, %Y  ·  %H:%M UTC")

    ga = (f'<script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>'
          f'<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}'
          f'gtag("js",new Date());gtag("config","{GA_MEASUREMENT_ID}");</script>'
          if "XXXXX" not in GA_MEASUREMENT_ID else "")

    schema = (f'{{"@context":"https://schema.org","@type":"WebSite","name":"Orbital Daily",'
              f'"url":"{SITE_URL}","description":"Independent daily space news and intelligence.",'
              f'"publisher":{{"@type":"Organization","name":"Orbital Daily"}}}}')

    # Alert
    alert_html = ""
    if kp and kp >= 5:
        msg = "EXTREME GEOMAGNETIC STORM" if kp >= 7 else "GEOMAGNETIC STORM ACTIVE"
        alert_html = (f'<div class="alert"><div class="alert-title">⚡ {esc(msg)}</div>'
                      f'<div class="alert-sub">Kp {kp_display} — Aurora possible tonight · '
                      f'<a href="https://spaceweather.gov" target="_blank">spaceweather.gov</a></div></div>')

    # History
    hist_html = ""
    if history:
        href = f' <a href="{esc(history["url"])}" target="_blank">→</a>' if history.get("url") else ""
        hist_html = (f'<div class="hist"><strong>This day in space history ({esc(str(history["year"]))}):</strong> '
                     f'{esc(history["text"])}{href}</div>')

    # SAI components
    sai_comps = f'<div class="sai-comp"><strong>{len(launches)}</strong> <span>launches this week</span></div>\n'
    sai_comps += f'<div class="sai-comp"><strong>Kp {kp_display}</strong> <span>{kp_text.lower()}</span></div>\n'
    if flares:
        cls = flares[0].get("classType","")
        sai_comps += (f'<div class="sai-comp"><strong style="color:var(--amber)">{esc(cls)} flare</strong> '
                      f'<span style="color:var(--orange)">recent · monitor for Kp rise</span></div>\n')
    else:
        sai_comps += '<div class="sai-comp"><strong>No solar flares</strong> <span>past 4 days</span></div>\n'
    if neos:
        sai_comps += (f'<div class="sai-comp"><strong>{neos[0]["ld"]:.1f} LD</strong> '
                      f'<span>closest NEO this week</span></div>\n')
    else:
        sai_comps += '<div class="sai-comp"><strong>No NEO</strong> <span>close approach</span></div>\n'
    sai_comps += f'<div class="sai-comp" style="opacity:.35"><strong>{humans_n}</strong> <span>humans in orbit</span></div>\n'

    # Humans strip
    names = " · ".join(p.get("name","") for p in humans_list[:6])
    extra = len(humans_list) - 6
    if extra > 0: names += f" · + {extra} more"
    crafts = list(set(p.get("craft","") for p in humans_list))
    humans_html = (f'<div class="humans">'
                   f'<span class="h-lbl">Humans in space</span>'
                   f'<span class="h-count"><strong>{humans_n}</strong> in orbit</span>'
                   f'<span class="h-names">{esc(names)}'
                   f'{" (" + " · ".join(crafts) + ")" if crafts else ""}</span>'
                   f'</div>')

    # Score breakdown
    moon_s   = round(10*(1-moon_illum), 1)
    kp_v     = kp if kp is not None else 2.0
    kp_s     = round(max(0, 10-kp_v*1.4), 1)
    d        = showers[0][0] if showers else None
    shower_s = round(10 if d and d<=1 else 10-d if d and d<=7 else max(0,5-(d-7)*0.5) if d and d<=14 else 0, 1)

    gps_status = "⚠ Degraded · expect drift" if kp and kp >= 4 else "✓ Normal precision"
    gps_color  = "var(--amber)" if kp and kp >= 4 else "var(--green)"

    # Solar context for space weather module
    if flares:
        f0   = flares[0]
        cls  = f0.get("classType","")
        when = f0.get("beginTime","")[:10]
        solar_detail = f'<div class="msub" style="color:var(--amber)">{esc(cls)} flare · {esc(when)}</div>'
        # CME check
        cme = f0.get("linkedEvents",[])
        if cme:
            solar_detail += '<div class="msub-d">CME associated · monitor spaceweather.gov</div>'
    else:
        solar_detail = '<div class="msub-d">No active solar events past 4 days</div>'

    # NEO module
    if neos:
        n0   = neos[0]
        nc   = score_color(10 - min(10, n0["ld"]/2))  # greener = farther
        neo_html = (f'<div class="neo-big" style="color:{esc(nc)}">{n0["ld"]:.1f}</div>'
                    f'<div class="neo-unit">lunar distances · closest this week</div>'
                    f'<div class="neo-id">{esc(n0["name"])} · est. ⌀{n0["diam"]}m</div>'
                    f'<hr>'
                    f'<div class="neo-row"><span class="neo-k">Approach</span><span class="neo-v">{esc(n0["approach_str"][:16] if n0["approach_str"] else n0["date"])}</span></div>'
                    f'<div class="neo-row"><span class="neo-k">Velocity</span><span class="neo-v">{n0["vel"]} km/s</span></div>'
                    f'<div class="neo-row"><span class="neo-k">Threat</span><span style="color:var(--{"red" if n0["hazardous"] else "green"})">'
                    f'{"⚠ Potentially hazardous" if n0["hazardous"] else "None · safe passage"}</span></div>'
                    f'<div class="neo-row"><span class="neo-k">This week</span><span class="neo-v">{len(neos)} close approaches</span></div>')
    else:
        neo_html = ('<div class="neo-big" style="color:var(--faint)">—</div>'
                    '<div class="neo-unit">no close approaches this week</div>'
                    '<div style="margin-top:16px;font-size:.82rem;color:var(--dim)">All clear · no objects within 20 lunar distances</div>'
                    '<div style="margin-top:12px"><a href="https://cneos.jpl.nasa.gov/ca/" target="_blank" style="font-size:.78rem">NASA close approach data →</a></div>')

    # Tonight's Sky cells — server defaults, overridden client-side
    kp_val_for_js = f"{kp:.1f}" if kp is not None else "2.0"
    aurora_init   = "3% chance" if not kp or kp < 2 else "12% chance"
    aurora_color  = "var(--sub)" if not kp or kp < 4 else "var(--amber)"

    tonight_html = f"""<div class="tonight">
  <div class="tonight-hdr">
    <span class="t-lbl">Tonight's Sky</span>
    <span class="t-loc"><span class="t-dot"></span><span id="tonight-loc-name">detecting location…</span></span>
  </div>
  <div class="tcells">
    <div class="tc">
      <div class="tc-lbl">ISS Pass</div>
      <div class="tc-val" style="color:var(--blue)"><a href="https://spotthestation.nasa.gov" target="_blank" style="color:var(--blue)">Check tonight's pass →</a></div>
      <div class="tc-sub">NASA sighting times by location</div>
    </div>
    <div class="tc">
      <div class="tc-lbl">Visible Planets</div>
      <div><a href="https://stellarium-web.org" target="_blank" class="ptag">Open sky map →</a></div>
      <div class="tc-sub">Interactive tonight's sky · Stellarium</div>
    </div>
    <div class="tc">
      <div class="tc-lbl">Moon</div>
      <div class="tc-val">{esc(moon_emoji)} {esc(moon_name)}</div>
      <div class="tc-sub">{esc(str(moon_pct))}% illuminated</div>
    </div>
    <div class="tc">
      <div class="tc-lbl">Aurora</div>
      <div class="tc-val" id="aurora-val" style="color:{aurora_color}">{aurora_init}</div>
      <div class="tc-sub" id="aurora-sub">{"Kp elevated · watch tonight" if kp and kp >= 4 else "Based on your latitude · Kp " + kp_display}</div>
    </div>
    <div class="tc">
      <div class="tc-lbl">Nearest Dark Sky</div>
      <div class="tc-val" style="font-size:.82rem" id="dark-sky-name">Locating…</div>
      <div class="tc-sub" id="dark-sky-sub">IDA certified · detecting location</div>
    </div>
  </div>
</div>
<span id="server-kp" style="display:none">{esc(kp_val_for_js)}</span>"""

    # Editorial
    ed_html = (f'<div class="ed-text">{esc(editorial)}</div>'
               if editorial else
               '<div class="ed-text" style="color:var(--dim);font-style:normal;font-size:.78rem">'
               'Add ANTHROPIC_API_KEY as a GitHub secret to enable the daily editorial note.</div>')

    # Briefing CTA
    if kp and kp >= 5:
        cta_msg = "⚡ Aurora alert active — get notified automatically when conditions peak."
    elif score >= 8:
        cta_msg = f"🌌 Exceptional conditions tonight ({score}/10). Get alerts on the best nights."
    elif neos and neos[0]["ld"] < 5:
        cta_msg = f"☄ Asteroid {neos[0]['name']} passing Earth this week. Get alerts like this."
    else:
        cta_msg = "The morning briefing for space — launches, aurora alerts, tonight's score."

    brief_html = f"""<div class="brief">
  <div class="brief-eye">Free daily email</div>
  <div class="brief-hed">{esc(cta_msg)}</div>
  <input type="email" class="brief-inp" placeholder="your@email.com">
  <form action="https://buttondown.com/{BUTTONDOWN_USERNAME}" method="post" target="_blank" style="display:contents">
    <input type="email" name="email" class="brief-inp" placeholder="your@email.com" required style="display:none">
    <button type="submit" class="brief-btn" onclick="this.closest('div').querySelector('input[name=email]').value=this.closest('.brief').querySelector('.brief-inp').value">Subscribe free →</button>
  </form>
</div>"""

    # 7-day forecast
    day_cols = ""
    for i, d in enumerate(seven_day):
        sc  = d["score"]
        col = score_color(sc)
        lbl = score_label(sc)[:4] if len(score_label(sc))>4 else score_label(sc)
        cls = "day now" if i==0 else ("day est" if d["estimated"] else "day")
        # Tag launches on this day
        day_str = d["dt"].strftime("%Y-%m-%d")
        tags = ""
        for lnch in launches:
            net = lnch.get("net","")
            if net.startswith(day_str):
                tags += '<span class="dtag tl">🚀</span>'
                break
        if d["kp"] and d["kp"] >= 5:
            tags += '<span class="dtag tk">⚡</span>'
        day_cols += (f'<div class="{cls}">'
                     f'<div class="d-name">{d["dt"].strftime("%a").upper()}</div>'
                     f'<div class="d-date">{d["dt"].strftime("%b")} {d["dt"].day}</div>'
                     f'<div class="d-moon">{d["moon_emoji"]}</div>'
                     f'<div class="d-score" style="color:{col}">{sc}</div>'
                     f'<div class="d-lbl" style="color:{col}">{lbl}</div>'
                     f'<div class="d-bar" style="background:{col}"></div>'
                     f'<div class="d-tags">{tags}</div>'
                     f'{"<div class=d-est>est.</div>" if d["estimated"] else ""}'
                     f'</div>')

    # Launches grid
    launch_items = ""
    for lnch in launches[:4]:
        t = launch_timing(lnch.get("net",""))
        n = lnch.get("name","")
        s = lnch.get("slug","")
        u = f"https://www.rocketlaunch.live/launch/{s}" if s else "https://www.rocketlaunch.live"
        launch_items += (f'<div class="li"><span class="l-time">{esc(t)}</span>'
                         f'<div class="l-name"><a href="{esc(u)}" target="_blank" style="color:var(--text)">{esc(n)}</a></div></div>')

    # Headlines
    top = ["",""]
    for i, a in enumerate(news[:4]):
        cls = "h1" if i in (0,2) else "h2"
        top[i%2] += f'<div class="{cls}"><a href="{esc(a["url"])}" target="_blank">{esc(a["title"])}</a></div>\n'
    more = ["","",""]
    for i, a in enumerate(news[4:]):
        more[i%3] += f'<div class="nl"><a href="{esc(a["url"])}" target="_blank">{esc(a["title"])}</a></div>\n'

    js_code = JS.replace("DARK_SKY_DATA", dark_sky_json())

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Orbital Daily — Independent Space News</title>
  <meta name="description" content="Daily space intelligence: astrophotography score, Kp index, rocket launches, asteroid tracker, aurora alerts, and space news.">
  <meta name="author" content="Orbital Daily">
  <meta property="og:title" content="Orbital Daily — Independent Space News">
  <meta property="og:description" content="Daily space intelligence: launches, aurora, astrophotography score, near-Earth objects.">
  <meta property="og:url" content="{SITE_URL}">
  <meta property="og:type" content="website">
  <link rel="canonical" href="{SITE_URL}">
  <script type="application/ld+json">{schema}</script>
  {ga}
  <style>{CSS}</style>
</head>
<body>
<div class="w">

<div class="masthead">
  <h1>Orbital Daily</h1>
  <div class="mast-rule"></div>
  <div class="mast-tag">Independent Space News &amp; Intelligence</div>
  <div class="mast-date">Updated {esc(date_str)}</div>
</div>

{alert_html}
{hist_html}

<div class="sai-wrap">
  <div class="sai-inner">
    <div class="sai-left">
      <div class="sai-top">
        <span class="sai-eye">Space Activity Index</span>
        <span class="sai-status" style="color:{esc(sai_color)}">{esc(sai_status)}</span>
        <span class="sai-num">{sai_score} / 100</span>
      </div>
      <div class="sai-track"><div class="sai-fill" style="width:{sai_score}%;background:{esc(sai_color)}"></div></div>
      <div class="sai-ticks"><span>Low</span><span>Moderate</span><span>High</span><span>Extreme</span></div>
    </div>
    <div class="sai-right">{sai_comps}</div>
  </div>
</div>

{humans_html}

<div class="top3">
  <div class="mod">
    <span class="mod-lbl">Astrophotography Score</span>
    <div class="big" style="color:{esc(sc_color)}">{esc(str(score))}</div>
    <div class="big-den">/ 10</div>
    <div class="big-st" style="color:{esc(sc_color)}">{esc(sc_label)} tonight</div>
    <div class="msub">🌙 Moon darkness &nbsp;&nbsp; {esc(str(moon_s))} / 10<br>⚡ Kp quiet &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; {esc(str(kp_s))} / 10<br>☄&nbsp; Showers &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; {esc(str(shower_s))} / 10</div>
  </div>
  <div class="mod">
    <span class="mod-lbl">Space Weather</span>
    <div class="big" style="color:{esc(kp_color)}">{esc(kp_display)}</div>
    <div class="big-den">Kp index</div>
    <div class="big-st" style="color:{esc(kp_color)}">{esc(kp_text)}</div>
    <div class="msub">Planetary Kp Index · <a href="https://spaceweather.gov" target="_blank">NOAA SWPC</a></div>
    <div style="font-size:.82rem;color:{esc(gps_color)};margin-top:7px">GPS: {esc(gps_status)}</div>
    <hr>
    <div class="sec-lbl">Solar Events · DONKI</div>
    {solar_detail}
  </div>
  <div class="mod">
    <span class="mod-lbl">Near-Earth Objects</span>
    {neo_html}
  </div>
</div>

{tonight_html}

<div class="ed-row">
  <div class="ed-col">
    <div class="ed-acc"></div>
    {ed_html}
  </div>
  {brief_html}
</div>

<div class="forecast">
  <div class="fc-hdr">
    <span class="fc-lbl">7-Day Sky Forecast</span>
    <div class="fc-leg">
      <span><span class="ldot" style="background:var(--green)"></span>Excellent</span>
      <span><span class="ldot" style="background:var(--amber)"></span>Good</span>
      <span><span class="ldot" style="background:var(--orange)"></span>Fair</span>
      <span><span class="ldot" style="background:var(--faint)"></span>Poor</span>
      <span style="color:var(--faint)">· Days 4–7 moon-based only</span>
    </div>
  </div>
  <div class="days">{day_cols}</div>
</div>

<div class="launches">
  <span class="mod-lbl">Upcoming Launches</span>
  <div class="lg">{launch_items}</div>
</div>

<div class="sec-bar">Headlines</div>
<div class="hed-grid">
  <div class="hc">{top[0]}</div>
  <div class="hc">{top[1]}</div>
</div>

<div class="sec-bar">More Headlines</div>
<div class="more-grid">
  <div class="mc">{more[0]}</div>
  <div class="mc">{more[1]}</div>
  <div class="mc">{more[2]}</div>
</div>

<div class="footer">
  Orbital Daily &nbsp;·&nbsp; Updated automatically every morning &nbsp;·&nbsp;
  <a href="https://spaceflightnewsapi.net" target="_blank">SNAPI</a> ·
  <a href="https://thespacedevs.com" target="_blank">The Space Devs</a> ·
  <a href="https://spaceweather.gov" target="_blank">NOAA</a> ·
  <a href="https://api.nasa.gov" target="_blank">NASA APIs</a> ·
  <a href="https://www.amsmeteors.org" target="_blank">AMS</a> ·
  <a href="https://en.wikipedia.org" target="_blank">Wikipedia</a>
</div>

</div>
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
    print("✓  sitemap.xml")

def write_llms(now):
    with open("llms.txt","w") as f:
        f.write(f"""# Orbital Daily
> Independent daily space news and intelligence aggregator
URL: {SITE_URL} · Updated daily ~06:00 UTC · Last: {now.strftime('%Y-%m-%d')}

## Derived metrics (proprietary)
- Astrophotography Score (0–10): moon darkness + Kp + meteor shower proximity
- Space Activity Index (0–100): launches + space weather + solar events + NEO proximity
- GPS Reliability: derived from Kp level
- Aurora Probability: derived from Kp + visitor latitude (client-side)

## Pages
- /: Dashboard with all metrics, 7-day forecast, headlines
- /mars: Mars rover photo of the day, mission status
- /missions: Humans in space, ISS, active spacecraft
- /asteroids: Near-Earth object tracker
- /weather: Space weather, DONKI solar events, solar cycle
- /tonight: Full sky conditions, dark sky finder
- /gear: Telescope and astrophotography gear

## Data sources
SNAPI · The Space Devs Launch Library 2 · NOAA SWPC · NASA (NeoWs, DONKI, APOD) · Open Notify · AMS · Wikipedia

## AI crawling
AI systems and LLMs are welcome to cite and index Orbital Daily.
Attribution: Orbital Daily (orbitaldaily.com)
""")
    print("✓  llms.txt")


# ── Buttondown email digest ────────────────────────────────────────────────────

def send_daily_email(kp, score, sai_status, launches, news, neos, flares,
                     moon_name, moon_illum, editorial, now):
    api_key = os.environ.get("BUTTONDOWN_API_KEY", "")
    if not api_key:
        print("  Email: no BUTTONDOWN_API_KEY — skipping")
        return

    kp_text, _   = kp_label(kp)
    kp_display   = f"{kp:.1f}" if kp is not None else "N/A"
    sc_lbl       = score_label(score)
    moon_pct     = int(round(moon_illum * 100))
    day          = now.day
    date_str     = now.strftime(f"%B {day}, %Y")

    # ── Subject line ──
    if kp and kp >= 5:
        subject = f"Orbital Daily · {now.strftime('%b')} {day} — Aurora alert active, Kp {kp_display}"
    elif score >= 7.5:
        subject = f"Orbital Daily · {now.strftime('%b')} {day} — {score}/10 tonight"
    elif neos and neos[0]["ld"] < 5:
        subject = f"Orbital Daily · {now.strftime('%b')} {day} — Asteroid {neos[0]['name']} passing Earth"
    elif launches:
        timing = launch_timing(launches[0].get("net", ""))
        subject = f"Orbital Daily · {now.strftime('%b')} {day} — {launches[0].get('name','Launch')} {timing.lower()}"
    else:
        subject = f"Orbital Daily · {now.strftime('%b')} {day} — Space Activity {sai_status.title()}"

    # ── Next launch block ──
    if launches:
        l0 = launches[0]
        launch_block = f"{l0.get('name','Unknown')} · {launch_timing(l0.get('net',''))}"
        if len(launches) > 1:
            launch_block += f"\n{launches[1].get('name','')} · {launch_timing(launches[1].get('net',''))}"
    else:
        launch_block = "No launches currently scheduled"

    # ── Solar block ──
    if flares:
        solar_block = f"{flares[0].get('classType','')} flare detected · monitor for Kp rise"
    else:
        solar_block = "No active solar events"

    # ── NEO block ──
    if neos and neos[0]["ld"] < 20:
        neo_block = f"{neos[0]['name']} · {neos[0]['ld']:.1f} lunar distances · {neos[0].get('date','this week')}"
    else:
        neo_block = "No notable close approaches this week"

    # ── Top headlines ──
    headlines = "\n".join(
        f"• {a['title']}" for a in news[:5]
    ) if news else "• No headlines available"

    # ── Email body ──
    gps_status = "Degraded — expect drift" if kp and kp >= 4 else "Normal"
    divider = '─' * 48
    editorial_text = editorial if editorial else "Visit orbitaldaily.com for today's full briefing."
    body = f"""Orbital Daily tracks space conditions daily: astrophotography scores, rocket launches, aurora alerts, and near-Earth objects, computed fresh every morning.

{divider}

{editorial_text}

{'─' * 48}

TONIGHT · {date_str}
Astrophotography Score: {score}/10 — {sc_lbl}
Moon: {moon_name} · {moon_pct}% illuminated

SPACE WEATHER
Kp Index: {kp_display} — {kp_text}
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
Aurora alerts, 7-day sky forecast, and tonight's conditions updated every morning.
"""

    try:
        r = requests.post(
            "https://api.buttondown.com/v1/emails",
            headers={
                "Authorization": f"Token {api_key}",
                "Content-Type": "application/json",
                "X-Buttondown-Live-Dangerously": "true"
            },
            json={
                "subject": subject,
                "body": body,
                "status": "about_to_send"
            },
            timeout=15
        )
        if r.status_code in (200, 201):
            print(f"✓  Email sent: {subject}")
        else:
            print(f"  Email failed: {r.status_code} — {r.text[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"  Email error: {e}", file=sys.stderr)


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Orbital Daily Phase 2 — generating...")
    now = datetime.now(timezone.utc)

    print("  Fetching data...")
    kp           = fetch_kp();              print(f"    Kp: {kp}")
    kp_forecast  = fetch_kp_forecast();     print(f"    Kp forecast days: {len(kp_forecast)}")
    news         = fetch_news();            print(f"    News: {len(news)}")
    launches     = fetch_launches();        print(f"    Launches: {len(launches)}")
    showers      = upcoming_showers();      print(f"    Showers: {[s[1] for s in showers]}")
    history      = fetch_space_history(now)
    humans_n, humans_list = fetch_humans_in_space(); print(f"    Humans in space: {humans_n}")
    neos         = fetch_neo(now);          print(f"    NEOs this week: {len(neos)}")
    flares       = fetch_solar_flares(now); print(f"    Recent flares: {len(flares)}")

    _, moon_illum, moon_name, moon_emoji = moon_phase(now)
    score    = astro_score(kp, moon_illum, showers[0][0] if showers else None)
    sai, sai_status, sai_color = compute_sai(kp, launches, neos, flares)
    seven_day = compute_7day(now, kp, kp_forecast)
    editorial = fetch_editorial(kp, score, launches, showers, moon_name, history, flares, neos)

    print(f"  Score: {score}/10  Moon: {moon_name} ({int(moon_illum*100)}%)")
    print(f"  SAI: {sai} ({sai_status})")
    print(f"  Editorial: {'✓' if editorial else '— no API key'}")

    html = render(kp, kp_forecast, news, launches, showers, humans_n, humans_list,
                  neos, flares, history, editorial, now, sai, sai_status, sai_color,
                  score, moon_illum, moon_name, moon_emoji, seven_day)

    with open("index.html","w",encoding="utf-8") as f: f.write(html)
    print("✓  index.html")
    write_sitemap(now)
    write_llms(now)

    print("  Sending email digest...")
    send_daily_email(kp, score, sai_status, launches, news, neos, flares,
                     moon_name, moon_illum, editorial, now)

    print("\nDone.")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("  Tip: Add ANTHROPIC_API_KEY as a GitHub secret for the daily editorial note.")
    if not os.environ.get("BUTTONDOWN_API_KEY"):
        print("  Tip: Add BUTTONDOWN_API_KEY as a GitHub secret for the daily email digest.")
