import http.client
import json
import os
import sys
import urllib.error
import urllib.request

CANNOT_RUN = 75
BAD_SPEC = 2
ASSERTIONS = ("status", "status_class", "body", "body_has")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)


def kind(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    return "array" if isinstance(value, list) else "object"


def show(value):
    text = json.dumps(value, sort_keys=True)
    return text if len(text) <= 240 else text[:240] + "..."


def differences(want, got, where, subset=False):
    if kind(want) != kind(got):
        return ["%s is %s %s, expected %s %s" % (where, kind(got), show(got), kind(want), show(want))]
    if isinstance(want, dict):
        found = ["%s.%s is missing" % (where, k) for k in want if k not in got]
        found += [] if subset else ["%s.%s is unexpected" % (where, k) for k in got if k not in want]
        for key in want:
            found += differences(want[key], got[key], "%s.%s" % (where, key)) if key in got else []
        return found
    if isinstance(want, list):
        if len(want) != len(got):
            return ["%s has %d item(s) %s, expected %d %s" % (where, len(got), show(got), len(want), show(want))]
        found = []
        for index, (w, g) in enumerate(zip(want, got)):
            found += differences(w, g, "%s[%d]" % (where, index))
        return found
    return [] if want == got else ["%s is %s, expected %s" % (where, show(got), show(want))]


def fetch(base, path):
    try:
        with OPENER.open(urllib.request.Request(base + path, method="GET"), timeout=10) as reply:
            return reply.status, reply.headers.get("content-type", ""), reply.read()
    except urllib.error.HTTPError as reply:
        return reply.code, reply.headers.get("content-type", ""), reply.read()


def judge_body(req, content_type, raw):
    found = []
    if not content_type.lower().startswith("application/json"):
        found.append("content-type is %r, expected application/json" % content_type)
    try:
        got = json.loads(raw)
    except ValueError:
        return found + ["body is not JSON: %r" % raw[:120]]
    if "body" in req:
        found += differences(req["body"], got, "body")
    if "body_has" in req:
        found += differences(req["body_has"], got, "body", subset=True)
    return found


def judge(base, req):
    status, content_type, raw = fetch(base, req["path"])
    found = []
    if "status" in req and status != req["status"]:
        found.append("status is %d, expected %d" % (status, req["status"]))
    if "status_class" in req and status // 100 != req["status_class"]:
        found.append("status is %d, expected %dxx" % (status, req["status_class"]))
    if "body" in req or "body_has" in req:
        found += judge_body(req, content_type, raw)
    return status, found


def load_spec(path):
    with open(path, encoding="utf-8") as handle:
        spec = json.load(handle)
    requests = spec.get("requests") if isinstance(spec, dict) else None
    if not isinstance(requests, list) or not requests:
        raise ValueError("spec needs a non-empty 'requests' list")
    for req in requests:
        if not isinstance(req, dict) or not str(req.get("path", "")).startswith("/"):
            raise ValueError("every request needs a 'path' starting with /")
        if not any(a in req for a in ASSERTIONS):
            raise ValueError("request %s asserts nothing" % req["path"])
    return spec


def main(argv):
    if len(argv) != 2:
        print("usage: probe.py SPEC.json")
        return BAD_SPEC
    base = os.environ.get("BASE_URL", "").rstrip("/")
    if not base:
        print("BASE_URL is not set")
        return CANNOT_RUN
    try:
        spec = load_spec(argv[1])
    except (OSError, ValueError) as exc:
        print("bad spec %s: %s" % (argv[1], exc))
        return BAD_SPEC
    failed = 0
    for req in spec["requests"]:
        try:
            status, found = judge(base, req)
        except (OSError, http.client.HTTPException) as exc:
            print("cannot reach %s%s: %s" % (base, req["path"], exc))
            return CANNOT_RUN
        print("%s GET %s -> %d%s" % ("FAIL" if found else "ok  ", req["path"], status, ": " + "; ".join(found) if found else ""))
        failed += bool(found)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
