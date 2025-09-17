// vite.config.js
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:5001/synergyforge-ce43e/us-central1",
        changeOrigin: true,
        rewrite: (p) => {
          if (p === "/api/oauth/client") return "/oauthClientCreds";
          if (p === "/api/whoami") return "/whoami";
          if (p === "/api/tokenDebug") return "/tokenDebug";
          if (p.startsWith("/api/datasets")) return p.replace(/^\/api\/datasets/, "/datasets");
          if (p.startsWith("/api/msf")) return p.replace(/^\/api\/msf/, "/msfProxy");
          if (p === "/api/sync") return "/syncGameRef";
          return p;
        },
      },
    },
  },
});
