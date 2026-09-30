GATE0="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN="$(cd "$GATE0/../.." && pwd)"
FIXTURES="$GATE0/fixtures"
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/va-gate0"
DRIVE="${DRIVE_MJS:-$PLUGIN/benchmark/gates/drive.mjs}"
SUITE="${SUITE:-gate0}"
KILL_MB="${GATE0_KILL_MB:-600}"
pass=0; fail=0; TMP=""

chk(){ if [ "$2" = "$3" ]; then printf '  ok    %s\n' "$1"; pass=$((pass+1));
       else printf '  FAIL  %s\n        got  %s\n        want %s\n' "$1" "$2" "$3"; fail=$((fail+1)); fi; }
note(){ printf '        %s\n' "$*"; }
now(){ python3 -c 'import time; print("%.1f" % time.time())'; }
span(){ awk -v a="$1" -v b="$2" 'BEGIN { printf "%.0f", b - a }'; }

finish(){
  echo
  if [ "$fail" -eq 0 ] && [ "$pass" -gt 0 ]; then echo "$1 PASSED  ($pass checks)"; exit 0
  else echo "$1 FAILED  ($fail of $((pass + fail)) checks)"; exit 1; fi
}

not_run(){
  printf '\nNOT RUN: %s\n' "$1"
  printf '%s (%d checks ran before that, %d failed)\n' "$SUITE" "$((pass + fail))" "$fail"
  [ "$fail" -eq 0 ] && exit 75 || exit 1
}

stray_pids(){
  local real
  real="$(cd "$1" 2>/dev/null && pwd -P)" || return 0
  lsof -d cwd -Fpn 2>/dev/null | awk -v dir="$real" -v me="$$" '
    /^p/ { pid = substr($0, 2) }
    /^n/ { where = substr($0, 2); if (pid != me && (where == dir || index(where, dir "/") == 1)) print pid }' | sort -u
}

