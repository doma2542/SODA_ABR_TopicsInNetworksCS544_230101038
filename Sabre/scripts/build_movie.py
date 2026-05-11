import os
import json
import pandas as pd
from collections import defaultdict

# =========================
# CONFIG
# =========================

RAW_PATH = "../data/raw/video_size.csv"
OUT_PATH = "../data/processed/movie.json"

SEGMENT_DURATION_MS = 2000

# =========================
# LOAD DATA
# =========================

def load_data():
    df = pd.read_csv(RAW_PATH)

    # Convert timestamp
    df['time_s'] = df['time (ns GMT)'] / 1e9

    return df


# =========================
# PREPROCESS
# =========================

def extract_bitrates(df):
    """
    Extract unique formats → map to bitrate index
    """
    formats = sorted(df['format'].unique())

    # Assign index
    format_to_idx = {f: i for i, f in enumerate(formats)}

    return formats, format_to_idx


def estimate_bitrates(df, formats):
    """
    Estimate bitrate (kbps) for each format
    bitrate = size / duration
    """
    bitrate_map = {}

    for f in formats:
        subset = df[df['format'] == f]

        if len(subset) == 0:
            bitrate_map[f] = 0
            continue

        # average size (bytes → bits)
        avg_size_bits = subset['size'].median() * 8

        bitrate_kbps = avg_size_bits / (SEGMENT_DURATION_MS / 1000) / 1000
        bitrate_map[f] = int(bitrate_kbps)

    return bitrate_map


def build_segment_matrix(df, format_to_idx, num_formats):
    """
    Build segment_sizes_bits matrix
    """

    # group by segment
    grouped = df.groupby('video_ts')

    segment_matrix = []

    for _, group in grouped:
        sizes = [0] * num_formats

        for _, row in group.iterrows():
            fmt = row['format']
            idx = format_to_idx[fmt]

            size_bits = int(row['size'] * 8)
            sizes[idx] = size_bits

        # skip incomplete segments
        if 0 in sizes:
            continue

        segment_matrix.append(sizes)

    return segment_matrix


# =========================
# MAIN GENERATION
# =========================

def generate_movie():
    print("Loading video_size.csv...")
    df = load_data()

    print("Extracting formats...")
    formats, format_to_idx = extract_bitrates(df)

    print(f"Found {len(formats)} quality levels")

    print("Estimating bitrates...")
    bitrate_map = estimate_bitrates(df, formats)

    # sort formats by bitrate (important!)
    formats_sorted = sorted(formats, key=lambda f: bitrate_map[f])
    format_to_idx = {f: i for i, f in enumerate(formats_sorted)}

    bitrates_kbps = [bitrate_map[f] for f in formats_sorted]

    print("Building segment size matrix...")
    segment_matrix = build_segment_matrix(
        df, format_to_idx, len(formats_sorted)
    )

    print(f"Total segments: {len(segment_matrix)}")

    movie = {
        "segment_duration_ms": SEGMENT_DURATION_MS,
        "bitrates_kbps": bitrates_kbps,
        "segment_sizes_bits": segment_matrix
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)

    with open(OUT_PATH, "w") as f:
        json.dump(movie, f, indent=4)

    print(f"Saved movie.json → {OUT_PATH}")


# =========================
# RUN
# =========================

if __name__ == "__main__":
    generate_movie()