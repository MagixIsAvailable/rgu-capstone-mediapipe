import csv, statistics, math
from pathlib import Path
files = sorted(Path('logs/latency').glob('latency_log_*.csv'))
print(f'files={len(files)}')
rows = []
for p in files:
    lines = p.read_text(encoding='utf-8', errors='ignore').splitlines()
    res = 'unknown'
    cam = 'unknown'
    hdr = -1
    for i, l in enumerate(lines[:50]):
        if l.startswith('camera_resolution,'):
            res = l.split(',',1)[1].strip()
        if l.startswith('camera_label,'):
            cam = l.split(',',1)[1].strip()
        if l.strip() == 'timestamp,gesture_label,hand,latency_ms':
            hdr = i
            break
    if hdr < 0:
        continue
    reader = csv.DictReader(lines[hdr:])
    for r in reader:
        try:
            lat = float(r.get('latency_ms', ''))
        except Exception:
            continue
        rows.append((p.name, res, cam, lat))
print(f'rows={len(rows)}')
if not rows:
    raise SystemExit(0)
by = {}
for rec in rows:
    by.setdefault(rec[1], []).append(rec)

def pct(vals, p):
    s = sorted(vals)
    if not s:
        return float('nan')
    k = (len(s) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)

print('resolutions=' + ','.join(sorted(by.keys())))
for rk in sorted(by.keys()):
    vals = [x[3] for x in by[rk]]
    n = len(vals)
    over33 = sum(v > 33 for v in vals) / n * 100
    over100 = sum(v > 100 for v in vals) / n * 100
    print('RES {rk} n={n} mean={mean:.2f} max={mx:.2f} p50={p50:.2f} p90={p90:.2f} p95={p95:.2f} p99={p99:.2f} over33={o33:.1f}% over100={o100:.1f}%'.format(
        rk=rk, n=n, mean=statistics.fmean(vals), mx=max(vals), p50=pct(vals,0.5), p90=pct(vals,0.9), p95=pct(vals,0.95), p99=pct(vals,0.99), o33=over33, o100=over100
    ))
print('top10')
for f,res,cam,lat in sorted(rows, key=lambda x: x[3], reverse=True)[:10]:
    print(f'{f}|{res}|{lat:.2f}')
