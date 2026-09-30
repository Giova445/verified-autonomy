# G4 results: planted faults against the product contracts

Gate 0 G4 pass mark: at least 80% of planted faults caught and at most 10% false PASS, per fixture.
Caught means at least one outcome is FAILS, NOT PROVEN or WRONG BUILD. Missed means every outcome holds (a false PASS).
No signal means CANNOT RUN or NO VERDICT; it is reported separately and counted as not caught.

Provenance of the numbers:
- Counts, category tables, defect statements, marker, no-signal list: copied from the output of one full sequential run of `bash tests/gate0/g4.sh` on 2026-09-29 (g4.sh at commit 8cb0d60; the five per-fixture G4_ONLY runs gave identical counts).
- The Why column below is my reading of each fixture's `.claude` contract against the patch. It is not produced by the run.
- Faults were written and committed (ee389a7) before any contract was read.

Run result: `G4 FAULTS FAILED  (10 of 25 checks)`.

## Per fixture

| Fixture | Faults | Caught | Missed | No signal | Catch rate | False-PASS rate | Peak MB | Mark |
|---|---|---|---|---|---|---|---|---|
| cli | 32 | 21 | 11 | 0 | 65.6% | 34.4% | 14 | NOT MET |
| fastapi | 32 | 16 | 15 | 1 | 50.0% | 46.9% | 90 | NOT MET |
| monorepo | 30 | 15 | 10 | 5 | 50.0% | 33.3% | 288 | NOT MET |
| nextjs | 30 | 12 | 11 | 7 | 40.0% | 36.7% | 478 | NOT MET |
| signin | 31 | 20 | 9 | 2 | 64.5% | 29.0% | 283 | NOT MET |
| all | 155 | 84 | 56 | 15 | 54.2% | 36.1% | | |

## Per category

### cli

| Category | Faults | Caught | Missed | No signal | Catch rate |
|---|---|---|---|---|---|
| broken link/route | 1 | 1 | 0 | 0 | 100% |
| build or start breaks | 1 | 1 | 0 | 0 | 100% |
| crash | 2 | 2 | 0 | 0 | 100% |
| dead handler | 4 | 4 | 0 | 0 | 100% |
| loading/empty/error state wrong | 1 | 0 | 1 | 0 | 0% |
| mocked or hardcoded data | 4 | 3 | 1 | 0 | 75% |
| off-by-one | 3 | 3 | 0 | 0 | 100% |
| search/filter behavior wrong | 3 | 1 | 2 | 0 | 33% |
| stale deploy or wrong build | 2 | 1 | 1 | 0 | 50% |
| works in dev but not on the production build | 1 | 0 | 1 | 0 | 0% |
| wrong computation | 3 | 3 | 0 | 0 | 100% |
| wrong exit code / error handling | 1 | 0 | 1 | 0 | 0% |
| wrong field displayed | 1 | 0 | 1 | 0 | 0% |
| wrong field in search/filter | 2 | 2 | 0 | 0 | 100% |
| wrong sort | 3 | 0 | 3 | 0 | 0% |

### fastapi

| Category | Faults | Caught | Missed | No signal | Catch rate |
|---|---|---|---|---|---|
| broken link/route | 3 | 2 | 1 | 0 | 67% |
| build or start breaks | 1 | 0 | 0 | 1 | 0% |
| crash on edge case | 2 | 0 | 2 | 0 | 0% |
| dead handler | 3 | 2 | 1 | 0 | 67% |
| loading/empty/error state wrong | 5 | 2 | 3 | 0 | 40% |
| mocked or hardcoded data | 3 | 2 | 1 | 0 | 67% |
| off-by-one | 2 | 1 | 1 | 0 | 50% |
| search/filter behavior wrong | 4 | 3 | 1 | 0 | 75% |
| stale deploy or wrong build | 2 | 0 | 2 | 0 | 0% |
| works in dev but not on the production build | 1 | 1 | 0 | 0 | 100% |
| wrong computation | 2 | 1 | 1 | 0 | 50% |
| wrong field in search/filter | 3 | 2 | 1 | 0 | 67% |
| wrong sort | 1 | 0 | 1 | 0 | 0% |

