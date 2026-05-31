# belief-state-runtime (c) 2026 hqzzdsda — MIT License
# https://github.com/hqzzdsda/belief-state-runtime

# -*- coding: utf-8 -*-
"""Epistemic module — feature extraction + calibration + analysis."""
from .feature_extractor import FeatureExtractor
from .calibration import (
    log_calibration_sample,
    load_calibration_data,
    compute_reliability_diagram,
    evaluate_calibration,
    PlattScaler,
    IsotonicCalibrator,
    auto_calibrate,
    bayesian_weight_update,
    verify_calibration,
)
from .correlation import (
    compute_signal_correlations,
    report_correlations,
    plot_correlation_matrix,
    flag_redundant_signals,
)
from .cost_monitor import (
    CostMonitor,
    CostAwareSampler,
    get_cost_monitor,
    format_cost_report,
)
