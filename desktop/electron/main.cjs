const { app, BrowserWindow, Menu } = require("electron");
const path = require("path");
const fs = require("fs");
const http = require("http");

let localServer = null;

function startStaticServer(distDir, callback) {
  if (localServer) {
    const port = localServer.address().port;
    return callback(`http://127.0.0.1:${port}`);
  }

  const mimeTypes = {
    ".html": "text/html",
    ".js": "text/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf"
  };

  localServer = http.createServer((req, res) => {
    let reqUrl = (req.url || "/").split("?")[0];
    let filePath = path.join(distDir, reqUrl === "/" ? "index.html" : reqUrl);

    if (!filePath.startsWith(distDir)) {
      res.statusCode = 403;
      return res.end("Forbidden");
    }

    fs.stat(filePath, (err, stats) => {
      if (err || !stats.isFile()) {
        filePath = path.join(distDir, "index.html");
      }

      const ext = path.extname(filePath).toLowerCase();
      const contentType = mimeTypes[ext] || "application/octet-stream";

      fs.readFile(filePath, (readErr, data) => {
        if (readErr) {
          res.statusCode = 500;
          return res.end("Server Error");
        }
        res.writeHead(200, {
          "Content-Type": contentType,
          "Access-Control-Allow-Origin": "*"
        });
        res.end(data);
      });
    });
  });

  localServer.listen(0, "127.0.0.1", () => {
    const port = localServer.address().port;
    callback(`http://127.0.0.1:${port}`);
  });
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1250,
    height: 850,
    minWidth: 980,
    minHeight: 700,
    title: "AI Video Dubber & Dịch Thuật Tự Động",
    backgroundColor: "#0b0f19",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      webSecurity: false
    }
  });

  const distDir = path.join(__dirname, "../dist");

  function loadLocalDist() {
    if (fs.existsSync(path.join(distDir, "index.html"))) {
      startStaticServer(distDir, (url) => {
        win.loadURL(url);
      });
    } else {
      setTimeout(tryLoad, 800);
    }
  }

  function tryLoad() {
    const req = http.get("http://127.0.0.1:5173", (res) => {
      if (res.statusCode === 200) {
        win.loadURL("http://127.0.0.1:5173");
      } else {
        loadLocalDist();
      }
    });

    req.on("error", () => {
      loadLocalDist();
    });

    req.end();
  }

  tryLoad();
}

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (localServer) {
    try { localServer.close(); } catch (e) {}
  }
  if (process.platform !== "darwin") app.quit();
});
