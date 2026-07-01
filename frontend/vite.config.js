import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
// TradingBrain frontend dev server runs on port 5174 (backend on 8200).
// strictPort ensures Vite fails rather than silently picking another port,
// keeping it aligned with the backend CORS allow-list.
export default defineConfig({
    plugins: [react()],
    server: {
        port: 5174,
        strictPort: true,
    },
    preview: {
        port: 5174,
        strictPort: true,
    },
});
