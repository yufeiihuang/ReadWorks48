import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const template = JSON.parse(readFileSync(new URL('../cdk.out/SoundWorksSandbox.template.json', import.meta.url)));
const resources = Object.values(template.Resources);
const ofType = type => resources.filter(r => r.Type === type);
test('both storage buckets are private, encrypted, versioned, and retained', () => {
  assert.equal(ofType('AWS::S3::Bucket').length, 2);
  for (const bucket of ofType('AWS::S3::Bucket')) {
    assert.equal(bucket.DeletionPolicy, 'Retain');
    assert.equal(bucket.Properties.VersioningConfiguration.Status, 'Enabled');
    assert.ok(bucket.Properties.BucketEncryption);
    assert.ok(Object.values(bucket.Properties.PublicAccessBlockConfiguration).every(Boolean));
  }
});
test('reader, API, and generated assets share HTTPS distribution', () => {
  const config = ofType('AWS::CloudFront::Distribution')[0].Properties.DistributionConfig;
  assert.equal(config.DefaultRootObject, 'index.html');
  assert.equal(config.DefaultCacheBehavior.ViewerProtocolPolicy, 'redirect-to-https');
  assert.deepEqual(config.CacheBehaviors.map(b => b.PathPattern).sort(), ['/api/*', '/generated/*']);
  assert.equal(ofType('AWS::CloudFront::OriginAccessControl').length, 2);
});
test('only read-only passage API is public; generation is private', () => {
  const routes = ofType('AWS::ApiGatewayV2::Route');
  assert.equal(routes.length, 1);
  assert.equal(routes[0].Properties.RouteKey, 'GET /api/{proxy+}');
  assert.equal(ofType('AWS::Lambda::Url').length, 0);
  assert.ok(ofType('AWS::Lambda::Function').some(r => r.Properties.Runtime === 'python3.14'));
});
