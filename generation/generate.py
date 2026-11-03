"""Prepare matching Stephen Neural narration and word timings with one command."""
import argparse
import json
import sys
from pathlib import Path
from pipeline import prepare, validate_passage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('passage', type=Path)
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--output', type=Path, default=Path(__file__).parent / 'output')
    parser.add_argument('--voice', default='Stephen')
    parser.add_argument('--region', default='us-west-2')
    parser.add_argument('--profile')
    parser.add_argument('--bucket', help='Optional S3 destination; manifest is uploaded last')
    parser.add_argument('--force', action='store_true', help='Bypass both the S3 and local caches')
    args = parser.parse_args()
    try:
        passage = json.loads(args.passage.read_text())
        validate_passage(passage)
        if args.validate_only:
            print(f"Valid generation input: {passage['id']}")
            return
        import boto3
        from botocore.config import Config
        session = boto3.Session(profile_name=args.profile, region_name=args.region)
        polly = session.client('polly', config=Config(retries={'mode': 'standard', 'max_attempts': 4}))
        prepared = prepare(passage, args.output, polly, s3=session.client('s3') if args.bucket else None,
                           bucket=args.bucket, voice=args.voice, force=args.force)
        manifest, directory = prepared['manifest'], prepared['directory']
        result = {'manifest': str(directory / 'manifest.json') if directory else prepared['manifestUrl'],
                  'audio': str(directory / 'audio.wav') if directory else manifest['audio']['url'],
                  'cached': prepared['cached'], 'cacheSource': prepared['cacheSource'],
                  'synthesisRequestCharacters': prepared['synthesisRequestCharacters'],
                  'words': len(manifest['tokens']), 'generation': manifest['generation']}
        if args.bucket:
            result['manifestUrl'] = prepared['manifestUrl']
        print(json.dumps(result, indent=2))
    except Exception as error:
        print(f'Generation failed: {error}', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
