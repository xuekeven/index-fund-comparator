const path = require("node:path");

const root = __dirname;

module.exports = {
  apps: [
    {
      name: "index-fund-api",
      cwd: path.join(root, "backend"),
      script: ".venv/bin/uvicorn",
      args: "app.main:app --host 0.0.0.0 --port 8000",
      interpreter: "none",
      autorestart: true,
      max_restarts: 10,
      restart_delay: 3000,
      time: true,
    },
  ],
  static: [
    {
      name: "index-fund-web",
      path: path.join(root, "frontend", "dist"),
      port: 3000,
      spa: true,
    },
  ],
};
