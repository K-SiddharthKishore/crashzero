from pathlib import Path
import json,urllib.request
root=Path(__file__).resolve().parents[1]
p=root/'data/historical/nyc_2024.csv'
if not p.exists():
    source=json.loads((p.parent/'source.json').read_text())
    with urllib.request.urlopen(source['query_url'],timeout=120) as r: p.write_bytes(r.read())
print(p)
