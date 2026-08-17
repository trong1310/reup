const { app, BrowserWindow, Menu } = require("electron");
const path = require("path");
const fs = require("fs");

function createWindow() {
  const win = new BrowserWindow({
    width: 1200,
    height: 840,
    minWidth: 980,
    minHeight: 700,
    title: "AI Video Dubber & Dịch Thuật Tự Động",
    backgroundColor: "#0b0f19",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  // Tùy chọn ẩn menu mặc định để giao diện trông chuyên nghiệp
  Menu.setApplicationMenu(null);

  const distIndex = path.join(__dirname, "../dist/index.html");
  if (fs.existsSync(distIndex)) {
    win.loadFile(distIndex);
  } else {
    win.loadURL("http://127.0.0.1:5173");
  }
}

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
