import { orders } from "../../../lib/orders.js";

export function GET() {
  return Response.json(orders);
}
