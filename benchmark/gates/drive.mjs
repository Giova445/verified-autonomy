// drive.mjs — assert things about a deliverable that only exist when it is RUNNING.
//
//   node drive.mjs <target> <checks.json>   drive the target, assert, exit 0/1
//   node drive.mjs --self-test              run the positive controls
//
// WHY A SEPARATE DRIVER
//
// acceptance.py runs shell commands and judges exit codes. That is deliberately dumb: it
// works for any deliverable in any language. But the deliverable people actually complain
// about is a page, and "the unit tests pass" has never once caught a login form that
// renders with the submit button permanently disabled. Something has to open it.
//
// This is that something, and it is a COMMAND, not an agent capability. A gate that says
// "the agent should look at the page" is persuasion, and persuasion is exactly what failed:
// it is why a green run and a broken login page coexist. Codex gets this for free for the
// same reason — it is a shell command, not an MCP tool.
//
// WHY THE LIBRARY AND NOT `playwright test`
//
// A standing note on this host read "e2e is dead here". That is true of the RUNNER, which
// loads playwright.config.ts through Node's module customization hooks and dies before
// reaching a spec. The LIBRARY launches Chromium and drives a page fine — verified
// 2026-09-15 on node v24.1.0 / playwright 1.61.0. Designing around the broader claim would
// have thrown away the only mechanical route to seeing the deliverable.
//
// THE VOCABULARY IS THE MANUAL QA PASS, WRITTEN DOWN ONCE
//
// The defects a person finds in five minutes are not exotic; they repeat. Empty state,
// error state, disabled control, console noise, a layout that overflows on a phone, a
// control no keyboard can reach. Those are the assertions below. Nothing here names a
// product: a project declares WHICH apply to WHICH selector, in its own contract.
//
// FAIL CLOSED, EVERYWHERE
//
// A missing Playwright, a page that will not load, an unreadable checks file and an empty
// checks file all exit non-zero. A driver that exits 0 when it could not look is worse than
// no driver, because the gate above it reports green.
import { createRequire } from "node:module";
import { readFileSync, existsSync, mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, isAbsolute } from "node:path";

const require_ = createRequire(import.meta.url);

// Declared as a literal beside the assertions it counts. Deriving it from the dispatch
// table would mean deleting an assertion also deletes the expectation that it exists.
const EXPECTED_CONTROLS = 9;

function loadPlaywright() {
  const roots = [];
  if (process.env.PLAYWRIGHT_PATH) roots.push(process.env.PLAYWRIGHT_PATH);
  roots.push("playwright");
  // The project's own install, and nothing else. An earlier version also reached into a
  // specific checkout under $HOME — which made this pass on one laptop and exit 2 in CI and
  // on every other machine. A resolution path that only works where it was written is worse
  // than no fallback: it hides the missing dependency from the person who could install it.
  roots.push(join(process.cwd(), "node_modules", "playwright"));

  for (const r of roots) {
    try { return require_(r); } catch { /* try the next */ }
  }
  return null;
}

