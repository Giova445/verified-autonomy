import { createRequire } from "node:module";
import { createServer } from "node:http";
import { createServer as createTcpServer } from "node:net";
import { readFileSync, existsSync, mkdtempSync, writeFileSync, rmSync, readdirSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, isAbsolute } from "node:path";

const require_ = createRequire(import.meta.url);

const EXPECTED_CONTROLS = 32;
const CANNOT_RUN = 75;
const DEFAULT_TIMEOUT = 5000;
const SETTLE_MS = 800;
const POLL_MS = 50;
const ENV_ERROR = /ERR_(CONNECTION_REFUSED|CONNECTION_RESET|CONNECTION_CLOSED|CONNECTION_ABORTED|CONNECTION_TIMED_OUT|SOCKET_NOT_CONNECTED|EMPTY_RESPONSE|NAME_NOT_RESOLVED|ADDRESS_UNREACHABLE|INTERNET_DISCONNECTED)|Timeout \d+ms exceeded/;

class EnvError extends Error {}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const firstLine = (e) => String(e?.message ?? e).split("\n")[0];
const navTimeout = () => Number(process.env.ACCEPT_NAV_TIMEOUT) || 30000;
const done = (detail) => ({ ok: true, detail });

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

const missing = (sel) => ({ ok: false, detail: `no element matches ${sel}` });

async function onElement(page, sel, judge) {
  if (await page.locator(sel).count() === 0) return missing(sel);
  return judge(page.locator(sel).first());
}

const CHECKS = {
  visible: (page, arg) => onElement(page, arg, async (el) => {
    const on = await el.isVisible();
    return { ok: on, detail: on ? `${arg} is visible` : `${arg} exists but is not visible` };
  }),
  async hidden(page, arg) {
    if (await page.locator(arg).count() === 0) return done(`${arg} is absent`);
    const on = await page.locator(arg).first().isVisible();
    return { ok: !on, detail: on ? `${arg} is visible and should not be` : `${arg} is hidden` };
  },
  text: (page, { selector, equals, contains }) => onElement(page, selector, async (el) => {
    const got = ((await el.textContent()) || "").trim();
    if (equals !== undefined)
      return { ok: got === equals, detail: `${selector} text is ${JSON.stringify(got)}, expected ${JSON.stringify(equals)}` };
    if (contains !== undefined)
      return { ok: got.includes(contains), detail: `${selector} text is ${JSON.stringify(got)}, expected to contain ${JSON.stringify(contains)}` };
    return { ok: false, final: true, detail: "text assertion needs 'equals' or 'contains'" };
  }),
  enabled: (page, arg) => onElement(page, arg, async (el) => {
    const on = await el.isEnabled();
    return { ok: on, detail: on ? `${arg} is enabled` : `${arg} is disabled and should not be` };
  }),
  disabled: (page, arg) => onElement(page, arg, async (el) => {
    const off = await el.isDisabled();
    return { ok: off, detail: off ? `${arg} is disabled` : `${arg} is enabled and should not be` };
  }),
  async count(page, { selector, equals }) {
    const got = await page.locator(selector).count();
    return { ok: got === equals, detail: `${selector} matched ${got}, expected ${equals}` };
  },
  async consoleClean(page, _arg, ctx) {
    const errs = ctx.consoleErrors;
    return { ok: errs.length === 0, final: true, detail: errs.length ? `${errs.length} console error(s): ${errs[0]}` : "no console errors" };
  },
  async noOverflow(page, arg) {
    const width = arg?.width || 375;
    await page.setViewportSize({ width, height: arg?.height || 812 });
    const over = await page.evaluate(() =>
      document.documentElement.scrollWidth > document.documentElement.clientWidth);
    return { ok: !over, detail: over ? `content overflows horizontally at ${width}px` : `no horizontal overflow at ${width}px` };
  },
  focusable: (page, arg) => onElement(page, arg, async () => {
    const reached = await page.evaluate((sel) => {
      const el = document.querySelector(sel);
      if (!el) return false;
      el.focus();
      return document.activeElement === el;
    }, arg);
    return { ok: reached, detail: reached ? `${arg} takes focus` : `${arg} cannot take focus` };
  }),
  async url(page, { equals, contains }) {
    const now = new URL(page.url());
    const shown = equals?.startsWith("/") ? now.pathname + now.search : now.href;
    if (equals !== undefined) return { ok: shown === equals, detail: `url is ${shown}, expected ${equals}` };
    if (contains !== undefined) return { ok: now.href.includes(contains), detail: `url is ${now.href}, expected to contain ${contains}` };
    return { ok: false, final: true, detail: "url assertion needs 'equals' or 'contains'" };
  },
};

