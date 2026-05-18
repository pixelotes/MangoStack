#!/usr/bin/env bash
# bootstrap.sh — interactive setup for MangoStack.
#
# Walks you through the values that change between rebuilds (passwords, paths,
# active services) and writes them into .env and the per-service configs.
#
# Idempotent on a freshly cloned tree. To redo it after secrets are already
# baked into the configs, reset the tree first:
#
#     git checkout -- . && ./bootstrap.sh
#
# After bootstrap, paste the remaining API keys (TMDB, Trakt, OpenSubtitles,
# Pushbullet…) from your password manager — the script prints a checklist of
# the placeholders that are still pending.

set -euo pipefail

# Require bash 4+ for associative arrays.
if (( BASH_VERSINFO[0] < 4 )); then
  echo "bootstrap.sh needs bash 4 or newer (you have ${BASH_VERSION})." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -f .env.example || ! -f docker-compose.yaml ]]; then
  echo "Run this from the MangoStack repo root." >&2
  exit 1
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required for JWT secret generation." >&2
  exit 1
fi

# --- styling ----------------------------------------------------------------

if [[ -t 1 ]]; then
  c_reset=$'\033[0m'; c_bold=$'\033[1m'; c_dim=$'\033[2m'
  c_blue=$'\033[34m'; c_yellow=$'\033[33m'
  c_green=$'\033[32m'; c_red=$'\033[31m'
else
  c_reset=""; c_bold=""; c_dim=""
  c_blue=""; c_yellow=""; c_green=""; c_red=""
fi

info() { printf '%s•%s %s\n' "$c_blue" "$c_reset" "$*"; }
warn() { printf '%s!%s %s\n' "$c_yellow" "$c_reset" "$*"; }
ok()   { printf '%s✓%s %s\n' "$c_green" "$c_reset" "$*"; }
err()  { printf '%s✗%s %s\n' "$c_red" "$c_reset" "$*" >&2; }

ask() {
  local var="$1" prompt="$2" default="${3:-}"
  local answer
  if [[ -n "$default" ]]; then
    printf '%s %s[%s]%s: ' "$prompt" "$c_dim" "$default" "$c_reset"
  else
    printf '%s: ' "$prompt"
  fi
  IFS= read -r answer
  printf -v "$var" '%s' "${answer:-$default}"
}

# Marker-based file substitution that is safe with any character in the value
# (no sed-delimiter or backslash escaping landmines).
substitute() {
  local file="$1" key="$2" value="$3"
  [[ ! -f "$file" ]] && return 0
  awk -v key="$key" -v val="$value" '
    {
      out = ""; rest = $0
      while ((i = index(rest, key)) > 0) {
        out = out substr(rest, 1, i - 1) val
        rest = substr(rest, i + length(key))
      }
      print out rest
    }
  ' "$file" > "$file.tmp" && mv "$file.tmp" "$file"
}

# --- banner -----------------------------------------------------------------

cat <<EOF

${c_bold}🥭 MangoStack bootstrap${c_reset}

Fills in .env, JWT secrets and your default UI password across the active
services. Run again after ${c_bold}git checkout -- .${c_reset} to change any of these later.

EOF

# --- prompts ----------------------------------------------------------------

ask PASSWORD  "Default UI password for the apps"
while [[ -z "$PASSWORD" ]]; do
  warn "Password can't be empty."
  ask PASSWORD "Default UI password for the apps"
done

ask BASE_DIR  "Storage root (downloads + completed media)" "/media/usb/Storage"
ask MEDIA_DIR "Media library path"                         "${BASE_DIR}/Completed"
ask TZ        "Timezone (IANA)"                            "Europe/Madrid"
ask LANGS     "Subtitle languages (comma-separated ISO)"   "en,es"
ask PUID      "Host PUID"                                  "$(id -u 2>/dev/null || echo 1000)"
ask PGID      "Host PGID"                                  "$(id -g 2>/dev/null || echo 1000)"

# --- service selection ------------------------------------------------------

declare -A SVC_LABEL=(
  [tango]="Tango      — torrent client"
  [scarf]="Scarf      — indexer aggregator"
  [reel]="Reel       — media automator"
  [rms]="RMS        — media server"
  [dashboarr]="Dashboarr  — homepage"
  [navidrome]="Navidrome  — music streaming"
  [suika]="Suika      — manga reader"
)
SVC_ORDER=(tango scarf reel rms dashboarr navidrome suika)
declare -A SVC_ENABLED=(
  [tango]=1 [scarf]=1 [reel]=1 [rms]=1 [dashboarr]=1
  [navidrome]=0 [suika]=0
)

print_services() {
  printf '\n%sServices to enable:%s\n' "$c_bold" "$c_reset"
  local i=1
  for s in "${SVC_ORDER[@]}"; do
    local mark=" "
    [[ "${SVC_ENABLED[$s]}" == 1 ]] && mark="x"
    printf "  [%s] %d) %s\n" "$mark" "$i" "${SVC_LABEL[$s]}"
    i=$((i + 1))
  done
}

