# Sandbox deployment

## Resources

- Private, encrypted, versioned S3 passage bucket. Only `generated/*` is readable through CloudFront; other objects remain private.
- Separate private website bucket, readable only through CloudFront origin access control.
- HTTPS CloudFront reader URL. `/api/*` routes to the Express API without caching. `/generated/*` routes to prepared passage assets. Relative browser URLs avoid cross-origin requests.
- Node.js 24 Express Lambda and HTTP API exposing only GET passage routes. The sample is bundled into the function; S3-backed passage discovery is follow-up work.
- Python 3.14 generation Lambda with no public endpoint. It has access to `generated/*` and `polly:SynthesizeSpeech`. This is a foundation, not working narration generation.

Only approved/public demonstration content belongs in publicly delivered paths. Never publish credentials, student records, or private source documents there. No custom domain, database, VM, or VPC is required.

## Prerequisites

- Node.js 24 (`nvm use` if you use nvm) and npm.
- Access to the team's Workshop Studio sandbox. Everyone must deploy to the same account and `us-west-2` region to update this environment.
- AWS credentials with permission to deploy the stack. The CDK CLI is installed by `npm ci`; a separate global CDK installation is unnecessary.

## Authenticate and deploy

Open Workshop Studio → AWS account access → Get AWS CLI credentials → Linux or macOS (bash). Copy the export commands into the terminal you will use to deploy. These set short-lived credentials for that terminal session. Refresh them from Workshop Studio if you receive an expired-token error. Do not save them in source files, commit them, or paste them into chat. An existing authenticated AWS profile is also supported.

Use the sandbox account, not a personal or production account. Deployment region defaults to `us-west-2`.

```sh
npm ci
npm run test -w @soundworks/infra
# Only needed once per AWS account/region; this sandbox is already bootstrapped.
npm run bootstrap -w @soundworks/infra
npm run diff -w @soundworks/infra
npm run deploy -w @soundworks/infra -- --outputs-file cdk.out/outputs.json
```

For a named profile, pass it after npm's `--`, for example `npm run diff -w @soundworks/infra -- --profile YOUR_PROFILE`.

The scripts rebuild Vue before synthesis, diff, and deployment. The root lockfile is used to bundle Express and its dependencies. CDK prints ReaderUrl, ApiUrl, bucket names, and GenerationFunctionName. Bootstrap only initializes the sandbox's CDK tooling; leave organizer-managed guardrails untouched.

## Deploy future changes

Develop and check changes locally, then refresh sandbox credentials and deploy from the repo root:

```sh
npm ci
npm run check -w @soundworks/api
npm run test -w @soundworks/infra
npm run diff -w @soundworks/infra
npm run deploy -w @soundworks/infra -- --outputs-file cdk.out/outputs.json
node scripts/smoke-deployment.mjs https://d1381qenwhm2qw.cloudfront.net
```

Review the diff before accepting deployment. Vue changes upload to the website bucket and invalidate CloudFront's cache. Express changes update the bundled API Lambda. Python generation changes update its Lambda package. CDK changes update the AWS resources and permissions described by the stack. Use ReaderUrl from the latest deployment outputs if recreating the environment changes the domain.

GitHub pushes do not deploy automatically. Coordinate deployments so two builders do not update the shared stack simultaneously. Never edit deployed functions manually in the AWS console; keep deployable changes in this repo.

## Verify after deployment

Run `node scripts/smoke-deployment.mjs https://READER_DOMAIN` from the repo root. Open ReaderUrl and confirm the sample passage renders. Check `ReaderUrl/api/health` returns `{"status":"ok"}`, `/api/passages` returns a listing, `/api/passages/demo` returns the manifest, and `/api/passages/missing` returns 404. Check developer tools for failed asset requests. Audio is intentionally unavailable in this skeleton.

Use an authenticated AWS Lambda invocation to test the private generation foundation with `{"passageId":"demo"}`; expect `status: not_implemented`, not successful narration. Once generation is implemented, verify a generated audio/timing object through `/generated/...`.

## Cleanup

Delete only the SoundWorksSandbox stack when it is no longer needed. Both versioned buckets are deliberately retained to avoid accidental data loss, so they may continue to incur storage costs. Review and remove retained data separately when authorized. Do not delete or change the workshop base stack, audit trail, or budget controls. Workshop access expires at the event deadline.

## Verified sandbox deployment

Deployed November 3, 2026 to `us-west-2`.

- Reader: https://d1381qenwhm2qw.cloudfront.net
- API: https://rygjnadug4.execute-api.us-west-2.amazonaws.com
- Stack: `SoundWorksSandbox`
- Checks: reader HTML and static assets, health/list/detail API routes, missing-passage 404, private generation invocation, generated-object delivery through CloudFront, private/versioned buckets, and blocked unauthenticated direct S3 reads.
- Temporary deployment credentials were removed after verification.

Audio generation is still a stub, as expected for SW-05. The sample manifest remains bundled with Express until the source-adapter/storage tickets are completed.
