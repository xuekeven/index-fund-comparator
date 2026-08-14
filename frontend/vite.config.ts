import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const apiProxy = {
  "/indexfund/api": {
    target: "http://127.0.0.1:7006",
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/indexfund/, ""),
  },
};

export default defineConfig({
  base: "/indexfund/",
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL(".", import.meta.url)),
    },
  },
  server: {
    host: "127.0.0.1",
    port: 6006,
    proxy: apiProxy,
  },
  preview: {
    host: "127.0.0.1",
    port: 6006,
    proxy: apiProxy,
  },
});
