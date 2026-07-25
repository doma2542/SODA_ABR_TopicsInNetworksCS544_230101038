# SODA ABR Agent — Quick Start + Technical Overview

This repository contains an ABR research toolkit centered on two controllers: a SODA-inspired QoE optimizer and a robust-MPC baseline. The code is arranged so you can (1) convert raw network logs into test traces, (2) construct a video manifest, and (3) run repeatable simulations that produce standard QoE metrics.

---

## Part I — Quick Start & Layman Overview

What problem this solves
- Video streaming must adapt the video bitrate to changing network speed. If the bitrate is too high, playback stalls (rebuffering). If it's too low, quality drops. The goal is to choose bitrates that keep viewers happy by balancing quality, smoothness, and avoiding stalls.

What this project does (plain language)
- We provide a small experiment pipeline that: turns network logs into playable traces, generates a movie manifest (how big each chunk is at each quality), and runs a simulator that mimics playback. Two decision modules choose the next quality level for each chunk — one that follows a robust model predictive control (MPC) approach, and one inspired by the SODA paper that searches smarter to reduce unnecessary switches.

Why this is useful
- Reproducible comparisons: run many real-world traces and compare average bitrate, rebuffering, and how often quality jumps happen.
- Research-ready: the code is clear and modular so you can swap or extend controllers, change evaluation metrics, or plug in new traces.

Quick commands (get started fast)

```powershell
# Generate processed network traces (from CSV logs placed in data/raw)
python scripts/preprocess.py

# Build the movie manifest used by the simulator
python scripts/build_movie.py

# Run experiments across processed traces and aggregate QoE metrics
python run_all.py
```

Files you'll use most
- `scripts/preprocess.py` — prepares uniform 10-minute traces from raw logs.
- `scripts/build_movie.py` — derives per-segment sizes and bitrate ladder into `data/processed/movie.json`.
- `run_all.py` — runs the simulator (`sabre/src/sabre.py`) over traces and aggregates results.

Scope and expectations
- This repository is a simulator and evaluation harness. It does not perform live streaming or collect online metrics. Expect CPU-bound runs for many traces; reduce the sample count if you want faster iterations.

---

## Part II — Technical Explanation (concise & conceptual)

How the agents work (conceptual)
- Both controllers are implemented as modular ABR agents that the simulator calls for each chunk. An agent observes recent network behavior and the current buffer, predicts short-term bandwidth, and picks the next quality index.

- The robust-MPC controller evaluates many short future bitrate plans, simulating their immediate effects on buffer and playback, and selects the plan whose first action maximizes a combined score of expected quality, penalty for stalls, and penalty for large quality changes.

- The SODA-inspired controller shares the same prediction approach but replaces brute-force planning with a guided recursive search that focuses on monotonic (increasing or decreasing) bitrate paths and adds buffer-aware safety checks. This reduces the number of candidate plans evaluated while still targeting smooth, high-quality playback.

Key conceptual components
- Trace preprocessor: converts packet-level or event CSV logs into evenly spaced time bins (2s by default) with a single representative bandwidth and latency per bin — this is what the simulator consumes.
- Movie manifest: maps each quality level to per-segment sizes; the simulator uses it to compute download times under a trace.
- Predictor: both agents use a short-term bandwidth estimator (an exponential moving average) to estimate what the next chunk download speed will be.
- Planner / Selector: the core of each agent — either brute-force MPC or the SODA recursive search — which reasons about how a choice now affects buffer, future downloads, and viewer QoE.

Outputs and metrics (what you measure)
- Average played bitrate — how much quality (on average) was delivered.
- Rebuffering ratio — fraction of playback time spent stalled.
- Smoothness — how frequently or how much bitrate changes between consecutive segments.

Extending or experimenting (recommendations)
- Swap a new ABR module by adding a Python file that subclasses the simulator's agent base and implements the decision method.
- To compare strategies, run the driver with a moderate number of processed traces and inspect aggregated metrics printed by `run_all.py`.

---

## Installation & Minimal Setup (recap)

```powershell
git clone <REPO_URL>
cd Sabre
python -m venv .venv
.\.venv\Scripts\activate
pip install --upgrade pip
pip install pandas
```

Optional for plotting:

```powershell
pip install matplotlib seaborn numpy
```

## Files & Where to Look
- Entrypoint simulator: `sabre/src/sabre.py` (the simulator CLI used by `run_all.py`).
- Core scripts: `scripts/preprocess.py`, `scripts/build_movie.py`, `run_all.py`.
- Controllers: `scripts/abr_mpc.py`, `scripts/abr_soda.py`.

---

