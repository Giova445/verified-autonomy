import hashlib
import hmac
import json
import secrets
from html import escape
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

USERS = json.loads((Path(__file__).resolve().parent.parent / "data" / "users.json").read_text())
SESSIONS = {}
COOKIE = "session"
ITERATIONS = 10000

app = FastAPI()


def page(title, body):
    return HTMLResponse(f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><title>{title}</title></head><body>{body}</body></html>")


def password_ok(email, password):
    user = USERS.get(email)
    if not user:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(user["salt"]), ITERATIONS).hex()
    return hmac.compare_digest(digest, user["hash"])


def signed_in_email(request):
    return SESSIONS.get(request.cookies.get(COOKIE, ""))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def home():
    return RedirectResponse("/orders", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_form(error: str = ""):
    message = "<p id=\"error\" role=\"alert\">Wrong email or password</p>" if error else ""
    return page("Sign in", f"""<h1>Sign in</h1>{message}
<form method="post" action="/login">
<label>Email <input id="email" name="email" type="email" autocomplete="username"></label>
<label>Password <input id="password" name="password" type="password" autocomplete="current-password"></label>
<button id="signin" type="submit">Sign in</button>
</form>""")


@app.post("/login")
async def login(request: Request):
    form = parse_qs((await request.body()).decode())
    email = (form.get("email") or [""])[0]
    password = (form.get("password") or [""])[0]
    if not password_ok(email, password):
        return RedirectResponse("/login?error=1", status_code=303)
    token = secrets.token_hex(16)
    SESSIONS[token] = email
    response = RedirectResponse("/orders", status_code=303)
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax")
    return response


@app.get("/orders")
def orders(request: Request):
    email = signed_in_email(request)
    if not email:
        return RedirectResponse("/login", status_code=303)
    rows = "".join(
        f"<li class=\"order\">#{order['id']} {escape(order['item'])} ${order['total']}</li>"
        for order in USERS[email]["orders"]
    )
    return page("Your orders", f"""<h1>Your orders</h1>
<p>Signed in as <span id="who">{escape(email)}</span></p>
<ul id="orders">{rows}</ul>
<form method="post" action="/logout"><button id="signout" type="submit">Sign out</button></form>""")


@app.post("/logout")
def logout(request: Request):
    SESSIONS.pop(request.cookies.get(COOKIE, ""), None)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(COOKIE)
    return response
