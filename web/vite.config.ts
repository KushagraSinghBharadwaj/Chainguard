import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend only allows chrome-extension origins (CORS), so the site talks to it
// through this dev proxy. The backend needs no change.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/v1": "http://127.0.0.1:8000" } },
});
