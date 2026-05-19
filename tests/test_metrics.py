"""Tests for the native Rust metrics ring buffer (Python-level stub)."""
import pytest


# Test the Python-level metrics stub that lives in the Vorte app
# (Native MetricsCollector from _vorte_engine is tested separately if available)

def test_native_metrics_collector_if_available():
    try:
        from vorte._vorte_engine import MetricsCollector
    except ImportError:
        pytest.skip("vorte._vorte_engine not compiled — skipping native metrics test")

    mc = MetricsCollector()
    assert mc.buffered == 0
    assert mc.capacity == 10_000


def test_native_metrics_push_and_drain():
    try:
        from vorte._vorte_engine import MetricsCollector
    except ImportError:
        pytest.skip("vorte._vorte_engine not compiled")

    mc = MetricsCollector()
    mc.push("GET", "/api/users", 200, 45_000)
    mc.push("POST", "/api/orders", 201, 120_000)

    assert mc.buffered == 2
    spans = mc.drain()
    assert len(spans) == 2
    assert mc.buffered == 0

    methods = {s["method"] for s in spans}
    assert "GET" in methods
    assert "POST" in methods


def test_native_metrics_latency_ms_computed():
    try:
        from vorte._vorte_engine import MetricsCollector
    except ImportError:
        pytest.skip("vorte._vorte_engine not compiled")

    mc = MetricsCollector()
    mc.push("GET", "/", 200, 1_500_000)  # 1.5ms in ns
    spans = mc.drain()
    assert abs(spans[0]["latency_ms"] - 1.5) < 0.001


def test_native_metrics_tail_does_not_drain():
    try:
        from vorte._vorte_engine import MetricsCollector
    except ImportError:
        pytest.skip("vorte._vorte_engine not compiled")

    mc = MetricsCollector()
    mc.push("GET", "/a", 200, 1_000)
    mc.push("GET", "/b", 200, 2_000)

    tail = mc.tail(1)
    assert len(tail) == 1
    assert mc.buffered == 2  # tail doesn't drain


def test_native_metrics_ring_buffer_eviction():
    try:
        from vorte._vorte_engine import MetricsCollector
    except ImportError:
        pytest.skip("vorte._vorte_engine not compiled")

    mc = MetricsCollector()
    # Overflow the ring buffer
    for i in range(mc.capacity + 100):
        mc.push("GET", f"/path/{i}", 200, i)
    assert mc.buffered == mc.capacity  # capped at capacity


def test_app_exposes_blueprint_properties():
    """Vorte app should expose executor, type_mirror, and query_planner."""
    from vorte import Vorte
    app = Vorte(auto_load=False)
    assert hasattr(app, "executor")
    assert hasattr(app, "type_mirror")
    assert hasattr(app, "query_planner")
