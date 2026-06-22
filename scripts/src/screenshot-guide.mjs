// Generate annotated tester-guide screenshots (RFC 0004).
//
// For each screen in the config below: navigate, optionally pre-seed UI state,
// inject an SVG overlay with one amber-circled letter per element of interest,
// snap a full-page PNG, save to apps/sentinel-ui/public/guide/.
//
// Re-run any time the UI changes. Output PNGs are committed (small enough)
// so contributors who don't have Playwright installed still see the doc.
//
// Usage:
//   pnpm --filter @workspace/scripts exec node src/screenshot-guide.mjs
//   pnpm --filter @workspace/scripts exec node src/screenshot-guide.mjs creation
//   BASE_URL=http://localhost:5173 pnpm --filter @workspace/scripts exec node src/screenshot-guide.mjs
//
// Requires a Vite dev server running (default http://localhost:5173). Use
// `just dev-frontend` in another shell first.

import { chromium } from 'playwright';
import { resolve } from 'node:path';
import { mkdir } from 'node:fs/promises';

const BASE_URL = process.env.BASE_URL || 'http://localhost:5173';
const REPO_ROOT = resolve(import.meta.dirname, '../..');
const OUT_DIR = resolve(REPO_ROOT, 'apps/sentinel-ui/public/guide');
const VIEWPORT = { width: 1280, height: 900 };

// ────────────────────────────────────────────────────────────────────────
// Screen configs. Each entry:
//   url:           path relative to BASE_URL
//   waitFor:       selector(s) we wait for before snapping (handles async hydration)
//   prep:          optional async function (page) => {} run before annotation
//                  (pre-fill forms, inject Zustand store state, stub APIs)
//   annotations:   [{key, selector, label}] — one circle per entry, in order.
//                  `label` is used in the doc; the script doesn't render it on
//                  the screenshot itself (the letter does the pointing).
// ────────────────────────────────────────────────────────────────────────

// Russell's actual Trog world UUID — used for the game / settings shots so
// the HUD renders with real persisted state (Russalo the Shadowmancer, etc.).
// The script depends on this world existing on the local backend; if it's
// ever deleted, regenerating screenshots needs an updated UUID or a stubbed
// mock. Documented in the README so the dep is loud.
const TROG_WORLD_ID = '2097371f-a031-46ab-9875-81436161b96f';

