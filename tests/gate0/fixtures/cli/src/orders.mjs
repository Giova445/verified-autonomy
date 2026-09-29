export const orders = [
  { id: 1001, customer: "Alice Nguyen", item: "Standing desk", total: 480 },
  { id: 1002, customer: "Bob Ferreira", item: "Monitor arm", total: 95 },
  { id: 1003, customer: "Alice Nguyen", item: "Desk mat", total: 35 },
  { id: 1004, customer: "Chidi Okafor", item: "Webcam", total: 120 },
  { id: 1005, customer: "Dana Whitfield", item: "Headset", total: 150 },
];

export function search(query) {
  const needle = query.trim().toLowerCase();
  return orders.filter((order) => order.customer.toLowerCase().includes(needle));
}

export function formatRow(order) {
  return `${order.id}  ${order.customer.padEnd(15)}  ${order.item.padEnd(14)}  ${order.total.toFixed(2)}`;
}

export function formatTotal(rows) {
  return `Total: ${rows.reduce((sum, order) => sum + order.total, 0).toFixed(2)}`;
}
