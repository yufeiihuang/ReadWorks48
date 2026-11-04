import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const template = JSON.parse(readFileSync(new URL('../github-oidc.json', import.meta.url)));
const role = template.Resources.DeployRole.Properties;

test('GitHub deployment trust excludes PRs, other branches, and other repositories', () => {
  const statements = role.AssumeRolePolicyDocument.Statement;
  assert.equal(statements.length, 1);
  assert.equal(statements[0].Action, 'sts:AssumeRoleWithWebIdentity');
  assert.deepEqual(statements[0].Condition, {
    StringEquals: {
      'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com',
      'token.actions.githubusercontent.com:sub': 'repo:yufeiihuang@170985509/ReadWorks48@1444655571:ref:refs/heads/main',
    },
  });
});

test('deployment identity delegates only to named regional CDK roles, not account administrators', () => {
  const statements = role.Policies.flatMap(p => p.PolicyDocument.Statement);
  const assume = statements.find(s => s.Action === 'sts:AssumeRole');
  assert.equal(assume.Resource.length, 3);
  for (const resource of assume.Resource) {
    assert.match(resource['Fn::Sub'], /:role\/cdk-hnb659fds-(deploy|file-publishing|lookup)-role-\$\{AWS::AccountId\}-\$\{AWS::Region\}$/);
    assert.ok(!resource['Fn::Sub'].includes('*'));
  }
  assert.equal(role.ManagedPolicyArns, undefined);
  assert.ok(statements.every(s => s.Action !== '*' && s.Resource !== '*'));
});
