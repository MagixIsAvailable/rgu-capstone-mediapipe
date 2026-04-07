import csv, statistics, math
from pathlib import Path
rows=[]
for p in sorted(Path('logs/latency').glob('latency_log_*.csv')):
    lines=p.read_text(encoding='utf-8', errors='ignore').splitlines()
    res='unknown'; cam='unknown'; hdr=-1
    for i,l in enumerate(lines[:60]):
        if l.startswith('camera_resolution,'): res=l.split(',',1)[1].strip()
        if l.startswith('camera_label,'): cam=l.split(',',1)[1].strip()
        if l.strip()=='timestamp,gesture_label,hand,latency_ms': hdr=i; break
    if hdr<0: continue
    for r in csv.DictReader(lines[hdr:]):
        try: lat=float(r.get('latency_ms',''))
        except: continue
        rows.append((cam,res,lat,p.name))
print('rows',len(rows))
from collections import defaultdict
by=defaultdict(list)
for cam,res,lat,f in rows:
    by[(cam,res)].append(lat)
for (cam,res),vals in sorted(by.items(), key=lambda kv:(kv[0][0],kv[0][1])):
    n=len(vals)
    print(f'{cam}|{res}|n={n}|mean={statistics.fmean(vals):.2f}|max={max(vals):.2f}|p90={sorted(vals)[int((n-1)*0.9)]:.2f}')
