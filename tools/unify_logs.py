import csv
import re
from pathlib import Path
import pandas as pd
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

# -----------------------------
# SETTINGS
# -----------------------------
FOLDER = Path("./logs")
OUTPUT_FILE = Path("./merged_logs.xlsx")

_EXTRA_CONTROL_RE = re.compile(r"[\x00-\x08\x0B-\x0C\x0E-\x1F]")


def clean_for_excel(df: pd.DataFrame) -> pd.DataFrame:
    """Remove control chars that Excel/openpyxl rejects."""
    out = df.copy()

    out.columns = [
        ILLEGAL_CHARACTERS_RE.sub("", str(col)) if col is not None else col
        for col in out.columns
    ]

    obj_cols = out.select_dtypes(include=["object", "string"]).columns
    for col in obj_cols:
        out[col] = out[col].map(
            lambda v: _EXTRA_CONTROL_RE.sub("", ILLEGAL_CHARACTERS_RE.sub("", v))
            if isinstance(v, str)
            else v
        )

    return out

def parse_log_file(path: Path):
    try:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
            rows = list(csv.reader(f))

        # Find first real data header row (starts with timestamp or session_created_at)
        header_idx = None
        for i, row in enumerate(rows):
            if row:
                first_col = row[0].strip().lower()
                if first_col in ("timestamp", "session_created_at"):
                    header_idx = i
                    break

        if header_idx is None:
            print(f"[SKIP] No data header found: {path}")
            return None

        # Metadata is key,value pairs before header
        metadata = {}
        for row in rows[:header_idx]:
            if len(row) >= 2:
                k = row[0].strip()
                v = row[1].strip()
                if k:
                    metadata[k] = v

        if "camera_label" not in metadata:
            metadata["camera_label"] = "Unknown (legacy log)"

        header = [c.strip() for c in rows[header_idx]]
        data_rows = rows[header_idx + 1 :]

        records = []
        for row in data_rows:
            if not any(cell.strip() for cell in row):
                continue

            # Normalize row length to header length
            if len(row) < len(header):
                row = row + [""] * (len(header) - len(row))
            elif len(row) > len(header):
                row = row[:len(header)]

            rec = {header[j]: row[j].strip() for j in range(len(header))}
            rec.update(metadata)
            rec["source_file"] = path.name
            rec["source_path"] = str(path.as_posix())
            records.append(rec)

        if not records:
            print(f"[SKIP] No data rows: {path}")
            return None

        df = pd.DataFrame(records)

        # Numeric coercion for known telemetry columns
        numeric_cols = [
            "frame_index", "hand_confidence", "hand_count", "latency_ms",
            "norm_x", "norm_y", "fps_rolling_1s", "capture_ms",
            "preprocess_ms", "mediapipe_ms", "output_ms", "loop_ms",
            "read_failed_count", "duration_s", "frames", "fps",
            "capture_ms_per_frame", "preprocess_ms_per_frame",
            "mediapipe_ms_per_frame", "output_ms_per_frame",
            "loop_total_ms_per_frame", "negotiated_fps", "requested_fps",
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if "is_non_neutral" in df.columns:
            df["is_non_neutral"] = (
                df["is_non_neutral"]
                .astype(str)
                .str.strip()
                .str.lower()
                .map({"true": True, "false": False})
            )

        print(f"[OK] Loaded: {path.name} ({len(df)} rows)")
        return df

    except Exception as e:
        print(f"[ERROR] Failed to load {path}: {e}")
        return None


# -----------------------------
# LOAD ALL CSV FILES RECURSIVELY
# -----------------------------
all_files = sorted(FOLDER.rglob("*.csv"))
print(f"\nScanning folder: {FOLDER}")
print(f"Found {len(all_files)} CSV files\n")

tables = []
for file_path in all_files:
    df = parse_log_file(file_path)
    if df is not None and not df.empty:
        tables.append(df)

if not tables:
    print("\n[STOP] No parsable data tables found. Nothing to merge.")
    raise SystemExit(1)

merged = pd.concat(tables, ignore_index=True, sort=False)
merged = clean_for_excel(merged)
merged.to_excel(OUTPUT_FILE, index=False)

print(f"\nUnified logs exported to: {OUTPUT_FILE}")
print(f"Total rows: {len(merged)}")