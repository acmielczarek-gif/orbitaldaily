#!/usr/bin/env python3
"""
Orbital Daily — Daily space news aggregator
Pulls from free public APIs and writes index.html
Run manually: python generate.py
Run automatically: GitHub Actions (daily.yml)
"""

import requests
import json
import sys
from datetime import datetime, timedelta, timezone
from html import escape

UA = {"User-Agent": "OrbitalDaily/1.0 (orbitaldaily.com)"}


# ── Data fetchers ──────────────────────────────────────────────────────────────

def get(url):
    try:
        r = requests.get(url, headers=UA, timeout=12)
        r.raise_for_status()
        return r
    except Exception as e:
        print(f"  Warning: could not fetch {url}: {e}", file=sys.stderr)
        return None


def fetch_kp():
    """Current planetary Kp index from NOAA Space Weather Prediction Center."""
    r = get("https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json")
    if not r:
        return None
    rows = r.json()
    for row in reversed(rows):
        try:
            if isinstance(row, dict):
                kp_val = row.get("kp") or row.get("Kp") or row.get("kp_index")
            else:
                kp_val = row[1]
            val = float(kp_val)
            if val >= 0:
                return val
        except (IndexError, ValueError, TypeError, KeyError):
            continue
    return None


def kp_label(kp):
    """Human-readable Kp status and color."""
    if kp is None:      return "UNKNOWN",          "#888888"
    if kp >= 7:         return "EXTREME STORM",     "#ff1100"
    if kp >= 5:         return "GEOMAGNETIC STORM", "#ff5500"
    if kp >= 4:         return "ACTIVE",            "#ffaa00"
    if kp >= 2:         return "UNSETTLED",         "#88cc33"
    return               "QUIET",                   "#33cc88"


def fetch_news():
    """Latest space news from Spaceflight News API (free, no key)."""
    r = get("https://api.spaceflightnewsapi.net/v4/articles/?limit=20&ordering=-published_at")
    if not r:
        return []
    return r.json().get("results", [])


def fetch_launches():
    """Upcoming rocket launches from The Space Devs Launch Library 2 (free, no key)."""
    r = get("https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit=5&format=json")
    if not r:
        return []
    return r.json().get("results", [])


# Annual meteor shower calendar (peaks don't change year to year)
SHOWERS = [
    (1,  3,  "QUADRANTIDS",   120),
    (4,  22, "LYRIDS",         20),
    (5,   6, "ETA AQUARIIDS",  50),
    (8,  12, "PERSEIDS",      100),
    (10, 21, "ORIONIDS",       20),
    (11, 17, "LEONIDS",        15),
    (12, 13, "GEMINIDS",      150),
    (12, 22, "URSIDS",         10),
]


def upcoming_showers(n=3):
    """Return the next N meteor shower peaks."""
    now = datetime.now(timezone.utc)
    out = []
    for mo, dy, name, zhr in SHOWERS:
        try:
            peak = datetime(now.year, mo, dy, tzinfo=timezone.utc)
            if peak < now - timedelta(days=3):
                peak = datetime(now.year + 1, mo, dy, tzinfo=timezone.utc)
            days = (peak - now).days
            out.append((days, name, f"{peak.strftime('%b')} {peak.day}", zhr))
        except ValueError:
            continue
    out.sort()
    return out[:n]


# ── HTML helpers ───────────────────────────────────────────────────────────────

def esc(s):
    return escape(str(s))