// ------------------------------------------------------------------ assertions
// Each returns { ok, detail }. They never throw: a selector that matches nothing is a
// FAILED assertion, not a crashed driver, because a crash reads as infrastructure trouble
// and gets retried instead of fixed.
const ASSERTIONS = {
  async visible(page, arg) {
    const n = await page.locator(arg).count();
    if (n === 0) return { ok: false, detail: `no element matches ${arg}` };
    const vis = await page.locator(arg).first().isVisible();
    return { ok: vis, detail: vis ? `${arg} is visible` : `${arg} exists but is not visible` };
  },
  async hidden(page, arg) {
    const n = await page.locator(arg).count();
    if (n === 0) return { ok: true, detail: `${arg} is absent` };
    const vis = await page.locator(arg).first().isVisible();
    return { ok: !vis, detail: vis ? `${arg} is visible and should not be` : `${arg} is hidden` };
  },
  async text(page, arg) {
    const { selector, equals, contains } = arg;
    if (await page.locator(selector).count() === 0)
      return { ok: false, detail: `no element matches ${selector}` };
    const got = (await page.locator(selector).first().textContent() || "").trim();
    if (equals !== undefined)
      return { ok: got === equals, detail: `${selector} text is ${JSON.stringify(got)}, expected ${JSON.stringify(equals)}` };
    if (contains !== undefined)
      return { ok: got.includes(contains), detail: `${selector} text is ${JSON.stringify(got)}, expected to contain ${JSON.stringify(contains)}` };
    return { ok: false, detail: "text assertion needs 'equals' or 'contains'" };
  },
  async enabled(page, arg) {
    if (await page.locator(arg).count() === 0)
      return { ok: false, detail: `no element matches ${arg}` };
    const on = await page.locator(arg).first().isEnabled();
    return { ok: on, detail: on ? `${arg} is enabled` : `${arg} is disabled and should not be` };
  },
  async disabled(page, arg) {
    if (await page.locator(arg).count() === 0)
      return { ok: false, detail: `no element matches ${arg}` };
    const off = await page.locator(arg).first().isDisabled();
    return { ok: off, detail: off ? `${arg} is disabled` : `${arg} is enabled and should not be` };
  },
  async count(page, arg) {
    const got = await page.locator(arg.selector).count();
    return { ok: got === arg.equals, detail: `${arg.selector} matched ${got}, expected ${arg.equals}` };
  },
  async consoleClean(page, _arg, ctx) {
    const errs = ctx.consoleErrors;
    return { ok: errs.length === 0, detail: errs.length ? `${errs.length} console error(s): ${errs[0]}` : "no console errors" };
  },
  async noOverflow(page, arg) {
    const width = arg?.width || 375;
    await page.setViewportSize({ width, height: arg?.height || 812 });
    const over = await page.evaluate(() =>
      document.documentElement.scrollWidth > document.documentElement.clientWidth);
    return { ok: !over, detail: over ? `content overflows horizontally at ${width}px` : `no horizontal overflow at ${width}px` };
  },
  // --- actions -------------------------------------------------------------
  // The checks list is ORDERED, so a fill or a click turns it into a short script. Without
  // these the driver can only see the first paint, and most of what a person finds by hand
  // is on the other side of an interaction: the button that never enables, the error that
  // never renders, the spinner that never stops. A missing target is a FAILED step, not a
  // crash — and every later assertion then runs against the state the page really is in.
  async fill(page, arg) {
    const { selector, value } = arg;
    if (await page.locator(selector).count() === 0)
      return { ok: false, detail: `cannot fill ${selector} — no element matches` };
    await page.locator(selector).first().fill(String(value ?? ""));
    return { ok: true, detail: `filled ${selector}` };
  },
  async click(page, arg) {
    if (await page.locator(arg).count() === 0)
      return { ok: false, detail: `cannot click ${arg} — no element matches` };
    await page.locator(arg).first().click();
    return { ok: true, detail: `clicked ${arg}` };
  },
  async focusable(page, arg) {
    if (await page.locator(arg).count() === 0)
      return { ok: false, detail: `no element matches ${arg}` };
    const reached = await page.evaluate((sel) => {
      const el = document.querySelector(sel);
      if (!el) return false;
      el.focus();
      return document.activeElement === el;
    }, arg);
    return { ok: reached, detail: reached ? `${arg} takes focus` : `${arg} cannot take focus` };
  },
};

function fail(msg, code = 2) { console.error(msg); process.exit(code); }

async function drive(target, checks) {
  const pw = loadPlaywright();
  // Never exit 0 here. A gate above this would read it as "the page is fine".
  if (!pw) fail("drive: playwright is not resolvable. Set PLAYWRIGHT_PATH or install it. " +
                "Refusing to report on a page this cannot open.", 2);

  const browser = await pw.chromium.launch();
  const ctx = { consoleErrors: [] };
  const page = await browser.newPage();
  page.on("console", (m) => { if (m.type() === "error") ctx.consoleErrors.push(m.text()); });
  page.on("pageerror", (e) => ctx.consoleErrors.push(String(e)));

  let failures = 0;
  try {
    const url = /^https?:|^file:/.test(target)
      ? target
      : "file://" + (isAbsolute(target) ? target : resolve(process.cwd(), target));
    const resp = await page.goto(url, { waitUntil: "load" });
    if (resp && !resp.ok() && /^https?:/.test(url)) {
      console.log(`  FAIL  page load — HTTP ${resp.status()} from ${url}`);
      failures++;
    }
    for (const c of checks) {
      const [kind] = Object.keys(c);
      const fn = ASSERTIONS[kind];
      if (!fn) { console.log(`  FAIL  unknown assertion ${JSON.stringify(kind)}`); failures++; continue; }
      let r;
      try { r = await fn(page, c[kind], ctx); }
      catch (e) { r = { ok: false, detail: `assertion threw: ${e.message}` }; }
      console.log(`  ${r.ok ? "ok  " : "FAIL"}  ${kind}: ${r.detail}`);
      if (!r.ok) failures++;
    }
  } catch (e) {
    console.log(`  FAIL  could not drive ${target}: ${e.message}`);
    failures++;
  } finally {
    await browser.close();
  }
  return failures === 0 ? 0 : 1;
}

