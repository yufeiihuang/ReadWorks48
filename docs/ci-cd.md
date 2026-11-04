# GitHub Actions deployment

`.github/workflows/ci-deploy.yml` runs API, reader, and Python generation tests, builds the reader, and checks the synthesized AWS stack on every pull request to `main`. No AWS credentials are provided to PR jobs. After a merge to `main`, the same checks must pass before deployment starts. A manual run from `main` is also supported.

Deployment updates the existing `SoundWorksSandbox` CDK stack in `us-west-2`: reader files in S3, CloudFront cache invalidation, Express API Lambda, Python generation Lambda, and infrastructure changes. It preserves passage assets in the separate bucket. CDK waits for the website deployment/invalidation, then the workflow checks the reader assets and API routes and puts the reader URL and deployed commit in the run summary. It does not regenerate every passage or run paid Polly/Transcribe jobs.

Only one main-branch workflow runs at a time; an active deployment is never canceled by a newer commit. GitHub may replace an intermediate pending run with the newest one. Keep manual local deployments out of the way while an Actions deployment runs.

## One-time workshop setup

An AWS account administrator or workshop facilitator must authorize the deployment role. Workshop access may forbid IAM identity providers or roles; if so, keep CI and manual deployment until the facilitator grants an approved role or move to a team-owned account. Do not replace this with shared access keys or copied workshop session credentials.

1. Sign in with your own workshop CLI access and verify the account with `aws sts get-caller-identity`. The account must be the existing deployment account. CDK bootstrap is already present; do not change workshop guardrails or rebootstrap with broader trust.
2. Check whether the GitHub provider already exists:

   ```sh
   aws iam list-open-id-connect-providers
   ```

3. Review `infra/github-oidc.json`, then create the separate access stack with authorized AWS credentials:

   ```sh
   aws cloudformation deploy \
     --region us-west-2 \
     --stack-name SoundWorksGitHubAccess \
     --template-file infra/github-oidc.json \
     --capabilities CAPABILITY_IAM
   ```

   If the provider already exists, append `--parameter-overrides ExistingProviderArn=arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com`. Do not create a second provider for the same URL or delete a shared provider.

   This role can assume the account's existing CDK deployment, file-publishing, and lookup roles in this region. Those bootstrap roles ultimately use the existing CloudFormation execution permissions, which may be broad. This is deployment authority, not a narrowly restricted S3 uploader. Use only the authorized workshop account; a production migration should review and restrict the CloudFormation execution role separately.

4. Read the new role ARN:

   ```sh
   aws cloudformation describe-stacks --region us-west-2 \
     --stack-name SoundWorksGitHubAccess \
     --query 'Stacks[0].Outputs[?OutputKey==`DeployRoleArn`].OutputValue' --output text
   ```

5. Add two **repository variables** in GitHub → Settings → Secrets and variables → Actions → Variables, or use:

   ```sh
   gh variable set AWS_ACCOUNT_ID --body YOUR_12_DIGIT_WORKSHOP_ACCOUNT_ID
   gh variable set AWS_DEPLOY_ROLE_ARN --body YOUR_DEPLOY_ROLE_ARN
   ```

   These identifiers are not credentials. AWS issues short-lived credentials during the workflow. No AWS secrets are needed.

6. Merge the workflow PR, then watch Actions → CI and deploy. The first main run deploys only after checks pass. If the workflow is merged before the AWS setup is complete, checks still run and deployment fails with a setup message. After setup, rerun the failed jobs or use Run workflow on `main`.

## Trust and repository settings

The role trusts only this repository's `main` branch and the `sts.amazonaws.com` audience. This repo uses GitHub's immutable OIDC subject format; the template includes the verified owner/repository IDs:

```text
repo:yufeiihuang@170985509/ReadWorks48@1444655571:ref:refs/heads/main
```

Fork PRs and feature branches cannot assume it. The workflow intentionally has no GitHub Environment: adding one changes the token subject and requires a matching trust policy plus main-only environment deployment rules. A repo transfer, OIDC customization, or a new repo requires updating trust first. Check the subject configuration using `gh api repos/yufeiihuang/ReadWorks48/actions/oidc/customization/sub`.

Protect `main` with required PR reviews and the **Build and test** check before merging. Restrict who can edit workflow files and merge changes because merged code can deploy AWS changes. Actions are pinned to commit SHAs; update those pins deliberately when upgrading actions.

References: [GitHub AWS OIDC](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws), [CDK bootstrap roles](https://docs.aws.amazon.com/cdk/v2/guide/bootstrapping-env.html).

## Failures and rollback

- A failed test prevents deployment. Fix it through a PR.
- An OIDC error usually means the role ARN/account variable is incorrect, the token subject differs, or workshop IAM permissions do not allow the role. Refreshing local workshop credentials does not fix Actions OIDC trust.
- A failed CDK update normally rolls back through CloudFormation; inspect the stack events. Do not retry a stack in `UPDATE_ROLLBACK_FAILED` until its rollback issue is resolved.
- A failed smoke check reports a failed run even if CloudFormation completed. Inspect the deployed app before deciding whether to revert; smoke failures do not automatically roll back a completed deployment.
- Revert a faulty application change through a PR and merge it. That creates a new main commit and redeploys the previous code. Do not launch an old workflow run to roll back, because that can deploy an outdated stack template unexpectedly.
- To pause automatic deployment, disable the workflow in GitHub Actions. This also pauses its CI checks; use manual checks until it is reenabled. Remove the access stack/role when workshop access ends, with administrator approval and care for any reused OIDC provider.
