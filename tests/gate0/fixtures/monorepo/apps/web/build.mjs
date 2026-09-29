import { copyFileSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { orders } from "../../packages/orders/index.js";

const here = dirname(fileURLToPath(import.meta.url));
const dist = join(here, "dist");

rmSync(dist, { recursive: true, force: true });
mkdirSync(dist, { recursive: true });
copyFileSync(join(here, "src", "index.html"), join(dist, "index.html"));
copyFileSync(join(here, "src", "app.js"), join(dist, "app.js"));
writeFileSync(join(dist, "orders.json"), JSON.stringify(orders));
console.log(`built ${orders.length} orders into ${dist}`);
