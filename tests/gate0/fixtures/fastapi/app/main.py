from fastapi import FastAPI, HTTPException

app = FastAPI()

ORDERS = [
    {"id": 1001, "customer": "Alice Nguyen", "item": "Standing desk", "total": 480},
    {"id": 1002, "customer": "Bob Ferreira", "item": "Monitor arm", "total": 95},
    {"id": 1003, "customer": "Alice Nguyen", "item": "Desk mat", "total": 35},
    {"id": 1004, "customer": "Chidi Okafor", "item": "Webcam", "total": 120},
    {"id": 1005, "customer": "Dana Whitfield", "item": "Headset", "total": 150},
]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/orders")
def list_orders(q: str = ""):
    needle = q.strip().lower()
    return [order for order in ORDERS if needle in order["customer"].lower()]


@app.get("/api/orders/{order_id}")
def get_order(order_id: int):
    for order in ORDERS:
        if order["id"] == order_id:
            return order
    raise HTTPException(status_code=404, detail="order not found")
