#!/bin/bash
# Re-take every report screenshot from the runs in docs/benchmark.json (app must be running on :8077).
cd "$(dirname "$0")/.."
PY=.venv/bin/python
MDT=$($PY -c "import json;print(next(r['id'] for r in json.load(open('docs/benchmark.json')) if r['company']=='Medtronic' and not r['web'] and not r['red_team']))")
RED=$($PY -c "import json;print(next(r['id'] for r in json.load(open('docs/benchmark.json')) if r['red_team']))")
S=docs/screenshots
scripts/shot.sh "#run=$MDT" full_medtronic.png 2800 >/dev/null
$PY - "$S/full_medtronic.png" <<'PY'
import sys
from PIL import Image
im = Image.open(sys.argv[1]); px = im.load()
# The introducer cards start at the first card row below the summary; cut there.
def blank(y): return all(px[x, y][:3] == (244, 246, 249) for x in range(100, 960, 20))
# Blocks down the main column: form, stage strip, summary card, then the cards. Cut after the 3rd.
y, ends, prev = 120, [], blank(120)
while y < im.height - 1 and len(ends) < 3:
    b = blank(y)
    if b and not prev:
        ends.append(y)
    prev, y = b, y + 1
cut = ends[-1] + 4
end = im.height - 1
while blank(end) and end > cut: end -= 1
im.crop((0, 0, im.width, cut)).save(sys.argv[1].replace("full_medtronic", "01_run_top"), optimize=True)
im.crop((0, cut, im.width, end + 20)).save(sys.argv[1].replace("full_medtronic", "02_run_bottom"), optimize=True)
print("cut at", cut, "end", end)
PY
scripts/shot.sh "#run=$RED" tmp_red.png 1300 >/dev/null && $PY scripts/crop.py $S/tmp_red.png $S/05_redteam.png 0 1180
$PY -c "from PIL import Image; im=Image.open('$S/tmp_red.png'); im.crop((990, 460, 1355, 1180)).save('$S/05b_redteam_trace.png', optimize=True)"
scripts/shot.sh "#safety" tmp_s.png 900 >/dev/null && $PY scripts/crop.py $S/tmp_s.png $S/06_safety.png 0 760
scripts/shot.sh "#cost" tmp_c.png 1100 >/dev/null && $PY scripts/crop.py $S/tmp_c.png $S/07_cost.png 0 900
scripts/shot.sh "#history" tmp_h.png 900 >/dev/null && $PY scripts/crop.py $S/tmp_h.png $S/08_history.png 0 820
rm -f $S/tmp_*.png
echo "MDT=$MDT RED=$RED"
