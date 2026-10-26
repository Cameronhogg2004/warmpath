#!/bin/bash
# shot.sh <url-fragment> <out.png> [height]  — full-width PNG of the running app via headless Chrome.
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT="$(cd "$(dirname "$0")/.." && pwd)/docs/screenshots/$2"
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --window-size=1440,${3:-1400} \
  --virtual-time-budget=6000 --screenshot="$OUT" "http://127.0.0.1:8077/$1" 2>/dev/null
echo "$OUT"
