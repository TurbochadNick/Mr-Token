import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  root: 'web',
  plugins: [react()],
  build: {
    outDir: '../dist/ui',
    emptyOutDir: true
  },
  server: {
    host: '127.0.0.1',
    port: 4317
  }
});
