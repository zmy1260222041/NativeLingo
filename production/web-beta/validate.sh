#!/usr/bin/env bash
# Post-deploy smoke validation for the Stranger Web Beta.
#
# Required env:
#   WEB_BETA_DOMAIN=example.com
#   WEB_BETA_TEST_USER=tester01
#   WEB_BETA_TEST_PASSWORD=<the generated password>
#
# Checks: 401 unauth / 401 wrong password / 200 valid auth / WASM MIME /
# gzip static serving / security headers / microphone permission policy /
# 5 concurrent cold loads without 5xx / theoretical 20 Mbps first-load time.
set -euo pipefail

DOMAIN="${WEB_BETA_DOMAIN:-}"
USERNAME="${WEB_BETA_TEST_USER:-}"
PASSWORD="${WEB_BETA_TEST_PASSWORD:-}"
BASE="https://beta.${DOMAIN}"

[[ -n "$DOMAIN" && -n "$USERNAME" && -n "$PASSWORD" ]] || {
  echo "required: WEB_BETA_DOMAIN, WEB_BETA_TEST_USER, WEB_BETA_TEST_PASSWORD" >&2
  exit 1
}

fail=0
check() {
  local label="$1"; local ok="$2"; local detail="$3"
  if [[ "$ok" == "0" ]]; then
    echo "  OK   $label${detail:+  ($detail)}"
  else
    echo "  FAIL $label${detail:+  ($detail)}"
    fail=1
  fi
}

status() {
  local user="$1"; local pass="$2"; local path="$3"
  curl -sS -o /dev/null -w '%{http_code}' -u "$user:$pass" "$BASE$path"
}

code_noauth="$(curl -sS -o /dev/null -w '%{http_code}' "$BASE/")"
check "unauthenticated request is 401" "$([[ "$code_noauth" == "401" ]]; echo $?)" "$code_noauth"

code_bad="$(curl -sS -o /dev/null -w '%{http_code}' -u "$USERNAME:definitely-wrong" "$BASE/")"
check "wrong password is 401" "$([[ "$code_bad" == "401" ]]; echo $?)" "$code_bad"

code_ok="$(status "$USERNAME" "$PASSWORD" "/")"
check "valid account loads index" "$([[ "$code_ok" == "200" ]]; echo $?)" "$code_ok"

headers_wasm="$(curl -sSI -H 'Accept-Encoding: gzip' -u "$USERNAME:$PASSWORD" "$BASE/index.wasm")"
mime="$(grep -i '^content-type:' <<<"$headers_wasm" | tr -d '\r' | awk '{print $2}')"
check "WASM MIME is application/wasm" "$([[ "$mime" == "application/wasm" ]]; echo $?)" "$mime"

gzip_wasm="$(grep -i '^content-encoding:' <<<"$headers_wasm" | tr -d '\r' | awk '{print $2}')"
check "WASM served precompressed" "$([[ "$gzip_wasm" == "gzip" ]]; echo $?)" "$gzip_wasm"

headers_pck="$(curl -sSI -H 'Accept-Encoding: gzip' -u "$USERNAME:$PASSWORD" "$BASE/index.pck")"
gzip_pck="$(grep -i '^content-encoding:' <<<"$headers_pck" | tr -d '\r' | awk '{print $2}')"
check "PCK served precompressed" "$([[ "$gzip_pck" == "gzip" ]]; echo $?)" "$gzip_pck"

headers_index="$(curl -sSI -u "$USERNAME:$PASSWORD" "$BASE/index.html")"
cache_index="$(grep -i '^cache-control:' <<<"$headers_index" | tr -d '\r' | awk '{$1=""; print $0}' | xargs)"
check "index.html is never cached" "$(grep -qi 'no-store' <<<"$cache_index"; echo $?)" "$cache_index"

headers_security="$(curl -sSI -u "$USERNAME:$PASSWORD" "$BASE/")"
for h in x-content-type-options referrer-policy strict-transport-security content-security-policy permissions-policy; do
  check "security header $h present" "$(grep -qi "^$h:" <<<"$headers_security"; echo $?)"
done
perm_policy="$(grep -i '^permissions-policy:' <<<"$headers_security" | tr -d '\r' | awk '{$1=""; print $0}')"
check "microphone permission disabled" "$(grep -qi 'microphone=()' <<<"$perm_policy"; echo $?)" "$perm_policy"
check "no COOP/COEP (single-thread build)" "$(grep -qiE '^cross-origin-(opener|embedder)-policy:' <<<"$headers_security" && echo 1 || echo 0)"

echo "  concurrent cold loads (5x):"
results="$(printf '%s\n' 1 2 3 4 5 | xargs -P5 -I{} curl -sS -o /dev/null -w '%{http_code}\n' -u "$USERNAME:$PASSWORD" "$BASE/")"
echo "$results" | sort | uniq -c | sed 's/^/    /'
if grep -q '^5' <<<"$results"; then
  check "5 concurrent cold loads without 5xx" 1
else
  check "5 concurrent cold loads without 5xx" 0
fi

# 20 Mbps theoretical first-load estimate from actual transfer sizes.
sizes="$(
  curl -sS -u "$USERNAME:$PASSWORD" "$BASE/index.wasm.gz" -o /tmp/stranger_wasm.gz -w '%{size_download} ' &&
  curl -sS -u "$USERNAME:$PASSWORD" "$BASE/index.pck.gz" -o /tmp/stranger_pck.gz -w '%{size_download}' &&
  echo
)"
wasm_bytes="$(cut -d' ' -f1 <<<"$sizes")"
pck_bytes="$(cut -d' ' -f2 <<<"$sizes")"
estimate="$(awk -v w="$wasm_bytes" -v p="$pck_bytes" 'BEGIN { printf "%.1f", (w+p)*8/20000000 }')"
check "20 Mbps first-load estimate <= 30 s" "$(awk -v e="$estimate" 'BEGIN { exit !(e <= 30) }'; echo $?)" "${estimate}s (wasm.gz ${wasm_bytes}B + pck.gz ${pck_bytes}B)"
rm -f /tmp/stranger_wasm.gz /tmp/stranger_pck.gz

echo
if [[ "$fail" == "0" ]]; then
  echo "PASS: web beta smoke validation"
else
  echo "FAIL: one or more checks failed"
  exit 1
fi
