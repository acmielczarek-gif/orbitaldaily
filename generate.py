#!/usr/bin/env python3
"""
Orbital Daily — Phase 1c
Full metric modules, 2x2 grid, no horizontal scroll.
Outputs: index.html, sitemap.xml, llms.txt
"""

import math, os, sys, requests
from datetime import datetime, timedelta, timezone
from html import escape

GA_MEASUREMENT_ID   = "G-WKN4NLN7XC"
BUTTONDOWN_USERNAME = "orbitaldaily"
SITE_URL            = "https://orbitaldaily.com"
UA = {"User-Agent": "OrbitalDaily/1.0 (orbitaldaily.com)"}

# ── HTTP ───────────────────────────────────────────────────────────────────────

def get(url):
    try:
        r = requests.get(url, headers=UA, timeout=12)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"  ⚠  {url}: {e}", file=sys.stderr)
        return None

# ── Moon ───────────────────────────────────────────────────────────────────────

def moon_phase(date):
    known_new = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
    pos   = ((date - known_new).total_seconds() / 86400 % 29.53058770576) / 29.53058770576
    illum = (1 - math.cos(2 * math.pi * pos)) / 2
    names = ["New Moon","Waxing Crescent","First Quarter","Waxing Gibbous",
             "Full Moon","Waning Gibbous","Last Quarter","Waning Crescent"]
    thresholds = [0.0625, 0.1875, 0.3125, 0.4375, 0.5625, 0.6875, 0.8125, 0.9375]
    name = names[0]
    for i, t in enumerate(thresholds):
        if pos < t:
            name = names[i]
            break
    return pos, illum, name

# ── Astrophotography score ─────────────────────────────────────────────────────

def astro_score(kp, moon_illum, days_to_shower):
    moon_s   = 10.0 * (1.0 - moon_illum)
    kp_s     = max(0.0, 10.0 - (kp if kp else 2.0) * 1.4)
    d        = days_to_shower
    shower_s = (10 if d is not None and d <= 1
                else 10 - d if d and d <= 7
                else max(0, 5 - (d - 7) * 0.5) if d and d <= 14
                else 0)
    return round(min(10.0, max(0.0, moon_s * .55 + kp_s * .25 + shower_s * .20)), 1)

def score_label(s):
    if s >= 8.5: return "Exceptional", "#1a6b3c"
    if s >= 7.0: return "Excellent",   "#2a8a4c"
    if s >= 5.5: return "Good",        "#4a9a3c"
    if s >= 4.0: return "Fair",        "#c87800"
    if s >= 2.5: return "Poor",        "#b84000"
    return              "Unfavorable", "#941c00"

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

def kp_label(kp):
    if kp is None:  return "UNKNOWN",       "#999"
    if kp >= 7:     return "EXTREME STORM", "#c0120c"
    if kp >= 5:     return "GEOMAG STORM",  "#d44000"
    if kp >= 4:     return "ACTIVE",        "#c87800"
    if kp >= 2:     return "UNSETTLED",     "#6a8a30"
    return                  "QUIET",        "#1a6b3c"

def fetch_news():
    r = get("https://api.spaceflightnewsapi.net/v4/articles/?limit=18&ordering=-published_at")
    return r.json().get("results", []) if r else []

def fetch_launches():
    r = get("https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit=6&format=json")
    return r.json().get("results", []) if r else []

