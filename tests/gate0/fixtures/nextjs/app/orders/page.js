"use client";

import { useEffect, useState } from "react";

export default function OrdersPage() {
  const [orders, setOrders] = useState(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    fetch("/api/orders")
      .then((response) => response.json())
      .then(setOrders);
  }, []);

  const needle = query.trim().toLowerCase();
  const shown = (orders ?? []).filter((order) => order.customer.toLowerCase().includes(needle));

  return (
    <main>
      <h1>Orders</h1>
      <input
        id="search"
        type="search"
        aria-label="Search by customer"
        placeholder="Search by customer"
        value={query}
        disabled={orders === null}
        onChange={(event) => setQuery(event.target.value)}
      />
      {orders === null ? <p id="loading">Loading orders</p> : null}
      <ul id="orders">
        {shown.map((order) => (
          <li key={order.id} className="order">
            <span className="customer">{order.customer}</span> {order.item} ${order.total}
          </li>
        ))}
      </ul>
      {orders !== null && shown.length === 0 ? <p id="empty">No orders match {query}</p> : null}
    </main>
  );
}
