import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // The build writes into public/, which is what Vercel's Flask runtime serves
  // statically. We have no hand-authored static assets, so Vite's public-dir
  // copy is turned off — left on, it would try to copy the output into itself.
  publicDir: false,
  build: {
    outDir: 'public',
    emptyOutDir: true,
  },
  server: {
    port: 3000,
  },
});
