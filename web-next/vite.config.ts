import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend only allows chrome-extension origins, so the site reaches it through this proxy.
const API = process.env.VITE_PROXY_TARGET ?? "http://127.0.0.1:8000";
export default defineConfig({
  plugins: [react()],
  server: { port: 5174, proxy: { "/v1": API, "/health": API } },
});