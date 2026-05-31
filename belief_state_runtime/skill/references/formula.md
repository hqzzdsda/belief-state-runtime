# Aggregation Formula

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

## State Thresholds

```
conf >= 0.65  → VERIFIED
conf <= 0.25  → UNCERTAIN
else          → CONTESTED
```

## Incremental Update

```
delta = raw_conf - old_conf
if delta > 0.1:   new_conf = 0.5 × raw + 0.5 × old  (strengthener)
elif delta < -0.1: new_conf = min(old, raw)            (weakener)
else:              new_conf = (old + raw) / 2          (neutral)
```
