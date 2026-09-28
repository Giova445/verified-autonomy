import { createRequire } from "node:module";
import { readFileSync, existsSync, mkdtempSync, writeFileSync, rmSync, readdirSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, isAbsolute } from "node:path";

const require_ = createRequire(import.meta.url);

const EXPECTED_CONTROLS = 12;

function loadPlaywright(cwd = process.cwd()) {
  const roots = [];
  if (process.env.PLAYWRIGHT_PATH) roots.push(process.env.PLAYWRIGHT_PATH);
  roots.push("playwright");
  roots.push(join(cwd, "node_modules", "playwright"));
  for (const d of readdirSync(cwd, { withFileTypes: true })) {
    if (d.isDirectory() && d.name !== "node_modules" && !d.name.startsWith("."))
      roots.push(join(cwd, d.name, "node_modules", "playwright"));
  }

  for (const r of roots) {
    try { return require_(r); } catch { /* try the next */ }
  }
  return null;
}

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
  if (!pw) fail("drive: playwright is not resolvable. Set PLAYWRIGHT_PATH or install it. " +
                "Refusing to report on a page this cannot open.", 2);

  const browser = await pw.chromium.launch();
  const ctx = { consoleErrors: [] };
  const page = await browser.newPage();
  page.on("console", (m) => { if (m.type() === "error") ctx.consoleErrors.push(m.text()); });
  page.on("pageerror", (e) => ctx.consoleErrors.push(String(e)));

  let failures = 0;
  let unreachable = false;
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
    if (process.env.ACCEPT_SHOT) {
      await page.screenshot({ path: process.env.ACCEPT_SHOT, fullPage: true });
      console.log(`  shot  ${process.env.ACCEPT_SHOT}`);
    }
  } catch (e) {
    unreachable = /ERR_CONNECTION_REFUSED|ERR_NAME_NOT_RESOLVED|ERR_ADDRESS_UNREACHABLE|ERR_CONNECTION_RESET/.test(e.message);
    console.log(`  ${unreachable ? "CANNOT RUN" : "FAIL"}  could not drive ${target}: ${e.message.split("\n")[0]}`);
    failures++;
  } finally {
    await browser.close();
  }
  if (unreachable) return 2;
  return failures === 0 ? 0 : 1;
}

async function selftest() {
  const tmp = mkdtempSync(join(tmpdir(), "drive-selftest-"));
  let passed = 0, ran = 0;
  const chk = (label, cond) => { ran++; if (cond) { passed++; console.log(`  ok    ${label}`); } else console.log(`  FAIL  ${label}`); };

  const whole = join(tmp, "whole.html");
  const broken = join(tmp, "broken.html");
  writeFileSync(whole,
    `<h1 id="t">Sign in</h1><form><input id="u"><button type="submit" disabled>Go</button></form>`);
  writeFileSync(broken,
    `<h1 id="t">Sign in</h1><form><input id="u"><button type="submit">Go</button></form>`);

  const run = async (file, checks) => await drive(file, checks);

  chk("disabled holds on the whole artifact", await run(whole, [{ disabled: "button" }]) === 0);
  chk("disabled FAILS on the broken artifact", await run(broken, [{ disabled: "button" }]) === 1);

  chk("text equals discriminates",
    await run(whole, [{ text: { selector: "#t", equals: "Sign in" } }]) === 0 &&
    await run(whole, [{ text: { selector: "#t", equals: "Register" } }]) === 1);

  chk("a selector that matches nothing fails", await run(whole, [{ visible: "#nope" }]) === 1);

  const noisy = join(tmp, "noisy.html");
  writeFileSync(noisy, `<h1>x</h1><script>throw new Error("boom")</script>`);
  chk("consoleClean discriminates a page that throws",
    await run(whole, [{ consoleClean: true }]) === 0 &&
    await run(noisy, [{ consoleClean: true }]) === 1);

  const wide = join(tmp, "wide.html");
  writeFileSync(wide, `<div style="width:2000px;height:10px"></div>`);
  chk("noOverflow discriminates a page that overflows on mobile",
    await run(whole, [{ noOverflow: { width: 375 } }]) === 0 &&
    await run(wide, [{ noOverflow: { width: 375 } }]) === 1);

  chk("an unopenable target fails rather than passing",
    await run(join(tmp, "does-not-exist.html"), [{ visible: "h1" }]) === 1);

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

  chk("a fill against a missing selector fails",
    await run(live, [{ fill: { selector: "#nope", value: "x" } }]) === 1);

  const mono = join(tmp, "mono", "web", "node_modules", "playwright");
  mkdirSync(mono, { recursive: true });
  writeFileSync(join(mono, "package.json"), '{"name":"playwright","main":"index.js"}');
  writeFileSync(join(mono, "index.js"), "module.exports = { monorepoCopy: true };");
  const saved = process.env.PLAYWRIGHT_PATH;
  delete process.env.PLAYWRIGHT_PATH;
  const found = loadPlaywright(join(tmp, "mono"));
  if (saved !== undefined) process.env.PLAYWRIGHT_PATH = saved;
  chk("Playwright installed one directory down is found",
    found !== null && (found.monorepoCopy === true || typeof found.chromium === "object"));

  chk("a server that is not running is CANNOT RUN (exit 2), not a product failure",
    await run("http://127.0.0.1:59173/", [{ visible: "body" }]) === 2);

  const shot = join(tmp, "shot.png");
  process.env.ACCEPT_SHOT = shot;
  const shotRc = await run(live, [{ visible: "#go" }]);
  delete process.env.ACCEPT_SHOT;
  chk("ACCEPT_SHOT saves a screenshot of the driven page", shotRc === 0 && existsSync(shot));

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