### monorepo

| Category | Faults | Caught | Missed | No signal | Catch rate |
|---|---|---|---|---|---|
| broken link/route | 2 | 1 | 0 | 1 | 50% |
| build or start breaks | 5 | 0 | 1 | 4 | 0% |
| crash on edge case | 2 | 1 | 1 | 0 | 50% |
| dead handler | 3 | 3 | 0 | 0 | 100% |
| loading/empty/error state wrong | 2 | 1 | 1 | 0 | 50% |
| mocked or hardcoded data | 2 | 1 | 1 | 0 | 50% |
| off-by-one | 2 | 2 | 0 | 0 | 100% |
| search/filter behavior wrong | 1 | 0 | 1 | 0 | 0% |
| stale deploy or wrong build | 2 | 0 | 2 | 0 | 0% |
| works in dev but not on the production build | 3 | 3 | 0 | 0 | 100% |
| wrong computation | 2 | 2 | 0 | 0 | 100% |
| wrong field displayed | 1 | 0 | 1 | 0 | 0% |
| wrong field in search/filter | 1 | 1 | 0 | 0 | 100% |
| wrong sort | 2 | 0 | 2 | 0 | 0% |

### nextjs

| Category | Faults | Caught | Missed | No signal | Catch rate |
|---|---|---|---|---|---|
| broken link/route | 2 | 1 | 1 | 0 | 50% |
| build or start breaks | 6 | 0 | 0 | 6 | 0% |
| dead handler | 3 | 3 | 0 | 0 | 100% |
| loading/empty/error state wrong | 4 | 2 | 2 | 0 | 50% |
| mocked or hardcoded data | 2 | 2 | 0 | 0 | 100% |
| off-by-one | 1 | 1 | 0 | 0 | 100% |
| search/filter behavior wrong | 2 | 0 | 2 | 0 | 0% |
| stale deploy or wrong build | 2 | 1 | 1 | 0 | 50% |
| works in dev but not on the production build | 2 | 1 | 0 | 1 | 50% |
| wrong field displayed | 2 | 0 | 2 | 0 | 0% |
| wrong field in search/filter | 2 | 1 | 1 | 0 | 50% |
| wrong sort | 2 | 0 | 2 | 0 | 0% |

### signin

| Category | Faults | Caught | Missed | No signal | Catch rate |
|---|---|---|---|---|---|
| auth bypass or lockout | 10 | 8 | 2 | 0 | 80% |
| broken link/route | 6 | 5 | 1 | 0 | 83% |
| build or start breaks | 2 | 0 | 0 | 2 | 0% |
| crash on edge case | 2 | 1 | 1 | 0 | 50% |
| dead handler | 5 | 4 | 1 | 0 | 80% |
| loading/empty/error state wrong | 1 | 0 | 1 | 0 | 0% |
| mocked or hardcoded data | 1 | 1 | 0 | 0 | 100% |
| off-by-one | 1 | 1 | 0 | 0 | 100% |
| wrong computation | 1 | 0 | 1 | 0 | 0% |
| wrong field displayed | 2 | 0 | 2 | 0 | 0% |

## Missed faults (false PASS)

Marker: live means the fault was written to leave the app running; break means it was marked as a build or start break.

