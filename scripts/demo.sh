#!/usr/bin/env bash
# End-to-end smoke test against the running compose stack (make up first).
# Generates a 100 s test mp3, uploads it through nginx, polls to `done`,
# prints the timeline summary.
set -euo pipefail

BASE="${BASE:-http://localhost:8080}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "» generating 100s test mp3"
if command -v ffmpeg >/dev/null; then
  ffmpeg -y -hide_banner -loglevel error -f lavfi -i "sine=frequency=440:duration=100" \
    -q:a 9 "$TMP/lecture.mp3"
else
  docker compose -f infra/docker-compose.yml exec -T backend \
    ffmpeg -y -hide_banner -loglevel error -f lavfi -i "sine=frequency=440:duration=100" \
    -q:a 9 -f mp3 - > "$TMP/lecture.mp3"
fi

echo "» uploading (expected_speakers=3)"
ID=$(curl -sf -F "file=@$TMP/lecture.mp3" -F "expected_speakers=3" \
  "$BASE/api/recordings" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "  recording id: $ID"

echo "» polling status"
for _ in $(seq 1 60); do
  BODY=$(curl -sf "$BASE/api/recordings/$ID")
  STATUS=$(echo "$BODY" | python3 -c "import sys,json; r=json.load(sys.stdin); print(r['status'], r['progress']['done_chunks'], r['progress']['total_chunks'])")
  echo "  $STATUS"
  case "$STATUS" in
    done*)   break ;;
    failed*) echo "!! recording failed"; exit 1 ;;
  esac
  sleep 2
done
[[ "$STATUS" == done* ]] || { echo "!! timed out"; exit 1; }

echo "» timeline"
curl -sf "$BASE/api/recordings/$ID/timeline" | python3 -c "
import sys, json
t = json.load(sys.stdin)
print(f'  duration: {t[\"duration_s\"]}s, speakers: {[(s[\"id\"], round(s[\"total_s\"]))for s in t[\"speakers\"]]}')
print(f'  segments: {len(t[\"segments\"])}, first: {t[\"segments\"][0][\"speaker_id\"]}: {t[\"segments\"][0][\"text\"][:50]!r}')
"

echo "» audio range request (seek support)"
curl -sf -o /dev/null -w '  HTTP %{http_code} for bytes=0-99\n' \
  -H "Range: bytes=0-99" "$BASE/api/recordings/$ID/audio"

echo "OK — full loop works"
