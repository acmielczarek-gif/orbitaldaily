# Handoff: Observing Mode Selector (designs 1a / 2a)

## Overview

Orbital Daily currently shows one "Shoot Score" (0–10) in the rail beside the lede. It scores every
night as if everyone were imaging galaxies, which misleads planetary imagers, aurora chasers and
people who just want to know whether to walk outside. This feature splits that single number into
**five modes** — Deep Sky, Planetary/Lunar, Just Looking Up, Aurora, Meteors — each a different
weighting of the *same* sky signals, and adds a selector so the site knows which one you want.

The chosen interaction model (option **1a**) puts five compact tabs across the top of the score card
itself. The card *is* the selector: one tap, no modal, no onboarding, no settings page. The choice
persists in `localStorage`, so it is answered once and never asked again.

## About the design files

The files in this bundle are **design references written in HTML** — a working prototype of the
intended look and behavior, not a drop-in production component. The task is to **recreate this design
in the target codebase's environment** (React/Vue/SwiftUI/native) using its established patterns,
component library and styling approach.

The one exception: `observing-mode.js` contains the **scoring model** (signal names, per-mode weights,
verdict bands, copy fallbacks). That logic is the substance of the feature and should be ported
faithfully — port the numbers, not necessarily the DOM-string rendering.

`orbitaldaily.com` today is a single static `index.html` with vanilla JS. If that is the target, the
files here can be used nearly as-is (see §Integration).

## Fidelity

**High-fidelity.** Final colors, typography, spacing and interaction are specified below to the pixel.
Recreate the UI exactly; substitute the codebase's own primitives where they produce the same result.

---

## Screens / views

### 1. Score card — default state (nothing stored)

**Purpose:** the reader lands, sees the lede, and sees a score for the default mode (Deep Sky) with
the four other modes visible as tabs. No question is asked, nothing is gated.

**Layout (mobile, 375px reference width):**

| Region | Spec |
|---|---|
| Page gutter | `20px` left/right, applied to every block: status bar, masthead, lede, card, SAI |
| Status bar | `padding: 12px 20px 8px`, mono 11px, `--od-faint` |
| Masthead | centered, `padding: 8px 20px 16px`, bottom `1px solid --od-rule-mast`; wordmark mono 13px/600, `letter-spacing:.34em`, uppercase; dateline mono 9px `.14em` uppercase `--od-faint`, `margin-top:8px` |
| Lede | `padding-top:20px`; eyebrow mono 9px `.2em` uppercase `--od-faint`; h2 Newsreader 32px/1.05, weight 600, `letter-spacing:-.025em`, `margin:12px 0 8px`; body 15px/1.55 `--od-ink-3` |
| Score card | `margin-top:20px`, spans the 20px gutter, `1px solid --od-rule`, background `--od-field`, **no border radius** |
| SAI block | `margin-top:20px`, `border-top:1px solid --od-rule-row`, `padding:20px`, `gap:16px` |

**Score card internals — three stacked blocks separated by full-bleed rules:**

1. **Tab row.** `display:flex`, `border-bottom:1px solid --od-rule`. Five buttons, `flex:1`,
   `height:48px`, `border-right:1px solid --od-rule-row` (last one included — it lands on the card
   border), mono **9px**/600, `letter-spacing:.07em`, uppercase labels.
   Active: `background:--od-accent`, `color:--od-field`. Inactive: transparent, `--od-faint`.
   Labels are abbreviated to fit 375 ÷ 5 = 67px cells: `DEEP · PLANET · VISUAL · AURORA · METEOR`
   (full names go in `aria-label`).
2. **Score block.** `padding:16px`. Verdict word mono 9px/600 `.18em` uppercase in the verdict color;
   score Newsreader **52px**/0.82, weight 700, `letter-spacing:-.03em`, same color, `margin-top:4px`;
   `/ 10` mono 10px `--od-faint`, baseline-aligned with `padding-bottom:6px`. Right-aligned meta:
   mono 9px `.12em` uppercase `--od-faint`, `line-height:1.8`, two lines — `SHOOT SCORE` / location.
   Summary line beneath: Newsreader italic 15px/1.5 `--od-ink-3`, `margin-top:12px`.
3. **Metrics block.** `padding:16px`, `border-top:1px solid --od-rule-row`,
   `display:flex; flex-direction:column; gap:12px`. Each row: label (mono 10px `.06em`
   `--od-muted`) left, percentage (mono 10px `--od-ink`) right, then a `3px` bar
   (`background:--od-rule-row`, `margin-top:6px`) with an inner fill at `width:<pct>%`.
   Bar fill color by value: `≥70% --od-verdict-good`, `≥40% --od-accent`, else `--od-faint-2`.

Every vertical step is a multiple of 4px. There are no rounded corners and no shadows anywhere in
this design — the aesthetic is newsprint rules and precise gutters.

### 2. Score card — Planetary/Lunar selected

