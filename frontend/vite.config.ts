import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Vite-Konfiguration: React + Tailwind v4.
// Der Tailwind-Vite-Plugin ersetzt in v4 den früheren PostCSS-Weg
// (kein tailwind.config.js, keine @tailwind-Direktiven mehr —
// stattdessen ein einzelner @import "tailwindcss" in index.css).
export default defineConfig({
  plugins: [react(), tailwindcss()],
})