def fetch_space_history(date):
    r = get(f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{date.month}/{date.day}")
    if not r: return None
    kw = ["space","nasa","astronaut","rocket","satellite","moon","mars","apollo",
          "shuttle","iss","orbit","launch","cosmonaut","sputnik","hubble","spacex"]
    for ev in r.json().get("events", []):
        if any(k in ev.get("text","").lower() for k in kw):
            pages = ev.get("pages", [])
            url   = pages[0].get("content_urls",{}).get("desktop",{}).get("page","") if pages else ""
            return {"year": ev.get("year",""), "text": ev.get("text",""), "url": url}
    return None

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

def launch_timing(net):
    try:
        dt   = datetime.fromisoformat(net.replace("Z","+00:00"))
        diff = dt - datetime.now(timezone.utc)
        d    = diff.days
        if d < 0:  return "LAUNCHED"
        if d == 0: return f"T−{diff.seconds//3600}H"
        if d == 1: return "TOMORROW"
        return f"{dt.strftime('%b')} {dt.day}"
    except: return "TBD"

# ── Claude editorial note ──────────────────────────────────────────────────────

def fetch_editorial(kp, score, launches, showers, moon_name, history):
    api_key = os.environ.get("ANTHROPIC_API_KEY","")
    if not api_key: return None
    ctx = []
    if kp is not None: ctx.append(f"Kp: {kp:.1f} ({'quiet' if kp<2 else 'active' if kp<5 else 'stormy'})")
    ctx.append(f"Astrophotography score: {score}/10")
    if launches: ctx.append(f"Next launch: {launches[0].get('name','')} ({launch_timing(launches[0].get('net',''))})")
    if showers:  ctx.append(f"Next shower: {showers[0][1]} in {showers[0][0]} days")
    ctx.append(f"Moon: {moon_name}")
    if history:  ctx.append(f"Today in history ({history['year']}): {history['text'][:120]}")
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model":"claude-haiku-4-5-20251001","max_tokens":120,
                  "messages":[{"role":"user","content":
                    f"Today's space data:\n{chr(10).join(ctx)}\n\n"
                    "Write exactly 2 sentences about what makes today notable from a space perspective. "
                    "Specific and factual. No 'Today is a great day' openings. Informed reader voice."}]},
            timeout=15
        )
        if r.status_code == 200:
            for block in r.json().get("content",[]):
                if block.get("type") == "text": return block["text"].strip()
    except Exception as e:
        print(f"  Editorial: {e}", file=sys.stderr)
    return None

# ── HTML ───────────────────────────────────────────────────────────────────────

def esc(s): return escape(str(s))

