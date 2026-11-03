# SoundWorks

Three-day ReadWorks hackathon scaffold: Vue reader, Express API, Python audio preparation, and AWS CDK infrastructure. Narration will use Polly Neural.

## Start locally

Use Node 24 LTS (`nvm use` if available). Node 20.19+ also runs the current scaffold.

```sh
npm ci
npm run dev
```

Open http://127.0.0.1:5173. Vite forwards `/api` requests to Express on port 3001. The page loads original demo text; audio controls are intentionally disabled until the generation and playback tickets are implemented.

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

The generation entry point currently validates required input fields only. Polly calls and Lambda packaging are follow-up work. No AWS credentials are needed for local development. Never put credentials in frontend files or commit them.

## Infrastructure

The initial stack defines a private encrypted, versioned S3 asset bucket in `us-west-2`, retained on stack deletion. Reader hosting, API deployment, and generation Lambda are not implemented yet.

With sandbox credentials configured, review changes before deploying:

```sh
npm run diff -w @soundworks/infra
npm run deploy -w @soundworks/infra
```

Deployment may require bootstrapping the AWS sandbox first. No resources have been deployed by this scaffold.
