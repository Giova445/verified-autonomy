# Orders page with a running total

**User story.** As a shop admin, I want one page that lists orders with a total of what is shown, so I can see what a customer has spent.

**Demo data.** Five orders (id, customer, item, total): 1001 Alice Nguyen, Standing desk, $480; 1002 Bob Ferreira, Monitor arm, $95; 1003 Alice Nguyen, Desk mat, $35; 1004 Chidi Okafor, Webcam, $120; 1005 Dana Whitfield, Headset, $150.

**Acceptance criteria**

1. `/` shows the heading "Orders", a search box labelled "Search by customer", and one row per order in the id order above, each reading customer, item, then total with a dollar sign, e.g. "Alice Nguyen Standing desk $480".
2. Below the list a line reads "Total: $880", the sum of the rows shown.
3. While orders are loading, the page shows "Loading orders" and the search box is disabled. Once loaded, the message disappears and the box can be typed in.
4. Typing narrows the rows to orders whose customer name contains the text, ignoring case and surrounding spaces, and the total follows the rows: "alice" shows orders 1001 and 1003 and "Total: $515".
5. Search looks at customer names only: "desk", an item word, shows no rows and "Total: $0".
6. When nothing matches (for example "zed"), the list is empty and the total reads "Total: $0".
7. Clearing the box restores all five rows and "Total: $880".

**How to reach it.** From the repo root: `npm install`, `npm run build --workspace @fixture/web`, then `PORT=4173 npm run start --workspace @fixture/web`, and open `http://127.0.0.1:4173/`. The server needs the `PORT` environment variable.

**Test account.** None; there is no sign-in.
