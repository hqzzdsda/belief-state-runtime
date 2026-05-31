# belief-state-runtime (c) 2026 hqzzdsda — MIT License
# Tests that run without LLM API — deterministic, fast, zero cost.

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from belief_state_runtime import get_skill_definition


def test_skill_definition_structure():
    """Skill definition returns valid structure."""
    defn = get_skill_definition()
    assert defn["name"] == "belief_assessor"
    assert "claim" in defn["parameters"]
    assert "evidence" in defn["parameters"]
    assert defn["parameters"]["claim"]["required"] is True
    assert "state" in defn["returns"]
    assert "confidence" in defn["returns"]


def test_assess_claim_requires_llm_func():
    """assess_claim raises ValueError when no llm_func provided."""
    from belief_state_runtime import assess_claim
    try:
        assess_claim("Test claim")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "llm_func" in str(e)


def test_assess_incremental_requires_llm_func():
    """assess_incremental raises ValueError when no llm_func provided."""
    from belief_state_runtime import assess_incremental
    try:
        assess_incremental("Test claim", ["evidence 1"])
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "llm_func" in str(e)


def test_version():
    """Package version is defined."""
    from belief_state_runtime import __version__
    assert isinstance(__version__, str)
    assert len(__version__) > 0


def test_feature_extractor_import():
    """FeatureExtractor can be imported."""
    from belief_state_runtime.feature_extractor import FeatureExtractor
    assert FeatureExtractor is not None


def test_epistemic_calibration_import():
    """Calibration module can be imported."""
    from epistemic.calibration import evaluate_calibration
    assert evaluate_calibration is not None


def test_epistemic_correlation_import():
    """Correlation module can be imported."""
    from epistemic.correlation import compute_signal_correlations
    assert compute_signal_correlations is not None


def test_cost_monitor_import():
    """Cost monitor can be imported."""
    from epistemic.cost_monitor import CostMonitor
    assert CostMonitor is not None


def test_skill_scripts_exist():
    """All skill scripts are present."""
    base = os.path.join(os.path.dirname(__file__), "..", "belief_state_runtime", "skill")
    scripts_dir = os.path.join(base, "scripts")
    assert os.path.isfile(os.path.join(base, "SKILL.md"))
    assert os.path.isfile(os.path.join(scripts_dir, "assess.py"))
    assert os.path.isfile(os.path.join(scripts_dir, "cli.py"))


def test_no_test_files_in_skill():
    """Skill directory contains no test files."""
    base = os.path.join(os.path.dirname(__file__), "..", "belief_state_runtime", "skill")
    for root, _, files in os.walk(base):
        for f in files:
            assert not f.startswith("test_"), f"Test file found: {os.path.join(root, f)}"
            assert not f.startswith("demo_"), f"Demo file found: {os.path.join(root, f)}"


def test_no_pycache_in_repo():
    """No __pycache__ in committed source dirs (gitignored)."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Only check that gitignore covers __pycache__
    gitignore_path = os.path.join(repo_root, ".gitignore")
    assert os.path.isfile(gitignore_path)
    with open(gitignore_path) as f:
        content = f.read()
    assert "__pycache__/" in content, ".gitignore should contain __pycache__/"


def test_readme_exists():
    """README files exist."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.isfile(os.path.join(repo_root, "README.md"))
    assert os.path.isfile(os.path.join(repo_root, "README_CN.md"))