while true; do
  print_services
  printf '\nToggle a number, or press Enter to confirm: '
  IFS= read -r choice
  [[ -z "$choice" ]] && break
  if [[ "$choice" =~ ^[1-7]$ ]]; then
    s="${SVC_ORDER[$((choice - 1))]}"
    if [[ "${SVC_ENABLED[$s]}" == 1 ]]; then
      SVC_ENABLED[$s]=0
    else
      SVC_ENABLED[$s]=1
    fi
  else
    warn "Pick a number 1-7."
  fi
done

PROFILES=()
for s in "${SVC_ORDER[@]}"; do
  [[ "${SVC_ENABLED[$s]}" == 1 ]] && PROFILES+=("$s")
done
COMPOSE_PROFILES_VAL="$(IFS=,; echo "${PROFILES[*]}")"

# --- derived values ---------------------------------------------------------

# YAML inline list from comma-separated ISO codes: en,es -> ["en", "es"]
LANG_YAML="["
first=1
IFS=',' read -ra _langs <<< "$LANGS"
for l in "${_langs[@]}"; do
  l="${l// /}"
  [[ -z "$l" ]] && continue
  if (( first )); then
    LANG_YAML+="\"$l\""
    first=0
  else
    LANG_YAML+=", \"$l\""
  fi
done
LANG_YAML+="]"

SCARF_JWT="$(openssl rand -hex 48)"
REEL_JWT="$(openssl rand -hex 48)"
RMS_JWT="$(openssl rand -hex 48)"
SUIKA_JWT="$(openssl rand -hex 48)"

# --- write .env -------------------------------------------------------------

info "Writing .env"
cat > .env <<EOF
# Generated by bootstrap.sh — $(date '+%Y-%m-%dT%H:%M:%S%z')
# Re-run ./bootstrap.sh to regenerate.

PUID=$PUID
PGID=$PGID
TZ=$TZ

BASE_DIR=$BASE_DIR
MEDIA_DIR=$MEDIA_DIR

SCARF_UI_PASSWORD=$PASSWORD
SCARF_JWT_SECRET=$SCARF_JWT

COMPOSE_PROFILES=$COMPOSE_PROFILES_VAL
EOF

# --- render per-service configs --------------------------------------------

info "Rendering service configs"

render_languages() {
  local f="$1"
  [[ ! -f "$f" ]] && return 0
  # Replace any inline YAML list `languages: ["en", "es"]` with the user list.
  awk -v repl="$LANG_YAML" '
    {
      if (match($0, /languages: \[[^]]*\]/)) {
        $0 = substr($0, 1, RSTART - 1) "languages: " repl substr($0, RSTART + RLENGTH)
      }
      print
    }
  ' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
}

if [[ "${SVC_ENABLED[reel]}" == 1 ]]; then
  f=reel/config/config.yml
  substitute "$f" "REPLACE_WITH_STRONG_PASSWORD"  "$PASSWORD"
  substitute "$f" "REPLACE_WITH_LONG_RANDOM_STRING" "$REEL_JWT"
  render_languages "$f"
fi

if [[ "${SVC_ENABLED[rms]}" == 1 ]]; then
  f=rms/config/config.yml
  substitute "$f" "REPLACE_WITH_STRONG_PASSWORD"  "$PASSWORD"
  substitute "$f" "REPLACE_WITH_LONG_RANDOM_STRING" "$RMS_JWT"
  render_languages "$f"
fi

if [[ "${SVC_ENABLED[suika]}" == 1 ]]; then
  f=suika/config/config.yml
  substitute "$f" "REPLACE_WITH_STRONG_PASSWORD"  "$PASSWORD"
  substitute "$f" "REPLACE_WITH_LONG_RANDOM_STRING" "$SUIKA_JWT"
fi

# Tango's shipped config has no placeholders.

ok "Stack bootstrapped."

# --- pending-API-keys report ------------------------------------------------

pending=0
declare -a pending_files
for f in reel/config/config.yml rms/config/config.yml suika/config/config.yml; do
  [[ ! -f "$f" ]] && continue
  if grep -q 'REPLACE_WITH_' "$f"; then
    pending=1
    pending_files+=("$f")
  fi
done

if (( pending )); then
  printf '\n%sStill to do — paste from your password manager:%s\n' "$c_bold" "$c_reset"
  for f in "${pending_files[@]}"; do
    printf '\n%s%s%s:\n' "$c_yellow" "$f" "$c_reset"
    grep -n 'REPLACE_WITH_' "$f" | sed 's/^/  /'
  done
fi

cat <<EOF

${c_dim}When you're done editing keys, bring the stack up:${c_reset}
  ${c_bold}docker compose up -d${c_reset}

${c_dim}The rendered configs and .env contain secrets — do not commit them.${c_reset}

EOF
