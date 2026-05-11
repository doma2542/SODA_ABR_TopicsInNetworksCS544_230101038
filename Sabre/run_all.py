import subprocess
import re

# =========================================================
# Configuration
# =========================================================

TOTAL_TRACES = 40

MOVIE_FILE = "data/processed/movie.json"
ABR_FILE = "scripts/abr_mpc.py" 
#Keep File Name as abr_soda for soda controller session simulation 

# =========================================================
# Metrics Storage
# =========================================================

metrics_sum = {
    "time_average_played_bitrate": 0.0,
    "rebuffer_ratio": 0.0,
    "time_average_log_bitrate_change": 0.0,
    "time_average_score": 0.0,
    "rampup_time": 0.0
}

successful_runs = 0

# =========================================================
# Regex Patterns
# =========================================================

patterns = {
    "time_average_played_bitrate":
        r"time average played bitrate:\s+(-?\d+(?:\.\d+)?)",

    "rebuffer_ratio":
        r"rebuffer ratio:\s+(-?\d+(?:\.\d+)?)",

    "time_average_log_bitrate_change":
        r"time average log bitrate change:\s+(-?\d+(?:\.\d+)?)",

    "time_average_score":
        r"time average score:\s+(-?\d+(?:\.\d+)?)",

    "rampup_time":
        r"rampup time:\s+(-?\d+(?:\.\d+)?)"
}

# =========================================================
# Main Loop
# =========================================================

for i in range(TOTAL_TRACES):

    network_file = f"data/processed/network_{i}.json"

    cmd = [
        "py",
        "sabre/src/sabre.py",
        "-n", network_file,
        "-m", MOVIE_FILE,
        "-a", ABR_FILE
    ]

    print(f"Running trace {i}...")

    try:

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )

        output = result.stdout

        # Extract metrics
        trace_metrics = {}

        valid = True

        for key, pattern in patterns.items():

            match = re.search(pattern, output)

            if match:
                trace_metrics[key] = float(match.group(1))
            else:
                print(f"Metric missing in trace {i}: {key}")
                valid = False
                break

        if not valid:
            continue

        # Add metrics
        for key in metrics_sum:
            metrics_sum[key] += trace_metrics[key]

        successful_runs += 1

    except Exception as e:
        print(f"Error on trace {i}: {e}")

# =========================================================
# Final Averages
# =========================================================

print("\n==============================")
print("FINAL AVERAGE QoE METRICS")
print("==============================")

if successful_runs == 0:
    print("No successful runs.")
else:

    for key in metrics_sum:

        avg = metrics_sum[key] / successful_runs

        print(f"{key}: {avg:.6f}")

    print(f"\nSuccessful Runs: {successful_runs}")