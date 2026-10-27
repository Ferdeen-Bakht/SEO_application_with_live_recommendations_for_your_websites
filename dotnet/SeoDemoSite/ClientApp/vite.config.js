import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In production the .NET app serves ClientApp/dist. In `npm run dev`, API calls are proxied to .NET.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:5055' } },
})