const SCREENS = {
  creation: {
    url: '/create',
    waitFor: '[data-testid="creation-world-name"]',
    prep: async (page) => {
      // Pre-fill the form so every conditional section (tone, region, persona,
      // mood) renders. Bypasses the chained-reveal UX so the screenshot
      // documents every field at once.
      await page.evaluate(() => {
        // Use the SPA's Zustand setters via the global store reference.
        // World creation store is exposed at window.__creationStore in dev (we
        // don't expose it; the cleaner path is typing into the inputs).
      });
      // Pre-fill the form so every conditional section (tone, region, persona,
      // mood) renders. Each selector uses a different input shape — buttons
      // for genre + mood, native <select> for tone, radio <input> for region
      // + persona, checkbox for modifiers.
      await page.fill('[data-testid="creation-world-name"] input', 'Thornwatch Reaches');
      await page.fill('[data-testid="creation-character-name"] input', 'Russalo');
      await page.fill('[data-testid="creation-character-class"] input', 'Shadowmancer');
      // Click the fantasy genre button — unlocks Tone / Region / Persona.
      await page.locator('[data-testid="creation-genre"] button', { hasText: /fantasy/i }).first().click();
      // Wait for the conditionally-rendered sections to appear.
      await page.waitForSelector('[data-testid="creation-tone"]', { timeout: 5000 });
      // Tone is a native <select> dropdown.
      await page.selectOption('[data-testid="creation-tone"] select', 'gritty');
      // Region is a radio <input> list; check by value.
      await page.check('[data-testid="creation-region"] input[type="radio"][value="The Breach"]');
      // Persona is also radio inputs; oracle is one of three personas
      // compatible with fantasy.
      await page.check('[data-testid="creation-persona"] input[type="radio"][value="oracle"]');
      // Wait for Mood to render (gated on persona being set).
      await page.waitForSelector('[data-testid="creation-mood"]', { timeout: 5000 });
      // Mood is a button row; pick ominous if present, else fall back to
      // whatever default the persona supplied.
      const ominous = page.locator('[data-testid="creation-mood"] button', { hasText: /^ominous$/i });
      if (await ominous.count()) await ominous.first().click();
      // Toggle sandbox so the modifier displays its activated state.
      const sandbox = page.locator('[data-testid="creation-modifiers"] input[type="checkbox"]').first();
      if (await sandbox.count()) await sandbox.check();
      // Brief settle so any debounced seed preview generates.
      await page.waitForTimeout(500);
    },
    annotations: [
      { key: 'A', selector: '[data-testid="creation-world-name"]', label: 'World name' },
      { key: 'B', selector: '[data-testid="creation-character-name"]', label: 'Character name' },
      { key: 'C', selector: '[data-testid="creation-character-class"]', label: 'Class' },
      { key: 'D', selector: '[data-testid="creation-genre"]', label: 'Genre' },
      { key: 'E', selector: '[data-testid="creation-tone"]', label: 'Tone' },
      { key: 'F', selector: '[data-testid="creation-region"]', label: 'Starting region' },
      { key: 'G', selector: '[data-testid="creation-persona"]', label: 'DM persona' },
      { key: 'H', selector: '[data-testid="creation-mood"]', label: 'DM mood' },
      { key: 'I', selector: '[data-testid="creation-modifiers"]', label: 'Modifiers (sandbox + permadeath)' },
      { key: 'J', selector: '[data-testid="creation-begin"]', label: 'Begin journey' },
      { key: 'K', selector: '[data-testid="creation-seed-preview"]', label: 'Live seed preview (cosmetic-so-far)' },
    ],
  },

  'worlds-list': {
    url: '/',
    // Wait for either an empty-state or the worlds list (whichever the local
    // backend serves). The hydration call goes through useWorldsFetch.
    waitFor: 'h1',
    prep: async (page) => {
      // Give the worlds fetch ~1s to complete.
      await page.waitForTimeout(1000);
    },
    annotations: [
      { key: 'A', selector: '[aria-label="Refresh"]', label: 'Refresh the worlds list', placement: 'below' },
      { key: 'B', selector: 'a[href="/data"]', label: 'Training data browser', placement: 'below' },
      { key: 'C', selector: 'a[href="/create"]', label: 'Start a new world', placement: 'below' },
      { key: 'D', selector: '[data-testid="worlds-list"]', label: 'Your existing worlds (click to resume)' },
    ],
  },

  game: {
    url: `/w/${TROG_WORLD_ID}`,
    // Wait for the TopBar world name to populate (hydration done).
    waitFor: '[data-testid="topbar-world-name"]',
    prep: async (page) => {
      // The reauth flow may run if no token is held in localStorage; wait
      // long enough for the SPA to settle on the hydrated game shell.
      await page.waitForFunction(
        () => {
          const wn = document.querySelector('[data-testid="topbar-world-name"]');
          // World name populated AND vitals silhouette rendered = hydrated.
          return wn && wn.textContent && wn.textContent.trim().length > 0 &&
                 document.querySelector('[role="meter"]');
        },
        { timeout: 15000 },
      );
      // Pre-populate the per-turn DM action pills so the pill rail's top
      // row is visible in the snapshot. chatStore.suggestedActions is
      // ephemeral state — it only populates mid-stream during a live turn.
      // The screenshot tooling sets it directly via the dev-only window
      // handle (see chatStore.js).
      await page.evaluate(() => {
        if (window.__sentinelStores?.chat) {
          window.__sentinelStores.chat.setState({
            suggestedActions: [
              { label: 'approach the warden', tone: 'cautious' },
              { label: 'examine the breach', tone: 'curious' },
              { label: 'flee back the way you came', tone: 'defensive' },
            ],
          });
        }
      });
      await page.waitForTimeout(500);
    },
    annotations: [
      // TopBar — small icons in a horizontal row. Letters go BELOW the bar
      // so they don't cover the icons themselves (Russell 2026-06-16 cal).
      { key: 'A', selector: '[data-testid="topbar-world-name"]', label: 'World name', placement: 'below' },
      { key: 'B', selector: '[role="status"]', label: 'Status indicator (Ready / Streaming / Connection error)', placement: 'below' },
      { key: 'C', selector: '[aria-label="Send feedback"]', label: 'Feedback form', placement: 'below' },
      { key: 'D', selector: '[aria-label="Tester guide"]', label: 'Tester guide (this doc)', placement: 'below' },
      { key: 'E', selector: '[aria-label*="Settings"]', label: 'Settings drawer (font size + messages)', placement: 'below' },
      { key: 'F', selector: '[aria-label="Training data"]', label: 'Training data browser', placement: 'below' },
      { key: 'G', selector: '[data-testid="topbar-persona"]', label: 'DM persona + mood', placement: 'below' },
      // Panels + scroll + command bar — top-left is fine; these are large.
      { key: 'H', selector: '[role="meter"]', label: 'Vitals silhouette + band' },
      { key: 'I', selector: '[data-testid="world-metrics-day"]', label: 'Day counter (cosmetic-so-far — frozen at 1)' },
      { key: 'J', selector: '[data-testid="world-metrics-tension"]', label: 'Tension meter (0-10, DM-emitted)' },
      { key: 'K', selector: '[data-testid="panel-tab-codex"]', label: 'Codex tab' },
      { key: 'L', selector: '[data-testid="panel-tab-inventory"]', label: 'Inventory tab' },
      { key: 'M', selector: '[aria-label="DM-suggested actions"]', label: 'DM-suggested action pills' },
      { key: 'N', selector: '[aria-label="Always-available actions"]', label: 'Always-available action pills' },
      { key: 'O', selector: '[data-testid="command-bar-input"]', label: 'Command bar (type what to do)' },
      { key: 'P', selector: '[data-testid="command-bar-send"]', label: 'Send' },
    ],
  },

  settings: {
    url: `/w/${TROG_WORLD_ID}`,
    waitFor: '[data-testid="topbar-world-name"]',
    prep: async (page) => {
      // Hydrate, then open the settings drawer.
      await page.waitForFunction(
        () => {
          const wn = document.querySelector('[data-testid="topbar-world-name"]');
          return wn && wn.textContent && wn.textContent.trim().length > 0;
        },
        { timeout: 15000 },
      );
      // Click the settings gear to open the drawer.
      await page.locator('[aria-label*="Settings"]').first().click();
      // Drawer mounts with role="dialog"; wait for aria-hidden=false.
      await page.waitForFunction(
        () => {
          const dlg = document.querySelector('[role="dialog"][aria-label="Settings"]');
          return dlg && dlg.getAttribute('aria-hidden') === 'false';
        },
        { timeout: 5000 },
      );
      await page.waitForTimeout(400);
    },
    annotations: [
      { key: 'A', selector: '[aria-label="Close settings"]', label: 'Close the drawer' },
      { key: 'B', selector: '[aria-label="Decrease font size"]', label: 'Decrease narrative font size' },
      { key: 'C', selector: '[aria-label="Increase font size"]', label: 'Increase narrative font size' },
      // Anchor on the Messages section text within the drawer; querySelector
      // finds the first match, which is the section heading inside the drawer.
      { key: 'D', selector: '[role="dialog"] section:nth-of-type(2)', label: 'Operator messages (RFC 0002)' },
    ],
  },
};

