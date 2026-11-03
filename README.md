# SoundWorks

Three-day ReadWorks hackathon scaffold: Vue reader, Express API, Python audio preparation, and AWS CDK infrastructure. Narration will use Polly Neural.

## Start locally

Use Node 24 LTS (`nvm use` if available). Node 20.19+ also runs the current scaffold.

```sh
npm ci
npm run dev
```

Open http://127.0.0.1:5173. Vite forwards `/api` requests to Express on port 3001. The page loads the generated Stephen Neural sample with the atomic audio console, live highlighting, and word replay. `/preview.html` opens the same reader. The existing-recording reference is available at `/?passage=pride-and-prejudice`; it has no timings yet.

## Checks

```sh
npm run build
npm run check
python3 generation/generate.py shared/fixtures/demo.json --validate-only
```

`npm run check` checks API syntax and synthesizes the CDK template without deploying resources.

## Layout and ownership

| Folder | Responsibility | Builder |
| --- | --- | --- |
| apps/reader | Vue interface; playback controller and synchronization | A + C |
| apps/api | Express passage routes and source adapter | D |
| generation | Python Polly and timing preparation | B |
| infra | CDK sandbox resources and deployment | E |
| shared/fixtures | Shared manifest and sample passage | A + B + D |

See [architecture and contract](docs/architecture.md).

## Generation setup

```sh
python3 -m venv generation/.venv
source generation/.venv/bin/activate
pip install -r generation/requirements.txt
```

The generation workflow now produces Stephen Neural audio and word timings, including automatic chunking for long passages. See [generation instructions](docs/generation.md) for one-command preparation, S3 publishing, and the reader contract. No AWS credentials are needed for local development. Never put credentials in frontend files or commit them.

## Infrastructure

See [sandbox deployment guide](docs/deployment.md). CDK defines HTTPS CloudFront hosting, private encrypted/versioned S3 buckets, an Express Lambda/API Gateway, and an IAM-only Python generation Lambda foundation. All browser requests use the same origin; no permissive CORS policy is needed.

```sh
npm run test -w @soundworks/infra
npm run diff -w @soundworks/infra
npm run deploy -w @soundworks/infra -- --outputs-file cdk.out/outputs.json
```

The private generation Lambda accepts a complete passage object and prepares Stephen Neural narration and timings. No generation endpoint is public. Deployment requires temporary sandbox credentials and may require CDK bootstrapping. Buckets are retained when the stack is deleted; see the cleanup instructions.