// ------------------------------------------------------------------ controls
async function selftest() {
  const tmp = mkdtempSync(join(tmpdir(), "drive-selftest-"));
  let passed = 0, ran = 0;
  const chk = (label, cond) => { ran++; if (cond) { passed++; console.log(`  ok    ${label}`); } else console.log(`  FAIL  ${label}`); };

  const whole = join(tmp, "whole.html");
  const broken = join(tmp, "broken.html");
  writeFileSync(whole,
    `<h1 id="t">Sign in</h1><form><input id="u"><button type="submit" disabled>Go</button></form>`);
  // The same page with the ONE property under test inverted. Every control below drives
  // this, so each assertion is shown able to tell the two apart.
  writeFileSync(broken,
    `<h1 id="t">Sign in</h1><form><input id="u"><button type="submit">Go</button></form>`);

  const run = async (file, checks) => await drive(file, checks);

  // 1/2 — the load-bearing pair. `disabled` must hold on the whole page and FAIL on the
  // broken one. An assertion that passes on both is not evidence of anything.
  chk("disabled holds on the whole artifact", await run(whole, [{ disabled: "button" }]) === 0);
  chk("disabled FAILS on the broken artifact", await run(broken, [{ disabled: "button" }]) === 1);

  // 3 — text content, both directions in one run.
  chk("text equals discriminates",
    await run(whole, [{ text: { selector: "#t", equals: "Sign in" } }]) === 0 &&
    await run(whole, [{ text: { selector: "#t", equals: "Register" } }]) === 1);

  // 4 — a selector matching nothing is a FAILED assertion, not a crash and not a pass.
  // The natural bug here is `count() === 0` short-circuiting to success.
  chk("a selector that matches nothing fails", await run(whole, [{ visible: "#nope" }]) === 1);

  // 5 — console errors are caught. A page that throws on load looks fine to every static
  // gate in this repository.
  const noisy = join(tmp, "noisy.html");
  writeFileSync(noisy, `<h1>x</h1><script>throw new Error("boom")</script>`);
  chk("consoleClean discriminates a page that throws",
    await run(whole, [{ consoleClean: true }]) === 0 &&
    await run(noisy, [{ consoleClean: true }]) === 1);

  // 6 — horizontal overflow at a phone viewport.
  const wide = join(tmp, "wide.html");
  writeFileSync(wide, `<div style="width:2000px;height:10px"></div>`);
  chk("noOverflow discriminates a page that overflows on mobile",
    await run(whole, [{ noOverflow: { width: 375 } }]) === 0 &&
    await run(wide, [{ noOverflow: { width: 375 } }]) === 1);

  // 7 — a target that cannot be opened is a failure, never a pass. This is the case that
  // turns the whole gate vacuous if it is wrong.
  chk("an unopenable target fails rather than passing",
    await run(join(tmp, "does-not-exist.html"), [{ visible: "h1" }]) === 1);

  // 8 — the interactive case, which is where the hand-QA defects actually live. Two pages
  // that are IDENTICAL on first paint: both show a disabled submit. One enables it once the
  // fields are filled; the other never does. Every static gate in this repository sees the
  // same thing for both.
  const live = join(tmp, "live.html");
  const stuck = join(tmp, "stuck.html");
  const form = (wire) =>
    `<form><input id="u"><input id="p"><button id="go" type="submit" disabled>Go</button></form>
     <script>${wire}</script>`;
  writeFileSync(live, form(
    `const f=()=>{go.disabled=!(u.value&&p.value)};u.oninput=f;p.oninput=f;`));
  writeFileSync(stuck, form(``)); // the bug: nothing ever re-enables it
  const fillBoth = [
    { fill: { selector: "#u", value: "a@b.c" } },
    { fill: { selector: "#p", value: "hunter2" } },
    { enabled: "#go" },
  ];
  chk("an interaction-gated outcome discriminates two pages that paint identically",
    await run(live, fillBoth) === 0 && await run(stuck, fillBoth) === 1);

  // 9 — a step whose target is absent fails instead of being silently skipped. A skipped
  // fill would leave every later assertion judging the wrong page state, and the run would
  // still exit 0.
  chk("a fill against a missing selector fails",
    await run(live, [{ fill: { selector: "#nope", value: "x" } }]) === 1);

  rmSync(tmp, { recursive: true, force: true });
  if (ran !== EXPECTED_CONTROLS) { console.log(`  FAIL  ran ${ran} controls, expected ${EXPECTED_CONTROLS}`); passed = -1; }
  console.log("");
  if (passed === EXPECTED_CONTROLS) { console.log(`SELF-TEST PASSED  (${EXPECTED_CONTROLS} checks)`); return 0; }
  console.log(`SELF-TEST FAILED  (${passed} of ${EXPECTED_CONTROLS} checks)`);
  return 1;
}

const [, , a, b] = process.argv;
if (a === "--self-test" || a === "selftest") {
  process.exit(await selftest());
}
if (!a || !b) fail("usage: drive.mjs <target> <checks.json> | drive.mjs --self-test", 2);
if (!existsSync(b)) fail(`drive: checks file not found: ${b}`, 2);
let checks;
try { checks = JSON.parse(readFileSync(b, "utf-8")); }
catch (e) { fail(`drive: checks file will not parse: ${e.message}`, 2); }
if (!Array.isArray(checks) || checks.length === 0)
  fail("drive: checks file declares no assertions — that would pass without looking at anything", 2);
process.exit(await drive(a, checks));
