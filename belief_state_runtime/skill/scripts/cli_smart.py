# belief-state-runtime (c) 2026 hqzzdsda — MIT License
# https://github.com/hqzzdsda/belief-state-runtime

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Better CLI for belief-assessor with improved mock LLM.
"""

import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from assess import assess_claim


def smart_mock_llm(messages, temperature, max_tokens):
    """Smarter mock LLM that actually analyzes evidence content."""
    # Extract claim and evidence from messages
    claim = ""
    evidence = ""
    
    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content", "")
            
            # Extract claim
            if "Claim:" in content:
                lines = content.split("\n")
                for i, line in enumerate(lines):
                    if line.startswith("Claim:"):
                        claim = line.replace("Claim:", "").strip()
                        break
            
            # Extract evidence
            if "Evidence:" in content:
                lines = content.split("\n")
                for i, line in enumerate(lines):
                    if line.startswith("Evidence:"):
                        evidence = "\n".join(lines[i+1:]).strip()
                        break
    
    # Smart analysis based on keywords
    evidence_lower = evidence.lower()
    claim_lower = claim.lower()
    
    # Check for strong support keywords
    has_consensus = any(word in evidence_lower for word in ["consensus", "prove", "confirm", "scientific", "satellite"])
    has_refutation = any(word in evidence_lower for word in ["no evidence", "debunked", "false", "fake"])
    
    # For "Earth is flat" claim with scientific evidence
    if "flat" in claim_lower and has_consensus:
        # This is a false claim with strong contradicting evidence
        return json.dumps({
            "direct_support": False,
            "new_info": False,
            "logical_consistent": True,
            "direct_refute": True,  # Evidence directly refutes the claim
            "limitation": False,
            "error_outdated": False
        })
    
    # Default: neutral
    return json.dumps({
        "direct_support": has_consensus,
        "new_info": False,
        "logical_consistent": True,
        "direct_refute": has_refutation,
        "limitation": False,
        "error_outdated": False
    })


def main():
    parser = argparse.ArgumentParser(description="Belief Assessor CLI (Smart Version)")
    parser.add_argument("claim", help="The claim to evaluate")
    parser.add_argument("--evidence", default="", help="Evidence text")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    args = parser.parse_args()
    
    result = assess_claim(
        claim=args.claim,
        evidence=args.evidence,
        llm_func=smart_mock_llm
    )
    
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"State: {result['state']}")
        print(f"Confidence: {result['confidence']:.2f}")
        print(f"Summary: {result['summary']}")
        if result.get('confidence_range'):
            print(f"Confidence Range: [{result['confidence_range'][0]:.2f}, {result['confidence_range'][1]:.2f}]")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
