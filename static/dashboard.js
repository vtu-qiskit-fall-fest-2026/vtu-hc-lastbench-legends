/**
 * QuantumFlow — Dashboard Controller with Plotly Visualizations
 * static/dashboard.js  ·  Owner: Frontend Engineer
 *
 * Connects frontend UI to real Flask endpoints:
 *   - GET  /api/traffic
 *   - POST /api/traffic
 *   - POST /api/optimize/baseline
 *   - POST /api/optimize/responsive
 *   - POST /api/optimize/qaoa
 *   - GET  /api/results
 *
 * Rules:
 *   - NO hardcoded fake chart data or mock results.
 *   - NO client-side traffic calculations in JavaScript.
 *   - Multi-algorithm side-by-side comparison on identical traffic inputs.
 *   - Clear labeling of simulated data, estimated metrics, and units (veh, s, ms).
 *   - Graceful handling of missing results and failed QAOA runs.
 */

document.addEventListener("DOMContentLoaded", () => {
  // -------------------------------------------------------------------------
  // DOM Element References
  // -------------------------------------------------------------------------
  const intersections = ["A", "B", "C", "D"];

  // Header & Banner
  const headerTotalVehicles = document.getElementById("header-total-vehicles");
  const statusBanner = document.getElementById("status-banner");
  const bannerMessage = document.getElementById("banner-message");
  const bannerIcon = document.getElementById("banner-icon");
  const btnBannerClose = document.getElementById("btn-banner-close");

  // Traffic & Scenario Buttons
  const scenarioButtons = document.querySelectorAll(".scenario-btn");
  const btnApplyTraffic = document.getElementById("btn-apply-traffic");
  const btnRefreshTraffic = document.getElementById("btn-refresh-traffic");
  const trafficSyncStatus = document.getElementById("traffic-sync-status");

  // Optimization Buttons
  const btnOptBaseline = document.getElementById("btn-optimize-baseline");
  const btnOptResponsive = document.getElementById("btn-optimize-responsive");
  const btnOptQAOA = document.getElementById("btn-optimize-qaoa");
  const btnOptimizeAll = document.getElementById("btn-optimize-all");
  const btnChartsCompareAll = document.getElementById("btn-charts-compare-all");

  // QAOA Advanced Tuning
  const selectQAOAP = document.getElementById("select-qaoa-p");
  const selectQAOAShots = document.getElementById("select-qaoa-shots");
  const inputQAOAMaxiter = document.getElementById("input-qaoa-maxiter");
  const inputQAOASeed = document.getElementById("input-qaoa-seed");

  // KPI Elements
  const activeAlgoName = document.getElementById("active-algo-name");
  const activeAlgoStatus = document.getElementById("active-algo-status");
  const bitstringWrapper = document.getElementById("bitstring-display-wrapper");
  const displayMeasuredBitstring = document.getElementById("display-measured-bitstring");

  const kpiTotalVehicles = document.getElementById("kpi-total-vehicles");
  const kpiVehiclesServed = document.getElementById("kpi-vehicles-served");
  const kpiRemainingQueue = document.getElementById("kpi-remaining-queue");
  const kpiTotalDelay = document.getElementById("kpi-total-delay");
  const kpiAvgWait = document.getElementById("kpi-avg-wait");
  const kpiDelayReduction = document.getElementById("kpi-delay-reduction");
  const kpiDelayReductionCaption = document.getElementById("kpi-delay-reduction-caption");
  const kpiRuntime = document.getElementById("kpi-runtime");

  // Charts Elements
  const chartsTrafficContext = document.getElementById("charts-traffic-context");
  const chartDelaysEl = document.getElementById("chart-delays");
  const chartThroughputEl = document.getElementById("chart-throughput");
  const chartTimingsEl = document.getElementById("chart-timings");
  const chartRuntimeEl = document.getElementById("chart-runtime");

  // History Log Table
  const tableResultsBody = document.getElementById("table-results-body");
  const btnRefreshHistory = document.getElementById("btn-refresh-history");

  // Hackathon Polish: Stale Data & QAOA Failure Indicators
  const staleAlertBanner = document.getElementById("stale-alert-banner");
  const btnStaleRecalculate = document.getElementById("btn-stale-recalculate");
  const qaoaFailureCard = document.getElementById("qaoa-failure-card");
  const qaoaFailureStatus = document.getElementById("qaoa-failure-status");
  const qaoaFailureMsg = document.getElementById("qaoa-failure-msg");
  const kpiGrid = document.getElementById("kpi-grid");

  // -------------------------------------------------------------------------
  // Stale State & Failure Display Helpers
  // -------------------------------------------------------------------------
  function markResultsStale(isStale) {
    if (isStale) {
      if (staleAlertBanner) staleAlertBanner.classList.remove("hidden");
      if (kpiGrid) kpiGrid.classList.add("kpi-stale");
      if (activeAlgoStatus) {
        activeAlgoStatus.textContent = "Outdated";
        activeAlgoStatus.className = "status-badge status-stale";
      }
      if (chartsTrafficContext) {
        chartsTrafficContext.textContent = "⚠️ Input Modified — Re-run Required";
      }
    } else {
      if (staleAlertBanner) staleAlertBanner.classList.add("hidden");
      if (kpiGrid) kpiGrid.classList.remove("kpi-stale");
    }
  }

  function updateQAOAFailureState(data) {
    if (!qaoaFailureCard) return;
    if (data && (data.status !== "ok" || (data.solver_status && data.solver_status !== "ok"))) {
      qaoaFailureCard.classList.remove("hidden");
      if (qaoaFailureStatus) {
        qaoaFailureStatus.textContent = `Status: ${data.solver_status || data.status || "error"}`;
      }
      if (qaoaFailureMsg) {
        qaoaFailureMsg.textContent = data.error_msg || data.message || "QAOA quantum circuit simulation encountered an error or timeout.";
      }
    } else {
      qaoaFailureCard.classList.add("hidden");
    }
  }

  // -------------------------------------------------------------------------
  // In-Memory Comparison Cache (Stores Real API Responses on Current Traffic)

  // -------------------------------------------------------------------------
  const comparisonState = {
    trafficKey: null,
    trafficInput: null,
    totalVehicles: 0,
    baseline: null,
    responsive: null,
    qaoa: null,
  };

  // -------------------------------------------------------------------------
  // Notification Banner Helpers
  // -------------------------------------------------------------------------
  function showBanner(message, type = "info") {
    statusBanner.className = `status-banner banner-${type}`;
    bannerMessage.textContent = message;

    if (type === "success") bannerIcon.textContent = "✓";
    else if (type === "error") bannerIcon.textContent = "⚠";
    else bannerIcon.textContent = "ℹ";

    statusBanner.classList.remove("hidden");
  }

  function hideBanner() {
    statusBanner.classList.add("hidden");
  }

  if (btnBannerClose) {
    btnBannerClose.addEventListener("click", hideBanner);
  }

  // -------------------------------------------------------------------------
  // Loading State Helper
  // -------------------------------------------------------------------------
  function setButtonLoading(button, isLoading, loadingText = "Running...") {
    if (!button) return;
    const textSpan = button.querySelector(".btn-text");
    const spinner = button.querySelector(".btn-spinner");

    if (isLoading) {
      button.disabled = true;
      if (textSpan) {
        if (!textSpan.dataset.originalText) {
          textSpan.dataset.originalText = textSpan.textContent;
        }
        textSpan.textContent = loadingText;
      }
      if (spinner) spinner.classList.remove("hidden");
    } else {
      button.disabled = false;
      if (textSpan && textSpan.dataset.originalText) {
        textSpan.textContent = textSpan.dataset.originalText;
      }
      if (spinner) spinner.classList.add("hidden");
    }
  }

  // -------------------------------------------------------------------------
  // Traffic Density Indicators
  // -------------------------------------------------------------------------
  function getDensityClass(queue) {
    if (queue <= 0) return { level: "low", tag: "Zero" };
    if (queue < 15) return { level: "low", tag: "Low" };
    if (queue <= 30) return { level: "mod", tag: "Mod" };
    if (queue <= 45) return { level: "high", tag: "High" };
    return { level: "congested", tag: "Congested" };
  }

  function updateTrafficDensityIndicators() {
    let totalQueued = 0;
    intersections.forEach((iid) => {
      const nsInput = document.getElementById(`input-ns-${iid}`);
      const ewInput = document.getElementById(`input-ew-${iid}`);
      const nsVal = Math.max(0, parseInt(nsInput?.value || "0", 10) || 0);
      const ewVal = Math.max(0, parseInt(ewInput?.value || "0", 10) || 0);
      const iTotal = nsVal + ewVal;
      totalQueued += iTotal;

      // Overall intersection badge
      const maxQueue = Math.max(nsVal, ewVal);
      const iDensity = getDensityClass(maxQueue);
      const badge = document.getElementById(`density-badge-${iid}`);
      if (badge) {
        badge.className = `density-badge density-${iDensity.level}`;
        badge.textContent = `${iDensity.tag} (${iTotal} veh)`;
      }

      // Approach density tags & dots
      const nsDensity = getDensityClass(nsVal);
      const tagNS = document.getElementById(`density-tag-ns-${iid}`);
      const dotNS = document.getElementById(`density-dot-ns-${iid}`);
      if (tagNS) {
        tagNS.className = `approach-density-tag density-${nsDensity.level}`;
        tagNS.textContent = nsDensity.tag;
      }
      if (dotNS) {
        dotNS.className = `density-indicator-dot dot-${nsDensity.level}`;
        dotNS.title = `NS queue: ${nsVal} veh (${nsDensity.tag})`;
      }

      const ewDensity = getDensityClass(ewVal);
      const tagEW = document.getElementById(`density-tag-ew-${iid}`);
      const dotEW = document.getElementById(`density-dot-ew-${iid}`);
      if (tagEW) {
        tagEW.className = `approach-density-tag density-${ewDensity.level}`;
        tagEW.textContent = ewDensity.tag;
      }
      if (dotEW) {
        dotEW.className = `density-indicator-dot dot-${ewDensity.level}`;
        dotEW.title = `EW queue: ${ewVal} veh (${ewDensity.tag})`;
      }
    });

    if (headerTotalVehicles) {
      headerTotalVehicles.textContent = `${totalQueued} veh`;
    }
    if (chartsTrafficContext) {
      chartsTrafficContext.textContent = `Input: ${totalQueued} veh across 4 nodes`;
    }

    // Check if traffic input has changed compared to cached comparison state
    const currentKey = getCurrentTrafficKey();
    if (comparisonState.trafficKey && comparisonState.trafficKey !== currentKey) {
      // Mark comparison state outdated
      markResultsStale(true);
      if (chartsTrafficContext) {
        chartsTrafficContext.textContent = `Input changed (${totalQueued} veh) — Click 'Compare All' to refresh`;
      }
    } else if (comparisonState.trafficKey && comparisonState.trafficKey === currentKey) {
      markResultsStale(false);
    }
  }

  function getCurrentTrafficInput() {
    const trafficInput = {};
    intersections.forEach((iid) => {
      const nsVal = Math.max(0, parseInt(document.getElementById(`input-ns-${iid}`)?.value || "0", 10) || 0);
      const ewVal = Math.max(0, parseInt(document.getElementById(`input-ew-${iid}`)?.value || "0", 10) || 0);
      trafficInput[iid] = { ns_count: nsVal, ew_count: ewVal };
    });
    return trafficInput;
  }

  function getCurrentTrafficKey() {
    return JSON.stringify(getCurrentTrafficInput());
  }

  // -------------------------------------------------------------------------
  // Fetch & Render Traffic State
  // -------------------------------------------------------------------------
  async function loadTrafficState() {
    try {
      trafficSyncStatus.textContent = "Fetching traffic snapshot...";
      const res = await fetch("/api/traffic");
      const data = await res.json();

      if (!res.ok || data.status !== "ok") {
        throw new Error(data.message || `Server error (${res.status})`);
      }

      renderTrafficInputs(data.traffic_input);
      updateTrafficDensityIndicators();

      trafficSyncStatus.textContent = "Synchronized with backend traffic snapshot.";
      // Run comparison automatically for the initial state to populate all charts
      runAllSolversAndCompare();
    } catch (err) {
      showBanner(`Failed to load traffic state: ${err.message}`, "error");
      trafficSyncStatus.textContent = "Synchronization error.";
    }
  }

  function renderTrafficInputs(trafficInput) {
    if (!trafficInput) return;

    intersections.forEach((iid) => {
      const counts = trafficInput[iid] || trafficInput[`(${iid})`];
      if (!counts) return;

      const inputNS = document.getElementById(`input-ns-${iid}`);
      const inputEW = document.getElementById(`input-ew-${iid}`);

      if (inputNS) inputNS.value = counts.ns_count;
      if (inputEW) inputEW.value = counts.ew_count;
    });

    updateTrafficDensityIndicators();
  }

  // -------------------------------------------------------------------------
  // Apply Custom Queue Counts (POST /api/traffic)
  // -------------------------------------------------------------------------
  async function applyCustomTraffic() {
    hideBanner();
    const trafficInput = getCurrentTrafficInput();

    try {
      btnApplyTraffic.disabled = true;
      trafficSyncStatus.textContent = "Applying queue counts...";

      const res = await fetch("/api/traffic", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ traffic_input: trafficInput }),
      });
      const data = await res.json();

      if (!res.ok || data.status !== "ok") {
        throw new Error(data.message || `Failed to update traffic (${res.status})`);
      }

      renderTrafficInputs(data.traffic_input);
      showBanner(`Traffic queues successfully updated (${data.total_vehicles} total vehicles). Re-running comparisons...`, "success");
      trafficSyncStatus.textContent = "Custom queues applied.";

      scenarioButtons.forEach((b) => b.classList.remove("active"));

      // Re-run all algorithms on the new traffic input to update Plotly charts
      await runAllSolversAndCompare();
    } catch (err) {
      showBanner(`Error updating traffic queues: ${err.message}`, "error");
      trafficSyncStatus.textContent = "Error applying queues.";
    } finally {
      btnApplyTraffic.disabled = false;
    }
  }

  // -------------------------------------------------------------------------
  // Preset Scenario Handler (POST /api/traffic with scenario)
  // -------------------------------------------------------------------------
  async function loadScenario(scenarioName, buttonEl) {
    hideBanner();
    try {
      scenarioButtons.forEach((b) => b.classList.remove("active"));
      if (buttonEl) buttonEl.classList.add("active");

      trafficSyncStatus.textContent = `Generating ${scenarioName} scenario...`;

      let payload = {};
      if (scenarioName === "benchmark") {
        payload = {
          traffic_input: {
            A: { ns_count: 45, ew_count: 12 },
            B: { ns_count: 30, ew_count: 20 },
            C: { ns_count: 10, ew_count: 40 },
            D: { ns_count: 25, ew_count: 15 },
          },
        };
      } else {
        payload = { scenario: scenarioName, seed: 42 };
      }

      const res = await fetch("/api/traffic", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      if (!res.ok || data.status !== "ok") {
        throw new Error(data.message || `Failed to set scenario (${res.status})`);
      }

      renderTrafficInputs(data.traffic_input);
      showBanner(`Scenario '${scenarioName}' loaded (${data.total_vehicles} vehicles). Re-running comparisons...`, "info");
      trafficSyncStatus.textContent = `Active scenario: ${scenarioName}`;

      // Automatically re-evaluate all algorithms against new scenario
      await runAllSolversAndCompare();
    } catch (err) {
      showBanner(`Error loading scenario: ${err.message}`, "error");
      trafficSyncStatus.textContent = "Failed to load scenario.";
    }
  }

  // -------------------------------------------------------------------------
  // Optimization Dispatchers (Single Algorithm)
  // -------------------------------------------------------------------------
  async function runSingleOptimization(endpoint, buttonEl, algoKey, payload = {}) {
    hideBanner();
    markResultsStale(false);

    let loadingMsg = "Optimizing...";
    if (algoKey === "baseline") loadingMsg = "Fixed-Time...";
    else if (algoKey === "responsive") loadingMsg = "Responsive...";
    else if (algoKey === "qaoa") loadingMsg = "QAOA (Aer)...";

    setButtonLoading(buttonEl, true, loadingMsg);

    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      if (!res.ok || data.status !== "ok") {
        throw new Error(data.message || `Solver execution failed (${res.status})`);
      }

      // Update comparison cache for this algorithm
      const currentKey = getCurrentTrafficKey();
      if (comparisonState.trafficKey !== currentKey) {
        comparisonState.trafficKey = currentKey;
        comparisonState.baseline = null;
        comparisonState.responsive = null;
        comparisonState.qaoa = null;
      }
      comparisonState[algoKey] = data;

      renderSolverResult(data);
      updateQAOAFailureState(comparisonState.qaoa);
      renderPlotlyCharts();
      showBanner(`Optimization complete: ${formatAlgorithmName(data.algorithm)} (${data.solver_status || "ok"}).`, "success");
      loadResultsHistory();
    } catch (err) {
      showBanner(`Optimization Error: ${err.message}`, "error");
      if (algoKey === "qaoa") {
        comparisonState.qaoa = {
          algorithm: "qaoa",
          status: "error",
          solver_status: "error",
          message: err.message,
          runtime_ms: 0,
        };
        updateQAOAFailureState(comparisonState.qaoa);
        renderPlotlyCharts();
      }
    } finally {
      setButtonLoading(buttonEl, false);
    }
  }

  // -------------------------------------------------------------------------
  // Multi-Algorithm Dispatcher: Run All & Compare on Identical Traffic Input
  // -------------------------------------------------------------------------
  async function runAllSolversAndCompare() {
    hideBanner();
    markResultsStale(false);
    const trafficInput = getCurrentTrafficInput();
    const currentKey = JSON.stringify(trafficInput);

    setButtonLoading(btnOptimizeAll, true, "Simulating All 3 Solvers...");
    setButtonLoading(btnChartsCompareAll, true, "Simulating All 3 Solvers...");
    setButtonLoading(btnOptBaseline, true, "Fixed-Time...");
    setButtonLoading(btnOptResponsive, true, "Responsive...");
    setButtonLoading(btnOptQAOA, true, "QAOA (Aer)...");

    // QAOA tuning params
    const pVal = parseInt(selectQAOAP?.value || "1", 10) || 1;
    const shotsVal = parseInt(selectQAOAShots?.value || "1024", 10) || 1024;
    const maxiterVal = parseInt(inputQAOAMaxiter?.value || "50", 10) || 50;
    const seedVal = parseInt(inputQAOASeed?.value || "42", 10) || 42;

    const qaoaPayload = {
      traffic_input: trafficInput,
      p_layers: pVal,
      shots: shotsVal,
      maxiter: maxiterVal,
      seed: seedVal,
      timeout_sec: 30.0,
    };

    try {
      // Execute Baseline, Responsive, and QAOA on the exact same traffic input
      const [baselineRes, responsiveRes, qaoaRes] = await Promise.allSettled([
        fetch("/api/optimize/baseline", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ traffic_input: trafficInput }),
        }).then((r) => r.json()),

        fetch("/api/optimize/responsive", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ traffic_input: trafficInput }),
        }).then((r) => r.json()),

        fetch("/api/optimize/qaoa", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(qaoaPayload),
        }).then((r) => r.json()),
      ]);

      comparisonState.trafficKey = currentKey;
      comparisonState.trafficInput = trafficInput;

      // Unpack baseline
      if (baselineRes.status === "fulfilled" && baselineRes.value.status === "ok") {
        comparisonState.baseline = baselineRes.value;
      } else {
        comparisonState.baseline = null;
        console.warn("Baseline run failed:", baselineRes);
      }

      // Unpack responsive
      if (responsiveRes.status === "fulfilled" && responsiveRes.value.status === "ok") {
        comparisonState.responsive = responsiveRes.value;
      } else {
        comparisonState.responsive = null;
        console.warn("Responsive run failed:", responsiveRes);
      }

      // Unpack QAOA
      if (qaoaRes.status === "fulfilled" && qaoaRes.value.status === "ok") {
        comparisonState.qaoa = qaoaRes.value;
      } else {
        const errVal = qaoaRes.status === "fulfilled" ? qaoaRes.value : { message: "QAOA network/timeout error" };
        comparisonState.qaoa = {
          algorithm: "qaoa",
          status: "error",
          solver_status: errVal.solver_status || "error",
          message: errVal.message || "Execution failed",
          runtime_ms: errVal.runtime_ms || 0,
        };
        console.warn("QAOA run failed/timed out:", errVal);
      }

      // Render the primary solver result to KPIs (prefer QAOA if ok, else responsive, else baseline)
      const primaryResult = (comparisonState.qaoa?.status === "ok" ? comparisonState.qaoa : null)
        || comparisonState.responsive
        || comparisonState.baseline;

      if (primaryResult) {
        renderSolverResult(primaryResult);
      }
      updateQAOAFailureState(comparisonState.qaoa);

      // Update all 4 Plotly charts with the new data
      renderPlotlyCharts();

      // Refresh history table
      loadResultsHistory();

      if (comparisonState.qaoa?.status === "ok") {
        showBanner("All 3 solvers evaluated successfully on active traffic input.", "success");
      } else {
        showBanner("Baseline and Responsive evaluated. QAOA failed or timed out — handled gracefully in charts.", "info");
      }
    } catch (err) {
      showBanner(`Multi-solver evaluation error: ${err.message}`, "error");
    } finally {
      setButtonLoading(btnOptimizeAll, false);
      setButtonLoading(btnChartsCompareAll, false);
      setButtonLoading(btnOptBaseline, false);
      setButtonLoading(btnOptResponsive, false);
      setButtonLoading(btnOptQAOA, false);
    }
  }

  // -------------------------------------------------------------------------
  // Render Solver Results & Metrics to UI KPI Cards
  // -------------------------------------------------------------------------
  function renderSolverResult(data) {
    if (!data) return;

    // Algorithm & Status Badges
    const algoName = data.algorithm || "unknown";
    if (activeAlgoName) activeAlgoName.textContent = formatAlgorithmName(algoName);

    const status = data.solver_status || data.status || "ok";
    if (activeAlgoStatus) {
      activeAlgoStatus.textContent = status;
      activeAlgoStatus.className = `status-badge status-${status}`;
    }

    // QAOA Bitstring
    if (bitstringWrapper) {
      if (data.bitstring) {
        bitstringWrapper.classList.remove("hidden");
        if (displayMeasuredBitstring) displayMeasuredBitstring.textContent = data.bitstring;
      } else {
        bitstringWrapper.classList.add("hidden");
      }
    }

    // Metrics KPIs
    const m = data.metrics || {};
    if (kpiTotalVehicles) kpiTotalVehicles.textContent = m.total_vehicles ?? "--";
    if (kpiVehiclesServed) kpiVehiclesServed.textContent = m.vehicles_served ?? "--";
    if (kpiRemainingQueue) kpiRemainingQueue.textContent = m.remaining_queue ?? "--";
    if (kpiTotalDelay) kpiTotalDelay.textContent = m.total_delay_sec !== undefined ? `${m.total_delay_sec.toFixed(1)} s` : "--";
    if (kpiAvgWait) kpiAvgWait.textContent = m.avg_wait_sec !== undefined ? `${m.avg_wait_sec.toFixed(2)} s` : "--";
    if (kpiRuntime) kpiRuntime.textContent = data.runtime_ms !== undefined ? `${data.runtime_ms.toFixed(1)} ms` : "--";

    // Delay Reduction vs Baseline
    if (kpiDelayReduction) {
      if (data.baseline_comparison && data.baseline_comparison.delay_reduction_pct !== undefined) {
        const red = data.baseline_comparison.delay_reduction_pct;
        kpiDelayReduction.textContent = `${red >= 0 ? "+" : ""}${red.toFixed(1)}%`;
        if (kpiDelayReductionCaption) kpiDelayReductionCaption.textContent = "Improvement vs Fixed-Time";
      } else if (algoName === "fixed-time") {
        kpiDelayReduction.textContent = "+0.0%";
        if (kpiDelayReductionCaption) kpiDelayReductionCaption.textContent = "Baseline reference";
      } else {
        kpiDelayReduction.textContent = "--";
      }
    }

    // Timing Plan on Intersection Cards
    if (data.timing_plan) {
      renderTimingPlan(data.timing_plan);
    }
  }

  function renderTimingPlan(timingPlan) {
    intersections.forEach((iid) => {
      const timing = timingPlan[iid] || timingPlan[`(${iid})`];
      if (!timing) return;

      const nsG = timing.ns_green;
      const ewG = timing.ew_green;
      const cycle = nsG + ewG || 60;

      const nsPct = Math.round((nsG / cycle) * 100);
      const ewPct = 100 - nsPct;

      const badge = document.getElementById(`badge-timing-${iid}`);
      const valNS = document.getElementById(`val-ns-${iid}`);
      const valEW = document.getElementById(`val-ew-${iid}`);
      const pctNS = document.getElementById(`pct-ns-${iid}`);
      const pctEW = document.getElementById(`pct-ew-${iid}`);
      const barNS = document.getElementById(`bar-ns-${iid}`);
      const barEW = document.getElementById(`bar-ew-${iid}`);

      if (badge) badge.textContent = `${nsG}s / ${ewG}s`;
      if (valNS) valNS.textContent = `${nsG}s`;
      if (valEW) valEW.textContent = `${ewG}s`;
      if (pctNS) pctNS.textContent = `${nsPct}%`;
      if (pctEW) pctEW.textContent = `${ewPct}%`;
      if (barNS) barNS.style.width = `${nsPct}%`;
      if (barEW) barEW.style.width = `${ewPct}%`;
    });
  }

  // -------------------------------------------------------------------------
  // Plotly Comparative Visualizations
  // -------------------------------------------------------------------------
  function renderPlotlyCharts() {
    if (typeof Plotly === "undefined") {
      console.warn("Plotly is not loaded yet.");
      return;
    }

    const { baseline, responsive, qaoa } = comparisonState;

    const baseMetrics = baseline?.metrics || null;
    const respMetrics = responsive?.metrics || null;
    const isQAOAValid = qaoa && qaoa.status === "ok" && (!qaoa.solver_status || qaoa.solver_status === "ok");
    const qaoaMetrics = isQAOAValid ? qaoa?.metrics : null;
    const qaoaFailed = qaoa && (qaoa.status !== "ok" || (qaoa.solver_status && qaoa.solver_status !== "ok"));

    const algoCategories = ["Fixed-Time (Baseline)", "Traffic-Responsive", "QAOA Quantum"];

    // Base Plotly Layout Token Palette (Dark theme matching design system)
    const baseLayout = {
      paper_bgcolor: "rgba(0, 0, 0, 0)",
      plot_bgcolor: "rgba(0, 0, 0, 0)",
      font: { family: "Inter, sans-serif", color: "#9ca3af", size: 11 },
      margin: { t: 30, r: 35, b: 45, l: 50 },
      xaxis: {
        gridcolor: "rgba(255, 255, 255, 0.06)",
        zerolinecolor: "rgba(255, 255, 255, 0.1)",
        tickfont: { size: 10, color: "#d1d5db" },
      },
      yaxis: {
        gridcolor: "rgba(255, 255, 255, 0.06)",
        zerolinecolor: "rgba(255, 255, 255, 0.1)",
        tickfont: { size: 10, color: "#d1d5db" },
      },
      legend: {
        orientation: "h",
        x: 0.5,
        xanchor: "center",
        y: -0.25,
        font: { size: 10, color: "#d1d5db" },
        bgcolor: "rgba(0, 0, 0, 0)",
      },
    };

    const plotlyConfig = { responsive: true, displayModeBar: false };

    // =========================================================================
    // Chart 1: Delay Metrics (Estimated Total Delay & Avg Wait Time)
    // =========================================================================
    if (chartDelaysEl) {
      const totalDelayValues = [
        baseMetrics ? baseMetrics.total_delay_sec : null,
        respMetrics ? respMetrics.total_delay_sec : null,
        qaoaMetrics ? qaoaMetrics.total_delay_sec : null,
      ];

      const avgWaitValues = [
        baseMetrics ? baseMetrics.avg_wait_sec : null,
        respMetrics ? respMetrics.avg_wait_sec : null,
        qaoaMetrics ? qaoaMetrics.avg_wait_sec : null,
      ];

      const traceTotalDelay = {
        x: algoCategories,
        y: totalDelayValues,
        name: "Estimated Total Delay (s)",
        type: "bar",
        marker: { color: "#3b82f6" },
        yaxis: "y",
        hovertemplate: "<b>%{x}</b><br>Total Delay: %{y:.1f} s<extra></extra>",
      };

      const traceAvgWait = {
        x: algoCategories,
        y: avgWaitValues,
        name: "Estimated Avg Wait (s/veh)",
        type: "bar",
        marker: { color: "#00f2fe" },
        yaxis: "y2",
        hovertemplate: "<b>%{x}</b><br>Avg Wait: %{y:.2f} s/veh<extra></extra>",
      };

      const annotations = [];
      if (qaoaFailed) {
        const failText = qaoa?.solver_status === "timeout" ? "QAOA: Timeout (Limit Exceeded)" : "QAOA: Failed / Error";
        annotations.push({
          x: "QAOA Quantum",
          y: 0,
          text: failText,
          showarrow: false,
          font: { color: "#ef4444", size: 10, family: "Inter, sans-serif" },
          bgcolor: "rgba(239, 68, 68, 0.15)",
          bordercolor: "rgba(239, 68, 68, 0.4)",
          borderwidth: 1,
          borderpad: 4,
        });
      } else if (!qaoa) {
        annotations.push({
          x: "QAOA Quantum",
          y: 0,
          text: "Not Executed Yet",
          showarrow: false,
          font: { color: "#9ca3af", size: 10 },
        });
      }

      const layoutDelays = {
        ...baseLayout,
        barmode: "group",
        yaxis: {
          ...baseLayout.yaxis,
          title: "Total Delay (seconds)",
          titlefont: { color: "#3b82f6", size: 11 },
        },
        yaxis2: {
          title: "Avg Wait (s/veh)",
          titlefont: { color: "#00f2fe", size: 11 },
          tickfont: { color: "#00f2fe", size: 10 },
          overlaying: "y",
          side: "right",
          gridcolor: "rgba(0, 0, 0, 0)",
          zeroline: false,
        },
        annotations,
      };

      Plotly.react(chartDelaysEl, [traceTotalDelay, traceAvgWait], layoutDelays, plotlyConfig);
    }

    // =========================================================================
    // Chart 2: Vehicle Throughput (Vehicles Served vs Remaining Queue)
    // =========================================================================
    if (chartThroughputEl) {
      const servedValues = [
        baseMetrics ? baseMetrics.vehicles_served : null,
        respMetrics ? respMetrics.vehicles_served : null,
        qaoaMetrics ? qaoaMetrics.vehicles_served : null,
      ];

      const queueValues = [
        baseMetrics ? baseMetrics.remaining_queue : null,
        respMetrics ? respMetrics.remaining_queue : null,
        qaoaMetrics ? qaoaMetrics.remaining_queue : null,
      ];

      const traceServed = {
        x: algoCategories,
        y: servedValues,
        name: "Vehicles Served (veh)",
        type: "bar",
        marker: { color: "#10b981" },
        hovertemplate: "<b>%{x}</b><br>Served: %{y} veh<extra></extra>",
      };

      const traceQueue = {
        x: algoCategories,
        y: queueValues,
        name: "Estimated Remaining Queue (veh)",
        type: "bar",
        marker: { color: "#ef4444" },
        hovertemplate: "<b>%{x}</b><br>Remaining Queue: %{y} veh<extra></extra>",
      };

      const annotationsThroughput = [];
      if (qaoaFailed) {
        const failText = qaoa?.solver_status === "timeout" ? "QAOA: Timeout" : "QAOA: Execution Failed";
        annotationsThroughput.push({
          x: "QAOA Quantum",
          y: 0,
          text: failText,
          showarrow: false,
          font: { color: "#ef4444", size: 10 },
          bgcolor: "rgba(239, 68, 68, 0.15)",
          borderpad: 4,
        });
      }

      const layoutThroughput = {
        ...baseLayout,
        barmode: "group",
        yaxis: {
          ...baseLayout.yaxis,
          title: "Vehicle Count (veh)",
        },
        annotations: annotationsThroughput,
      };

      Plotly.react(chartThroughputEl, [traceServed, traceQueue], layoutThroughput, plotlyConfig);
    }

    // =========================================================================
    // Chart 3: Green-Light Durations per Approach (NS vs EW per Node)
    // =========================================================================
    if (chartTimingsEl) {
      // Approach categories: A(NS), A(EW), B(NS), B(EW), C(NS), C(EW), D(NS), D(EW)
      const approachCategories = [];
      const fixedDurations = [];
      const respDurations = [];
      const qaoaDurations = [];

      intersections.forEach((iid) => {
        approachCategories.push(`${iid} (NS)`);
        approachCategories.push(`${iid} (EW)`);

        // Baseline (fixed 30s / 30s)
        const bPlan = baseline?.timing_plan?.[iid] || { ns_green: 30, ew_green: 30 };
        fixedDurations.push(baseline ? bPlan.ns_green : null);
        fixedDurations.push(baseline ? bPlan.ew_green : null);

        // Responsive
        const rPlan = responsive?.timing_plan?.[iid];
        respDurations.push(rPlan ? rPlan.ns_green : null);
        respDurations.push(rPlan ? rPlan.ew_green : null);

        // QAOA
        const qPlan = qaoaMetrics ? qaoa?.timing_plan?.[iid] : null;
        qaoaDurations.push(qPlan ? qPlan.ns_green : null);
        qaoaDurations.push(qPlan ? qPlan.ew_green : null);
      });

      const traceFixed = {
        x: approachCategories,
        y: fixedDurations,
        name: "Fixed-Time (Baseline)",
        type: "bar",
        marker: { color: "#f59e0b" },
        hovertemplate: "<b>Fixed-Time</b><br>%{x}: %{y}s<extra></extra>",
      };

      const traceResp = {
        x: approachCategories,
        y: respDurations,
        name: "Traffic-Responsive",
        type: "bar",
        marker: { color: "#10b981" },
        hovertemplate: "<b>Traffic-Responsive</b><br>%{x}: %{y}s<extra></extra>",
      };

      const traceQAOA = {
        x: approachCategories,
        y: qaoaDurations,
        name: "QAOA Quantum",
        type: "bar",
        marker: { color: "#00f2fe" },
        hovertemplate: "<b>QAOA Quantum</b><br>%{x}: %{y}s<extra></extra>",
      };

      const layoutTimings = {
        ...baseLayout,
        barmode: "group",
        yaxis: {
          ...baseLayout.yaxis,
          title: "Green Duration (s) [Cycle = 60s]",
          range: [0, 52],
        },
      };

      Plotly.react(chartTimingsEl, [traceFixed, traceResp, traceQAOA], layoutTimings, plotlyConfig);
    }

    // =========================================================================
    // Chart 4: Solver Runtime & Computational Latency
    // =========================================================================
    if (chartRuntimeEl) {
      const runtimeValues = [
        baseline?.runtime_ms !== undefined ? Math.max(0.01, baseline.runtime_ms) : null,
        responsive?.runtime_ms !== undefined ? Math.max(0.01, responsive.runtime_ms) : null,
        qaoa?.runtime_ms !== undefined ? Math.max(0.01, qaoa.runtime_ms) : null,
      ];

      const textValues = [
        baseline?.runtime_ms !== undefined ? `${baseline.runtime_ms.toFixed(2)} ms` : "Not Run",
        responsive?.runtime_ms !== undefined ? `${responsive.runtime_ms.toFixed(2)} ms` : "Not Run",
        isQAOAValid
          ? `${qaoa.runtime_ms.toFixed(1)} ms`
          : qaoaFailed
          ? (qaoa?.solver_status === "timeout" ? `Timeout (${qaoa.runtime_ms ? qaoa.runtime_ms.toFixed(0) : "0"}ms)` : "Failed")
          : "Not Run",
      ];

      const traceRuntime = {
        x: algoCategories,
        y: runtimeValues,
        text: textValues,
        textposition: "auto",
        type: "bar",
        marker: {
          color: ["#f59e0b", "#10b981", qaoaFailed ? "#ef4444" : "#00f2fe"],
        },
        hovertemplate: "<b>%{x}</b><br>Solver Runtime: %{y:.2f} ms<extra></extra>",
      };

      const layoutRuntime = {
        ...baseLayout,
        yaxis: {
          ...baseLayout.yaxis,
          title: "Runtime (milliseconds)",
        },
        showlegend: false,
      };

      Plotly.react(chartRuntimeEl, [traceRuntime], layoutRuntime, plotlyConfig);
    }
  }

  // -------------------------------------------------------------------------
  // Resize Handler for Responsive Plotly Charts
  // -------------------------------------------------------------------------
  window.addEventListener("resize", () => {
    if (typeof Plotly === "undefined") return;
    if (chartDelaysEl) Plotly.Plots.resize(chartDelaysEl);
    if (chartThroughputEl) Plotly.Plots.resize(chartThroughputEl);
    if (chartTimingsEl) Plotly.Plots.resize(chartTimingsEl);
    if (chartRuntimeEl) Plotly.Plots.resize(chartRuntimeEl);
  });

  // -------------------------------------------------------------------------
  // Optimization History Log (GET /api/results)
  // -------------------------------------------------------------------------
  async function loadResultsHistory() {
    try {
      const res = await fetch("/api/results?limit=15");
      const data = await res.json();

      if (!res.ok || data.status !== "ok") {
        return;
      }

      renderHistoryTable(data.results || []);
    } catch (err) {
      console.warn("Could not load history log:", err);
    }
  }

  function renderHistoryTable(results) {
    if (!tableResultsBody) return;

    if (!results || results.length === 0) {
      tableResultsBody.innerHTML = `
        <tr>
          <td colspan="10" class="text-center text-muted">No runs recorded yet. Execute an optimizer above to populate.</td>
        </tr>
      `;
      return;
    }

    tableResultsBody.innerHTML = results
      .map((item) => {
        const m = item.metrics || {};
        const runId = item.run_id || "--";
        const algo = formatAlgorithmName(item.algorithm || "--");
        const status = item.status || "ok";
        const totalVeh = m.total_vehicles ?? "--";
        const served = m.vehicles_served ?? "--";
        const queue = m.remaining_queue ?? "--";
        const wait = m.avg_wait_sec !== undefined ? `${m.avg_wait_sec.toFixed(2)}` : "--";
        const delay = m.total_delay_sec !== undefined ? `${m.total_delay_sec.toFixed(1)}` : "--";
        const runtime = item.runtime_ms !== undefined ? `${item.runtime_ms.toFixed(1)} ms` : "--";

        let redText = "--";
        if (item.baseline_comparison && item.baseline_comparison.delay_reduction_pct !== undefined) {
          const r = item.baseline_comparison.delay_reduction_pct;
          redText = `${r >= 0 ? "+" : ""}${r.toFixed(1)}%`;
        } else if (item.algorithm === "fixed-time") {
          redText = "+0.0%";
        }

        return `
          <tr>
            <td><code>${runId}</code></td>
            <td><strong>${algo}</strong></td>
            <td><span class="status-badge status-${status}">${status}</span></td>
            <td>${totalVeh}</td>
            <td class="kpi-served">${served}</td>
            <td class="kpi-queue">${queue}</td>
            <td>${wait}</td>
            <td>${delay}</td>
            <td class="kpi-delta">${redText}</td>
            <td>${runtime}</td>
          </tr>
        `;
      })
      .join("");
  }

  function formatAlgorithmName(raw) {
    if (raw === "fixed-time") return "Fixed-Time (Baseline)";
    if (raw === "traffic-responsive") return "Traffic-Responsive";
    if (raw === "qaoa") return "QAOA Quantum";
    if (raw === "greedy") return "Classical Greedy";
    return raw;
  }

  // -------------------------------------------------------------------------
  // Event Listeners Binding
  // -------------------------------------------------------------------------
  // Listen to input changes in real-time to update density badges
  intersections.forEach((iid) => {
    const inputNS = document.getElementById(`input-ns-${iid}`);
    const inputEW = document.getElementById(`input-ew-${iid}`);

    if (inputNS) inputNS.addEventListener("input", updateTrafficDensityIndicators);
    if (inputEW) inputEW.addEventListener("input", updateTrafficDensityIndicators);
  });

  // Apply traffic button
  if (btnApplyTraffic) {
    btnApplyTraffic.addEventListener("click", applyCustomTraffic);
  }

  // Refresh traffic
  if (btnRefreshTraffic) {
    btnRefreshTraffic.addEventListener("click", loadTrafficState);
  }

  // Scenario buttons
  scenarioButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const scenario = btn.dataset.scenario;
      if (scenario) loadScenario(scenario, btn);
    });
  });

  // Fixed-Time Baseline
  if (btnOptBaseline) {
    btnOptBaseline.addEventListener("click", () => {
      runSingleOptimization("/api/optimize/baseline", btnOptBaseline, "baseline", {
        traffic_input: getCurrentTrafficInput(),
      });
    });
  }

  // Traffic-Responsive
  if (btnOptResponsive) {
    btnOptResponsive.addEventListener("click", () => {
      runSingleOptimization("/api/optimize/responsive", btnOptResponsive, "responsive", {
        traffic_input: getCurrentTrafficInput(),
      });
    });
  }

  // QAOA Quantum
  if (btnOptQAOA) {
    btnOptQAOA.addEventListener("click", () => {
      const pVal = parseInt(selectQAOAP?.value || "1", 10) || 1;
      const shotsVal = parseInt(selectQAOAShots?.value || "1024", 10) || 1024;
      const maxiterVal = parseInt(inputQAOAMaxiter?.value || "50", 10) || 50;
      const seedVal = parseInt(inputQAOASeed?.value || "42", 10) || 42;

      const payload = {
        traffic_input: getCurrentTrafficInput(),
        p_layers: pVal,
        shots: shotsVal,
        maxiter: maxiterVal,
        seed: seedVal,
        timeout_sec: 30.0,
      };

      runSingleOptimization("/api/optimize/qaoa", btnOptQAOA, "qaoa", payload);
    });
  }

  // Run All & Compare buttons
  if (btnOptimizeAll) {
    btnOptimizeAll.addEventListener("click", runAllSolversAndCompare);
  }
  if (btnChartsCompareAll) {
    btnChartsCompareAll.addEventListener("click", runAllSolversAndCompare);
  }

  // Refresh history
  if (btnRefreshHistory) {
    btnRefreshHistory.addEventListener("click", loadResultsHistory);
  }

  // Stale recalculate action
  if (btnStaleRecalculate) {
    btnStaleRecalculate.addEventListener("click", runAllSolversAndCompare);
  }

  // -------------------------------------------------------------------------
  // Initial Bootstrapping
  // -------------------------------------------------------------------------
  loadTrafficState();
  loadResultsHistory();
});
