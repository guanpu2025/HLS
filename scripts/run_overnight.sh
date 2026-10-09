#!/usr/bin/env bash
# One night on EVO. Does not change selftest/env.sh.
#   1. 8 interface tasks, 950s, 3 rounds (today's interface skill)
#   2. header / array_type / never-reached-csynth, 950s, 3 rounds
#   3. 30 csynth timeouts, 900s, 2 rounds (more synthesis time, not the new skills)
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "===== interface ====="
bash "$ROOT/scripts/run_interface_retry.sh"

echo "===== header, array_type, no-csynth ====="
# shellcheck disable=SC1091
source "$ROOT/selftest/env.sh"
export AGENT_DEADLINE_S=950
export AGENT_MAX_ROUNDS=3
extra=(
  he_machsuite_md_grid
  he_rosetta_rendering_3d__projection
  he_c2hlsc_present
  he_c2hlsc_des
  he_chstone_df_countLeadingZeros64
  he_chstone_dfdiv
  he_machsuite_aes_aes
  he_polybench_fixed_durbin
)
for name in "${extra[@]}"; do
  echo "=== $name ==="
  "$ROOT/example/run.sh" \
    "$ROOT/tasks/$name" \
    "$ROOT/selftest/out/agent/$name/s0"
done

echo "===== csynth timeout 900s ====="
bash "$ROOT/scripts/run_csynth_timeout_900.sh"

echo "===== overnight done ====="
