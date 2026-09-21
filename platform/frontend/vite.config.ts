import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // The backend's CORS policy allows exactly this origin. If 5173 is taken, Vite
    // would otherwise move to 5174 silently, and every API call would then fail in
    // the browser as "TypeError: Failed to fetch", with nothing pointing at the
    // port. strictPort makes Vite stop with "Port 5173 is in use" instead.
    port: 5173,
    strictPort: true,
  },
})