// ────────────────────────────────────────────────────────────────────────
// SVG overlay injection. Each annotation gets a filled amber circle with a
// black letter, positioned at the top-left corner of the target element's
// bounding box (slightly offset so the circle sits *just outside* the box
// rather than overlapping content).
// ────────────────────────────────────────────────────────────────────────

async function initOverlay(page) {
  await page.evaluate(() => {
    const ID = 'sentinel-guide-overlay';
    document.getElementById(ID)?.remove();
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.id = ID;
    Object.assign(svg.style, {
      position: 'absolute',
      top: '0',
      left: '0',
      width: document.documentElement.scrollWidth + 'px',
      height: document.documentElement.scrollHeight + 'px',
      pointerEvents: 'none',
      zIndex: '99999',
    });
    document.body.appendChild(svg);
  });
}

async function addMarker(page, selector, letter, placement = 'top-left') {
  return page.evaluate(
    (args) => {
      const { selector, letter, placement } = args;
      const el = document.querySelector(selector);
      if (!el) return { ok: false, reason: 'not found: ' + selector };
      const r = el.getBoundingClientRect();
      const sx = window.scrollX;
      const sy = window.scrollY;
      // Pick the circle's center based on placement. The circle is 18px
      // radius (36px diameter); offsets keep it just outside the element.
      let cx, cy;
      switch (placement) {
        case 'below':
          // Centered horizontally under the element, 22px below the bottom.
          cx = r.left + sx + r.width / 2;
          cy = r.bottom + sy + 22;
          break;
        case 'above':
          cx = r.left + sx + r.width / 2;
          cy = r.top + sy - 22;
          break;
        case 'right':
          cx = r.right + sx + 22;
          cy = r.top + sy + r.height / 2;
          break;
        case 'top-left':
        default:
          cx = r.left + sx - 4;
          cy = r.top + sy - 4;
      }
      const svg = document.getElementById('sentinel-guide-overlay');
      const ns = 'http://www.w3.org/2000/svg';
      const g = document.createElementNS(ns, 'g');
      g.setAttribute('transform', `translate(${cx}, ${cy})`);
      const circle = document.createElementNS(ns, 'circle');
      circle.setAttribute('r', '18');
      circle.setAttribute('fill', '#c9973a');
      circle.setAttribute('stroke', '#0d0d0f');
      circle.setAttribute('stroke-width', '2');
      g.appendChild(circle);
      const text = document.createElementNS(ns, 'text');
      text.setAttribute('text-anchor', 'middle');
      text.setAttribute('dominant-baseline', 'central');
      text.setAttribute('fill', '#0d0d0f');
      text.setAttribute('font-family', 'Georgia, serif');
      text.setAttribute('font-weight', 'bold');
      text.setAttribute('font-size', '20');
      text.textContent = letter;
      g.appendChild(text);
      svg.appendChild(g);
      return { ok: true };
    },
    { selector, letter, placement },
  );
}

