import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // The build writes into public/, which is what Vercel's Flask runtime serves
  // statically — so the static source directory cannot also be public/ or the
  // build would copy its own output into itself.
  publicDir: 'static',
  build: {
    outDir: 'public',
    emptyOutDir: true,
  },
  server: {
    port: 3000,
  },
});
