const search = document.getElementById("search");
const list = document.getElementById("orders");
const total = document.getElementById("total");
const loading = document.getElementById("loading");

function render(orders, query) {
  const needle = query.trim().toLowerCase();
  const shown = orders.filter((order) => order.customer.toLowerCase().includes(needle));
  list.replaceChildren(
    ...shown.map((order) => {
      const item = document.createElement("li");
      item.className = "order";
      item.textContent = `${order.customer} ${order.item} $${order.total}`;
      return item;
    }),
  );
  total.textContent = `Total: $${shown.reduce((sum, order) => sum + order.total, 0)}`;
}

fetch("/orders.json")
  .then((response) => response.json())
  .then((orders) => {
    loading.remove();
    search.disabled = false;
    search.addEventListener("input", () => render(orders, search.value));
    render(orders, "");
  });
