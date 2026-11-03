"""Generation entry point. Implement Polly Neural and timing conversion in SW-02."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Validate a SoundWorks generation input")
    parser.add_argument("passage", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    passage = json.loads(args.passage.read_text())
    for field in ("id", "revision", "title", "language", "paragraphs"):
        if field not in passage:
            parser.error(f"Missing required field: {field}")
    if not args.validate_only:
        parser.error("Polly generation is not implemented yet. Use --validate-only to check input.")
    print(f"Valid generation input: {passage['id']}")


if __name__ == "__main__":
    main()
