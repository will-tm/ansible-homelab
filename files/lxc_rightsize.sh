#!/usr/bin/env bash
# Right-size running LXCs on this Proxmox node so community-scripts updaters
# never hit their unattended-mode prechecks (build.func):
#   check_container_storage   -> exit 114 when / (/boot) is > 80% used
#   check_container_resources -> exit 113 when nproc/RAM < ct/<slug>.sh var_cpu/var_ram
# Grow-only: disks are resized up, cores/memory raised to the upstream minimum.
# Usage: lxc_rightsize.sh [--dry-run]
# Prints one "CHANGED ..." line per change; exit 0 unless a fix was needed but failed.
set -uo pipefail

DRY=0; [[ "${1:-}" == "--dry-run" ]] && DRY=1
DISK_TRIGGER=70   # grow when usage >= this % (updater aborts above 80%; builds eat space mid-update)
DISK_TARGET=60    # grow so usage lands at about this %
POOL_FREE_MIN_G=20  # never let a resize leave the storage with less than this free
CS_URL="https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main"
rc=0

run() {
  if ((DRY)); then echo "DRY-RUN: $*"; else "$@"; fi
}

for id in $(pct list | awk 'NR>1 && $2=="running"{print $1}'); do
  name=$(pct config "$id" | awk '/^hostname:/{print $2}')

  # --- disk ---------------------------------------------------------------
  read -r size_k used_k < <(pct exec "$id" -- df -Pk / 2>/dev/null | awk 'NR==2{print $2, $3}')
  if [[ -n "${size_k:-}" && "$size_k" -gt 0 ]]; then
    pct_used=$((100 * used_k / size_k))
    if ((pct_used >= DISK_TRIGGER)); then
      size_g=$(( (size_k + 1048575) / 1048576 ))
      want_g=$(( (used_k * 100 / DISK_TARGET + 1048575) / 1048576 ))
      add_g=$((want_g - size_g)); ((add_g < 2)) && add_g=2
      storage=$(pct config "$id" | sed -n 's/^rootfs: \([^:]*\):.*/\1/p')
      avail_g=$(pvesm status --storage "$storage" 2>/dev/null | awk 'NR==2{print int($6/1048576)}')
      if [[ -n "$avail_g" ]] && ((avail_g - add_g >= POOL_FREE_MIN_G)); then
        echo "CHANGED $id/$name: rootfs ${pct_used}% of ${size_g}G -> +${add_g}G"
        run pct resize "$id" rootfs "+${add_g}G" || { echo "FAILED $id/$name: pct resize"; rc=1; }
      else
        echo "FAILED $id/$name: rootfs ${pct_used}% but storage $storage has only ${avail_g:-?}G free"
        rc=1
      fi
    fi
  fi

  # --- community-scripts CPU/RAM minimums -----------------------------------
  slug=$(pct exec "$id" -- sh -c 'cat /usr/bin/update 2>/dev/null' |
    sed -n -e 's/^export UPDATE_SCRIPT_NAME="\([^"]*\)".*/\1/p' -e 's#.*/ct/\([A-Za-z0-9_-]*\)\.sh.*#\1#p' | head -1)
  [[ -z "$slug" ]] && continue
  ct_script=$(curl -fsSL --connect-timeout 10 "$CS_URL/ct/$slug.sh" 2>/dev/null) || continue
  need_cpu=$(sed -n 's/^var_cpu="${var_cpu:-\([0-9]*\)}".*/\1/p' <<<"$ct_script")
  need_ram=$(sed -n 's/^var_ram="${var_ram:-\([0-9]*\)}".*/\1/p' <<<"$ct_script")
  have_cpu=$(pct config "$id" | awk '/^cores:/{print $2}'); have_cpu=${have_cpu:-$(nproc)}
  have_ram=$(pct config "$id" | awk '/^memory:/{print $2}'); have_ram=${have_ram:-512}
  args=()
  [[ -n "$need_cpu" ]] && ((have_cpu < need_cpu)) && args+=(--cores "$need_cpu")
  [[ -n "$need_ram" ]] && ((have_ram < need_ram)) && args+=(--memory "$need_ram")
  if ((${#args[@]})); then
    echo "CHANGED $id/$name ($slug): ${have_cpu}c/${have_ram}MB -> ${args[*]}"
    run pct set "$id" "${args[@]}" || { echo "FAILED $id/$name: pct set"; rc=1; }
  fi
done
exit $rc
