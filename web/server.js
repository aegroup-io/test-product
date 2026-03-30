const http = require("http");
const fs = require("fs");
const path = require("path");

const PORT = Number(process.env.PORT || process.env.WEBSITES_PORT || 8080);
const ROOT_DIR = __dirname;

const mimeTypes = {
  ".css": "text/css",
  ".html": "text/html",
  ".ico": "image/x-icon",
  ".jpeg": "image/jpeg",
  ".jpg": "image/jpeg",
  ".js": "application/javascript",
  ".json": "application/json",
  ".map": "application/json",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".txt": "text/plain",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

function safePath(requestPath) {
  return path
    .normalize(requestPath)
    .replace(/^(\.\.[/\\])+/, "")
    .replace(/^[/\\]+/, "");
}

function serveFile(filePath, res) {
  fs.readFile(filePath, (error, data) => {
    if (error) {
      res.writeHead(404, { "Content-Type": "text/plain" });
      res.end("Not found");
      return;
    }

    const contentType = mimeTypes[path.extname(filePath).toLowerCase()] || "application/octet-stream";
    res.writeHead(200, { "Content-Type": contentType });
    res.end(data);
  });
}

const server = http.createServer((req, res) => {
  const requestPath = decodeURIComponent((req.url || "/").split("?")[0] || "/");
  let filePath = path.join(ROOT_DIR, safePath(requestPath === "/" ? "/index.html" : requestPath));

  fs.stat(filePath, (error, stats) => {
    if (error || !stats.isFile()) {
      filePath = path.join(ROOT_DIR, "index.html");
    }
    serveFile(filePath, res);
  });
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`Orcha web server listening on ${PORT}`);
});
