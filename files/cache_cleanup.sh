#!/bin/sh
# Prune package-manager / build caches that community-scripts updates and
# npm/pnpm/uv installs leave behind and nothing else ever cleans (n8n: 2G npm
# cache, immich: 4.5G pnpm store). Caches only: never app data, and never
# immich's /opt/staging (its updater reuses it).
used() { df -Pk / | awk 'NR==2{print $3}'; }
before=$(used)

command -v npm >/dev/null 2>&1 && npm cache clean --force >/dev/null 2>&1
if command -v pnpm >/dev/null 2>&1; then
  pnpm store prune >/dev/null 2>&1
  # A pnpm major upgrade starts a new store/vN and orphans the old one whole
  # (immich: 2.5G store/v10 left behind by pnpm 11).
  cur=$(pnpm store path 2>/dev/null)
  case "$cur" in
    */store/v[0-9]*)
      for old in "${cur%/v*}"/v[0-9]*; do
        [ "$old" = "$cur" ] || rm -rf "$old"
      done ;;
  esac
fi
command -v uv >/dev/null 2>&1 && uv cache prune >/dev/null 2>&1

# n8n copies its editor UI into ~/.cache/n8n/public on every start but never
# removes the previous version's hashed assets (~700-1500 files per upgrade).
# Keep exactly the files the installed version ships.
if command -v npm >/dev/null 2>&1; then
  dist="$(npm root -g 2>/dev/null)/n8n/node_modules/n8n-editor-ui/dist/assets"
  for pub in /.cache/n8n/public/assets /root/.cache/n8n/public/assets \
             /home/*/.cache/n8n/public/assets; do
    [ -d "$pub" ] && [ -d "$dist" ] || continue
    for f in "$pub"/*; do
      [ -e "$dist/${f##*/}" ] || rm -rf "$f"
    done
  done
fi

freed=$(( ($before - $(used)) / 1024 ))
[ "$freed" -gt 0 ] && echo "CHANGED freed ${freed}MB"
exit 0