async function snap(page, name, screen) {
  await page.goto(BASE_URL + screen.url, { waitUntil: 'networkidle' });
  if (screen.waitFor) {
    await page.waitForSelector(screen.waitFor, { timeout: 5000 });
  }
  if (screen.prep) {
    await screen.prep(page);
  }
  // Re-measure: the prep may have grown the page. Wait one animation frame
  // so layout settles before reading bounding boxes.
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(r)));

  // Initialize the overlay layer, then add one marker per annotation.
  await initOverlay(page);
  const missing = [];
  for (const a of screen.annotations) {
    const result = await addMarker(page, a.selector, a.key, a.placement);
    if (!result?.ok) missing.push({ ...a, reason: result?.reason || 'unknown' });
  }
  if (missing.length) {
    console.warn(`  [${name}] WARNING: ${missing.length} annotation(s) skipped:`);
    for (const m of missing) console.warn(`    - ${m.key} (${m.label}): ${m.reason}`);
  }

  const outPath = resolve(OUT_DIR, `${name}.png`);
  await page.screenshot({ path: outPath, fullPage: true });
  console.log(`  [${name}] -> ${outPath}  (${screen.annotations.length - missing.length}/${screen.annotations.length} markers)`);
}

// ────────────────────────────────────────────────────────────────────────
// Main
// ────────────────────────────────────────────────────────────────────────

const args = process.argv.slice(2);
const target = args[0];

await mkdir(OUT_DIR, { recursive: true });

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: VIEWPORT });
const page = await ctx.newPage();

const names = target ? [target] : Object.keys(SCREENS);
console.log(`Snapping ${names.length} screen(s) → ${OUT_DIR}`);

for (const name of names) {
  const screen = SCREENS[name];
  if (!screen) {
    console.error(`Unknown screen "${name}". Available: ${Object.keys(SCREENS).join(', ')}`);
    process.exit(1);
  }
  console.log(`- ${name}`);
  await snap(page, name, screen);
}

await browser.close();
console.log('done.');