const isStable = (kind, arg) =>
  kind === "hidden" || kind === "consoleClean" || kind === "noOverflow" || (kind === "count" && arg?.equals === 0);

async function navigate(page, url, timeout) {
  try {
    const resp = await page.goto(url, { waitUntil: "load", timeout });
    if (resp && !resp.ok() && /^https?:/.test(url)) return { ok: false, detail: `HTTP ${resp.status()} from ${url}` };
    return done(`opened ${url}`);
  } catch (e) {
    if (ENV_ERROR.test(firstLine(e))) throw new EnvError(firstLine(e));
    throw e;
  }
}

const ROUTE_KEYS = ["match", "json", "body", "contentType", "status", "delay"];
const isRoute = (step) => Boolean(step) && typeof step === "object" && !Array.isArray(step) && "route" in step;
const need = (ok, why) => { if (!ok) throw new Error(why); };

function routeSpec(arg, base) {
  need(arg && typeof arg === "object" && !Array.isArray(arg), "the argument must be an object such as {match, json, status, delay}");
  const unknown = Object.keys(arg).filter((k) => !ROUTE_KEYS.includes(k));
  need(unknown.length === 0, `unknown ${JSON.stringify(unknown)}; a route takes ${ROUTE_KEYS.join(", ")}`);
  const { match, json, body, contentType, status, delay = 0 } = arg;
  need(typeof match === "string" && match !== "", `'match' must be a non-empty URL pattern such as "**/api/items*"`);
  need(json !== undefined || body !== undefined || status !== undefined, "give at least one of 'json', 'body' or 'status'");
  need(json === undefined || body === undefined, "give 'json' or 'body', not both");
  need(body === undefined || typeof body === "string", "'body' must be a string; use 'json' for data");
  need(contentType === undefined || (typeof contentType === "string" && body !== undefined), "'contentType' must be a string and goes with 'body'");
  need(status === undefined || (Number.isInteger(status) && status >= 100 && status <= 599), "'status' must be an integer from 100 to 599");
  need(Number.isFinite(delay) && delay >= 0, "'delay' must be a number of milliseconds, 0 or more");
  const pattern = match.startsWith("/") && /^https?:/.test(base) ? new URL(base).origin + match : match;
  return { match, pattern, delay, response: { status, ...(json !== undefined ? { json, contentType: "application/json" } : { body: body ?? "", contentType }) } };
}

const ACTIONS = {
  async route(page, arg, { base, routes }) {
    const { match, pattern, delay, response } = routeSpec(arg, base);
    const entry = { match, hits: 0 };
    await page.route(pattern, async (r) => {
      entry.hits++;
      if (delay) await sleep(delay);
      await r.fulfill(response);
    });
    routes.push(entry);
    return done(`${match} answers ${response.status ?? 200}${delay ? ` after ${delay} ms` : ""}`);
  },
  async fill(page, { selector, value }, { timeout }) {
    await page.locator(selector).first().fill(String(value ?? ""), { timeout });
    return done(`filled ${selector}`);
  },
  async click(page, arg, { timeout }) {
    await page.locator(arg).first().click({ timeout });
    return done(`clicked ${arg}`);
  },
  async press(page, arg, { timeout }) {
    const { selector, key } = typeof arg === "string" ? { key: arg } : arg;
    if (selector) await page.locator(selector).first().press(key, { timeout });
    else await page.keyboard.press(key);
    return done(`pressed ${key}${selector ? ` on ${selector}` : ""}`);
  },
  async goto(page, arg, { timeout, base }) {
    return navigate(page, new URL(arg, base).href, timeout);
  },
  async waitFor(page, arg, { timeout }) {
    const { selector, state = "visible" } = typeof arg === "string" ? { selector: arg } : arg;
    await page.locator(selector).first().waitFor({ state, timeout });
    return done(`${selector} is ${state}`);
  },
};

