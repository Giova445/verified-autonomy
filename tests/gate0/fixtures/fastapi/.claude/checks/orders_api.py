import json
import sys
import urllib.error
import urllib.parse
import urllib.request

CANNOT_RUN = 75
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def fetch(url):
    try:
        with OPENER.open(url, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, None
    except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
        print("CANNOT RUN  %s: %s" % (url, error))
        sys.exit(CANNOT_RUN)


def search(base, query, customer):
    url = "%s/api/orders?q=%s" % (base, urllib.parse.quote(query))
    status, body = fetch(url)
    if status != 200 or not body:
        return "GET %s gave status %s and %s" % (url, status, "no orders" if not body else "orders")
    others = sorted({order["customer"] for order in body if order["customer"] != customer})
    if others:
        return "search %r also listed %s" % (query, ", ".join(others))
    print("ok  search %r listed %d order(s), all %s's" % (query, len(body), customer))
    return None


def detail(base, order_id, status_wanted, customer=None):
    url = "%s/api/orders/%s" % (base, order_id)
    status, body = fetch(url)
    if status != int(status_wanted):
        return "GET %s gave status %s, wanted %s" % (url, status, status_wanted)
    if customer and (body or {}).get("customer") != customer:
        return "GET %s named %r, wanted %r" % (url, (body or {}).get("customer"), customer)
    print("ok  order %s answered %s%s" % (order_id, status, " for " + customer if customer else ""))
    return None


def main(argv):
    if len(argv) < 3 or argv[1] not in ("search", "detail"):
        print("usage: orders_api.py {search|detail} BASE_URL ARGS...")
        return 2
    kind, base, args = argv[1], argv[2].rstrip("/"), argv[3:]
    problem = search(base, *args) if kind == "search" else detail(base, *args)
    if problem:
        print("FAIL  %s" % problem)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