CSS = """
:root {
  --bg:     #f5f4ef;
  --bg2:    #edecea;
  --bg3:    #e4e2dc;
  --border: #ccc9c0;
  --text:   #191817;
  --dim:    #6e6a62;
  --red:    #bf3a1c;
  --orange: #c85800;
  --navy:   #1c3461;
  --green:  #1a6b3c;
  --mono:   'Courier New', Courier, monospace;
  --serif:  Georgia, 'Times New Roman', serif;
  --sans:   system-ui, -apple-system, sans-serif;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); font-family: var(--sans); font-size: 15px; line-height: 1.6; }
a { color: var(--navy); text-decoration: none; }
a:hover { text-decoration: underline; }
hr { border: none; border-top: 1px solid var(--border); margin: 10px 0; }
.wrapper { max-width: 1000px; margin: 0 auto; padding: 0 14px; }

/* Masthead */
.masthead { text-align: center; padding: 22px 16px 14px; border-bottom: 2px solid var(--text); }
.masthead h1 { font-family: var(--serif); font-size: clamp(2rem,6vw,3.6rem); font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.masthead-rule { width: 60px; border-top: 1px solid var(--dim); margin: 8px auto; }
.tagline { font-family: var(--mono); font-size: .68rem; color: var(--dim); letter-spacing: .2em; text-transform: uppercase; }
.dateline { font-family: var(--mono); font-size: .66rem; color: var(--dim); margin-top: 5px; }

/* Alert */
.alert-banner { background: #fff0ed; border-top: 3px solid var(--red); border-bottom: 1px solid #e8b8ae; padding: 10px 20px; text-align: center; }
.alert-title { color: var(--red); font-family: var(--mono); font-size: .78rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
.alert-sub { color: #7a3020; font-size: .8rem; }
.alert-sub a { color: var(--red); }

/* History bar */
.history-bar { background: var(--bg2); border-bottom: 1px solid var(--border); padding: 8px 16px; font-size: .8rem; color: var(--dim); text-align: center; }
.history-bar strong { color: var(--text); }

/* ── METRIC MODULES — 2×2 grid ── */
.metrics-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  border-bottom: 1px solid var(--border);
}
@media(max-width: 600px) { .metrics-grid { grid-template-columns: 1fr; } }

.module {
  padding: 22px 20px;
  border-right: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
}
.module:nth-child(2n) { border-right: none; }
.module:nth-last-child(-n+2) { border-bottom: none; }
@media(max-width:600px) {
  .module { border-right: none !important; border-bottom: 1px solid var(--border) !important; }
  .module:last-child { border-bottom: none !important; }
}

.module-label {
  font-family: var(--mono); font-size: .6rem; letter-spacing: .22em;
  text-transform: uppercase; color: var(--dim);
  margin-bottom: 12px; display: block;
}

/* Astrophotography module */
.score-display { display: flex; align-items: baseline; gap: 6px; margin-bottom: 4px; }
.score-big { font-family: var(--serif); font-size: 4rem; font-weight: 700; line-height: 1; }
.score-denom { font-size: 1.1rem; color: var(--dim); }
.score-status { font-family: var(--mono); font-size: .7rem; letter-spacing: .14em; text-transform: uppercase; margin-bottom: 8px; }
.score-breakdown { font-size: .78rem; color: var(--dim); }
.score-breakdown span { display: inline-block; margin-right: 12px; }

/* Space weather module */
.kp-display { display: flex; align-items: baseline; gap: 8px; margin-bottom: 4px; }
.kp-big { font-family: var(--serif); font-size: 4rem; font-weight: 700; line-height: 1; }
.kp-status { font-family: var(--mono); font-size: .7rem; letter-spacing: .14em; text-transform: uppercase; margin-bottom: 8px; }
.kp-sub { font-size: .78rem; color: var(--dim); margin-bottom: 6px; }

/* Launches module */
.launch-list { display: grid; gap: 10px; }
.launch-row { display: grid; grid-template-columns: 80px 1fr; gap: 6px; align-items: start; }
.launch-timing { font-family: var(--mono); font-size: .62rem; color: var(--orange); text-transform: uppercase; letter-spacing: .08em; padding-top: 2px; }
.launch-name { font-size: .88rem; font-weight: 600; line-height: 1.3; }
.launch-name a { color: var(--text); }
.launch-name a:hover { color: var(--navy); }

/* Sky conditions module */
.sky-items { display: grid; gap: 10px; }
.sky-row { display: grid; grid-template-columns: 110px 1fr; gap: 6px; align-items: start; padding: 8px 0; border-bottom: 1px solid var(--border); }
.sky-row:last-child { border-bottom: none; padding-bottom: 0; }
.sky-key { font-family: var(--mono); font-size: .6rem; letter-spacing: .12em; text-transform: uppercase; color: var(--dim); padding-top: 2px; }
.sky-val { font-size: .88rem; font-weight: 600; }
.sky-sub { font-size: .75rem; color: var(--dim); }

/* Editorial */
.editorial-bar {
  padding: 16px 20px; border-bottom: 1px solid var(--border);
  display: grid; grid-template-columns: 3px 1fr; gap: 16px; align-items: start;
}
.editorial-accent { background: var(--red); border-radius: 2px; }
.editorial-text { font-family: var(--serif); font-style: italic; font-size: .92rem; color: #3a3630; line-height: 1.6; }
.editorial-placeholder { font-family: var(--mono); font-size: .72rem; color: var(--dim); }

/* Contextual subscribe CTA */
.cta-bar {
  background: var(--navy); color: #c8d4ea;
  padding: 14px 20px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 20px; flex-wrap: wrap;
}
.cta-text { flex: 1; min-width: 200px; font-size: .88rem; }
.cta-text strong { color: #fff; }
.cta-form { display: flex; gap: 6px; flex-shrink: 0; }
.cta-form input[type=email] { padding: 7px 12px; border: none; border-radius: 2px; font-size: .82rem; width: 200px; }
.cta-form button { padding: 7px 16px; background: var(--orange); color: #fff; border: none; border-radius: 2px; font-family: var(--mono); font-size: .75rem; letter-spacing: .06em; text-transform: uppercase; cursor: pointer; white-space: nowrap; }

/* Headlines */
.section-bar { font-family: var(--mono); font-size: .6rem; letter-spacing: .2em; text-transform: uppercase; color: var(--dim); background: var(--bg2); padding: 6px 14px; border-bottom: 1px solid var(--border); }
.headlines-grid { display: grid; grid-template-columns: 1fr 1fr; }
@media(max-width:580px) { .headlines-grid { grid-template-columns: 1fr; } }
.hed-col { padding: 12px 14px; border-right: 1px solid var(--border); }
.hed-col:last-child { border-right: none; }
.hed-1 { font-family: var(--serif); font-size: 1rem; font-weight: 700; line-height: 1.25; margin-bottom: 10px; }
.hed-1 a { color: var(--text); }
.hed-1 a:hover { color: var(--red); text-decoration: none; }
.hed-2 { font-family: var(--serif); font-size: .86rem; line-height: 1.3; margin-bottom: 8px; }
.hed-2 a { color: #4a4640; }
.news-grid { display: grid; grid-template-columns: repeat(3,1fr); }
@media(max-width:580px) { .news-grid { grid-template-columns: 1fr; } }
.news-col { padding: 10px 14px; border-right: 1px solid var(--border); }
.news-col:last-child { border-right: none; }
.news-link { margin-bottom: 8px; font-size: .8rem; line-height: 1.3; }
.news-link a { color: var(--navy); }

/* Footer */
.footer { text-align: center; padding: 14px; font-family: var(--mono); font-size: .62rem; color: var(--dim); border-top: 1px solid var(--border); }
.footer a { color: var(--dim); }
"""

