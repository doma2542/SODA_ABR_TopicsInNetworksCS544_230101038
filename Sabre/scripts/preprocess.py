import os
import json
import random
import pandas as pd
import logging
import time

# =========================
# LOGGING
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# =========================
# CONFIG
# =========================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

RAW_DIR = os.path.join(BASE_DIR, "..", "data", "raw")
OUT_DIR = os.path.join(BASE_DIR, "..", "data", "processed")

SESSION_DURATION = 600        # 10 minutes
CHUNK_DURATION = 2            # 2 sec bins (IMPORTANT)
MIN_SESSION_DURATION = 590
MAX_SESSIONS = 2000

# =========================
# LOAD MULTIPLE FILES
# =========================

def load_multiple_csv(prefix):
    files = [f for f in os.listdir(RAW_DIR) if f.startswith(prefix)]

    if not files:
        raise FileNotFoundError(f"No files found with prefix {prefix}")

    dfs = []
    for f in sorted(files):
        path = os.path.join(RAW_DIR, f)
        logging.info(f"Loading {f}")
        dfs.append(pd.read_csv(path))

    return pd.concat(dfs, ignore_index=True)

# =========================
# LOAD + MERGE
# =========================

def load_data():
    logging.info("Loading raw data...")

    acked = load_multiple_csv("video_acked")
    sent = load_multiple_csv("video_sent")

    # 🔥 FIX timestamps (scientific notation issue)
    acked['time_ns'] = pd.to_numeric(acked['time (ns GMT)'], errors='coerce')
    sent['time_ns'] = pd.to_numeric(sent['time (ns GMT)'], errors='coerce')

    acked = acked.dropna(subset=['time_ns'])
    sent = sent.dropna(subset=['time_ns'])

    acked['time_ns'] = acked['time_ns'].astype('int64')
    sent['time_ns'] = sent['time_ns'].astype('int64')

    acked['time_s'] = acked['time_ns'] / 1e9
    sent['time_s'] = sent['time_ns'] / 1e9

    logging.info("Merging per session...")

    sent_groups = dict(tuple(sent.groupby('session_id')))
    merged_sessions = []

    for session_id, ack_group in acked.groupby('session_id'):

        sent_group = sent_groups.get(session_id)
        if sent_group is None:
            continue

        ack_group = ack_group.sort_values('time_s')
        sent_group = sent_group.sort_values('time_s')

        try:
            merged = pd.merge_asof(
                ack_group,
                sent_group,
                on='time_s',
                direction='nearest'
            )
            merged['session_id'] = session_id
            merged_sessions.append(merged)

        except Exception as e:
            logging.warning(f"Skipping session {session_id}: {e}")

    df = pd.concat(merged_sessions, ignore_index=True)

    logging.info(f"Total rows after merge: {len(df)}")
    return df

# =========================
# SESSION CREATION
# =========================

def create_sessions(df):
    logging.info("Creating 10-minute sessions...")

    sessions = []

    for session_id, group in df.groupby('session_id'):

        group = group.sort_values('time_s')

        start = group['time_s'].min()
        end = group['time_s'].max()

        if (end - start) < MIN_SESSION_DURATION:
            continue

        current = start

        while current + SESSION_DURATION <= end:
            chunk = group[
                (group['time_s'] >= current) &
                (group['time_s'] < current + SESSION_DURATION)
            ]

            if len(chunk) > 0:
                sessions.append(chunk)

            current += SESSION_DURATION  # non-overlapping

    logging.info(f"Total sessions created: {len(sessions)}")
    return sessions

# =========================
# SAMPLING
# =========================

def sample_sessions(sessions):
    n = min(MAX_SESSIONS, len(sessions))
    sampled = random.sample(sessions, n)
    logging.info(f"Sampled sessions: {len(sampled)}")
    return sampled

# =========================
# METRICS
# =========================

def compute_metrics(chunk):
    if len(chunk) == 0:
        return None, None

    chunk = chunk[
        (chunk['delivery_rate'] > 1e5) &
        (chunk['delivery_rate'] < 1e8) &
        (chunk['rtt'] > 0)
    ]

    if len(chunk) == 0:
        return None, None

    bw = chunk['delivery_rate'].median() / 1000
    lat = chunk['rtt'].median() / 1000

    return int(bw), int(lat)

# =========================
# TRACE GENERATION
# =========================

def generate_network_trace(session):
    trace = []

    start = session['time_s'].min()
    end = start + SESSION_DURATION

    prev_bw = 1000
    prev_lat = 100

    while start < end:

        chunk = session[
            (session['time_s'] >= start) &
            (session['time_s'] < start + CHUNK_DURATION)
        ]

        bw, lat = compute_metrics(chunk)

        # 🔥 IMPORTANT: fill missing chunks
        if bw is None:
            bw = prev_bw
            lat = prev_lat
        else:
            prev_bw = bw
            prev_lat = lat

        trace.append({
            "duration_ms": int(CHUNK_DURATION * 1000),
            "bandwidth_kbps": bw,
            "latency_ms": lat
        })

        start += CHUNK_DURATION

    return trace

# =========================
# SAVE OUTPUT
# =========================

def save_traces(sessions):
    logging.info("Saving traces...")

    os.makedirs(OUT_DIR, exist_ok=True)

    count = 0

    for session in sessions:
        trace = generate_network_trace(session)

        if len(trace) < 50:  # sanity check
            continue

        path = os.path.join(OUT_DIR, f"network_{count}.json")

        with open(path, "w") as f:
            json.dump(trace, f, indent=4)

        count += 1

    logging.info(f"Saved {count} traces")

# =========================
# MAIN
# =========================

def main():
    start = time.time()

    df = load_data()
    sessions = create_sessions(df)
    sessions = sample_sessions(sessions)
    save_traces(sessions)

    logging.info(f"Done in {time.time() - start:.2f}s")

if __name__ == "__main__":
    main()