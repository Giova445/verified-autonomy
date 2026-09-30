# Orders API: list, search and fetch one order

**User story.** As a frontend developer, I want an HTTP API for orders, so the shop UI can list them, search by customer and open a single order.

**Demo data.** Five orders (id, customer, item, total): 1001 Alice Nguyen, Standing desk, 480; 1002 Bob Ferreira, Monitor arm, 95; 1003 Alice Nguyen, Desk mat, 35; 1004 Chidi Okafor, Webcam, 120; 1005 Dana Whitfield, Headset, 150.

**Acceptance criteria**

1. `GET /health` answers 200 with JSON saying status "ok".
2. `GET /api/orders` answers 200 with a JSON array of all five orders in the id order above, each with id, customer, item and total (id and total as numbers).
3. `GET /api/orders?q=alice` returns only orders whose customer name contains the text (1001 and 1003). Case and surrounding spaces do not matter: `q=%20ALICE%20` returns the same two.
4. `q` looks at customer names only: `q=desk`, an item word, returns an empty array.
5. When nothing matches (for example `q=zed`), the answer is 200 with an empty JSON array, not an error.
6. An empty or missing `q` returns all five orders.
7. `GET /api/orders/1004` answers 200 with that one order (Chidi Okafor, Webcam, 120) as a JSON object.
8. `GET /api/orders/9999` answers 404 with the message "order not found".
9. A non-numeric id such as `/api/orders/abc` is rejected with a 4xx client error, never a 200 or a 500.

**How to reach it.** From `fastapi/`: `pip install -r requirements.txt`, then `uvicorn app.main:app --port 8000`, and call `http://127.0.0.1:8000`.

**Test account.** None; the API has no sign-in.
