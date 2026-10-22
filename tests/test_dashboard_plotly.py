"""
QuantumFlow — Dashboard Plotly & Traffic Visualization Integration Tests
tests/test_dashboard_plotly.py
"""

import json
import pytest
from api.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestDashboardPlotlyHTML:
    """Verify that templates/index.html includes all required elements."""

    def test_index_contains_plotly_cdn(self, client):
        res = client.get("/")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "plotly" in html.lower()
        assert "cdn.plot.ly/plotly" in html

    def test_index_contains_all_four_chart_containers(self, client):
        res = client.get("/")
        html = res.data.decode("utf-8")
        assert 'id="chart-delays"' in html
        assert 'id="chart-throughput"' in html
        assert 'id="chart-timings"' in html
        assert 'id="chart-runtime"' in html

    def test_index_contains_traffic_density_badges(self, client):
        res = client.get("/")
        html = res.data.decode("utf-8")
        for iid in ["A", "B", "C", "D"]:
            assert f'id="density-badge-{iid}"' in html
            assert f'id="density-tag-ns-{iid}"' in html
            assert f'id="density-tag-ew-{iid}"' in html
            assert f'id="density-dot-ns-{iid}"' in html
            assert f'id="density-dot-ew-{iid}"' in html

    def test_index_contains_approach_green_durations(self, client):
        res = client.get("/")
        html = res.data.decode("utf-8")
        for iid in ["A", "B", "C", "D"]:
            assert f'id="val-ns-{iid}"' in html
            assert f'id="val-ew-{iid}"' in html
            assert f'NS Green:' in html
            assert f'EW Green:' in html

    def test_index_contains_compare_all_button(self, client):
        res = client.get("/")
        html = res.data.decode("utf-8")
        assert 'id="btn-optimize-all"' in html
        assert 'id="btn-charts-compare-all"' in html

    def test_index_labels_simulated_metrics_and_units(self, client):
        res = client.get("/")
        html = res.data.decode("utf-8")
        assert "Simulated Macroscopic Traffic Model" in html
        assert "veh" in html
        assert "ms" in html
        assert "Seconds (s)" in html


class TestDashboardPlotlyStaticAssets:
    """Verify static/style.css and static/dashboard.js contain the visualization code."""

    def test_static_css_contains_chart_and_density_styles(self, client):
        res = client.get("/static/style.css")
        assert res.status_code == 200
        css = res.data.decode("utf-8")
        assert ".density-badge" in css
        assert ".density-low" in css
        assert ".density-congested" in css
        assert ".section-charts" in css
        assert ".plotly-container" in css

    def test_static_js_contains_plotly_and_comparison_logic(self, client):
        res = client.get("/static/dashboard.js")
        assert res.status_code == 200
        js = res.data.decode("utf-8")
        assert "renderPlotlyCharts" in js
        assert "updateTrafficDensityIndicators" in js
        assert "runAllSolversAndCompare" in js
        assert "chart-delays" in js
        assert "chart-throughput" in js
        assert "chart-timings" in js
        assert "chart-runtime" in js


class TestAPIResponsesFeedCharts:
    """Verify that actual Flask API responses supply the exact metrics required by charts."""

    def test_chart_data_from_baseline_responsive_qaoa_identical_traffic(self, client):
        traffic_input = {
            "A": {"ns_count": 45, "ew_count": 12},
            "B": {"ns_count": 30, "ew_count": 20},
            "C": {"ns_count": 10, "ew_count": 40},
            "D": {"ns_count": 25, "ew_count": 15},
        }

        # 1. Baseline
        res_base = client.post("/api/optimize/baseline", json={"traffic_input": traffic_input})
        assert res_base.status_code == 200
        data_base = res_base.get_json()
        assert "metrics" in data_base
        assert "total_delay_sec" in data_base["metrics"]
        assert "avg_wait_sec" in data_base["metrics"]
        assert "vehicles_served" in data_base["metrics"]
        assert "remaining_queue" in data_base["metrics"]
        assert "runtime_ms" in data_base
        assert "timing_plan" in data_base

        # 2. Responsive
        res_resp = client.post("/api/optimize/responsive", json={"traffic_input": traffic_input})
        assert res_resp.status_code == 200
        data_resp = res_resp.get_json()
        assert "metrics" in data_resp
        assert "total_delay_sec" in data_resp["metrics"]
        assert "avg_wait_sec" in data_resp["metrics"]
        assert "vehicles_served" in data_resp["metrics"]
        assert "remaining_queue" in data_resp["metrics"]
        assert "runtime_ms" in data_resp
        assert "timing_plan" in data_resp

        # 3. QAOA
        res_qaoa = client.post("/api/optimize/qaoa", json={"traffic_input": traffic_input, "shots": 256, "maxiter": 20})
        assert res_qaoa.status_code == 200
        data_qaoa = res_qaoa.get_json()
        assert "metrics" in data_qaoa
        assert "total_delay_sec" in data_qaoa["metrics"]
        assert "avg_wait_sec" in data_qaoa["metrics"]
        assert "vehicles_served" in data_qaoa["metrics"]
        assert "remaining_queue" in data_qaoa["metrics"]
        assert "runtime_ms" in data_qaoa
        assert "timing_plan" in data_qaoa

        # Compare metrics on the same input
        assert data_base["metrics"]["total_vehicles"] == data_resp["metrics"]["total_vehicles"] == data_qaoa["metrics"]["total_vehicles"] == 197
        # Responsive should serve >= baseline
        assert data_resp["metrics"]["vehicles_served"] >= data_base["metrics"]["vehicles_served"]
        # Delay reduction % is calculated
        assert "baseline_comparison" in data_resp
        assert "delay_reduction_pct" in data_resp["baseline_comparison"]

    def test_chart_updates_after_changing_traffic_inputs(self, client):
        # Scenario: heavy traffic
        res = client.post("/api/traffic", json={"scenario": "heavy", "seed": 42})
        assert res.status_code == 200
        heavy_data = res.get_json()
        heavy_traffic = heavy_data["traffic_input"]
        heavy_total = heavy_data["total_vehicles"]

        res_resp = client.post("/api/optimize/responsive", json={"traffic_input": heavy_traffic})
        assert res_resp.status_code == 200
        resp_data = res_resp.get_json()
        assert resp_data["metrics"]["total_vehicles"] == heavy_total

        # Scenario: zero traffic
        res_zero = client.post("/api/traffic", json={"scenario": "zero"})
        assert res_zero.status_code == 200
        zero_data = res_zero.get_json()
        res_zero_opt = client.post("/api/optimize/baseline", json={"traffic_input": zero_data["traffic_input"]})
        assert res_zero_opt.status_code == 200
        assert res_zero_opt.get_json()["metrics"]["total_vehicles"] == 0
