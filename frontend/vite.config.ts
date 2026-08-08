import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const rootDir = path.dirname(fileURLToPath(import.meta.url));

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: "/static/frontend/",
  build: {
    outDir: path.resolve(rootDir, "../static/frontend"),
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: path.resolve(rootDir, "src/main.tsx"),
      output: {
        entryFileNames: "assets/main.js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: (info) => {
          const name = info.name || "";
          if (name.endsWith(".css")) {
            return "assets/main.css";
          }
          return "assets/[name]-[hash][extname]";
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/static": "http://127.0.0.1:8000",
      "/login": "http://127.0.0.1:8000",
      "/browse": "http://127.0.0.1:8000",
    },
  },
});