def render_html(kp, news, launches, showers, score, moon_illum, moon_name,
                history, editorial, now):
    kp_text, kp_color  = kp_label(kp)
    kp_display         = f"{kp:.1f}" if kp is not None else "N/A"
    score_text, sc_col = score_label(score)
    moon_pct           = int(round(moon_illum * 100))
    day                = now.day
    date_str           = now.strftime(f"%A, %B {day}, %Y  ·  %H:%M UTC")

    ga = (f'<script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>'
          f'<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}'
          f'gtag("js",new Date());gtag("config","{GA_MEASUREMENT_ID}");</script>'
          if "XXXXX" not in GA_MEASUREMENT_ID else "")

    schema = (f'{{"@context":"https://schema.org","@type":"WebSite","name":"Orbital Daily",'
              f'"url":"{SITE_URL}","description":"Independent daily space news and intelligence.",'
              f'"publisher":{{"@type":"Organization","name":"Orbital Daily"}}}}')

    # Alert banner
    alert = ""
    if kp and kp >= 5:
        msg = "EXTREME GEOMAGNETIC STORM" if kp >= 7 else "GEOMAGNETIC STORM ACTIVE"
        alert = (f'<div class="alert-banner"><div class="alert-title">⚡ {esc(msg)}</div>'
                 f'<div class="alert-sub">Kp {kp_display} — Aurora possible tonight · '
                 f'<a href="https://spaceweather.gov" target="_blank">spaceweather.gov</a></div></div>')

    # History bar
    hist_bar = ""
    if history:
        href = f' <a href="{esc(history["url"])}" target="_blank">→</a>' if history.get("url") else ""
        hist_bar = (f'<div class="history-bar"><strong>This day in space history '
                    f'({esc(str(history["year"]))}):</strong> {esc(history["text"])}{href}</div>')

    # ── MODULE 1: Astrophotography Score ──
    moon_score  = round(10 * (1 - moon_illum), 1)
    kp_val      = kp if kp is not None else 2.0
    kp_s        = round(max(0, 10 - kp_val * 1.4), 1)
    d           = showers[0][0] if showers else None
    shower_s    = round(10 if d is not None and d<=1 else 10-d if d and d<=7
                        else max(0,5-(d-7)*0.5) if d and d<=14 else 0, 1)

    mod_astro = f"""
<div class="module">
  <span class="module-label">Astrophotography Score</span>
  <div class="score-display">
    <div class="score-big" style="color:{esc(sc_col)}">{esc(str(score))}</div>
    <div class="score-denom">/ 10</div>
  </div>
  <div class="score-status" style="color:{esc(sc_col)}">{esc(score_text)} tonight</div>
  <div class="score-breakdown">
    <span>🌙 Moon darkness {esc(str(moon_score))}/10</span>
    <span>⚡ Kp quiet {esc(str(kp_s))}/10</span>
    <span>☄ Showers {esc(str(shower_s))}/10</span>
  </div>
</div>"""

    # ── MODULE 2: Space Weather ──
    mod_weather = f"""
<div class="module">
  <span class="module-label">Space Weather</span>
  <div class="kp-display">
    <div class="kp-big" style="color:{esc(kp_color)}">{esc(kp_display)}</div>
  </div>
  <div class="kp-status" style="color:{esc(kp_color)}">{esc(kp_text)}</div>
  <div class="kp-sub">Planetary Kp Index · <a href="https://spaceweather.gov" target="_blank">NOAA SWPC</a></div>
  <div class="kp-sub">GPS reliability: {"⚠ Degraded — expect drift" if kp and kp >= 4 else "✓ Normal"}</div>
  <hr style="margin:12px 0">
  <div class="kp-sub" style="font-family:var(--mono);font-size:.62rem;color:var(--dim);letter-spacing:.1em;text-transform:uppercase;margin-bottom:6px">Solar Cycle 25</div>
  <div class="kp-sub">Near solar maximum · elevated aurora frequency expected through 2025–26</div>
</div>"""

    # ── MODULE 3: Launches ──
    launch_rows = ""
    for lnch in launches[:5]:
        t    = launch_timing(lnch.get("net",""))
        name = lnch.get("name","Unknown")
        slug = lnch.get("slug","")
        url  = f"https://www.rocketlaunch.live/launch/{slug}" if slug else "https://www.rocketlaunch.live"
        launch_rows += f"""<div class="launch-row">
  <div class="launch-timing">{esc(t)}</div>
  <div class="launch-name"><a href="{esc(url)}" target="_blank">{esc(name)}</a></div>
</div>\n"""
    if not launch_rows:
        launch_rows = '<div class="kp-sub">No launches currently scheduled.</div>'

    mod_launches = f"""
<div class="module">
  <span class="module-label">Upcoming Launches</span>
  <div class="launch-list">
    {launch_rows}
  </div>
  <hr style="margin:12px 0">
  <div style="font-family:var(--mono);font-size:.68rem"><a href="https://www.rocketlaunch.live" target="_blank" style="color:var(--dim)">Full schedule →</a></div>
</div>"""

    # ── MODULE 4: Tonight's Sky ──
    moon_emoji = {"New Moon":"🌑","Waxing Crescent":"🌒","First Quarter":"🌓","Waxing Gibbous":"🌔",
                  "Full Moon":"🌕","Waning Gibbous":"🌖","Last Quarter":"🌗","Waning Crescent":"🌘"}.get(moon_name,"🌙")

    shower_rows = ""
    for days, name, peak_str, zhr in showers:
        when = "Tonight" if days<=0 else "Tomorrow" if days==1 else f"In {days} days · {peak_str}"
        shower_rows += f"""<div class="sky-row">
  <div class="sky-key">{esc(when)}</div>
  <div><div class="sky-val"><a href="https://www.amsmeteors.org/meteor-showers/meteor-shower-calendar/" target="_blank">{esc(name)}</a></div>
  <div class="sky-sub">Peak {zhr}/hr</div></div>
</div>\n"""

    mod_sky = f"""
<div class="module">
  <span class="module-label">Tonight's Sky</span>
  <div class="sky-items">
    <div class="sky-row">
      <div class="sky-key">Moon</div>
      <div><div class="sky-val">{moon_emoji} {esc(moon_name)}</div>
      <div class="sky-sub">{esc(str(moon_pct))}% illuminated</div></div>
    </div>
    {shower_rows}
    <div class="sky-row">
      <div class="sky-key">ISS Passes</div>
      <div><div class="sky-val"><a href="https://spotthestation.nasa.gov" target="_blank">Spot the Station</a></div>
      <div class="sky-sub">NASA sighting times by location</div></div>
    </div>
    <div class="sky-row">
      <div class="sky-key">Dark Skies</div>
      <div><div class="sky-val"><a href="https://www.darksky.org/dark-sky-places-program/" target="_blank">Find a dark sky →</a></div>
      <div class="sky-sub">IDA certified locations</div></div>
    </div>
  </div>
</div>"""

    # Editorial
    if editorial:
        ed_block = f'<div class="editorial-text">{esc(editorial)}</div>'
    else:
        ed_block = '<div class="editorial-placeholder">Add ANTHROPIC_API_KEY as a GitHub secret to enable the daily editorial note.</div>'

    # Contextual CTA
    if kp and kp >= 5:
        cta_msg = "⚡ <strong>Aurora alert active.</strong> Get notified automatically when aurora is visible."
    elif score >= 8:
        cta_msg = f"🌌 <strong>Exceptional conditions tonight ({score}/10).</strong> Get alerts on great astrophotography nights."
    else:
        cta_msg = "☄ <strong>Morning briefing, free.</strong> Launches, aurora alerts, and tonight's conditions."

    cta_block = f"""<div class="cta-bar">
  <div class="cta-text">{cta_msg}</div>
  <form class="cta-form" action="https://buttondown.com/{BUTTONDOWN_USERNAME}" method="post" target="_blank">
    <input type="email" name="email" placeholder="your@email.com" required>
    <button type="submit">Subscribe Free</button>
  </form>
</div>"""

    # Headlines
    top_cols = ["",""]
    for i, a in enumerate(news[:4]):
        cls = "hed-1" if i in (0,2) else "hed-2"
        top_cols[i%2] += f'<div class="{cls}"><a href="{esc(a["url"])}" target="_blank">{esc(a["title"])}</a></div>\n'

    rest = news[4:]
    more = ["","",""]
    for i, a in enumerate(rest):
        more[i%3] += f'<div class="news-link"><a href="{esc(a["url"])}" target="_blank">{esc(a["title"])}</a></div>\n'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Orbital Daily — Independent Space News</title>
  <meta name="description" content="Daily space intelligence: rocket launches, aurora alerts, astrophotography conditions, meteor showers, and space news.">
  <meta name="author" content="Orbital Daily">
  <meta property="og:title" content="Orbital Daily">
  <meta property="og:description" content="Daily space intelligence: launches, aurora, astrophotography score.">
  <meta property="og:url" content="{SITE_URL}">
  <meta property="og:type" content="website">
  <link rel="canonical" href="{SITE_URL}">
  <script type="application/ld+json">{schema}</script>
  {ga}
  <style>{CSS}</style>
