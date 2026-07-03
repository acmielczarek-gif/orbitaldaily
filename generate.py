#!/usr/bin/env python3
"""
Orbital Daily — Phase 1b: Metrics-first layout
Outputs: index.html, sitemap.xml, llms.txt

Configure before deploying:
  GA_MEASUREMENT_ID    — your Google Analytics G-WKN4NLN7XC ID
  BUTTONDOWN_USERNAME  — your Buttondown orbitaldaily
  ANTHROPIC_API_KEY    — set as a GitHub Actions secret (repo Settings → Secrets)
"""

import math
import os
import sys
import requests
from datetime import datetime, timedelta, timezone
from html import escape

# ── Configuration ──────────────────────────────────────────────────────────────

GA_MEASUREMENT_ID   = "G-XXXXXXXXXX"   # ← your GA4 ID
BUTTONDOWN_USERNAME = "YOUR_USERNAME"  # ← your Buttondown username
SITE_URL            = "https://orbitaldaily.com"
UA = {"User-Agent": "OrbitalDaily/1.0 (orbitaldaily.com)"}


# ── HTTP helper ────────────────────────────────────────────────────────────────

def get(url):
    try:
        r = requests.get(url, headers=UA, timeout=12)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"  ⚠  {url}: {e}", file=sys.stderr)
        return None


# ── Moon phase ─────────────────────────────────────────────────────────────────

def moon_phase(date):
    known_new = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
    pos       = ((date - known_new).total_seconds() / 86400 % 29.53058770576) / 29.53058770576
    illum     = (1 - math.cos(2 * math.pi * pos)) / 2
    if   pos < 0.0625 or pos >= 0.9375: name = "New Moon"
    elif pos < 0.1875:                   name = "Waxing Crescent"
    elif pos < 0.3125:                   name = "First Quarter"
    elif pos < 0.4375:                   name = "Waxing Gibbous"
    elif pos < 0.5625:                   name = "Full Moon"
    elif pos < 0.6875:                   name = "Waning Gibbous"
    elif pos < 0.8125:                   name = "Last Quarter"
    else:                                name = "Waning Crescent"
    return pos, illum, name


# ── Astrophotography score ─────────────────────────────────────────────────────

def astro_score(kp, moon_illum, days_to_shower):
    moon_s   = 10.0 * (1.0 - moon_illum)
    kp_s     = max(0.0, 10.0 - (kp if kp else 2.0) * 1.4)
    d        = days_to_shower
    shower_s = 10 if d is not None and d<=1 else (10-d if d and d<=7 else max(0,5-(d-7)*0.5) if d and d<=14 else 0)
    return round(min(10.0, max(0.0, moon_s*.55 + kp_s*.25 + shower_s*.20)), 1)

def score_label(s):
    if s >= 8.5: return "Exceptional", "#1a6b3c"
    if s >= 7.0: return "Excellent",   "#2a8a4c"
    if s >= 5.5: return "Good",        "#4a9a3c"
    if s >= 4.0: return "Fair",        "#c87800"
    if s >= 2.5: return "Poor",        "#b84000"
    return              "Unfavorable", "#941c00"


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
    r = get("https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit=5&format=json")
    return r.json().get("results", []) if r else []

