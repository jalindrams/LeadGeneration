import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: Vite on :5173 proxies /api to the ASP.NET API on :5080.
// Build: output goes into the API's wwwroot so one process serves everything.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': 'http://localhost:5080', '/health': 'http://localhost:5080' } },
  build: { outDir: '../Api/wwwroot', emptyOutDir: true },
})
