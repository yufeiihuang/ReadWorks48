import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { fileURLToPath } from 'node:url';
import { createReadStream, statSync } from 'node:fs';
import { join } from 'node:path';

// Dev only: serve recordings made with `generate.py` (no --bucket) from generation/output, so they
// can be heard without publishing. Anything not found locally goes on to the CloudFront proxy.
const localOutput = fileURLToPath(new URL('../../generation/output/', import.meta.url));
const types = { '.json': 'application/json', '.wav': 'audio/wav', '.mp3': 'audio/mpeg' };
function localGeneration() {
  return {
    name: 'soundworks-local-generation',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const path = (req.url || '').split('?')[0];
        const words = path.match(/^\/generated\/words\/([A-Za-z0-9_-]+)\/([a-f0-9]{20}\.mp3)$/);
        const asset = path.match(/^\/generated\/([A-Za-z0-9_-]+)\/([a-f0-9]{20})-[a-f0-9]{12}\/([a-z-]+\.(?:json|wav))$/);
        const file = words ? join(localOutput, 'generated', 'words', words[1], words[2])
          : asset ? join(localOutput, asset[1], asset[2], asset[3]) : null;
        let size = 0;
        try { size = file ? statSync(file).size : 0; } catch {}
        if (!size) return next();
        const type = types[file.slice(file.lastIndexOf('.'))];
        const range = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range || '');
        if (range) {
          // Audio elements seek with range requests.
          const start = range[1] ? Number(range[1]) : size - Number(range[2]);
          const end = range[1] && range[2] ? Math.min(Number(range[2]), size - 1) : size - 1;
          res.writeHead(206, { 'Content-Type': type, 'Content-Length': end - start + 1, 'Content-Range': `bytes ${start}-${end}/${size}`, 'Accept-Ranges': 'bytes' });
          createReadStream(file, { start, end }).pipe(res);
          return;
        }
        res.writeHead(200, { 'Content-Type': type, 'Content-Length': size, 'Accept-Ranges': 'bytes' });
        createReadStream(file).pipe(res);
      });
    },
  };
}

export default defineConfig({
  plugins: [vue(), localGeneration()],
  build: { rollupOptions: { input: {
    main: fileURLToPath(new URL('./index.html', import.meta.url)),
    preview: fileURLToPath(new URL('./preview.html', import.meta.url)),
  } } },
  server: { proxy: {
    '/api': 'http://127.0.0.1:3001',
    '/generated': { target: 'https://d1381qenwhm2qw.cloudfront.net', changeOrigin: true },
  } },
});
