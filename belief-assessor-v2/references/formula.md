# Belief Assessor v2 — Formula Reference

## Quality Factor Q

```
Q = 0.4 × source_reliability + 0.3 × evidence_density + 0.2 × temporal_freshness + 0.1 × provenance_quality
```

## Support & Refute Scores

```
support_score = (direct_support + 0.5 × new_info + 0.3 × logical_consistent) / 1.8
refute_score  = (direct_refute + 0.6 × error_outdated) / 1.6
```

## Raw Confidence

```
semantic = support_score × (1 - refute_score)
raw_conf = 0.6 × semantic + 0.4 × Q
if limitation: raw_conf ×= 0.85
```

## v2 Projection Layer

### Constraint Caps (in order)

| # | Constraint | Trigger | Cap | Effect |
|---|-----------|---------|-----|--------|
| 1 | Contradiction | refute_score ≥ contest_threshold | contradiction_cap (0.55) | Caps confidence |
| 1b | Contradiction dominates | refute > support × 2 | — | Force CONTESTED |
| 1c | Direct refute | direct_refute = True | 0.60 | Immediate CONTESTED |
| 2 | Provenance gate | quality_factor < min_provenance_quality | provenance_cap (0.60) | Cannot be VERIFIED |
| 3 | Temporal decay | temporal_freshness < decay_threshold AND NOT is_historical_claim(claim) | temporal_cap (0.50) | Demotes VERIFIED |
| 4 | Density floor | evidence_density < density_floor | density_cap (0.55) | Cannot be VERIFIED |

### Final State Determination

```
cannot_verify = (quality_factor < min_provenance_quality) OR (evidence_density < density_floor)

conf ≥ verify_threshold AND NOT cannot_verify  → VERIFIED
conf ≤ contest_threshold                        → UNCERTAIN
else                                            → CONTESTED
```

### Confidence Interval (Formula-based)

```
n_eff = max(int(evidence_density × 10), 1)
uncertainty_margin = (1 - quality_factor) × uncertainty_base + uncertainty_min / √n_eff
lower = max(scalar - uncertainty_margin, 0)
upper = min(scalar + uncertainty_margin, confidence_cap)
```

Semantics:
- High quality → narrow interval; low quality → wide interval
- More evidence → narrower interval (1/√n convergence)
- Interval always bounded by 0 and the applied cap

## Three Presets

| Parameter | standard | conservative | permissive |
|-----------|----------|--------------|------------|
| verify_threshold | 0.70 | 0.78 | 0.62 |
| contest_threshold | 0.25 | 0.30 | 0.20 |
| contradiction_cap | 0.55 | 0.50 | 0.60 |
| provenance_cap | 0.60 | 0.55 | 0.65 |
| min_provenance_quality | 0.55 | 0.60 | 0.45 |
| decay_threshold | 0.40 | 0.35 | 0.30 |
| temporal_cap | 0.50 | 0.50 | 0.55 |
| density_floor | 0.30 | 0.35 | 0.20 |
| density_cap | 0.55 | 0.55 | 0.55 |
| uncertainty_base | 0.50 | 0.55 | 0.40 |
| uncertainty_min | 0.10 | 0.12 | 0.08 |
| alpha | 0.50 | 0.50 | 0.50 |

## Incremental Update (preserved from v1)

```
delta = raw_conf - old_conf
if delta > 0.1:   new_conf = alpha × raw + (1-alpha) × old  (strengthener)
elif delta < -0.1: new_conf = min(old, raw)                   (weakener)
else:              new_conf = (old + raw) / 2                 (neutral)
```