cleanup(){
  [ -n "$TMP" ] && [ -d "$TMP" ] || return 0
  stray_pids "$TMP" | xargs kill -9 2>/dev/null
  find "$TMP" -maxdepth 0 -exec rm -rf {} +
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

ensure_tmp(){
  [ -n "$TMP" ] && return 0
  TMP="$(mktemp -d "${TMPDIR:-/tmp}/gate0.XXXXXX")" && TMP="$(cd "$TMP" && pwd -P)"
}

need_browser(){
  ensure_tmp
  [ -z "${PLAYWRIGHT_PATH:-}" ] && [ -d "$PLUGIN/node_modules/playwright" ] && export PLAYWRIGHT_PATH="$PLUGIN/node_modules/playwright"
  [ -f "$DRIVE" ] || not_run "drive.mjs is not at $DRIVE"
  command -v node >/dev/null 2>&1 || not_run "node is not installed"
  node -e 'require(process.env.PLAYWRIGHT_PATH || "playwright")' 2>/dev/null \
    || not_run "Playwright is not resolvable. Set PLAYWRIGHT_PATH to an installed playwright package."
  node -e 'const p = require(process.env.PLAYWRIGHT_PATH || "playwright");
    p.chromium.launch().then((b) => b.close()).catch((e) => { console.error(String(e.message).split("\n")[0]); process.exit(1); });' \
    2> "$TMP/browser.err" || not_run "Chromium cannot launch: $(head -c 300 "$TMP/browser.err")"
}

ensure_python_deps(){
  python3 -c 'import fastapi, uvicorn' 2>/dev/null && return 0
  local site="$CACHE/python/site"
  if [ -d "$site" ] && PYTHONPATH="$site" python3 -c 'import fastapi, uvicorn' 2>/dev/null; then
    export PYTHONPATH="$site${PYTHONPATH:+:$PYTHONPATH}"; return 0
  fi
  ensure_tmp
  rm -rf "$CACHE/python"; mkdir -p "$site"
  if ! python3 -m pip install --quiet --disable-pip-version-check --target "$site" -r "$FIXTURES/fastapi/requirements.txt" > "$TMP/pip.log" 2>&1; then
    rm -rf "$CACHE/python"
    not_run "fastapi and uvicorn are not importable and pip could not install them: $(tail -n 1 "$TMP/pip.log" | head -c 300)"
  fi
  export PYTHONPATH="$site${PYTHONPATH:+:$PYTHONPATH}"
}

ensure_node_deps(){
  local name="$1" dir="$CACHE/$1" want began ended
  want="$(cat "$FIXTURES/$name/package.json" "$FIXTURES/$name/package-lock.json" | shasum -a 256 | cut -d' ' -f1)"
  if [ -d "$dir/node_modules" ] && [ "$(cat "$dir/.installed" 2>/dev/null)" = "$want" ]; then return 0; fi
  ensure_tmp
  command -v npm >/dev/null 2>&1 || not_run "npm is not installed, so the $name dependencies cannot be installed"
  rm -rf "$dir"; mkdir -p "$dir"
  cp "$FIXTURES/$name/package.json" "$FIXTURES/$name/package-lock.json" "$dir/"
  began="$(now)"
  if ! ( cd "$dir" && NEXT_TELEMETRY_DISABLED=1 npm ci --no-audit --no-fund ) > "$TMP/npm-$name.log" 2>&1; then
    rm -rf "$dir"
    not_run "npm ci for the $name fixture failed: $(tail -n 3 "$TMP/npm-$name.log" | tr '\n' ' ' | head -c 400)"
  fi
  ended="$(now)"
  span "$began" "$ended" > "$dir/.install-seconds"
  printf '%s\n' "$want" > "$dir/.installed"
}

report_cache(){
  local dir="$CACHE/$1"
  [ -d "$dir/node_modules" ] || return 0
  note "dependency cache $dir: $(du -sk "$dir" | awk '{ printf "%.0f MB", $1 / 1024 }'), installed in $(cat "$dir/.install-seconds" 2>/dev/null || echo unknown) s by npm ci"
}

make_repo(){
  local name="$1" d
  ensure_tmp
  d="$(mktemp -d "$TMP/$name.XXXXXX")" && d="$(cd "$d" && pwd -P)"
  cp -R "$FIXTURES/$name/." "$d/"
  if [ "${G4_CONTRACTS:-}" = "spec" ]; then
    rm -rf "$d/.claude" && cp -R "$GATE0/spec/$name/.claude" "$d/.claude" || return 1
  fi
  if grep -rqs 'drive\.mjs' "$d/.claude"; then
    mkdir -p "$d/.claude/gates" && cp "$DRIVE" "$d/.claude/gates/drive.mjs"
  fi
  ( cd "$d" && git init -q . && git config user.email t@t && git config user.name t \
      && git add -A && git commit -qm "fixture $name" ) >/dev/null 2>&1
  [ -f "$FIXTURES/$name/package-lock.json" ] && ln -s "$CACHE/$name/node_modules" "$d/node_modules"
  printf '%s' "$d"
}

tracked_sources_only(){
  local d="$1" dirty tracked
  dirty="$(cd "$d" && git status --porcelain | wc -l | tr -d ' ')"
  tracked="$(cd "$d" && git ls-files | grep -cE 'node_modules|\.next/|/dist/|__pycache__')"
  printf '%s dirty, %s generated files tracked' "$dirty" "$tracked"
}

run_verify(){
  local repo="$1" out="$2" pid guard rc flag timer=""
  for flag in -l -v; do /usr/bin/time "$flag" true >/dev/null 2>&1 && { timer="$flag"; break; }; done
  (
    cd "$repo" || exit 1
    export CLAUDE_PROJECT_DIR="$repo" VERIFY_ROOT="$repo" NEXT_TELEMETRY_DISABLED=1
    if [ -n "$timer" ]; then exec /usr/bin/time "$timer" -o "$out.time" bash "$PLUGIN/bin/verify" product
    else exec bash "$PLUGIN/bin/verify" product; fi
  ) > "$out" 2>&1 &
  pid=$!
  python3 "$GATE0/guard.py" "$pid" "$KILL_MB" > "$out.guard" 2>&1 &
  guard=$!
  wait "$pid"; rc=$?
  wait "$guard" 2>/dev/null
  return $rc
}

peak_mb(){ sed -n 's/^memory  : peak \([0-9]*\) MB.*/\1/p' "$1" | tail -n 1; }
largest_rss_mb(){ awk '/maximum resident set size/ { printf "%.0f", $1 / 1048576 } /Maximum resident set size/ { printf "%.0f", $NF / 1024 }' "$1.time"; }
guard_said(){ [ -s "$1.guard" ] && cat "$1.guard"; }

verdicts(){
  python3 -c 'import json, sys
print(" ".join(o["verdict"] for o in json.load(open(sys.argv[1] + "/.claude/evidence/product.json"))["outcomes"]))' "$1" 2>/dev/null
}

outcome_rows(){
  python3 - "$1" <<'PY' 2>/dev/null
import json, os, re, sys
repo = sys.argv[1]
NOT_A_FAILURE = {"0", "75", "126", "127"}
for o in json.load(open(os.path.join(repo, ".claude/evidence/product.json")))["outcomes"]:
    text = open(os.path.join(repo, o["log"])).read() if o.get("log") else ""
    exits = dict(re.findall(r"\[(check|control) exit ([^\]]+)\]", text))
    after = text.split("[check exit", 1)[-1]
    reason = next((l.strip() for l in after.splitlines() if "FAIL" in l), "")
    check = "check passed" if exits.get("check") == "0" else "check exit %s" % exits.get("check", "missing")
    control_code = exits.get("control", "missing")
    control = "control failed" if control_code not in NOT_A_FAILURE and control_code != "missing" else "control exit %s" % control_code
    print("\t".join([o["name"], o["verdict"], check, control, "exit " + control_code, reason]))
PY
}

logged_ports(){
  cat "$1"/.claude/evidence/server-*.log 2>/dev/null \
    | grep -Eo '(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::\]):[0-9]{2,5}' | sed 's/.*://' | sort -u
}

listening(){ [ -n "$(lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null)" ]; }

left_behind(){
  local repo="$1" port found="" tries=0
  while [ "$tries" -lt 15 ]; do
    found=""
    for port in $(logged_ports "$repo"); do listening "$port" && found="$found port:$port"; done
    for pid in $(stray_pids "$repo"); do found="$found pid:$pid"; done
    [ -z "$found" ] && { printf 'nothing'; return 0; }
    tries=$((tries + 1)); sleep 0.4
  done
  printf '%s' "${found# }"
}

ensure_tmp