def fetch_space_history(date):
    r = get(f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{date.month}/{date.day}")
    if not r: return None
    kw = ["space","nasa","astronaut","rocket","satellite","moon","mars","apollo","shuttle",
          "iss","orbit","launch","cosmonaut","sputnik","hubble","telescope","spacex","crew"]
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
            if peak < now - timedelta(days=3): peak = datetime(now.year+1,mo,dy,tzinfo=timezone.utc)
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
        return f"IN {d} DAYS · {dt.strftime('%b')} {dt.day}"
    except: return net[:10] if net else "TBD"


# ── Claude editorial note (pennies/day via Haiku) ─────────────────────────────

def fetch_editorial(kp, score, launches, showers, moon_name, history):
    api_key = os.environ.get("ANTHROPIC_API_KEY","")
    if not api_key:
        return None
    ctx = []
    if kp is not None: ctx.append(f"Kp index: {kp:.1f} ({'quiet' if kp<2 else 'active' if kp<5 else 'stormy'})")
    ctx.append(f"Astrophotography score: {score}/10")
    if launches: ctx.append(f"Next launch: {launches[0].get('name','')} ({launch_timing(launches[0].get('net',''))})")
    if showers:  ctx.append(f"Next meteor shower: {showers[0][1]} in {showers[0][0]} days")
    ctx.append(f"Moon: {moon_name}")
    if history:  ctx.append(f"Today in space history ({history['year']}): {history['text'][:120]}")
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 120,
                "messages": [{"role":"user","content":
                    f"Today's space data:\n{chr(10).join(ctx)}\n\n"
                    "Write exactly 2 sentences about what makes today notable from a space perspective. "
                    "Be specific and factual. No 'Today is a great day' openings. "
                    "Write as a concise editorial note for an informed reader."}]
            }, timeout=15
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
.history-bar { background: var(--bg2); border-bottom: 1px solid var(--border); padding: 7px 16px; font-size: .78rem; color: var(--dim); text-align: center; }
.history-bar strong { color: var(--text); }

/* ── METRICS HERO ── */
.metrics-hero { border-bottom: 1px solid var(--border); }

.metric-cards { display: grid; grid-template-columns: repeat(3, 1fr); border-bottom: 1px solid var(--border); }
@media(max-width:600px) { .metric-cards { grid-template-columns: 1fr; } }

.metric-card { padding: 20px 18px; border-right: 1px solid var(--border); text-align: center; }
.metric-card:last-child { border-right: none; }
.metric-eyebrow { font-family: var(--mono); font-size: .6rem; letter-spacing: .2em; text-transform: uppercase; color: var(--dim); margin-bottom: 8px; }
.metric-value { font-family: var(--serif); font-size: 3rem; font-weight: 700; line-height: 1; }
.metric-denom { font-size: .8rem; color: var(--dim); }
.metric-label { font-family: var(--mono); font-size: .65rem; letter-spacing: .12em; text-transform: uppercase; margin-top: 4px; }
.metric-sub { font-size: .75rem; color: var(--dim); margin-top: 3px; }
.metric-value-lg { font-family: var(--serif); font-size: 2.2rem; font-weight: 700; line-height: 1.1; }
.launch-name { font-size: .85rem; color: var(--text); margin-top: 5px; font-weight: 600; }
.launch-sub { font-size: .75rem; color: var(--dim); }