async function settle(evaluate, timeout, stableFor) {
  const start = Date.now();
  let since = null;
  let last = { ok: false, detail: "never evaluated" };
  for (;;) {
    try { last = await evaluate(); } catch (e) { last = { ok: false, detail: `assertion threw: ${firstLine(e)}` }; }
    const now = Date.now();
    if (last.ok) {
      since ??= now;
      if (now - since >= stableFor) return last;
    } else {
      if (last.final) return last;
      since = null;
    }
    if (now - start >= timeout && since === null) return { ok: false, detail: `${last.detail} (after ${timeout} ms)` };
    await sleep(POLL_MS);
  }
}

async function runStep(page, step, ctx) {
  if (!step || typeof step !== "object" || Array.isArray(step)) return { ok: false, detail: "step is not an object", kind: "step" };
  const kinds = Object.keys(step).filter((k) => k !== "timeout" && k !== "settle");
  const kind = kinds[0];
  if (kinds.length !== 1) return { ok: false, detail: `a step needs exactly one action or assertion, got ${JSON.stringify(Object.keys(step))}`, kind: "step" };
  const timeout = Number(step.timeout ?? DEFAULT_TIMEOUT);
  if (!(timeout > 0)) return { ok: false, detail: "timeout must be a positive number of milliseconds", kind };
  const arg = step[kind];
  if (kind in ACTIONS) {
    try { return { ...(await ACTIONS[kind](page, arg, { timeout, base: ctx.base, routes: ctx.routes })), kind, action: true }; }
    catch (e) {
      if (e instanceof EnvError) throw e;
      return { ok: false, detail: `cannot ${kind}: ${firstLine(e)}`, kind, action: true };
    }
  }
  if (!(kind in CHECKS)) return { ok: false, detail: `unknown assertion ${JSON.stringify(kind)}`, kind };
  const stableFor = isStable(kind, arg) ? (step.settle ?? SETTLE_MS) : 0;
  return { ...(await settle(() => CHECKS[kind](page, arg, ctx), timeout, stableFor)), kind };
}

function fail(msg, code = 2) { console.error(msg); process.exit(code); }

async function drive(target, checks, pw = loadPlaywright()) {
  if (!pw) {
    console.log("  CANNOT RUN  playwright is not resolvable. Set PLAYWRIGHT_PATH or install it (npm i -D playwright)");
    return CANNOT_RUN;
  }
  const url = /^https?:|^file:/.test(target)
    ? target
    : "file://" + (isAbsolute(target) ? target : resolve(process.cwd(), target));
  const ctx = { consoleErrors: [], base: url, routes: [] };
  let browser;
  let failures = 0;
  try {
    browser = await pw.chromium.launch();
    const page = await browser.newPage(checks.some(isRoute) ? { serviceWorkers: "block" } : {});
    page.on("console", (m) => { if (m.type() === "error") ctx.consoleErrors.push(m.text()); });
    page.on("pageerror", (e) => ctx.consoleErrors.push(String(e)));
    const firstOther = checks.findIndex((s) => !isRoute(s));
    let loaded = false;
    let complete = true;
    const load = async () => {
      loaded = true;
      const first = await navigate(page, url, navTimeout());
      if (!first.ok) { console.log(`  FAIL  page load: ${first.detail}`); failures++; }
      return first.ok;
    };
    for (let i = 0; complete && i < checks.length; i++) {
      if (i === firstOther) { complete = await load(); if (!complete) break; }
      const r = await runStep(page, checks[i], ctx);
      console.log(`  ${r.ok ? "ok  " : "FAIL"}  ${r.kind}: ${r.detail}`);
      if (r.ok) continue;
      failures++;
      if (!r.action) continue;
      complete = false;
      if (i + 1 < checks.length) console.log(`  skip  ${checks.length - i - 1} step(s) after the failed ${r.kind}`);
    }
    if (!loaded && failures === 0) complete = await load();
    for (const r of complete ? ctx.routes : []) {
      if (r.hits > 0) continue;
      console.log(`  FAIL  route: ${r.match} never matched a request`);
      failures++;
    }
    if (process.env.ACCEPT_SHOT) {
      try {
        await page.screenshot({ path: process.env.ACCEPT_SHOT, fullPage: true });
        console.log(`  shot  ${process.env.ACCEPT_SHOT}`);
      } catch (e) { console.log(`  note  no screenshot: ${firstLine(e)}`); }
    }
  } catch (e) {
    const environment = e instanceof EnvError || !browser;
    console.log(`  ${environment ? "CANNOT RUN" : "FAIL"}  could not ${browser ? "drive" : "launch a browser for"} ${target}: ${firstLine(e)}`);
    return environment ? CANNOT_RUN : 1;
  } finally {
    await browser?.close().catch(() => {});
  }
  return failures === 0 ? 0 : 1;
}

