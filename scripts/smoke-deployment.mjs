import assert from 'node:assert/strict';
const base = process.argv[2];
if (!base || !base.startsWith('https://')) throw new Error('Usage: node scripts/smoke-deployment.mjs https://READER_DOMAIN');
for (const [path, status] of [['/',200],['/api/health',200],['/api/passages',200],['/api/passages/demo',200],['/api/passages/missing',404]]) {
  const response = await fetch(new URL(path, base));
  assert.equal(response.status, status, path);
  if (path === '/') {
    const html = await response.text();
    assert.ok(html.includes('<div id="app"></div>'));
    for (const asset of html.matchAll(/(?:src|href)="(\/assets\/[^\"]+)"/g)) {
      const result = await fetch(new URL(asset[1], base));
      assert.equal(result.status,200,asset[1]);
    }
  } else {
    const data = await response.json();
    if (path === '/api/health') assert.equal(data.status,'ok');
    if (path === '/api/passages/demo') assert.equal(data.id,'demo');
  }
  console.log(`${status} ${path}`);
}
