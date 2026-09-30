# Sign in to see my orders

**User story.** As a customer, I want to sign in with my email and password to see my own orders, and sign out when I am done, so nobody else can see them.

**Account data.** The test account has three orders: #2001 Standing desk $480, #2002 Desk mat $35, #2003 Webcam $120.

**Acceptance criteria**

1. A signed-out visitor who opens `/` or `/orders` ends up on the sign-in page (`/login`). It shows the heading "Sign in", an Email field, a Password field and a "Sign in" button, and no order information.
2. Signing in with the test account takes the user to `/orders`. The page shows the heading "Your orders", "Signed in as" followed by the account's email, and the three orders in the order above, each like "#2001 Standing desk $480".
3. A wrong password puts the user back on the sign-in page with an alert reading "Wrong email or password". The user is not signed in: opening `/orders` sends them to the sign-in page again.
4. An unknown email, or empty fields, give the same alert as a wrong password, so nothing reveals whether an email has an account.
5. Reloading `/orders` while signed in keeps the user signed in.
6. The orders page has a "Sign out" button. Using it returns the user to the sign-in page, and opening `/orders` afterwards sends them there again.

**How to reach it.** `fastapi` and `uvicorn` must be installed. From `signin/` run `uvicorn app.main:app --port 8000`, and open `http://127.0.0.1:8000/`.

**Test account.** Email and password come from the environment variables `TEST_ACCOUNT_EMAIL` and `TEST_ACCOUNT_PASSWORD`. Never write the values into tests or files.
