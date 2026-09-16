import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1", port: 5173, strictPort: true,
    // This workspace lives on a mounted Windows drive; native file events can
    // miss edits and leave Vite serving stale transformed modules.
    watch: { usePolling: true, interval: 300 },
  },
});
