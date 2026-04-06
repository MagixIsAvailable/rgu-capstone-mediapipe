#!/usr/bin/env python3
"""
analyze_logs.py — VisionInput Latency Analysis for Dissertation
Run: python analyze_logs.py merged_logs.xlsx
Or:  python analyze_logs.py logs/latency/
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path

DEADLINE_MS = 33.33  # 30fps frame budget


def resolve_input_path(raw_arg: str | None) -> Path:
    """Resolve input path, searching recursively for merged_logs.xlsx when needed."""
    default_name = 'merged_logs.xlsx'
    candidate = Path(raw_arg) if raw_arg else Path(default_name)

    if candidate.exists():
        return candidate

    # If a non-existent path was provided, first try matching by file name.
    search_name = candidate.name if raw_arg else default_name
    search_roots = [Path.cwd(), Path(__file__).resolve().parent, Path(__file__).resolve().parent.parent]
    seen = set()
    dedup_roots = []
    for root in search_roots:
        resolved = root.resolve()
        if resolved not in seen and resolved.exists():
            seen.add(resolved)
            dedup_roots.append(resolved)

    matches = []
    for root in dedup_roots:
        matches.extend(root.rglob(search_name))

    if not matches and search_name != default_name:
        # Fallback to merged_logs.xlsx if a custom path was provided but not found.
        for root in dedup_roots:
            matches.extend(root.rglob(default_name))

    matches = sorted({m.resolve() for m in matches})

    if not matches:
        raise FileNotFoundError(
            f"Could not find '{search_name}' (or '{default_name}') under {Path.cwd()}"
        )

    if len(matches) > 1:
        print(f"Multiple matches found for '{search_name}', using: {matches[0]}")

    return matches[0]

def load_data(path: Path) -> pd.DataFrame:
    """Load from xlsx or directory of CSVs."""
    if path.suffix == '.xlsx':
        # Try all sheets, concatenate
        xls = pd.ExcelFile(path)
        frames = []
        for sheet in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet)
            df['_source_sheet'] = sheet
            frames.append(df)
        return pd.concat(frames, ignore_index=True)
    elif path.is_dir():
        frames = []
        for csv in path.rglob('*.csv'):
            try:
                df = pd.read_csv(csv, on_bad_lines='skip')
                df['_source_file'] = csv.name
                frames.append(df)
            except Exception as e:
                print(f"  Skipped {csv.name}: {e}")
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    else:
        return pd.read_csv(path)

def find_latency_column(df: pd.DataFrame) -> str:
    """Find the latency column regardless of naming."""
    candidates = ['latency_ms', 'loop_total_ms', 'frame_latency_ms', 'total_ms', 'latency']
    for col in candidates:
        if col in df.columns:
            return col
    # Fallback: first column containing 'latency' or 'ms'
    for col in df.columns:
        if 'latency' in col.lower() or '_ms' in col.lower():
            return col
    raise ValueError(f"No latency column found. Columns: {list(df.columns)}")

def analyze(df: pd.DataFrame, latency_col: str) -> dict:
    """Compute dissertation-ready stats."""
    data = pd.to_numeric(df[latency_col], errors='coerce').dropna()
    
    if len(data) == 0:
        return {'error': 'No valid latency data'}
    
    stats = {
        'n_trials': len(data),
        'min_ms': data.min(),
        'max_ms': data.max(),
        'mean_ms': data.mean(),
        'median_ms': data.median(),
        'std_ms': data.std(),
        'p90_ms': np.percentile(data, 90),
        'p95_ms': np.percentile(data, 95),
        'p99_ms': np.percentile(data, 99),
        'within_deadline': (data <= DEADLINE_MS).sum(),
        'deadline_miss_rate': (data > DEADLINE_MS).mean() * 100,
        'outliers_100ms': (data > 100).sum(),
    }
    stats['within_deadline_pct'] = stats['within_deadline'] / stats['n_trials'] * 100
    return stats

def print_report(stats: dict, label: str = "All Data"):
    """Print dissertation-formatted table."""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    if 'error' in stats:
        print(f"  ERROR: {stats['error']}")
        return
    
    print(f"  Trials:           {stats['n_trials']:,}")
    print(f"  Min:              {stats['min_ms']:.2f} ms")
    print(f"  Max:              {stats['max_ms']:.2f} ms")
    print(f"  Mean:             {stats['mean_ms']:.2f} ms")
    print(f"  Median:           {stats['median_ms']:.2f} ms")
    print(f"  Std Dev:          {stats['std_ms']:.2f} ms")
    print(f"  p90:              {stats['p90_ms']:.2f} ms")
    print(f"  p95:              {stats['p95_ms']:.2f} ms")
    print(f"  p99:              {stats['p99_ms']:.2f} ms")
    print(f"  ≤33.3ms:          {stats['within_deadline']:,} ({stats['within_deadline_pct']:.1f}%)")
    print(f"  >33.3ms (miss):   {stats['deadline_miss_rate']:.1f}%")
    print(f"  >100ms outliers:  {stats['outliers_100ms']}")
    
    # NFR verdict
    print(f"\n  NFR VERDICT (≤33ms target):")
    if stats['median_ms'] <= 33:
        print(f"    ✅ PASS — Median {stats['median_ms']:.2f}ms meets target")
    else:
        print(f"    ❌ FAIL — Median {stats['median_ms']:.2f}ms exceeds target")

def main():
    try:
        path = resolve_input_path(sys.argv[1] if len(sys.argv) >= 2 else None)
    except FileNotFoundError as exc:
        print(str(exc))
        print("Usage: python analyze_logs.py <merged_logs.xlsx | logs_directory/>")
        print("Tip: If omitted, the script searches recursively for merged_logs.xlsx.")
        sys.exit(1)

    print(f"Loading data from: {path}")
    
    df = load_data(path)
    print(f"Loaded {len(df):,} rows")
    
    if df.empty:
        print("ERROR: No data loaded.")
        sys.exit(1)
    
    latency_col = find_latency_column(df)
    print(f"Using latency column: '{latency_col}'")
    
    # Overall stats
    stats = analyze(df, latency_col)
    print_report(stats, "OVERALL LATENCY ANALYSIS")
    
    # Per-camera breakdown if available
    camera_cols = ['camera_label', 'camera', 'run_tag', 'source']
    for col in camera_cols:
        if col in df.columns:
            print(f"\n{'='*60}")
            print(f"  BREAKDOWN BY: {col}")
            print(f"{'='*60}")
            for group, group_df in df.groupby(col):
                group_stats = analyze(group_df, latency_col)
                print_report(group_stats, f"{col} = {group}")
            break
    
    print("\n" + "="*60)
    print("  Analysis complete. Copy stats to dissertation Chapter 4.")
    print("="*60)

if __name__ == '__main__':
    main()