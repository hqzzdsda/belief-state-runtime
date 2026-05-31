# belief-state-runtime (c) 2026 hqzzdsda — MIT License
# https://github.com/hqzzdsda/belief-state-runtime

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI wrapper for belief-assessor skill.
Allows skillbench to test the skill as if it were a CLI tool.
"""

import sys
import json
import argparse
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from assess import assess_claim


def main():
    parser = argparse.ArgumentParser(description="Belief Assessor CLI")
    parser.add_argument("claim", help="The claim to evaluate")
    parser.add_argument("--evidence", default="", help="Evidence text")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    args = parser.parse_args()
    
    # Simple mock LLM for CLI testing
    def mock_llm(messages, temperature, max_tokens):
        return json.dumps({
            "direct_support": "consensus" in args.evidence.lower(),
            "new_info": False,
            "logical_consistent": True,
            "direct_refute": "no evidence" in args.evidence.lower(),
            "limitation": False,
            "error_outdated": False
        })
    
    result = assess_claim(
        claim=args.claim,
        evidence=args.evidence,
        llm_func=mock_llm
    )
    
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"State: {result['state']}")
        print(f"Confidence: {result['confidence']:.2f}")
        print(f"Summary: {result['summary']}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
