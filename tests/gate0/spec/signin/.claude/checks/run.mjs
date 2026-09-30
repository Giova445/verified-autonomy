import { spawn } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { scenarios } from "./scenarios.mjs";

const CANNOT_RUN = 75;
const CONTROL_STEP_TIMEOUT_MS = 800;
const UNTIMED_STEPS = ["goto", "route"];
const drive = join(dirname(fileURLToPath(import.meta.url)), "..", "gates", "drive.mjs");

const [mode, name] = process.argv.slice(2);
const scenario = scenarios[name];

const finish = (code, message) => {
  if (message) console.log(message);
  process.exit(code);
};

if (!["check", "control"].includes(mode) || !scenario) {
  finish(2, `usage: run.mjs check|control <${Object.keys(scenarios).join("|")}>`);
}

const baseUrl = process.env.BASE_URL;
const account = {
  email: process.env.TEST_ACCOUNT_EMAIL,
  password: process.env.TEST_ACCOUNT_PASSWORD,
};
const unset = [
  ["BASE_URL", baseUrl],
  ["TEST_ACCOUNT_EMAIL", account.email],
  ["TEST_ACCOUNT_PASSWORD", account.password],
].filter(([, value]) => !value).map(([key]) => key);
if (unset.length > 0) finish(CANNOT_RUN, `  CANNOT RUN  ${unset.join(", ")} not set`);

const target = new URL(scenario.target, baseUrl).href;
const workDir = mkdtempSync(join(tmpdir(), "signin-check-"));
let running = null;

const cleanup = () => rmSync(workDir, { recursive: true, force: true });
for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    running?.kill("SIGKILL");
    cleanup();
    process.exit(CANNOT_RUN);
  });
}

const redact = (text) => text
  .split(account.password).join("<TEST_ACCOUNT_PASSWORD>")
  .split(account.email).join("<TEST_ACCOUNT_EMAIL>");

const timed = (steps) => steps.map((step) =>
  UNTIMED_STEPS.some((kind) => kind in step) || "timeout" in step
    ? step
    : { ...step, timeout: CONTROL_STEP_TIMEOUT_MS });

const runDrive = (steps) => new Promise((resolve) => {
  const stepsFile = join(workDir, "steps.json");
  writeFileSync(stepsFile, JSON.stringify(steps), { mode: 0o600 });
  const child = spawn(process.execPath, [drive, target, stepsFile], {
    stdio: ["ignore", "pipe", "pipe"],
  });
  running = child;
  let output = "";
  child.stdout.on("data", (chunk) => { output += chunk; });
  child.stderr.on("data", (chunk) => { output += chunk; });
  child.on("close", (code, signal) => {
    running = null;
    resolve({ code: signal ? CANNOT_RUN : code, output: redact(output) });
  });
});

const indent = (text) => text.split("\n").filter(Boolean).map((line) => `    ${line}`).join("\n");

const runCheck = async () => {
  const { code, output } = await runDrive(scenario.check(account));
  process.stdout.write(output);
  return code;
};

const runControl = async () => {
  const results = [];
  for (const variant of scenario.controls(account)) {
    const { code, output } = await runDrive(timed(variant.steps));
    console.log(`  variant "${variant.name}" exited ${code}`);
    console.log(indent(output));
    results.push({ variant, code });
  }
  const passed = results.filter(({ code }) => code === 0);
  const broken = results.filter(({ code }) => code !== 0 && code !== 1);
  if (broken.length > 0) {
    console.log(`  CANNOT RUN  variant "${broken[0].variant.name}" ended with exit ${broken[0].code}, not a product failure`);
    return CANNOT_RUN;
  }
  if (passed.length > 0) {
    console.log(`  NOT PROVEN  variant "${passed[0].variant.name}" passed the check`);
    return 0;
  }
  console.log(`  every control variant failed as it must (${results.length})`);
  return 1;
};

const code = await (mode === "check" ? runCheck() : runControl()).finally(cleanup);
process.exit(code);