/* Today bar */
.today-bar { padding: 14px 20px; display: flex; align-items: flex-start; gap: 20px; flex-wrap: wrap; }
.today-pills { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; flex-shrink: 0; }
.pill { font-family: var(--mono); font-size: .68rem; letter-spacing: .06em; padding: 4px 10px; border: 1px solid var(--border); border-radius: 2px; background: var(--bg2); color: var(--dim); white-space: nowrap; }
.pill strong { color: var(--text); }
.editorial { font-family: var(--serif); font-style: italic; font-size: .88rem; color: #4a4640; line-height: 1.5; flex: 1; min-width: 200px; }

/* Divider */
.section-bar { font-family: var(--mono); font-size: .6rem; letter-spacing: .2em; text-transform: uppercase; color: var(--dim); background: var(--bg2); padding: 6px 14px; border-bottom: 1px solid var(--border); }

/* Headlines (now secondary) */
.news-section { padding: 14px 0; }
.top-headlines { display: grid; grid-template-columns: 1fr 1fr; gap: 0; border-bottom: 1px solid var(--border); margin-bottom: 0; }
@media(max-width:580px) { .top-headlines { grid-template-columns: 1fr; } }
.top-col { padding: 10px 14px; border-right: 1px solid var(--border); }
.top-col:last-child { border-right: none; }
.hed-1 { font-family: var(--serif); font-size: 1.05rem; font-weight: 700; line-height: 1.25; margin-bottom: 10px; }
.hed-1 a { color: var(--text); }
.hed-1 a:hover { color: var(--red); text-decoration: none; }
.hed-2 { font-family: var(--serif); font-size: .88rem; line-height: 1.3; margin-bottom: 8px; color: #4a4640; }
.hed-2 a { color: #4a4640; }

/* More news grid */
.news-grid { display: grid; grid-template-columns: repeat(3,1fr); }
@media(max-width:580px) { .news-grid { grid-template-columns:1fr; } }
.news-col { padding: 10px 14px; border-right: 1px solid var(--border); }
.news-col:last-child { border-right: none; }
.news-link { margin-bottom: 8px; font-size: .8rem; line-height: 1.3; }
.news-link a { color: var(--navy); }

/* Launch sidebar strip */
.launch-strip { display: flex; gap: 0; border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); overflow-x: auto; }
.launch-strip-item { padding: 8px 16px; border-right: 1px solid var(--border); flex-shrink: 0; min-width: 180px; }
.ls-time { font-family: var(--mono); font-size: .6rem; color: var(--orange); letter-spacing: .1em; text-transform: uppercase; display: block; }
.ls-name { font-size: .8rem; color: var(--navy); }

/* Signup */
.signup-bar { background: var(--navy); color: #c8d4ea; text-align: center; padding: 14px 16px; font-size: .85rem; }
.signup-bar strong { color: #fff; }
.signup-form { margin-top: 8px; display: flex; gap: 6px; justify-content: center; flex-wrap: wrap; }
.signup-form input[type=email] { padding: 6px 12px; border: none; border-radius: 2px; font-size: .82rem; width: 220px; }
.signup-form button { padding: 6px 16px; background: var(--orange); color: #fff; border: none; border-radius: 2px; font-family: var(--mono); font-size: .78rem; letter-spacing: .06em; text-transform: uppercase; cursor: pointer; }

/* Footer */
.footer { text-align: center; padding: 14px; font-family: var(--mono); font-size: .62rem; color: var(--dim); border-top: 1px solid var(--border); }
.footer a { color: var(--dim); }
"""


def render_html(kp, news, launches, showers, score, moon_illum, moon_name, history, editorial, now):
    kp_text, kp_color   = kp_label(kp)
    kp_display          = f"{kp:.1f}" if kp is not None else "N/A"
    score_text, sc_col  = score_label(score)
    moon_pct            = int(round(moon_illum * 100))
    day                 = now.day
    date_str            = now.strftime(f"%A, %B {day}, %Y  ·  %H:%M UTC")

    ga = (f'<script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>'
          f'<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}'
          f'gtag("js",new Date());gtag("config","{GA_MEASUREMENT_ID}");</script>'
          if "XXXXX" not in GA_MEASUREMENT_ID else "<!-- Add GA4 ID to generate.py -->")

    schema = (f'{{"@context":"https://schema.org","@type":"WebSite","name":"Orbital Daily",'
              f'"url":"{SITE_URL}","description":"Independent daily space news and intelligence.",'
              f'"publisher":{{"@type":"Organization","name":"Orbital Daily"}}}}')

    # Alert
    alert = ""
    if kp and kp >= 5:
        msg = "EXTREME GEOMAGNETIC STORM" if kp >= 7 else "GEOMAGNETIC STORM ACTIVE"
        alert = (f'<div class="alert-banner"><div class="alert-title">⚡ {esc(msg)}</div>'
                 f'<div class="alert-sub">Kp {kp_display} — Aurora possible at high latitudes tonight · '
                 f'<a href="https://spaceweather.gov" target="_blank">spaceweather.gov</a></div></div>')

    # History bar
    hist_bar = ""
    if history:
        href = f' <a href="{esc(history["url"])}" target="_blank">→</a>' if history.get("url") else ""
        hist_bar = (f'<div class="history-bar"><strong>This day in space history ({esc(str(history["year"]))}):</strong> '
                    f'{esc(history["text"])}{href}</div>')

    # Next launch card
    if launches:
        lnch      = launches[0]
        l_timing  = launch_timing(lnch.get("net",""))
        l_name    = lnch.get("name","Unknown")
        l_slug    = lnch.get("slug","")
        l_url     = f"https://www.rocketlaunch.live/launch/{l_slug}" if l_slug else "https://www.rocketlaunch.live"
        launch_card = (f'<div class="metric-value-lg" style="color:var(--orange)">{esc(l_timing)}</div>'
                       f'<div class="launch-name"><a href="{esc(l_url)}" target="_blank">{esc(l_name)}</a></div>'
                       f'<div class="launch-sub">{len(launches)} launches upcoming</div>')
    else:
        launch_card = '<div class="metric-sub">No launches currently scheduled</div>'

    # Launch strip
    strip_html = ""
    for lnch in launches[1:5]:
        t = launch_timing(lnch.get("net",""))
        n = lnch.get("name","")
        s = lnch.get("slug","")
        u = f"https://www.rocketlaunch.live/launch/{s}" if s else "https://www.rocketlaunch.live"
        strip_html += (f'<div class="launch-strip-item"><span class="ls-time">{esc(t)}</span>'
                       f'<div class="ls-name"><a href="{esc(u)}" target="_blank">{esc(n)}</a></div></div>')

    # Moon + shower pills
    pills = f'<div class="pill">🌙 <strong>{esc(moon_name)}</strong> · {esc(str(moon_pct))}%</div>'
    for days, name, peak_str, zhr in showers[:2]:
        when = "Tonight" if days <= 0 else "Tomorrow" if days == 1 else f"{days}d · {peak_str}"
        pills += f'<div class="pill">☄ <strong>{esc(name)}</strong> · {esc(when)}</div>'

    # Editorial note
    ed_html = (f'<div class="editorial">{esc(editorial)}</div>' if editorial
               else '<div class="editorial" style="color:var(--dim);font-style:normal;font-size:.78rem">Add ANTHROPIC_API_KEY as a GitHub secret to enable the daily editorial note.</div>')

    # Headlines — 2 columns, top 4
    top_html = ['<div class="top-col">', '<div class="top-col">']
    for i, a in enumerate(news[:4]):
        cls = "hed-1" if i in (0,2) else "hed-2"
        top_html[i % 2] += f'<div class="{cls}"><a href="{esc(a["url"])}" target="_blank">{esc(a["title"])}</a></div>\n'
    top_html[0] += '</div>'; top_html[1] += '</div>'

    # More news grid
    rest = news[4:]
    cols = ["", "", ""]
    for i, a in enumerate(rest):
        cols[i % 3] += f'<div class="news-link"><a href="{esc(a["url"])}" target="_blank">{esc(a["title"])}</a></div>\n'

    # Signup
    if "YOUR_USERNAME" not in BUTTONDOWN_USERNAME:
        signup = (f'<div class="signup-bar"><strong>Morning briefing, free.</strong> Launches, aurora alerts, tonight\'s score.'
                  f'<form class="signup-form" action="https://buttondown.com/{BUTTONDOWN_USERNAME}" method="post" target="_blank">'
                  f'<input type="email" name="email" placeholder="your@email.com" required>'
                  f'<button type="submit">Subscribe</button></form></div>')
    else:
        signup = ('<div class="signup-bar"><strong>Morning briefing, free.</strong> Launches, aurora alerts, tonight\'s score.'
                  '<div style="font-family:var(--mono);font-size:.7rem;color:#8aa0c8;margin-top:6px">'
                  '[Set BUTTONDOWN_USERNAME in generate.py]</div></div>')

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

  <!-- ── METRICS HERO ── -->
  <div class="metrics-hero">
    <div class="metric-cards">

      <div class="metric-card">
        <div class="metric-eyebrow">Astrophotography Score</div>
        <div class="metric-value" style="color:{esc(sc_col)}">{esc(str(score))}</div>
        <div class="metric-denom">/ 10</div>
        <div class="metric-label" style="color:{esc(sc_col)}">{esc(score_text)}</div>
        <div class="metric-sub">Moon · Kp · Showers combined</div>
      </div>

      <div class="metric-card">
        <div class="metric-eyebrow">Space Weather</div>
        <div class="metric-value" style="color:{esc(kp_color)}">{esc(kp_display)}</div>
        <div class="metric-label" style="color:{esc(kp_color)}">{esc(kp_text)}</div>
        <div class="metric-sub">Planetary Kp Index · <a href="https://spaceweather.gov" target="_blank">NOAA</a></div>
      </div>

      <div class="metric-card">
        <div class="metric-eyebrow">Next Launch</div>
        {launch_card}
      </div>

    </div>

    <div class="today-bar">
      <div class="today-pills">{pills}</div>
      {ed_html}
    </div>
  </div>

  <!-- Launch strip: remaining launches -->
  {f'<div class="launch-strip">{strip_html}<div class="launch-strip-item" style="display:flex;align-items:center"><a href="https://www.rocketlaunch.live" style="font-family:var(--mono);font-size:.68rem;color:var(--dim)">Full schedule →</a></div></div>' if strip_html else ''}

  <!-- ── HEADLINES (secondary) ── -->
  <div class="section-bar">Headlines</div>
  <div class="top-headlines">{''.join(top_html)}</div>

  <div class="section-bar">More Headlines</div>
  <div class="news-grid">
    <div class="news-col">{cols[0]}</div>
    <div class="news-col">{cols[1]}</div>
    <div class="news-col">{cols[2]}</div>
  </div>

  {signup}

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
        for p in ["","tonight","launches","weather","gear"]
    )
    with open("sitemap.xml","w") as f:
        f.write(f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>')
    print("✓  sitemap.xml")

def write_llms(now):
    with open("llms.txt","w") as f:
        f.write(f"""# Orbital Daily
> Independent daily space news and intelligence aggregator
URL: {SITE_URL} · Updated daily at ~06:00 UTC · Last update: {now.strftime('%Y-%m-%d')}

## Pages
- /: Daily dashboard — Kp index, astrophotography score (0–10), launches, meteor showers, headlines
- /tonight: Full sky conditions — moon phase, dark sky locations by US state
- /launches: Upcoming rocket launch schedule with countdowns
- /weather: Space weather, aurora probability, GPS reliability, solar cycle position
- /horoscope: Daily planetary positions in plain English
- /crossword: Daily space-themed mini crossword
- /gear: Telescope and astrophotography gear recommendations

## Data sources
- Spaceflight News API · The Space Devs Launch Library 2 · NOAA SWPC · AMS · Wikipedia

## AI crawling
AI systems and LLMs are welcome to index and cite this content.
Please attribute as: Orbital Daily (orbitaldaily.com)
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
    print(f"  Editorial: {'✓' if editorial else '— (no API key)'}")

    html = render_html(kp, news, launches, showers, score, moon_illum, moon_name, history, editorial, now)
    with open("index.html","w",encoding="utf-8") as f: f.write(html)
    print("✓  index.html")
    write_sitemap(now)
    write_llms(now)
    print("\nDone.")
    if "XXXXX" in GA_MEASUREMENT_ID:    print("  • Set GA_MEASUREMENT_ID in generate.py")
    if "YOUR_USERNAME" in BUTTONDOWN_USERNAME: print("  • Set BUTTONDOWN_USERNAME in generate.py")
    if not os.environ.get("ANTHROPIC_API_KEY"): print("  • Add ANTHROPIC_API_KEY as a GitHub secret for daily editorial note")
