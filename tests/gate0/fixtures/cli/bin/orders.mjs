#!/usr/bin/env node
import { formatRow, formatTotal, orders, search } from "../src/orders.mjs";

const USAGE = "usage: orders {list|total} [--search NAME]";

function parse(argv) {
  const [command, ...rest] = argv;
  if (!["list", "total"].includes(command)) return { error: USAGE };
  if (rest.length === 0) return { command, query: "" };
  if (rest.length === 2 && rest[0] === "--search") return { command, query: rest[1] };
  return { error: USAGE };
}

const parsed = parse(process.argv.slice(2));
if (parsed.error) {
  console.error(parsed.error);
  process.exit(2);
}

const rows = parsed.query ? search(parsed.query) : orders;
if (parsed.command === "list") {
  if (rows.length === 0) console.log(`No orders match ${parsed.query}`);
  for (const order of rows) console.log(formatRow(order));
} else {
  console.log(formatTotal(rows));
}
