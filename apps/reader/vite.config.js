import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath } from 'node:url';
export default defineConfig({
  plugins: [vue()],
  build: { rollupOptions: { input: {
    main: fileURLToPath(new URL('./index.html', import.meta.url)),
    preview: fileURLToPath(new URL('./preview.html', import.meta.url)),
  } } },
  server: { proxy: {
    '/api': 'http://127.0.0.1:3001',
    '/generated': { target: 'https://d1381qenwhm2qw.cloudfront.net', changeOrigin: true },
  } },
});
