---
name: belief-state-runtime
description: LLM-driven epistemic reasoning engine. Evaluates claims against evidence, outputs calibrated confidence and structured belief state (VERIFIED/CONTESTED/UNCERTAIN). Use when the agent needs to assess whether information is trustworthy, detect contradictions in evidence, or quantify uncertainty.
---

# belief-state-runtime.skill

Evaluates the trustworthiness of a claim based on evidence.

## When to use

- User asks "is this true?" or "can I trust this?"
- Agent collects information from multiple sources and needs to assess reliability
- Detecting contradictions between evidence pieces
- Quantifying confidence in a conclusion

## ⚡ AUTO WORKFLOW (Default - Always Run This First)

**IMPORTANT: When this skill is triggered, you MUST follow this workflow automatically:**

```python
from assess import get_assessment_prompt, assess_claim_with_response

# Step 1: SEARCH FOR EVIDENCE (MANDATORY)
# Use your search tool (online-search, multi-search-engine, etc.) to find
# real, verifiable evidence about the claim. Search for:
#   - Official data and statistics
#   - Academic research and studies
#   - Credible news reports
#   - Expert opinions
#
# Example search queries:
#   - "[claim topic] facts evidence research"
#   - "[claim topic] statistics studies 2024"
#   - "专家观点 [claim topic]"

# Step 2: Get the assessment prompt
prompt = get_assessment_prompt(claim="The claim", evidence="Search results + user's evidence")

# Step 3: YOU (the AI) answer the prompt with 6 boolean judgments
# Based on your search results and analysis:
#   - direct_support: Does the evidence support the claim?
#   - new_info: Does it provide new information?
#   - logical_consistent: Is it logically consistent?
#   - direct_refute: Does it explicitly refute the claim?
#   - limitation: Are there limitations or exceptions?
#   - error_outdated: Is the claim outdated or wrong?
#
# Your answer format:
#   {"direct_support": true/false, "new_info": true/false, "logical_consistent": true/false, "direct_refute": true/false, "limitation": true/false, "error_outdated": true/false}

# Step 4: Get final result
result = assess_claim_with_response(
    claim="The claim",
    evidence="Search results + user's evidence",
    llm_response='{"direct_support": true, ...}'  # YOUR judgment
)

# Step 5: Present the result to the user
# Include: state, confidence, summary, and your interpretation
```

### Workflow Summary (Quick Reference)

| Step | Action | Tool/Function |
|------|--------|---------------|
| 1 | **Search for evidence** | online-search / multi-search-engine |
| 2 | **Get assessment prompt** | `get_assessment_prompt(claim, evidence)` |
| 3 | **Make 6 judgments** | YOU (the AI) |
| 4 | **Get result** | `assess_claim_with_response(claim, evidence, llm_response)` |
| 5 | **Present to user** | Your response |

## How it works

1. **Search for evidence** (MANDATORY): Use search tools to find real, verifiable evidence about the claim. This includes official data, academic research, credible news, and expert opinions.

2. **Rule layer** (Python): Extracts source reliability, evidence density, temporal freshness from the evidence text using URL matching, keyword detection, and year extraction.

3. **LLM layer** (YOU): The AI agent answers 6 boolean questions about the evidence:
   - Does it directly support the claim?
   - Does it provide new information?
   - Is it logically consistent?
   - Does it explicitly refute the claim?
   - Does it point out limitations?
   - Does it reveal errors or outdated info?

4. **Aggregation** (Python): Combines rule signals and your judgments into a calibrated confidence score and state.

## Output

```json
{
  "state": "VERIFIED",
  "confidence": 0.83,
  "confidence_range": [0.68, 0.98],
  "features": {"direct_support": true, "new_info": true, ...},
  "summary": "Evidence strongly supports the claim"
}
```

States:
- **VERIFIED** (confidence >= 0.65): Agent can cite this information
- **CONTESTED** (0.25 < confidence < 0.65): Agent should note "there is disagreement"
- **UNCERTAIN** (confidence <= 0.25): Agent should say "need more information"

## Incremental updates

When evidence arrives in stages, the engine updates beliefs incrementally:

```python
prompt = get_assessment_prompt(claim, evidence="stage 1")
# AI answers...
result1 = assess_claim_with_response(claim, evidence="stage 1", llm_response=ai_answer)

prompt = get_assessment_prompt(claim, evidence="stage 1 + stage 2")
# AI answers...
result2 = assess_claim_with_response(claim, evidence="stage 1 + stage 2",
                                     llm_response=ai_answer,
                                     previous_confidence=result1["confidence"])
```

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| claim | string | Yes | The claim to evaluate |
| evidence | string | No | Evidence text |
| previous_confidence | float | No | Previous confidence for incremental update |
| llm_response | string | Yes | AI agent's JSON response to the assessment prompt |

## Legacy API

For backward compatibility, `assess_claim()` with `llm_func` callback still works.

```python
from assess import assess_claim
result = assess_claim(claim="...", evidence="...", llm_func=my_llm)
```
