"""
CLI: verify ActionsDecided pointer integrity.
"""

import argparse
import json
import sys

# Clean bootstrap for CLI output
from engine.cli._bootstrap import bootstrap

bootstrap()

from engine.verify import verify_actions_decided_pointers


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify ActionsDecided pointers.")
    parser.add_argument("--log", required=True, help="Path to JSONL event log")
    args = parser.parse_args()

    result = verify_actions_decided_pointers(args.log)
    print(json.dumps(result.__dict__, sort_keys=True, indent=2))
    return 0 if result.valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
