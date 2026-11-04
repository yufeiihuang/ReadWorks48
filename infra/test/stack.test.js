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
  assert.deepEqual(config.CacheBehaviors.map(b => b.PathPattern).sort(), ['/api/*', '/generated/*', '/generated/*/current.json']);
  assert.equal(ofType('AWS::CloudFront::OriginAccessControl').length, 2);
  const pointer = config.CacheBehaviors.find(b => b.PathPattern === '/generated/*/current.json');
  const generated = config.CacheBehaviors.find(b => b.PathPattern === '/generated/*');
  assert.notDeepEqual(pointer.CachePolicyId, generated.CachePolicyId);
  assert.ok(config.CacheBehaviors.indexOf(pointer) < config.CacheBehaviors.indexOf(generated));
});
test('only read-only passage API is public; generation is private', () => {
  const routes = ofType('AWS::ApiGatewayV2::Route');
  assert.equal(routes.length, 1);
  assert.equal(routes[0].Properties.RouteKey, 'GET /api/{proxy+}');
  assert.equal(ofType('AWS::Lambda::Url').length, 0);
  assert.ok(ofType('AWS::Lambda::Function').some(r => r.Properties.Runtime === 'python3.14'));
});
test('Polly and human source uploads use separate notifications, excluding generated output', () => {
  const config = ofType('Custom::S3BucketNotifications')[0].Properties.NotificationConfiguration.LambdaFunctionConfigurations;
  assert.equal(config.length, 2);
  assert.deepEqual(config.map(c => c.Filter.Key.FilterRules.find(r => r.Name === 'prefix').Value).sort(), ['human-passages/', 'passages/']);
  for (const item of config) {
    assert.deepEqual(item.Events, ['s3:ObjectCreated:*']);
    assert.ok(item.Filter.Key.FilterRules.some(r => r.Name === 'suffix' && r.Value === '.json'));
  }
});
test('human transcription waits in Step Functions, with a bounded timeout and no public endpoint', () => {
  const machines = ofType('AWS::StepFunctions::StateMachine');
  assert.equal(machines.length, 1);
  const definition = JSON.stringify(machines[0].Properties.DefinitionString);
  assert.match(definition, /WaitForHumanTranscript/);
  assert.match(definition, /Seconds/);
  assert.match(definition, /1800/);
  assert.equal(ofType('AWS::Lambda::Url').length, 0);
  const humanTask = resources.find(r => r.Type === 'AWS::Lambda::Function' && r.Properties.Handler === 'human_handler.handler');
  assert.equal(humanTask.Properties.Timeout, 120);
  const policies = JSON.stringify(ofType('AWS::IAM::Policy'));
  assert.match(policies, /transcribe:StartTranscriptionJob/);
  assert.match(policies, /transcription-job\/soundworks-human-/);
  assert.ok(!policies.includes('transcribe:*'));
});

test('Transcribe start uses supported output-location conditions, while reads are restricted to our job names', () => {
  const statements = ofType('AWS::IAM::Policy').flatMap(p => p.Properties.PolicyDocument.Statement);
  const containsAction = (statement, action) => [statement.Action].flat().includes(action);
  const start = statements.find(s => containsAction(s, 'transcribe:StartTranscriptionJob'));
  const get = statements.find(s => containsAction(s, 'transcribe:GetTranscriptionJob'));
  assert.equal(start.Resource, '*');
  assert.ok(start.Condition.StringEquals['transcribe:OutputBucketName']);
  assert.equal(start.Condition.StringLike['transcribe:OutputKey'], 'human-transcripts/*');
  assert.match(JSON.stringify(get.Resource), /transcription-job\/soundworks-human-/);
  assert.notEqual(get.Resource, '*');
});