Identical layout; only the active tab, score, verdict color, summary line and the metric rows change.
This is the state that proves the feature: the deep-sky score for the same night is **1.7
Unfavourable** (red) while planetary is **6.8 Good** (green), because the planetary weighting ignores
moonlight entirely and leans on seeing and jet stream.

Note the fourth planetary row: `Moon · 79% lit, a target` shown at **79%** — the moon flips from
penalty to subject. It is the same `moonDark` signal rendered with `invert: true`, i.e. the lit
fraction, and it is informational: it carries no weight in the planetary score.

### 3. Dark mode (design 1a)

Same markup, different token values. The user's phone renders the site through Gmail-style dark-mode
inversion, so ship a real dark theme rather than relying on auto-inversion. All colors in the
reference come from `var(--od-*)`, so `[data-theme="dark"]` needs to override values only:

```css
[data-theme="dark"] {
  --od-paper:#121212; --od-field:#181818;
  --od-ink:#eceae4; --od-ink-2:#c8c5bd; --od-ink-3:#a8a49b;
  --od-muted:#8b877e; --od-faint:#6e6a62; --od-faint-2:#5e5b54;
  --od-rule:#33322e; --od-rule-row:#2b2b2b; --od-rule-mast:#2b2b2b;
  --od-accent:#8fb0dc;
  --od-verdict-poor:#e08466; --od-verdict-fair:#d4aa3a; --od-verdict-good:#6fbf7f;
  --od-moon-lit:#d8d4c8; --od-moon-shadow:#3a3d42;
}
```

The dark accent is lightened (`#8fb0dc`) because navy `#1b3a6b` fails contrast as a tab fill on
`#181818`; active-tab text becomes `#121212` against it.

---

## Interactions & behavior

- **Tap a tab** → set mode, write `localStorage['od.observingMode']`, re-render the card, fire
  `onChange(modeKey)` so anything else keyed to mode (the week-ahead column scores, the lede's
  "if you're chasing deep sky…" clause) can update. No page reload, no network round-trip: the
  weights are client-side, the signals are already loaded.
- **Instant, no transition.** The score is information, not an animation; a count-up or crossfade
  makes it feel slower. If a transition is wanted, cap it at 120ms opacity on the score block only.
- **Return visit** → stored mode is read before first paint; the card renders in that mode. Never
  show deep-sky first and then swap.
- **Touch targets:** 67 × 48px per tab, above the 44px minimum. Tabs are real `<button>`s inside a
  `role="tablist"`, `aria-selected` on the active one, full mode name in `aria-label`.
- **Storage disabled / private mode:** `read()`/`write()` are wrapped in try/catch; the feature
  degrades to per-session state, never throws.
- **Responsive:** at ≥640px the card returns to the desktop rail (~220px wide) where five 9px labels
  will not fit in a row — stack the tabs 2 + 3, or run them vertically down the rail. Not designed
  yet; ask before improvising.

## State management

One variable: `mode ∈ {deep, planetary, visual, aurora, meteors}`.

```
mount() → read localStorage → fall back to 'deep' → render
tap     → set mode → persist → render → onChange
```

No server state, no login, same client-only pattern as the existing location detection.

Signals (`moonDark`, `cloud`, …) are fetched once per page load for the detected location and shared
by all five modes — switching modes must never trigger a fetch.

## The scoring model

One normalized payload per night; every value `0..1` where **1 = ideal**:

`moonDark`, `bortle`, `transparency`, `cloud`, `seeing`, `jet`, `targetAlt`, `kpCalm`, `kpActive`,
`bzSouth`, `shower`, `radiant` — plus an optional `raw` object carrying the human-readable values
used in metric labels (`kp: 5.7`, `seeingArcsec: 2.1`, `jetKt: 24`, `cloudPct: 15`, `target:
'Jupiter'`, `targetAltDeg: 48`, `radiantDeg: 31`, `bzNt: -9`, `moonLitPct: 79`, `bortle: 4`).

Each mode is a weighted average of its base signals **multiplied by one gating signal**:

```
score = 10 × Σ(signal × weight) / Σ(weight) × gateSignal ^ gateExp
```

rounded to one decimal. The gate is not decoration — it is why the feature works. A straight weighted
average cannot say *no*: with `moonDark` at 0.21 but Bortle, transparency and cloud all decent, deep
sky still averages mid-scale, which is precisely the misleading answer this feature exists to kill.
Moonlight does not subtract from a galaxy, it erases it, so it gates. The exponent is the sensitivity.

| Mode | Base weights (sum 1.0) | Gate |
|---|---|---|
| Deep sky | bortle .30 · transparency .30 · cloud .25 · kpCalm .15 | `moonDark ^ 0.85` |
| Planetary / lunar | seeing .40 · jet .25 · targetAlt .20 · cloud .15 — **moon excluded** | `cloud ^ 0.60` |
| Just looking up | cloud .40 · transparency .30 · bortle .30 | `moonDark ^ 0.28` |
| Aurora | kpActive .55 · bzSouth .30 · cloud .15 | `cloud ^ 0.30` |
| Meteors | shower .45 · radiant .30 · cloud .25 | `moonDark ^ 0.38` |

