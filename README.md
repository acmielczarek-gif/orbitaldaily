# Orbital Daily

Auto-generated daily space news aggregator at [orbitaldaily.com](https://orbitaldaily.com).

## How it works

1. `generate.py` pulls from free public APIs and writes a static `index.html`
2. GitHub Actions runs `generate.py` every day at 6 AM UTC automatically
3. The updated `index.html` is committed back to this repo
4. Netlify sees the new commit and auto-deploys to orbitaldaily.com within seconds

**Cost: $0** (beyond your existing domain registration)

## Data sources

| Source | What it provides |
|---|---|
| [Spaceflight News API](https://spaceflightnewsapi.net) | Space news headlines |
| [The Space Devs — Launch Library 2](https://thespacedevs.com) | Upcoming rocket launches |
| [NOAA SWPC](https://spaceweather.gov) | Kp index / aurora forecast |
| Static calendar | Annual meteor shower peaks |

## To regenerate manually (optional)

```bash
pip install requests
python generate.py
open index.html
```
