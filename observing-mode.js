/* ============================================================================
   ORBITAL DAILY — Observing Mode Selector  (design 1a / 2a)
   ----------------------------------------------------------------------------
   Plain ES5-style browser script, no build step, no dependencies — matches the
   conventions already used in index.html. Exposes one global:

       window.OD_ObservingMode

   Drop-in usage (see README §Integration):

       <div id="shoot-score"></div>
       <script src="observing-mode.js"></script>
       <script>
         OD_ObservingMode.mount(document.getElementById('shoot-score'), {
           location: 'Albany, NY',
           signals:  window.OD_SIGNALS,        // see SIGNAL_KEYS below
           onChange: function (mode) { ...re-render anything else keyed to mode }
         });
       </script>

   The five modes are NOT five separate numbers from the backend. There is ONE
   set of normalized sky signals; each mode is a different weighting of them.
   That is the whole point of the feature: the same night is 1.7 for a galaxy
   and 6.8 for Jupiter.
   ========================================================================== */

(function (root) {
  'use strict';

  var STORAGE_KEY = 'od.observingMode';

  /* --------------------------------------------------------------------------
     SIGNALS — every input is normalized 0..1 where 1 = ideal for observing.
     Backend supplies these per location per night. Names are the contract.
     -------------------------------------------------------------------------- */
  var SIGNAL_KEYS = [
    'moonDark',     // 1 = new moon / moon below horizon, 0 = full and up
    'bortle',       // 1 = Bortle 1, 0 = Bortle 9 (light pollution at the site)
    'transparency', // atmospheric clarity / aerosol load
    'cloud',        // 1 = clear, 0 = overcast
    'seeing',       // 1 = sub-arcsecond, 0 = boiling  (arcsec inverted)
    'jet',          // 1 = calm jet stream aloft, 0 = 100+ kt overhead
    'targetAlt',    // altitude of the night's headline planet/moon
    'kpCalm',       // 1 = quiet magnetic field  (good for imaging)
    'kpActive',     // 1 = storming              (good for aurora) ≈ 1 - kpCalm
    'bzSouth',      // 1 = strongly southward Bz (aurora coupling)
    'shower',       // 1 = a major shower at peak, 0 = nothing active
    'radiant'       // altitude of that shower's radiant
  ];

  /* --------------------------------------------------------------------------
     MODES — each mode is a weighted average of its base signals, then MULTIPLIED
     by one gating signal raised to an exponent.

         score = 10 · Σ(signal·weight)/Σ(weight) · gate.signal ^ gate.exp

     The gate is the difference between a score that is merely pessimistic and one
     that is honest. A straight weighted average cannot say "no" — with moonDark
     at 0.21 but decent Bortle, transparency and cloud, deep sky still averages
     mid-scale, which is exactly the misleading answer this feature exists to
     kill. Moonlight does not subtract from a galaxy, it erases it, so it gates.
     Exponents are the sensitivity: deep sky 0.85 (near-total gate), meteors 0.38,
     visual 0.28, aurora gates on cloud only, planetary gates on cloud lightly.

     Base weights sum to 1.0. Do not change signal keys without updating
     SIGNAL_KEYS.
     -------------------------------------------------------------------------- */
  var MODES = [
    {
      key: 'deep',
      tab: 'DEEP',                      // 375px tab label (abbreviated)
      label: 'Deep sky',                // full label (menus, indicator, a11y)
      weights: { bortle: 0.30, transparency: 0.30, cloud: 0.25, kpCalm: 0.15 },
      gate: { signal: 'moonDark', exp: 0.85 },   // a lit sky erases faint targets
      // rows shown under the score, in order. `signal` picks the bar value.
      // `tip` keys into ROW_TOOLTIPS (below) for the tab-aware [i] tooltip.
      // Only present where copy exists for that row; rows without a `tip`
      // render exactly as before, no tooltip trigger added.
      rows: [
        { signal: 'moonDark',     label: 'Moon darkness', tip: 'moon' },
        { signal: 'kpCalm',       label: 'Field calm',        detail: 'kpLabeled', tip: 'kp' },
        { signal: 'transparency', label: 'Transparency', tip: 'transparency' },
        { signal: 'bortle',       label: 'Sky darkness',      detail: 'bortle', tip: 'bortle' }
      ]
    },
    {
      key: 'planetary',
      tab: 'PLANET',
      label: 'Planetary / lunar',
      // deliberately ignores moonDark — moonlight is not a penalty here
      weights: { seeing: 0.40, jet: 0.25, targetAlt: 0.20, cloud: 0.15 },
      gate: { signal: 'cloud', exp: 0.60 },
      rows: [
        { signal: 'seeing',    label: 'Seeing',           detail: 'seeing' },
        { signal: 'jet',       label: 'Jet stream',       detail: 'jet' },
        { signal: 'targetAlt', label: 'Target altitude',  detail: 'targetAlt' },
        { signal: 'moonDark',  label: 'Moon',             detail: 'moonAsset', invert: true, tip: 'moon' }
      ]
    },
    {
      key: 'visual',
      tab: 'VISUAL',
      label: 'Just looking up',
      weights: { cloud: 0.40, transparency: 0.30, bortle: 0.30 },
      gate: { signal: 'moonDark', exp: 0.28 },   // washes out the faint half of the sky
      rows: [
        { signal: 'cloud',        label: 'Cloud cover',   detail: 'cloud' },
        { signal: 'moonDark',     label: 'Moon darkness', tip: 'moon' },
        { signal: 'transparency', label: 'Transparency', tip: 'transparency' }
      ]
    },
    {
      key: 'aurora',
      tab: 'AURORA',
      label: 'Aurora',
      weights: { kpActive: 0.55, bzSouth: 0.30, cloud: 0.15 },
      gate: { signal: 'cloud', exp: 0.30 },      // moonlight barely matters to an aurora
      rows: [
        { signal: 'kpActive', label: 'Kp index',    detail: 'kp', tip: 'kp' },
        { signal: 'bzSouth',  label: 'Bz southward', detail: 'bz' },
        { signal: 'cloud',    label: 'Cloud cover',  detail: 'cloud' }
      ]
    },
    {
      key: 'meteors',
      tab: 'METEOR',
      label: 'Meteors',
      weights: { shower: 0.45, radiant: 0.30, cloud: 0.25 },
      gate: { signal: 'moonDark', exp: 0.38 },
      rows: [
        { signal: 'shower',   label: 'Shower activity' },
        { signal: 'moonDark', label: 'Moon darkness', tip: 'moon' },
        { signal: 'radiant',  label: 'Radiant altitude', detail: 'radiant' }
      ]
    }
  ];

  var DEFAULT_MODE = 'deep';

  /* --------------------------------------------------------------------------
     Scoring
     -------------------------------------------------------------------------- */
  function byKey(key) {
    for (var i = 0; i < MODES.length; i++) { if (MODES[i].key === key) return MODES[i]; }
    return MODES[0];
  }

  function clamp01(n) { return n < 0 ? 0 : n > 1 ? 1 : n; }

  function signal(signals, key) {
    return signals && typeof signals[key] === 'number' ? clamp01(signals[key]) : 0.5;
  }

  // returns 0.0 – 10.0, one decimal
  function score(modeKey, signals) {
    var mode = byKey(modeKey), w = mode.weights, sum = 0, total = 0, k;
    for (k in w) {
      if (!w.hasOwnProperty(k)) continue;
      sum += signal(signals, k) * w[k];
      total += w[k];
    }
    var base = total ? sum / total : 0;
    var gate = mode.gate ? Math.pow(signal(signals, mode.gate.signal), mode.gate.exp) : 1;
    return Math.round(base * gate * 100) / 10;
  }

  // verdict word + which CSS var to paint it with
  function verdict(n) {
    if (n >= 7.5) return { word: 'Excellent', tone: 'good' };
    if (n >= 6.0) return { word: 'Good',      tone: 'good' };
    if (n >= 4.5) return { word: 'Mixed',     tone: 'fair' };
    if (n >= 2.0) return { word: 'Poor',      tone: 'poor' };
    return { word: 'Unfavourable', tone: 'poor' };
  }

  var TONE_VAR = {
    good: 'var(--od-verdict-good)',
    fair: 'var(--od-verdict-fair)',
    poor: 'var(--od-verdict-poor)'
  };

  /* --------------------------------------------------------------------------
     Copy — one line per mode explaining the score in the desk's voice.
     Swap for a backend/Claude-written line if you'd rather; keep these as the
     fallback so the card is never empty.
     -------------------------------------------------------------------------- */
  var LINES = {
    deep: [
      'A gibbous moon and an active storm — nothing faint survives tonight.',
      'Workable, not generous. Short subs and low expectations.',
      'Dark, steady and clear — the night to spend on something faint.'
    ],
    planetary: [
      'The air is churning and the target sits low. Nothing will hold focus.',
      'Passable seeing. Shoot fast and keep the best ten percent.',
      "Moonlight barely matters here — the air is steady and the target rides high."
    ],
    visual: [
      'Bright moon, thick air. Little to see beyond the obvious.',
      'Clear enough for the bright stuff; the moon takes the rest of the sky.',
      'Clear and dark enough to just stand outside and look.'
    ],
    aurora: [
      'Field too quiet for a show this far south.',
      'A faint glow on the northern horizon at best.',
      'Storming and clear — the best northern window in weeks.'
    ],
    meteors: [
      'No shower near peak, and the moon drowns what sporadics there are.',
      'A handful an hour, if you are patient and the moon sets first.',
      'A shower near peak with a dark sky under it. Bring a chair.'
    ]
  };

  // banded off the score itself, so the prose can never contradict the verdict
  function summary(modeKey, signals, n) {
    var set = LINES[modeKey] || LINES.deep;
    return n >= 6.0 ? set[2] : n >= 4.5 ? set[1] : set[0];
  }

  /* --------------------------------------------------------------------------
     Row tooltip copy — one clause per metric per mode, keyed by *concept*
     ('kp' covers both deep's kpCalm row and aurora's kpActive row -- same
     underlying idea, different signal name) rather than by raw signal key, so
     modes that read the "Kp-ness" of the sky differently still share one
     lookup. Only rows with a matching `tip` key in MODES render the [i]
     trigger; a mode/metric combo with no row today (e.g. aurora has no moon
     row, so `moon.aurora` below is unreachable in the current UI) still has
     its copy here, just dormant until a row exists to attach it to.
     -------------------------------------------------------------------------- */
  var ROW_TOOLTIPS = {
    moon: {
      deep:      "How much of the moon's face is unlit. Critical for deep-sky — moonlight overwhelms faint nebulae and galaxies. Aim for >80%.",
      planetary: "Moon matters less for planets — they're bright enough to observe in moonlight. Still affects background sky contrast.",
      visual:    'Moderate impact for visual observing. Bright showpieces tolerate moon; faint targets suffer.',
      aurora:    'Minimal impact — aurora is bright enough to see even in moonlight. Focus on Kp instead.',
      meteors:   'Moon is the enemy of meteor showers — moonlight drowns out faint streaks. Darker is significantly better.'
    },
    kp: {
      deep:      'Geomagnetic activity index. Low Kp = steady atmosphere = sharper stars. High Kp adds atmospheric turbulence for deep-sky.',
      planetary: "The most important metric for planetary work. Low Kp = steady seeing = sharp detail on Jupiter's bands or Saturn's rings.",
      visual:    'Moderate effect. Most visual targets tolerate average Kp; very high Kp degrades fine detail.',
      aurora:    'The primary driver of aurora activity. Kp 5+ means visible aurora at mid-latitudes; Kp 7+ is a major display.',
      meteors:   'Low impact on meteor viewing. Kp affects atmospheric stability but meteors are bright enough to cut through.'
    },
    transparency: {
      deep:      'How cleanly light passes through the atmosphere. Critical for faint deep-sky targets — poor transparency hides dim nebulae entirely.',
      planetary: 'Less critical for planets than seeing is, but still affects contrast and fine surface detail.',
      visual:    'Important for any target relying on contrast — galaxies and nebulae fade fast in hazy skies.',
      aurora:    'Low impact — aurora brightness overwhelms atmospheric haze.',
      meteors:   'Moderate — clear skies help but meteors are bright enough to show through average haze.'
    },
    bortle: {
      deep:      'Bortle scale measures light pollution. 1 = pristine, 9 = inner-city. Deep-sky is the most Bortle-sensitive mode — a dark site makes a bigger difference here than any other factor.',
      planetary: "Light pollution has minimal effect on planets — they're bright point sources. Bortle barely moves the needle for planetary work.",
      visual:    'Moderate effect. Showpieces like the Orion Nebula or Pleiades are fine in Bortle 7; faint galaxies are not.',
      aurora:    'Bortle matters less for aurora — a strong display is visible even from suburbs. Kp and cloud cover are what matter.',
      meteors:   'Dark skies dramatically increase meteor counts — faint meteors that suburban skyglow hides become visible. A Bortle 3-4 site can triple your count.'
    }
  };

  /* --------------------------------------------------------------------------
     Row detail strings — the "· 2.1″" half of a metric label.
     Reads raw values off signals.raw (optional); falls back to no detail.
     -------------------------------------------------------------------------- */
  // true minus (U+2212), matching the STOCKS convention in index.html
  function minus(n) { return String(n).replace('-', '\u2212'); }

  function detail(kind, signals) {
    var r = (signals && signals.raw) || {};
    switch (kind) {
      case 'kp':        return r.kp != null ? minus(r.kp) : '';               // label carries the word
      case 'kpLabeled': return r.kp != null ? 'Kp ' + minus(r.kp) : '';       // label does not
      case 'bortle':    return r.bortle != null ? 'Bortle ' + r.bortle : '';
      case 'seeing':    return r.seeingArcsec != null ? r.seeingArcsec + '\u2033' : '';
      case 'jet':       return r.jetKt != null ? r.jetKt + ' kt' : '';
      case 'cloud':     return r.cloudPct != null ? r.cloudPct + '%' : '';
      case 'targetAlt': return r.target ? r.target + ' \u00b7 ' + r.targetAltDeg + '\u00b0' : '';
      case 'radiant':   return r.radiantDeg != null ? r.radiantDeg + '\u00b0' : '';
      case 'bz':        return r.bzNt != null ? minus(r.bzNt) + ' nT' : '';
      case 'moonAsset': return (r.moonLitPct != null ? r.moonLitPct + '% lit' : '') + ', a target';
    }
    return '';
  }

  function barVar(v) {
    return v >= 0.7 ? 'var(--od-verdict-good)'
         : v >= 0.4 ? 'var(--od-accent)'
                    : 'var(--od-faint-2)';
  }

  /* --------------------------------------------------------------------------
     Persistence
     -------------------------------------------------------------------------- */
  function read() {
    try {
      var v = window.localStorage.getItem(STORAGE_KEY);
      return v && byKey(v).key === v ? v : null;
    } catch (e) { return null; }          // private mode / storage disabled
  }
  function write(key) {
    try { window.localStorage.setItem(STORAGE_KEY, key); } catch (e) {}
  }

  /* --------------------------------------------------------------------------
     Render — design 1a / 2a. Same markup for both themes; all colors come from
     the --od-* tokens, so a [data-theme="dark"] block is the only difference.
     -------------------------------------------------------------------------- */
  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function cardHTML(modeKey, opts) {
    var mode = byKey(modeKey);
    var n = score(modeKey, opts.signals);
    var v = verdict(n);
    var tone = TONE_VAR[v.tone];

    // Sneak-peek: each tab shows its own verdict+score, computed off the same
    // shared signal payload the active card already uses -- score()/verdict()
    // reused as-is, not reimplemented, so this can never drift from the card.
    var tabs = MODES.map(function (m) {
      var on = m.key === mode.key;
      var tn = score(m.key, opts.signals);
      var tv = verdict(tn);
      var previewColor = on ? 'var(--od-field)' : TONE_VAR[tv.tone];
      var labelColor   = on ? 'var(--od-field)' : 'var(--od-faint)';
      return '<button type="button" role="tab" aria-selected="' + on + '" data-mode="' + m.key + '"'
        + ' aria-label="' + esc(m.label) + ' -- ' + esc(tv.word) + ' ' + tn.toFixed(1) + ' out of 10"'
        + ' style="appearance:none; flex:1; min-width:0; height:48px; padding:4px 3px; cursor:pointer;'
        + ' display:flex; flex-direction:column; align-items:center; justify-content:center; gap:2px; overflow:hidden;'
        + ' font-family:var(--od-mono); font-weight:600;'
        + ' border:none; border-right:1px solid var(--od-rule-row);'
        + ' background:' + (on ? 'var(--od-accent)' : 'transparent') + ';">'
        +   '<span style="font-size:10px; letter-spacing:.07em; color:' + labelColor + '; white-space:nowrap;">' + m.tab + '</span>'
        +   '<span style="font-size:8px; letter-spacing:.02em; color:' + previewColor + '; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:100%;">' + esc(tv.word) + ' · ' + tn.toFixed(1) + '</span>'
        + '</button>';
    }).join('');

    var rows = mode.rows.map(function (row) {
      var raw = opts.signals && typeof opts.signals[row.signal] === 'number' ? clamp01(opts.signals[row.signal]) : 0.5;
      var v01 = row.invert ? 1 - raw : raw;                 // moon-as-asset row
      var d = row.detail ? detail(row.detail, opts.signals) : '';
      var pct = Math.round(v01 * 100);
      var labelText = esc(row.label) + (d ? ' \u00b7 ' + esc(d) : '');
      // Tab-aware tooltip: only rows with a `tip` key AND matching copy for
      // this mode get the [i] trigger -- same .term/data-tip/.tip mechanism
      // used everywhere else on the page, nothing new. Rows without one
      // render identically to before.
      var tipText = row.tip && ROW_TOOLTIPS[row.tip] ? ROW_TOOLTIPS[row.tip][mode.key] : null;
      var labelRow = tipText
        ? '<div class="term" data-tip style="display:flex; justify-content:space-between; align-items:baseline;'
          + ' font-family:var(--od-mono); font-size:10px; letter-spacing:.06em; color:var(--od-muted);">'
          + '<span>' + labelText + ' <span class="idot">i</span></span>'
          + '<span style="color:var(--od-ink);">' + pct + '%</span>'
          + '<span class="tip below">' + esc(tipText) + '</span>'
          + '</div>'
        : '<div style="display:flex; justify-content:space-between; align-items:baseline;'
          + ' font-family:var(--od-mono); font-size:10px; letter-spacing:.06em; color:var(--od-muted);">'
          + '<span>' + labelText + '</span>'
          + '<span style="color:var(--od-ink);">' + pct + '%</span></div>';
      return '<div>'
        + labelRow
        + '<div style="height:3px; background:var(--od-rule-row); margin-top:6px;">'
        + '<div style="height:100%; width:' + pct + '%; background:' + barVar(v01) + ';"></div>'
        + '</div></div>';
    }).join('');

    return ''
      + '<div style="border:1px solid var(--od-rule); background:var(--od-field);">'
      +   '<div role="tablist" aria-label="Observing mode" style="display:flex; border-bottom:1px solid var(--od-rule);">' + tabs + '</div>'
      +   '<div style="padding:16px;">'
      +     '<div style="display:flex; align-items:flex-end; justify-content:space-between; gap:12px;">'
      +       '<div>'
      +         '<div style="font-family:var(--od-mono); font-size:9px; font-weight:600; letter-spacing:.18em; text-transform:uppercase; color:' + tone + ';">' + v.word + '</div>'
      +         '<div style="display:flex; align-items:flex-end; gap:6px; margin-top:12px;">'
      +           '<span style="font-size:52px; font-weight:700; line-height:.82; letter-spacing:-.03em; color:' + tone + ';">' + n.toFixed(1) + '</span>'
      +           '<span style="font-family:var(--od-mono); font-size:10px; letter-spacing:.12em; color:var(--od-faint); padding-bottom:6px;">/ 10</span>'
      +         '</div>'
      +       '</div>'
      +       '<div style="text-align:right; font-family:var(--od-mono); font-size:9px; letter-spacing:.12em; text-transform:uppercase; color:var(--od-faint); line-height:1.8;">'
      +         'Shoot score<br>' + esc(opts.location || '') + '</div>'
      +     '</div>'
      +     '<p style="font-family:var(--od-serif); font-style:italic; font-size:15px; line-height:1.5; color:var(--od-ink-3); margin:12px 0 0;">'
      +       esc(summary(mode.key, opts.signals, n)) + '</p>'
      +   '</div>'
      +   '<div style="display:flex; flex-direction:column; gap:12px; padding:16px; border-top:1px solid var(--od-rule-row);">' + rows + '</div>'
      + '</div>';
  }

  /* --------------------------------------------------------------------------
     mount(el, opts) -> { get, set, refresh }
     opts: { location, signals, defaultMode, onChange, modeClauses, clauseEl }
     refresh(signals, location) -- location is optional, for when it resolves
     after mount (e.g. geolocation completing after an instant nationwide
     fallback render).

     modeClauses + clauseEl -- optional. modeClauses is a { modeKey: text }
     map (e.g. the lede's five per-mode clauses); clauseEl is the DOM node
     whose textContent gets swapped to match the active mode. Only that one
     element's text changes on a mode switch -- the rest of the lede (and
     everything else on the page) is left alone. clauseEl is set once at
     mount so its own initial server-rendered text needs no JS to match the
     default mode, then kept in sync on every mode change from here on.
     -------------------------------------------------------------------------- */
  function mount(el, opts) {
    opts = opts || {};
    var current = read() || opts.defaultMode || DEFAULT_MODE;

    // Row tooltips (see ROW_TOOLTIPS above) live inside el's own re-rendered
    // markup. The page-level tooltip click-binding in index.html runs once,
    // before a tab has ever been switched, so it can never reach nodes that
    // paint() creates later. Re-bind after every paint(), scoped to el only
    // -- this never touches the page's static SAI/Weather/tile/eyebrow
    // tooltips, so nothing there risks a duplicate listener. Same click-to-
    // toggle behavior as the page-level binding, just re-applied to the
    // subtree that actually gets rebuilt.
    function bindRowTooltips() {
      var tips = el.querySelectorAll ? el.querySelectorAll('.term[data-tip]') : [];
      for (var i = 0; i < tips.length; i++) {
        (function (t) {
          t.addEventListener('click', function (e) {
            var wasOpen = t.classList.contains('open');
            var open = document.querySelectorAll('.term.open');
            for (var j = 0; j < open.length; j++) { open[j].classList.remove('open'); }
            if (!wasOpen) t.classList.add('open');
            e.stopPropagation();
          });
        })(tips[i]);
      }
    }

    function paint() { el.innerHTML = cardHTML(current, opts); bindRowTooltips(); }

    function syncClause() {
      if (!opts.modeClauses || !opts.clauseEl) return;
      var text = opts.modeClauses[current];
      if (text) opts.clauseEl.textContent = text;
    }

    el.addEventListener('click', function (e) {
      var btn = e.target.closest ? e.target.closest('[data-mode]') : null;
      if (!btn) return;
      var next = btn.getAttribute('data-mode');
      if (next === current) return;
      current = next;
      write(current);
      paint();
      syncClause();
      if (opts.onChange) opts.onChange(current, byKey(current));
    });

    paint();
    syncClause();

    return {
      get: function () { return current; },
      set: function (key) { current = byKey(key).key; write(current); paint(); syncClause(); },
      refresh: function (signals, location) {
        if (signals) opts.signals = signals;
        if (location) opts.location = location;
        paint();
      }
    };
  }

  root.OD_ObservingMode = {
    MODES: MODES,
    SIGNAL_KEYS: SIGNAL_KEYS,
    STORAGE_KEY: STORAGE_KEY,
    DEFAULT_MODE: DEFAULT_MODE,
    score: score,
    verdict: verdict,
    summary: summary,
    mount: mount,
    stored: read
  };
})(window);