Against the reference night in `observing-mode-reference.html` (moonDark .21, cloud .85, seeing .78,
kpActive .88, shower .14) this model reproduces the approved mock numbers exactly:

| Mode | Score | Verdict |
|---|---|---|
| Deep sky | **1.7** | Unfavourable |
| Planetary / lunar | **6.8** | Good |
| Just looking up | **4.6** | Mixed |
| Aurora | **8.1** | Excellent |
| Meteors | **2.4** | Poor |

Treat those five as the regression test when you retune anything.

Verdict bands and colors:

| Score | Word | Color token |
|---|---|---|
| ≥ 7.5 | Excellent | `--od-verdict-good` |
| ≥ 6.0 | Good | `--od-verdict-good` |
| ≥ 4.5 | Mixed | `--od-verdict-fair` |
| ≥ 2.0 | Poor | `--od-verdict-poor` |
| < 2.0 | Unfavourable | `--od-verdict-poor` |

Summary copy is three banded lines per mode in `LINES`, selected by the **same score bands** as the
verdict (≥6.0 / ≥4.5 / below) so the prose can never contradict the word above it. Keep the desk's
voice: concrete, declarative, no hedging, no percentages in prose.

## Design tokens

Light (site default — already in `index.html`):

```
--od-paper #faf9f5   --od-field #fffdf8
--od-ink #14181d     --od-ink-2 #2a2f36   --od-ink-3 #4a4f57
--od-muted #6b6a62   --od-faint #8a8578   --od-faint-2 #a8a294
--od-rule #ddd8cc    --od-rule-row #e7e3d8   --od-rule-mast #d8d4c8
--od-accent #1b3a6b  --od-alert #b45309
--od-verdict-poor #b04a2f   --od-verdict-fair #a07508   --od-verdict-good #2f7d3e
```

Dark: see §3 above.

**Type:** Newsreader (serif, 400/500/600/700 + italic) for prose, numerals and headlines;
IBM Plex Mono (400/500/600) for every label, eyebrow, tab and metric. Both from Google Fonts.
Sizes used here: 32 / 15 (lede) · 52 / 15 (score, summary) · 11 / 10 / 9 / 8 (mono labels).

**Spacing scale:** 4 · 6 · 8 · 12 · 16 · 20 (page gutter and block rhythm) · 48 (tab height).
**Radius:** 0 everywhere. **Shadows:** none.

## Assets

None. No icons, no images — the design is type, rules and bars. The moon in the rail is inline SVG
already present in `index.html` (two circles + a clip path); it is unchanged by this feature.

## Files in this bundle

| File | What it is |
|---|---|
| `observing-mode-reference.html` | Runnable reference build: 1a (dark) and 2a (light) side by side from one code path, plus a live dump of all five scores. Open it in a browser. |
| `observing-mode.js` | The scoring model + tab card renderer. Port the weights, bands and signal contract verbatim. Vanilla, no build step, exposes `window.OD_ObservingMode`. |
| `Observing Mode Selector.dc.html` | The original design exploration — includes options 1b (instrument dial) and 1c (asked once, then an indicator), which were **not** chosen. Reference only; useful if 1a's tab row proves too cramped. |

Project files this feature touches: `index.html` (the score card in `<aside>` inside `THE LEDE`,
around line 112–121; the week-ahead forecast renderer near the bottom).

## Integration into today's `index.html`

1. Copy `observing-mode.js` next to `index.html`.
2. Add the `[data-theme="dark"]` token block to the `:root` stylesheet, and
   `<html data-theme="…">` (or `prefers-color-scheme`) to switch it.
3. Replace the rotated `UNFAVOURABLE / 1.7 / SHOOT SCORE / 10` block in the lede `<aside>` with
   `<div id="shoot-score"></div>`. (The `-4deg` rotation and the tooltip go away — the tab row and the
   metric list now carry that explanation.)
4. Before `</body>`:

```html
<script src="observing-mode.js"></script>
<script>
  OD_ObservingMode.mount(document.getElementById('shoot-score'), {
    location: 'Albany, NY',           // from the existing location detection
    signals: window.OD_SIGNALS,       // TODO: your backend payload; keep a static fallback
    onChange: function (mode) { renderForecast(mode); }   // week-ahead re-scores per mode
  });
</script>
```

5. **The week ahead must follow the mode.** Seven nights scored for deep sky are wrong once someone
   picks planetary. Call `OD_ObservingMode.score(mode, nightSignals)` per night in the forecast
   renderer instead of using a precomputed number.
6. Tell the reader once, in the desk's voice, that the score is now mode-specific — one clause in the
   lede is enough. Do not add a tour or a "new!" badge.

## Open questions for the developer

- Desktop rail treatment of five tabs (see §Responsive) is undesigned.
- `targetAlt` needs a "target of the night" chooser server-side (brightest planet above ~25°).
- Should the aurora mode surface an alert when it crosses 7.5 while the reader is in another mode?
  Probably yes, in the existing `◆ BULLETIN` slot — not designed.
