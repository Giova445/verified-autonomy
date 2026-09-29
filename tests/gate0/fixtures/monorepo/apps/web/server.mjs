import { existsSync, readFileSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const dist = join(dirname(fileURLToPath(import.meta.url)), "dist");
const port = Number(process.env.PORT);
const types = { ".html": "text/html", ".js": "text/javascript", ".json": "application/json" };

if (!Number.isInteger(port) || port <= 0) {
  console.error("PORT must be set to a port number");
  process.exit(2);
}

const server = createServer((request, response) => {
  const name = request.url === "/" ? "/index.html" : request.url.split("?")[0];
  const file = join(dist, name);
  if (name.includes("..") || !existsSync(file)) {
    response.writeHead(404, { "content-type": "text/plain" });
    response.end("not found");
    return;
  }
  const extension = name.slice(name.lastIndexOf("."));
  response.writeHead(200, { "content-type": types[extension] ?? "application/octet-stream" });
  response.end(readFileSync(file));
});

server.listen(port, "127.0.0.1", () => console.log(`listening on http://127.0.0.1:${port}`));