const PAGES = {
  "/list.html": `<ul id="l"></ul><script>fetch("/slow.json").then(r=>r.json()).then(a=>{l.innerHTML=a.map(x=>'<li class="item">'+x+'</li>').join("")})</script>`,
  "/error-later.html": `<h1>ok</h1><script>setTimeout(()=>document.body.insertAdjacentHTML("beforeend",'<p class="error">boom</p>'),400)</script>`,
  "/login.html": `<input id="email"><button id="go">Go</button><script>go.onclick=()=>setTimeout(()=>{location.href="/done.html"},400)</script>`,
  "/done.html": `<h1 id="done">Done</h1>`,
  "/keys.html": `<input id="k"><p id="pressed" hidden>yes</p><script>k.onkeydown=e=>{if(e.key==="Enter")pressed.hidden=false}</script>`,
  "/items.html": `<p id="loading">Loading</p><ul id="l"></ul><p id="empty" hidden>Nothing here yet</p><p id="error" hidden>Could not load items</p><script>fetch("/api/items").then(r=>{if(!r.ok)throw r.status;return r.json()}).then(a=>{if(a.length)l.innerHTML=a.map(x=>'<li class="item">'+x+'</li>').join("");else empty.hidden=false}).catch(()=>{error.hidden=false}).finally(()=>{loading.hidden=true})</script>`,
  "/late.html": `<script>setTimeout(()=>document.body.insertAdjacentHTML("beforeend",'<p id="late">x</p>'),5600)</script>`,
};

