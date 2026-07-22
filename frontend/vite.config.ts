import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      // Types-only file: erased at build time, never served at runtime.
      "@contracts": fileURLToPath(
        new URL("../contracts/generated/contracts.ts", import.meta.url),
      ),
    },
  },
  server: {
    // Dev loop: `make up` (API on :8000) + `npm run dev`. Same-origin in prod
    // via nginx — never hardcode an API origin.
    proxy: { "/api": "http://localhost:8000" },
    fs: { allow: [".."] },
  },
});