def launch_timing(net_str):
    """Convert a NET (No Earlier Than) ISO timestamp to a human label."""
    try:
        dt = datetime.fromisoformat(net_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = dt - now
        days = diff.days
        if days < 0:
            return "LAUNCHED"
        if days == 0:
            hours = diff.seconds // 3600
            return f"T−{hours}H"
        if days == 1:
            return "TOMORROW"
        return f"IN {days} DAYS · {dt.strftime('%b')} {dt.day}"
    except Exception:
        return net_str[:10] if net_str else "TBD"


# ── HTML renderer ──────────────────────────────────────────────────────────────

def render_html(kp, news, launches, showers, now):
    kp_text, kp_color = kp_label(kp)
    kp_display = f"{kp:.1f}" if kp is not None else "N/A"

    day = now.day
    date_str = now.strftime(f"%A, %B {day}, %Y  ·  %H:%M UTC")

    # ── Aurora alert banner (only when Kp ≥ 5) ──
    aurora_banner = ""
    if kp is not None and kp >= 5:
        if kp >= 7:
            msg = "EXTREME GEOMAGNETIC STORM"
            sub = f"Kp {kp_display} — Aurora may be visible as far south as the central US tonight"
        else:
            msg = "GEOMAGNETIC STORM ACTIVE"
            sub = f"Kp {kp_display} — Aurora possible at high latitudes and some mid-latitude regions"
        aurora_banner = f"""
  <div class="alert-banner">
    <span class="alert-title">⚡ {esc(msg)}</span>
    <span class="alert-sub"> — {esc(sub)} · <a href="https://spaceweather.gov" target="_blank">spaceweather.gov</a></span>
  </div>"""

    # ── Top 3 headlines ──
    top_html = ""
    for i, a in enumerate(news[:3]):
        cls = "headline-1" if i == 0 else "headline-2"
        top_html += f'<div class="{cls}"><a href="{esc(a["url"])}" target="_blank">{esc(a["title"])}</a></div>\n'
    if not top_html:
        top_html = '<div class="headline-2">Space news temporarily unavailable.</div>'

    # ── Launch sidebar ──
    launch_html = ""
    for lnch in launches:
        name  = lnch.get("name", "Unknown Mission")
        net   = lnch.get("net", "")
        slug  = lnch.get("slug", "")
        timing = launch_timing(net)
        url = f"https://www.rocketlaunch.live/launch/{slug}" if slug else "https://www.rocketlaunch.live"
        launch_html += (
            f'<div class="event-item">'
            f'<span class="event-time">{esc(timing)}</span>'
            f'<a href="{esc(url)}" target="_blank">{esc(name)}</a>'
            f'</div>\n'
        )
    if not launch_html:
        launch_html = '<div class="event-item">No launches currently scheduled.</div>'

    # ── Meteor shower sidebar ──
    shower_html = ""
    for days, name, peak_str, zhr in showers:
        if days <= 0:
            when = f"TONIGHT · {peak_str}"
        elif days == 1:
            when = f"TOMORROW · {peak_str}"
        elif days <= 7:
            when = f"IN {days} DAYS · {peak_str}"
        else:
            when = peak_str
        shower_html += (
            f'<div class="event-item">'
            f'<span class="event-time">{esc(when)}</span>'
            f'<a href="https://www.amsmeteors.org/meteor-showers/meteor-shower-calendar/" target="_blank">{esc(name)}</a>'
            f' <span class="dim">({zhr}/hr peak)</span>'
            f'</div>\n'
        )

    # ── More news: 3 columns ──
    rest = news[3:]
    cols = ["", "", ""]
    for i, a in enumerate(rest):
        cols[i % 3] += (
            f'<div class="news-link">'
            f'<a href="{esc(a["url"])}" target="_blank">{esc(a["title"])}</a>'
            f'</div>\n'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ORBITAL DAILY — Independent Space News</title>
  <meta name="description" content="Daily space news: launches, auroras, meteor showers, and more.">
  <style>
    :root {{
      --bg:      #08090f;
      --bg2:     #0c0e17;
      --border:  #1b1f2e;
      --text:    #d0d2da;
      --dim:     #6a6f80;
      --red:     #cc2200;
      --orange:  #c85a00;
      --green:   #33cc88;
      --mono:    'Courier New', Courier, monospace;
      --serif:   Georgia, 'Times New Roman', serif;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ background: var(--bg); color: var(--text); font-family: var(--serif); font-size: 15px; line-height: 1.6; }}
    a {{ color: var(--text); text-decoration: none; }}
    a:hover {{ color: #fff; text-decoration: underline; }}
    hr {{ border: none; border-top: 1px solid var(--border); margin: 10px 0; }}

    /* Masthead */
    .masthead {{ text-align: center; padding: 20px 16px 12px; border-bottom: 2px solid var(--red); }}
    .masthead h1 {{
      font-family: var(--serif); font-size: clamp(2rem, 6vw, 3.8rem);
      font-weight: 700; letter-spacing: .1em; color: #fff; text-transform: uppercase;
    }}
    .tagline {{ font-family: var(--mono); font-size: .7rem; color: var(--dim); letter-spacing: .22em; text-transform: uppercase; margin-top: 4px; }}
    .dateline {{ font-family: var(--mono); font-size: .68rem; color: var(--dim); margin-top: 6px; }}

    /* Alert */
    .alert-banner {{
      background: #150000; border: 1px solid #7a1100; border-left: 4px solid var(--red);
      padding: 9px 16px; margin: 10px auto; max-width: 960px;
      font-family: var(--mono); font-size: .78rem;
    }}
    .alert-title {{ color: var(--red); font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }}
    .alert-sub {{ color: #aaa; }}
    .alert-sub a {{ color: #ff6644; }}

    /* Wrapper */
    .wrapper {{ max-width: 980px; margin: 0 auto; padding: 0 14px; }}

    /* Three-column top layout */
    .top-section {{
      display: grid;
      grid-template-columns: 210px 1fr 210px;
      border-bottom: 1px solid var(--border);
    }}
    @media (max-width: 680px) {{
      .top-section {{ grid-template-columns: 1fr; }}
      .sidebar {{ border-right: none !important; border-left: none !important; border-top: 1px solid var(--border); }}
    }}

    .center-col {{ padding: 18px 20px; border-left: 1px solid var(--border); border-right: 1px solid var(--border); text-align: center; }}
    .sidebar {{ padding: 14px 12px; font-size: .82rem; }}
    .sidebar-title {{
      font-family: var(--mono); font-size: .62rem; letter-spacing: .2em;
      text-transform: uppercase; color: var(--dim);
      border-bottom: 1px solid var(--border); padding-bottom: 6px; margin-bottom: 10px;
    }}

    /* Headlines */
    .headline-1 {{ font-size: clamp(1.2rem, 3.2vw, 1.9rem); font-weight: 700; line-height: 1.2; margin-bottom: 14px; }}
    .headline-1 a {{ color: #fff; }}
    .headline-1 a:hover {{ color: var(--red); text-decoration: none; }}
    .headline-2 {{ font-size: clamp(.9rem, 2.2vw, 1.08rem); line-height: 1.35; margin-bottom: 10px; color: #9ea2b0; }}
    .headline-2 a {{ color: #9ea2b0; }}
    .headline-2 a:hover {{ color: #fff; }}
    .center-divider {{ width: 36px; border-top: 2px solid var(--red); margin: 14px auto; }}

    /* Kp block */
    .kp-block {{ text-align: center; margin-bottom: 14px; padding: 10px 0; }}
    .kp-number {{ font-family: var(--mono); font-size: 2.5rem; font-weight: 700; line-height: 1; }}
    .kp-status {{ font-family: var(--mono); font-size: .62rem; letter-spacing: .16em; text-transform: uppercase; margin-top: 3px; }}
    .kp-caption {{ font-size: .7rem; color: var(--dim); margin-top: 2px; }}

    /* Event items */
    .event-item {{ margin-bottom: 9px; line-height: 1.3; }}
    .event-time {{ display: block; font-family: var(--mono); font-size: .59rem; letter-spacing: .1em; color: var(--orange); text-transform: uppercase; }}
    .event-item a {{ font-size: .81rem; }}
    .dim {{ color: var(--dim); font-size: .72rem; }}

    /* More news */
    .section-bar {{
      font-family: var(--mono); font-size: .62rem; letter-spacing: .2em;
      text-transform: uppercase; color: var(--dim);
      background: var(--bg2); padding: 6px 14px;
      border-top: 1px solid var(--border); border-bottom: 1px solid var(--border);
    }}
    .news-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); }}
    @media (max-width: 580px) {{ .news-grid {{ grid-template-columns: 1fr; }} }}
    .news-col {{ padding: 12px 14px; border-right: 1px solid var(--border); }}
    .news-col:last-child {{ border-right: none; }}
    .news-link {{ margin-bottom: 10px; font-size: .82rem; line-height: 1.35; }}
    .news-link a {{ color: #9296a8; }}
    .news-link a:hover {{ color: #fff; }}

    /* Footer */
    .footer {{
      text-align: center; padding: 14px; margin-top: 0;
      font-family: var(--mono); font-size: .63rem; color: var(--dim);
      border-top: 1px solid var(--border); letter-spacing: .05em;
    }}
    .footer a {{ color: var(--dim); }}
    .footer a:hover {{ color: var(--text); }}
  </style>
</head>
<body>
<div class="wrapper">

  <div class="masthead">
    <h1>Orbital Daily</h1>
    <div class="tagline">Independent Space News &amp; Intelligence</div>
    <div class="dateline">Updated {esc(date_str)}</div>
  </div>

  {aurora_banner}

  <div class="top-section">

    <!-- Left: Upcoming Launches -->
    <div class="sidebar">
      <div class="sidebar-title">Upcoming Launches</div>
      {launch_html}
      <hr>
      <div style="margin-top:8px">
        <a href="https://www.rocketlaunch.live" target="_blank" style="color:var(--dim);font-size:.75rem">Full schedule →</a>
      </div>
    </div>

    <!-- Center: Headlines -->
    <div class="center-col">
      {top_html}
      <div class="center-divider"></div>
      <a href="https://spaceflightnewsapi.net" target="_blank" style="font-size:.72rem;color:var(--dim)">More headlines →</a>
    </div>

    <!-- Right: Space Weather & Sky Events -->
    <div class="sidebar">
      <div class="sidebar-title">Space Weather</div>
      <div class="kp-block">
        <div class="kp-number" style="color:{esc(kp_color)}">{esc(kp_display)}</div>
        <div class="kp-status" style="color:{esc(kp_color)}">{esc(kp_text)}</div>
        <div class="kp-caption">Planetary Kp Index</div>
      </div>
      <hr>
      <div class="sidebar-title" style="margin-top:10px">Meteor Showers</div>
      {shower_html}
      <hr>
      <div style="margin-top:10px">
        <div class="event-item"><a href="https://spaceweather.gov" target="_blank">Space Weather Center →</a></div>
        <div class="event-item"><a href="https://www.timeanddate.com/eclipse/" target="_blank">Eclipse Calendar →</a></div>
        <div class="event-item"><a href="https://spotthestation.nasa.gov" target="_blank">ISS Sighting Times →</a></div>
        <div class="event-item"><a href="https://apod.nasa.gov" target="_blank">NASA Photo of the Day →</a></div>
      </div>
    </div>

  </div><!-- /.top-section -->

  <div class="section-bar">More Headlines</div>

  <div class="news-grid">
    <div class="news-col">{cols[0]}</div>
    <div class="news-col">{cols[1]}</div>
    <div class="news-col">{cols[2]}</div>
  </div>

  <div class="footer">
    Orbital Daily &nbsp;·&nbsp; Updated automatically every morning &nbsp;·&nbsp;
    Sources:
    <a href="https://spaceflightnewsapi.net" target="_blank">SNAPI</a> ·
    <a href="https://thespacedevs.com" target="_blank">The Space Devs</a> ·
    <a href="https://spaceweather.gov" target="_blank">NOAA SWPC</a> ·
    <a href="https://www.amsmeteors.org" target="_blank">AMS Meteors</a>
  </div>

</div>
</body>
</html>"""


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Orbital Daily — generating site...")
    now = datetime.now(timezone.utc)

    kp = fetch_kp()
    print(f"  Kp index: {kp}")

    news = fetch_news()
    print(f"  News articles: {len(news)}")

    launches = fetch_launches()
    print(f"  Upcoming launches: {len(launches)}")

    showers = upcoming_showers()
    print(f"  Next meteor showers: {[s[1] for s in showers]}")

    html = render_html(kp, news, launches, showers, now)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("✓  index.html written successfully.")