function fixtureServer() {
  const server = createServer((req, res) => {
    if (req.url === "/hang") return;
    if (req.url === "/api/items") return void (res.setHeader("content-type", "application/json"), res.end('["a","b","c"]'));
    if (req.url === "/slow.json") return void setTimeout(() => { res.setHeader("content-type", "application/json"); res.end('["a","b","c"]'); }, 400);
    const page = PAGES[req.url];
    res.statusCode = page ? 200 : 404;
    res.setHeader("content-type", "text/html");
    res.end(page ?? "missing");
  });
  return new Promise((ok) => server.listen(0, "127.0.0.1", () => ok(server)));
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
  const fast = 300;

  chk("disabled holds on the whole artifact", await run(whole, [{ disabled: "button" }]) === 0);
  chk("disabled FAILS on the broken artifact", await run(broken, [{ disabled: "button", timeout: fast }]) === 1);

  chk("text equals discriminates",
    await run(whole, [{ text: { selector: "#t", equals: "Sign in" } }]) === 0 &&
    await run(whole, [{ text: { selector: "#t", equals: "Register", }, timeout: fast }]) === 1);

  chk("a selector that matches nothing fails", await run(whole, [{ visible: "#nope", timeout: fast }]) === 1);

  const noisy = join(tmp, "noisy.html");
  writeFileSync(noisy, `<h1>x</h1><script>throw new Error("boom")</script>`);
  chk("consoleClean discriminates a page that throws",
    await run(whole, [{ consoleClean: true }]) === 0 &&
    await run(noisy, [{ consoleClean: true }]) === 1);

  const wide = join(tmp, "wide.html");
  writeFileSync(wide, `<div style="width:2000px;height:10px"></div>`);
  chk("noOverflow discriminates a page that overflows on mobile",
    await run(whole, [{ noOverflow: { width: 375 } }]) === 0 &&
    await run(wide, [{ noOverflow: { width: 375 }, timeout: fast }]) === 1);

  chk("a missing local file still FAILS: the artifact itself is absent",
    await run(join(tmp, "does-not-exist.html"), [{ visible: "h1" }]) === 1);

  const live = join(tmp, "live.html");
  const stuck = join(tmp, "stuck.html");
  const form = (wire) =>
    `<form><input id="u"><input id="p"><button id="go" type="submit" disabled>Go</button></form>
     <script>${wire}</script>`;
  writeFileSync(live, form(
    `const f=()=>{go.disabled=!(u.value&&p.value)};u.oninput=f;p.oninput=f;`));
  writeFileSync(stuck, form(``));
  const fillBoth = (timeout) => [
    { fill: { selector: "#u", value: "a@b.c" } },
    { fill: { selector: "#p", value: "hunter2" } },
    { enabled: "#go", timeout },
  ];
  chk("an interaction-gated outcome discriminates two pages that paint identically",
    await run(live, fillBoth(fast)) === 0 && await run(stuck, fillBoth(fast)) === 1);

  chk("a fill against a missing selector fails",
    await run(live, [{ fill: { selector: "#nope", value: "x" }, timeout: fast }]) === 1);

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

  const shot = join(tmp, "shot.png");
  process.env.ACCEPT_SHOT = shot;
  const shotRc = await run(live, [{ visible: "#go" }]);
  delete process.env.ACCEPT_SHOT;
  chk("ACCEPT_SHOT saves a screenshot of the driven page", shotRc === 0 && existsSync(shot));

  const server = await fixtureServer();
  const base = `http://127.0.0.1:${server.address().port}`;
  const slowDefault = (async () => {
    const t0 = Date.now();
    const rc = await run(`${base}/late.html`, [{ visible: "#late" }]);
    return { rc, took: Date.now() - t0 };
  })();

  chk("a list rendered after a 400 ms fetch passes: assertions wait",
    await run(`${base}/list.html`, [{ visible: ".item" }, { count: { selector: ".item", equals: 3 } },
      { text: { selector: ".item", equals: "a" } }]) === 0);
  chk("an error shown after 400 ms fails `hidden`: an absence must hold, not just glance true",
    await run(`${base}/error-later.html`, [{ hidden: ".error", timeout: 1500 }]) === 1 &&
    await run(`${base}/error-later.html`, [{ hidden: ".nothing-here" }]) === 0);
  chk("a click that redirects after 400 ms, then `hidden #email`, passes",
    await run(`${base}/login.html`, [{ click: "#go" }, { hidden: "#email" }, { url: { contains: "/done.html" } }]) === 0);
  chk("goto is relative to the target; url, waitFor and press work",
    await run(`${base}/login.html`, [{ url: { equals: "/login.html" } }, { goto: "/keys.html" },
      { press: { selector: "#k", key: "Enter" } }, { waitFor: "#pressed" }, { url: { equals: "/keys.html" } },
      { goto: "/done.html" }, { text: { selector: "#done", contains: "Done" } }]) === 0 &&
    await run(`${base}/login.html`, [{ url: { equals: "/nowhere", }, timeout: fast }]) === 1);
  const t0 = Date.now();
  chk("a per-assertion `timeout` bounds the wait",
    await run(`${base}/list.html`, [{ visible: ".ghost", timeout: 400 }]) === 1 && Date.now() - t0 < 4000);
  const lines = [];
  const say = console.log;
  console.log = (m) => lines.push(m);
  const skipRc = await run(`${base}/list.html`, [{ click: "#nope", timeout: fast }, { visible: ".item" }]);
  console.log = say;
  chk("a failed action skips the steps that depended on it",
    skipRc === 1 && lines.some((l) => l.includes("skip")) && !lines.some((l) => l.includes("visible:")));
  chk("a step with two actions, or an unknown one, fails rather than being half-run",
    await run(`${base}/list.html`, [{ visible: ".item", hidden: ".item" }]) === 1 &&
    await run(`${base}/list.html`, [{ levitates: ".item" }]) === 1);

  chk("connection refused is CANNOT RUN (75), not a product failure",
    await run("http://127.0.0.1:59173/", [{ visible: "body" }]) === CANNOT_RUN);
  process.env.ACCEPT_NAV_TIMEOUT = "700";
  const navRc = await run(`${base}/hang`, [{ visible: "body" }]);
  delete process.env.ACCEPT_NAV_TIMEOUT;
  chk("a navigation that times out is CANNOT RUN (75)", navRc === CANNOT_RUN);
  const resetter = createTcpServer((socket) => socket.resetAndDestroy());
  await new Promise((ok) => resetter.listen(0, "127.0.0.1", ok));
  const resetRc = await run(`http://127.0.0.1:${resetter.address().port}/`, [{ visible: "body" }]);
  resetter.close();
  chk("a connection that is reset is CANNOT RUN (75)", resetRc === CANNOT_RUN);
  const gotoFailing = (message) => ({ goto: async () => { throw new Error(`page.goto: net::${message} at http://x/`); } });
  const classified = async (message) => navigate(gotoFailing(message), "http://x/", 1).then(() => "none", (e) => e instanceof EnvError ? "environment" : "product");
  chk("a socket that is not connected or a connection that is aborted is an environment error; a certificate error is not",
    [await classified("ERR_SOCKET_NOT_CONNECTED"), await classified("ERR_CONNECTION_ABORTED"), await classified("ERR_CERT_AUTHORITY_INVALID")].join(" ") ===
    "environment environment product");
  chk("a name that does not resolve is CANNOT RUN (75)",
    await run("http://no-such-host.invalid/", [{ visible: "body" }]) === CANNOT_RUN);
  const noChromium = { chromium: { launch: async () => { throw new Error("Executable doesn't exist at /nowhere"); } } };
  chk("a Chromium that cannot launch is CANNOT RUN (75)",
    await drive(whole, [{ visible: "h1" }], noChromium) === CANNOT_RUN);
  chk("a 404 from the page under test is a FAIL, not CANNOT RUN",
    await drive(`${base}/missing.html`, [{ visible: "body" }]) === 1);

  const items = `${base}/items.html`;
  const api = "**/api/items";
  const via = (spec, ...steps) => [{ route: { match: api, ...spec } }, ...steps];
  const quick = (s) => ("visible" in s || "hidden" in s ? { ...s, timeout: 100 } : s);
  const outcome = async (steps) => await run(items, steps) === 0 && await run(items, steps.filter((s) => !s.route).map(quick)) === 1;
  chk("route: an outcome that passes only when the API returns empty fails without the route",
    await outcome(via({ json: [] }, { visible: "#empty" }, { hidden: ".item", settle: 100 })));
  chk("route: an outcome that passes only on a 500 shows the error state and fails without the route",
    await outcome(via({ status: 500, json: { error: "boom" } }, { visible: "#error" }, { hidden: ".item", settle: 100 })));
  chk("route: a delay makes the loading indicator observable; the outcome fails without the route",
    await outcome(via({ json: ["a"], delay: 900 }, { hidden: "#never", settle: 250 }, { visible: "#loading" }, { visible: ".item" })));
  const stacked = [...via({ json: [] }, { visible: "#empty" }), { route: { match: api, status: 503 } }, { goto: "/items.html" }, { visible: "#error" }];
  chk("route: one declared mid-run governs later requests and outranks an earlier route on the same pattern",
    await run(items, stacked) === 0 && await run(items, stacked.filter((_, i) => i !== 2).map(quick)) === 1);
  const attempt = (arg) => runStep({ route: async () => {} }, { route: arg }, { base, routes: [] });
  const invalid = await Promise.all([undefined, [], {}, { match: "", json: [] }, { match: api }, { match: api, json: [], typo: 1 },
    { match: api, json: [], body: "x" }, { match: api, status: 99 }, { match: api, json: [], delay: -1 }, { match: api, json: [], delay: "5" }].map(attempt));
  const valid = await Promise.all([{ match: api, json: [], status: 404, delay: 10 }, { match: "/api/x", body: "text", contentType: "text/plain" }, { match: api, json: null }].map(attempt));
  chk("route: invalid arguments fail the step with a reason, and a valid one is accepted",
    invalid.every((v) => !v.ok && v.detail.startsWith("cannot route: ")) && valid.every((v) => v.ok) &&
    await run(items, [{ route: { match: api, status: "500" } }, { visible: "#loading" }]) === 1);
  const seen = [];
  console.log = (m) => seen.push(m);
  const strayRc = await run(items, [{ route: { match: "**/api/itemz", json: [] } }, { visible: ".item" }]);
  console.log = say;
  chk("route: a route that no request matched fails the run, since the outcome never saw its state",
    strayRc === 1 && seen.some((l) => l.includes("never matched")) && await run(items, [{ route: { match: "/api/items", body: "[]", contentType: "application/json" } }, { visible: "#empty" }]) === 0);

  const late = await slowDefault;
  chk("the default wait is 5000 ms: an element that appears at 5.6 s is not waited for",
    late.rc === 1 && late.took >= 4800 && late.took < 9000);
  server.closeAllConnections();
  server.close();

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