</head>
<body>
<div class="wrapper">

  <div class="masthead">
    <h1>Orbital Daily</h1>
    <div class="masthead-rule"></div>
    <div class="tagline">Independent Space News &amp; Intelligence</div>
    <div class="dateline">Updated {esc(date_str)}</div>
  </div>

  {alert}
  {hist_bar}

  <!-- ── FOUR METRIC MODULES ── -->
  <div class="metrics-grid">
    {mod_astro}
    {mod_weather}
    {mod_launches}
    {mod_sky}
  </div>

  <!-- Editorial note -->
  <div class="editorial-bar">
    <div class="editorial-accent"></div>
    {ed_block}
  </div>

  <!-- Contextual subscribe CTA -->
  {cta_block}

  <!-- Headlines -->
  <div class="section-bar">Headlines</div>
  <div class="headlines-grid">
    <div class="hed-col">{top_cols[0]}</div>
    <div class="hed-col">{top_cols[1]}</div>
  </div>

  <div class="section-bar">More Headlines</div>
  <div class="news-grid">
    <div class="news-col">{more[0]}</div>
    <div class="news-col">{more[1]}</div>
    <div class="news-col">{more[2]}</div>
  </div>

  <div class="footer">
    Orbital Daily &nbsp;·&nbsp; Updated automatically every morning &nbsp;·&nbsp;
    Sources: <a href="https://spaceflightnewsapi.net" target="_blank">SNAPI</a> ·
    <a href="https://thespacedevs.com" target="_blank">The Space Devs</a> ·
    <a href="https://spaceweather.gov" target="_blank">NOAA SWPC</a> ·
    <a href="https://www.amsmeteors.org" target="_blank">AMS</a> ·
    <a href="https://en.wikipedia.org" target="_blank">Wikipedia</a>
  </div>

