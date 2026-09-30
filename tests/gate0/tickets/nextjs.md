# Shop admin: find orders by customer

**User story.** As a shop admin, I want an Orders page I can search by customer name, so I can find a customer's orders quickly.

**Demo data.** Five orders (id, customer, item, total): 1001 Alice Nguyen, Standing desk, $480; 1002 Bob Ferreira, Monitor arm, $95; 1003 Alice Nguyen, Desk mat, $35; 1004 Chidi Okafor, Webcam, $120; 1005 Dana Whitfield, Headset, $150.

**Acceptance criteria**

1. The home page (`/`) shows the heading "Shop admin" and a link "Orders" that opens `/orders`.
2. `/orders` shows the heading "Orders", a search box labelled "Search by customer", and one row per order in the id order above. A row shows customer, item and total with a dollar sign, e.g. "Alice Nguyen Standing desk $480".
3. While orders are loading, the page shows "Loading orders" and the search box is disabled. When loading finishes the message is gone and the box can be typed in.
4. Typing narrows the list to orders whose customer name contains the text. Case and surrounding spaces do not matter: "ali" and " ALICE " both leave only Alice Nguyen's two orders.
5. Search looks at customer names only: "desk", an item word, shows no orders.
6. When nothing matches, no rows are shown and the page says "No orders match" followed by what was typed, e.g. "No orders match zed".
7. Clearing the box brings back all five orders and hides that message.

**How to reach it.** From `nextjs/`: `npm install`, `npm run build && npm run start`, then open `http://localhost:3000/orders`.

**Test account.** None; there is no sign-in.