| Fixture | Id | Marker | Category | Defect | Why the contract did not see it |
|---|---|---|---|---|---|
| cli | cli-04 | live | search/filter behavior wrong | Searching "alice" (lowercase) finds nothing because the search is now case-sensitive. | The query typed is already lowercase, so removing the lowercase step never changes a match. |
| cli | cli-07 | live | wrong sort | `orders list` reorders rows by price instead of showing them in the original order. | Only the line count and a substring are checked, never the row order. |
| cli | cli-11 | live | works in dev but not on the production build | In a production build (NODE_ENV=production) the total loses its cents formatting, e.g. "Total: 880" instead of "Total: 880.00". | NODE_ENV is never set, so the production branch never runs. |
| cli | cli-12 | live | wrong exit code / error handling | Running an invalid command like `orders foo` prints the usage error but exits successfully (status 0) instead of failing. | No invalid command is ever run, so the exit code of a usage error is never read. |
| cli | cli-14 | live | wrong field displayed | `orders list` prints the item name in the customer column and the customer name in the item column. | A whole-line substring match for the query cannot see which column a name is in. |
| cli | cli-16 | live | loading/empty/error state wrong | Searching for a customer with no orders shows a blank list instead of "No orders match ...". | The only query used has matches, so the no-match branch never runs. |
| cli | cli-18 | live | stale deploy or wrong build | Installing the CLI (linking it or installing it globally) points the `orders` command at dist/orders.mjs, a build output that was never generated, so the installed command can't be found. | The check runs `node bin/orders.mjs` directly, never the packaged `orders` command from package.json. |
| cli | cli-20 | live | wrong sort | Search results for a customer with multiple orders show them in reverse order instead of original order. | Only the line count and a substring are checked, never the row order. |
| cli | cli-22 | live | search/filter behavior wrong | A search query with a trailing space (e.g. "Alice ") matches nothing even though "Alice" would. | No query with whitespace is ever sent. |
| cli | cli-30 | live | wrong sort | `orders list` reorders rows alphabetically by customer name instead of showing them in original order. | Only the line count and a substring are checked, never the row order. |
| cli | cli-31 | live | mocked or hardcoded data | Searching for any missing customer shows the fixed message "No orders match Nobody" instead of naming the actual query. | The only query used has matches, so the no-match branch never runs. |
| fastapi | fa-07 | live | search/filter behavior wrong | A search query with a leading space (" Alice") never matches, though "Alice" would. | The search always sends the query alice, with no whitespace. |
| fastapi | fa-11 | live | loading/empty/error state wrong | GET /api/orders (with no search box filled in) fails with a 422 error instead of showing all orders. | The search check always sends q, so a required q is never noticed. |
| fastapi | fa-12 | live | wrong sort | The orders list comes back sorted by price, highest first, instead of the original order. | The response order is never read; only which customers appear. |
| fastapi | fa-13 | live | stale deploy or wrong build | The two newest orders (Chidi Okafor's webcam and Dana Whitfield's headset) never show up; the deployed server is running an older snapshot of the order data. | Only Alice, Bob and id 9999 are ever asked for; the total order count and ids 1004 and 1005 are never read. |
| fastapi | fa-15 | live | crash on edge case | Requesting a negative or zero order id crashes the server with an unhandled error instead of returning a clean 404. | Only ids 1002 and 9999 are requested, never zero or negative. |
| fastapi | fa-17 | live | wrong computation | Opening a single order's detail (GET /api/orders/1001) shows a total twice the real price. | The detail check reads the status and the customer name, never the total. |
| fastapi | fa-18 | live | dead handler | The health check endpoint returns an empty object instead of {"status": "ok"}, so uptime monitors can't confirm the service is healthy. | /health is only a readiness probe on its HTTP status; its body is never read. |
| fastapi | fa-21 | break | stale deploy or wrong build | The pinned FastAPI version in requirements.txt is years out of date and fails to install/import in the current environment, so the service never starts. | The harness uses the packages already installed and never installs from requirements.txt, so the pin is never exercised. Whether a fresh install fails is not measured. |
| fastapi | fa-24 | live | loading/empty/error state wrong | When a search matches nothing, /api/orders returns an object {"orders": []} instead of an empty array, breaking clients that expect a list. | The only zero-match request is the zed control, which is expected to fail, so a changed empty-result shape is absorbed by it. |
| fastapi | fa-25 | live | wrong field in search/filter | A single order's detail view shows the price under the key "amount" instead of "total", and after the first request the price disappears from that order everywhere. | The detail check reads the status and the customer name, never the price field. |
| fastapi | fa-26 | live | off-by-one | Searching for a customer with multiple orders always leaves out the last one in the results. | The check asserts that no other customer appears, never how many of the customer's orders come back. |
| fastapi | fa-27 | live | mocked or hardcoded data | Every single-order detail page shows the item name as "Sample Item" instead of the real product. | The detail check reads the status and the customer name, never the item. |
| fastapi | fa-29 | live | broken link/route | GET /api/orders/1001 (no trailing slash) returns 404; the route now requires a trailing slash that the app's own links don't include. | urllib follows the redirect, so the client still gets 200. Arguably not a user-visible defect for a client that follows redirects. |
| fastapi | fa-30 | live | crash on edge case | Searching for a customer with zero matching orders crashes the endpoint with a division-by-zero error instead of returning an empty list. | The only zero-match request is the zed control, which is expected to fail, so the crash is absorbed by it. |
| fastapi | fa-32 | live | loading/empty/error state wrong | Loading the orders page normally (no search text) shows an empty list instead of every order; only typing something makes any orders appear. | The search check always sends q, so the bare listing is never requested. |
| monorepo | mr-06 | live | wrong sort | Orders on the page are sorted by price, most expensive first, instead of appearing in their original order. | Only row counts and the total are read, never the row order. |
| monorepo | mr-07 | live | loading/empty/error state wrong | The "Loading orders" message never goes away, even after the orders have loaded and search is enabled. | The #loading element is never asserted hidden. |
| monorepo | mr-09 | live | crash on edge case | Requesting any file that doesn't exist crashes the server with an unhandled exception instead of returning 404. | Only files that exist are requested, so the missing-file path never runs. |
| monorepo | mr-10 | live | stale deploy or wrong build | If PORT isn't set, the server doesn't fail clearly; it silently starts listening on a random port that nothing can find. | The harness always sets PORT, so the unset case never happens. |
| monorepo | mr-11 | live | mocked or hardcoded data | Every order on the page shows the item name "Widget", no matter what was actually ordered. | Item text is never read; rows are matched only on the customer name. |
| monorepo | mr-18 | live | wrong sort | The order list shows results in reverse order compared to the underlying data. | Only row counts and the total are read, never the row order. |
| monorepo | mr-19 | break | build or start breaks | Package installs no longer link the web app's workspace at all, so the build can't find its own app directory. | The harness builds and starts inside apps/web and never runs an install at the root, so the workspaces field is never used. Whether it breaks a real install is not measured. |
| monorepo | mr-21 | live | wrong field displayed | Each row on the page shows the item name before the customer's name, reversed from what the page is supposed to show. | Rows are matched with a has-text substring on the customer name, so word order in the row is never checked. |
| monorepo | mr-23 | live | stale deploy or wrong build | The server stops declaring a content type for the orders data file, serving it as application/octet-stream instead of application/json. | The page's fetch(...).json() ignores the content type and no check reads the header, so there is no visible effect. |
| monorepo | mr-24 | live | search/filter behavior wrong | Searching for a customer's last name (like "Nguyen") finds nothing; only matches at the very start of the name work now. | The query alice is a prefix of Alice Nguyen, so startsWith matches it too; a last-name query is never tried. |
| nextjs | nj-05 | live | loading/empty/error state wrong | The "Loading orders" message never goes away, even after the orders have finished loading and are visible on the page. | The #loading element is never asserted hidden. |
| nextjs | nj-07 | live | broken link/route | Clicking "Orders" from the admin home page leads to a 404 instead of the orders page. | The check opens /orders directly; the home page and its link are never visited. |
| nextjs | nj-08 | live | wrong sort | Orders on the page are sorted by price, highest first, instead of their normal order. | Only row counts and the customer name are read, never the row order. |
| nextjs | nj-12 | live | wrong field displayed | Each row shows the item name where the customer's name should be, and vice versa. | Rows are matched with a has-text substring on the customer name, so which field is where is never checked. |
| nextjs | nj-14 | live | search/filter behavior wrong | Typing a lowercase name like "alice" finds nothing, because the search is now case-sensitive. | The query typed is already lowercase, so removing the lowercase step never changes a match. |
| nextjs | nj-20 | live | wrong field displayed | The browser tab always shows "Untitled" instead of "Orders" as the page title. | The page title is never read. |
| nextjs | nj-23 | live | wrong sort | The order list shows results in reverse order from normal. | Only row counts and the customer name are read, never the row order. |
| nextjs | nj-25 | live | wrong field in search/filter | Every order on the page shows a blank instead of a price because the API renamed the price field from total to amount without updating the page. | Price text is never read; only row counts and the customer name. |
| nextjs | nj-26 | live | stale deploy or wrong build | `npm start` always binds to port 3999 no matter what port the deployment expects, so the live site is unreachable at its real address. | The harness starts with `npm run start -- -p $PORT`; the later -p overrides the pinned port. |
| nextjs | nj-28 | live | search/filter behavior wrong | A search with a leading space never matches, even though the same text without the space would. | No query with whitespace is ever sent. |
| nextjs | nj-31 | live | loading/empty/error state wrong | Right when the page opens, it briefly claims "No orders match" before any data has even loaded, instead of showing a loading message. | #empty is only asserted after the rows are visible, never while the page is still loading. |
| signin | si-02 | live | auth bypass or lockout | Signing in with an email that was never registered still logs you in. | Only the test account, and its wrong password, are ever tried; an unregistered email never is. |
| signin | si-04 | live | dead handler | Clicking "Sign out" sends you back to the login page, but your session cookie still works and you're still actually signed in. | After sign out the browser drops its cookie, so reopening /orders redirects; nobody replays the old cookie against the server. |
| signin | si-07 | live | broken link/route | Visiting the site's root URL redirects to a broken /order path instead of the real /orders page. | The check starts at /login and never visits /. |
| signin | si-08 | live | wrong field displayed | Each order in the list shows the price twice instead of showing the item name and its price. | Only the row count and #who are read, never the text in a row. |
| signin | si-09 | live | wrong computation | Every price in the orders list shows as a tiny fraction of the real amount, e.g. $4.8 instead of $480. | Only the row count and #who are read, never the text in a row. |
| signin | si-10 | live | crash on edge case | Submitting the sign-in form with the password field left out of the request crashes the server with an error page instead of showing "Wrong email or password". | A browser form always sends the password field, so a request without it is never made. |
| signin | si-12 | live | loading/empty/error state wrong | After a failed sign-in, the login page reloads with no error message at all, leaving the user unsure why it didn't work. | The wrong-password control only needs the arrival steps to fail; #error is never asserted. |
| signin | si-13 | live | auth bypass or lockout | Every sign-in reuses the exact same session token, so signing in as anyone signs out (and takes over the session of) whoever was previously signed in on any device. | A single sign-in per run, so two sessions are never compared. |
| signin | si-23 | live | wrong field displayed | Each order in the list is labeled with its price instead of its order number, e.g. "#480" instead of "#2001". | Only the row count and #who are read, never the text in a row. |