</div>
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
        f.write(f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>')
    print("✓  sitemap.xml")

def write_llms(now):
    with open("llms.txt","w") as f:
        f.write(f"""# Orbital Daily
> Independent daily space news and intelligence aggregator
URL: {SITE_URL} · Updated daily ~06:00 UTC · Last: {now.strftime('%Y-%m-%d')}

## Pages
- /: Dashboard — astrophotography score, Kp, launches, tonight's sky, headlines
- /mars: Mars rover photo of the day, sol counter, mission status
- /missions: Humans in space, ISS position, active spacecraft
- /asteroids: Near-Earth object close approaches in plain English
- /weather: Space weather, aurora probability, GPS reliability, solar cycle
- /tonight: Full sky conditions, moon phase, dark sky finder by state
- /gear: Telescope and astrophotography gear recommendations

## Data sources
SNAPI · The Space Devs Launch Library 2 · NOAA SWPC · AMS · Wikipedia · NASA APIs

## AI crawling
AI systems and LLMs are welcome to index and cite this content.
Attribution: Orbital Daily (orbitaldaily.com)
""")
    print("✓  llms.txt")

# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Orbital Daily — generating...")
    now      = datetime.now(timezone.utc)
    kp       = fetch_kp();         print(f"  Kp: {kp}")
    news     = fetch_news();       print(f"  News: {len(news)}")
    launches = fetch_launches();   print(f"  Launches: {len(launches)}")
    showers  = upcoming_showers(); print(f"  Showers: {[s[1] for s in showers]}")
    history  = fetch_space_history(now)
    _, moon_illum, moon_name = moon_phase(now)
    score    = astro_score(kp, moon_illum, showers[0][0] if showers else None)
    editorial = fetch_editorial(kp, score, launches, showers, moon_name, history)
    print(f"  Score: {score}/10  Moon: {moon_name} ({int(moon_illum*100)}%)")
    print(f"  Editorial: {'✓' if editorial else '— no API key'}")

    html = render_html(kp, news, launches, showers, score, moon_illum,
                       moon_name, history, editorial, now)
    with open("index.html","w",encoding="utf-8") as f: f.write(html)
    print("✓  index.html")
    write_sitemap(now)
    write_llms(now)
    print("Done.")
