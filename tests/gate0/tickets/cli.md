# orders CLI: list, search and total orders

**User story.** As a support agent, I want to list and total orders from the terminal, optionally for one customer, so I can answer "what did this customer order and spend" quickly.

**Demo data.** Five orders (id, customer, item, total): 1001 Alice Nguyen, Standing desk, 480; 1002 Bob Ferreira, Monitor arm, 95; 1003 Alice Nguyen, Desk mat, 35; 1004 Chidi Okafor, Webcam, 120; 1005 Dana Whitfield, Headset, 150.

**Acceptance criteria**

1. `orders list` prints one line per order in the id order above, each showing id, customer, item and total, in that order, with the total to two decimals (the first line carries 1001, Alice Nguyen, Standing desk, 480.00).
2. `orders total` prints one line, `Total: 880.00`.
3. `--search NAME` limits either command to orders whose customer name contains NAME, ignoring case and surrounding spaces. `orders list --search alice` prints the two Alice Nguyen lines; `orders total --search ALICE` prints `Total: 515.00`.
4. Search looks at customer names only: `orders list --search desk` finds nothing.
5. When nothing matches, `list` prints `No orders match NAME` (for example `No orders match zed`) and `total` prints `Total: 0.00`.
6. No command, an unknown command, `--search` without a name, or extra arguments prints `usage: orders {list|total} [--search NAME]` on the error stream, prints no orders, and exits with a non-zero status.
7. The successful runs above exit with status 0.

**How to reach it.** From `cli/` run `node bin/orders.mjs list` (this is the `orders` command). No build step, no server.

**Test account.** None; there is no sign-in.
