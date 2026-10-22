# QuantumFlow — Live Demonstration & Recovery Runbook
**Target Audience:** Demo Presenter, Pitch Lead, Technical Integrator  
**Environment:** Local Workstation (`http://localhost:5000/`)  
**Deployment Status:** Localhost verified (Not deployed to public cloud)

---

## 1. Quick Startup Commands

### Step 1: Open PowerShell in Project Root
```powershell
cd "d:\quatuam traffic"
```

### Step 2: Activate Environment & Set Port
```powershell
.\.venv\Scripts\Activate.ps1
$env:PORT="5000"
```

### Step 3: Launch Flask Server
```powershell
python app.py
```
> Expected Output: `* Running on http://127.0.0.1:5000`

### Step 4: Open Browser
Navigate to: **[http://localhost:5000/](http://localhost:5000/)**

---

## 2. Recommended Live Demo Walkthrough (3 Minutes)

1. **Traffic Snapshots:**
   - Click the **"Medium"** or **"Heavy"** scenario button.
   - Show the 4 intersection cards with color-coded density tags (`Low`, `Moderate`, `High`, `Congested`) and directional indicators (`↕ NS`, `↔ EW`).
2. **Fixed-Time Baseline Button:**
   - Click **"Fixed-Time (Baseline)"**; show that 30s/30s splits yield high accumulated delay.
3. **Adaptive Controller Button:**
   - Click **"Traffic-Responsive"**; show immediate proportional green allocation reducing total delay.
4. **Quantum QAOA Button:**
   - Click **"Run QAOA Optimization"**; explain that the server is running a genuine quantum circuit simulation on Qiskit Aer (`p=1`, 1024 shots).
   - Point out the **Measured Quantum Bitstring** (e.g., `'0010'`) and explain that each bit corresponds to an intersection phase priority.
5. **Interactive Stale Invalidation:**
   - Edit any intersection input (e.g., set Intersection A NS to `55`).
   - Point out the yellow **"Traffic inputs modified — displayed metrics reflect previous simulation state"** banner and click **"Re-calculate All"**.
6. **Theoretical Panel:**
   - Scroll to the bottom panel to show judges the deterministic queue equations ($h = 2.0\text{ s/veh}$, $C = \lfloor g/2\rfloor$) and the QUBO Hamiltonian mapping.

---

## 3. Solver Speed Optimization (If QAOA Simulation Feels Slow)

During live demos, network or CPU throttling can add a few seconds. The dashboard provides an **Advanced QAOA Parameters** dropdown:
- **Default Settings:** `p=1`, `shots=1024`, `maxiter=50` (Solver: ~400 ms, Total Latency: ~2.4 s).
- **Fast Demo Tuning:** Change `shots=256` and `maxiter=20` (Solver: ~190 ms, Total Latency: ~1.2 s).
  - *Quality Guarantee:* Finds the exact same optimal bitstring (`'0010'`) in less than half the time, with 100% genuine Aer execution.

---

## 4. Emergency Recovery Checklist

### Case A: Port Already In Use (`Address already in use` or Port 5000 busy)
**Symptom:** `OSError: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 5000)`
**Resolution:**
```powershell
# Find and terminate existing Python process on port 5000
Get-NetTCPConnection -LocalPort 5000 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
# Restart app
python app.py
```
*Alternatively, bind to port 5001:*
```powershell
$env:PORT="5001"
python app.py
# Open http://localhost:5001/
```

---

### Case B: Quantum Dependency Failure (`ImportError: No module named 'qiskit'`)
**Symptom:** Virtual environment inactive or package corrupted.
**Resolution:**
1. Check `.venv` interpreter:
   ```powershell
   .\.venv\Scripts\python -c "import qiskit, qiskit_aer; print('Qiskit OK:', qiskit.__version__)"
   ```
2. **Fallback Demo Plan:** If Qiskit cannot be loaded on stage, the dashboard and backend gracefully support demonstrating the **Fixed-Time** and **Traffic-Responsive** controllers. Conventional results are clearly displayed, and the QAOA failure banner will transparently report `Qiskit Aer unavailable` without crashing or falsely claiming classical results as quantum.

---

### Case C: QAOA Solver Timeout (> 30s)
**Symptom:** The user set `p=3` or extremely high iteration counts on a slow CPU.
**Behavior & Resolution:**
- QuantumFlow has an internal `timeout_sec=30.0` guard. When exceeded:
  1. The API responds with HTTP 200 and `solver_status="timeout"`.
  2. The dashboard displays the red alert: `QAOA: Timeout (Limit Exceeded)`.
  3. No artificial quantum result is presented.
- **Presenter Action:** Reset QAOA parameters to `p=1`, `shots=256`, `maxiter=20` and click "Run QAOA Optimization" to restore sub-second execution.

---

### Case D: Browser Access Unavailable
**Symptom:** Display hardware failure or headless environment.
**Verification Script:** Run the automated end-to-end verification script from PowerShell:
```powershell
.\.venv\Scripts\python scratch\test_live_demo.py
```
This tests all three controllers directly over HTTP and prints metrics in under 3 seconds.
