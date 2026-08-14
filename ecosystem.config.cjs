const path = require("node:path");

const root = __dirname;

module.exports = {
  apps: [
    {
      name: "index-fund-api",
      cwd: path.join(root, "backend"),
      script: ".venv/bin/uvicorn",
      args: "app.main:app --host 127.0.0.1 --port 6006",
      interpreter: "none",
      autorestart: true,
      max_restarts: 10,
      restart_delay: 3000,
      time: true,
    },
  ],
};
