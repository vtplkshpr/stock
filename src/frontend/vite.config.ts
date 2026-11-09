import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` serves the frontend on :5173 and forwards /api to the Python server
// (python src/backend/server.py). `npm run build` writes dist/, which that server serves itself.
// To call an API on another host, build with VITE_API_BASE_URL=http://<host>:<port>.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": process.env.DIAGRAM_API ?? "http://127.0.0.1:8765" },
  },
  build: { outDir: "dist", emptyOutDir: true, chunkSizeWarningLimit: 1200 },
});