## No signal (CANNOT RUN, counted as not caught)

| Fixture | Id | Marker | Category | Defect | Outcomes |
|---|---|---|---|---|---|
| fastapi | fa-22 | break | build or start breaks | The whole API fails to start: even GET /health returns nothing because the server process can't boot due to a code error. | search lists only the matching customer's orders=CANNOT RUN / an order id finds its order or is not found=CANNOT RUN |
| monorepo | mr-08 | live | broken link/route | Loading the site's homepage returns 404 Not Found because the server looks for home.html instead of index.html. | search narrows the orders list=CANNOT RUN / the total follows the search=CANNOT RUN |
| monorepo | mr-12 | break | build or start breaks | Running the production build fails outright with a module-not-found error, so there is nothing to deploy. | search narrows the orders list=CANNOT RUN / the total follows the search=CANNOT RUN |
| monorepo | mr-20 | break | build or start breaks | Running the deploy's build script fails immediately: it looks for build.js, but the real script is build.mjs. | search narrows the orders list=CANNOT RUN / the total follows the search=CANNOT RUN |
| monorepo | mr-25 | break | build or start breaks | The build fails outright: the shared orders module has invalid syntax, so nothing can be built or served. | search narrows the orders list=CANNOT RUN / the total follows the search=CANNOT RUN |
| monorepo | mr-28 | break | build or start breaks | `npm start` always tries to bind to port 80, which fails with a permissions error on any machine that isn't running as root. | search narrows the orders list=CANNOT RUN / the total follows the search=CANNOT RUN |
| nextjs | nj-11 | break | build or start breaks | The whole app fails to build: the orders page throws while rendering its initial (still-loading) state, and the production build never completes. | search narrows the orders list=CANNOT RUN / a search with no match says so=CANNOT RUN |
| nextjs | nj-16 | break | build or start breaks | The whole app fails to build; a broken tag in the root layout stops the production build from completing. | search narrows the orders list=CANNOT RUN / a search with no match says so=CANNOT RUN |
| nextjs | nj-17 | break | build or start breaks | The production build fails because static export was turned on, but the app has a live API route (/api/orders) that static export can't support. | search narrows the orders list=CANNOT RUN / a search with no match says so=CANNOT RUN |
| nextjs | nj-19 | break | build or start breaks | The admin home page fails to build/render at all because of a bad import; nothing loads. | search narrows the orders list=CANNOT RUN / a search with no match says so=CANNOT RUN |
| nextjs | nj-21 | break | build or start breaks | The whole app fails to build; the admin home page references an undefined variable, and the production build never completes. | search narrows the orders list=CANNOT RUN / a search with no match says so=CANNOT RUN |
| nextjs | nj-29 | live | works in dev but not on the production build | The production build now uses a different bundler than the one this app was written for, and it fails (or behaves differently) as a result. | search narrows the orders list=CANNOT RUN / a search with no match says so=CANNOT RUN |
| nextjs | nj-30 | break | build or start breaks | The whole app fails to build: the admin home page's "Orders" link is missing its href, and Next.js can't prerender the page without one. | search narrows the orders list=CANNOT RUN / a search with no match says so=CANNOT RUN |
| signin | si-19 | break | build or start breaks | The whole sign-in service fails to start at all. | the test account signs in and sees its orders=CANNOT RUN / signing out ends the session=CANNOT RUN |
| signin | si-30 | break | build or start breaks | The whole sign-in service fails to start because the user database file is corrupted JSON. | the test account signs in and sees its orders=CANNOT RUN / signing out ends the session=CANNOT RUN |

## Notes on individual faults

- mr-08 is marked live but the harness reads it as a start failure: its ready probe is the homepage, which the fault makes a 404.
- nj-29 is marked live. The harness reports CANNOT RUN because it symlinks node_modules and Turbopack rejects the symlink ("Symlink [project]/node_modules is invalid"). Measured separately: with a real in-tree node_modules the same build succeeds, so nj-29 is not a demonstrated user-visible defect. nextjs has 29 valid faults.
- fa-21 and mr-19 are marked break but exercised nothing in the harness, so they appear as missed. Whether either breaks a real install is not measured.
- fa-29 (redirect followed) and mr-23 (JSON content type ignored by fetch) are arguably not user-visible defects.
- Excluding every break-marked fault from the denominators gives 67.7% (cli), 53.3% (fastapi), 60.0% (monorepo), 50.0% (nextjs) and 69.0% (signin) caught. None reaches 80%.

