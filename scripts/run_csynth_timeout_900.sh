#!/usr/bin/env bash
# Re-run the 30 tasks whose csynth hit the 360s budget.
# Leaves selftest/env.sh at 360. Only this process uses 900.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/selftest/env.sh"
export AGENT_DEADLINE_S=900
export AGENT_MAX_ROUNDS=2

tasks=(
  he_chstone_df_countLeadingZeros32
  he_machsuite_gemm_blocked
  he_machsuite_gemm_ncubed
  he_machsuite_md_knn
  he_machsuite_sort_merge
  he_machsuite_sort_radix
  he_machsuite_spmv_ellpack
  he_machsuite_viterbi_viterbi
  he_polybench_durbin
  he_polybench_fixed_atax
  he_polybench_fixed_bicg
  he_polybench_fixed_cholesky
  he_polybench_fixed_correlation
  he_polybench_fixed_floyd-warshall
  he_polybench_fixed_gemm
  he_polybench_fixed_gemver
  he_polybench_fixed_gesummv
  he_polybench_fixed_jacobi-2d
  he_polybench_fixed_lu
  he_polybench_fixed_seidel-2d
  he_polybench_fixed_symm
  he_polybench_fixed_syr2k
  he_polybench_fixed_trmm
  he_polybench_floyd-warshall
  he_polybench_gemver
  he_polybench_jacobi-2d
  he_polybench_nussinov
  he_polybench_seidel-2d
  he_rosetta_optical_flow__outer_product
  he_rosetta_spam_filter__computeGradient
)

for name in "${tasks[@]}"; do
  echo "=== $name ==="
  "$ROOT/example/run.sh" \
    "$ROOT/tasks/$name" \
    "$ROOT/selftest/out/agent/$name/s0"
done

python3 - "$ROOT" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1]) / "selftest/out/agent"
names = """
he_chstone_df_countLeadingZeros32
he_machsuite_gemm_blocked
he_machsuite_gemm_ncubed
he_machsuite_md_knn
he_machsuite_sort_merge
he_machsuite_sort_radix
he_machsuite_spmv_ellpack
he_machsuite_viterbi_viterbi
he_polybench_durbin
he_polybench_fixed_atax
he_polybench_fixed_bicg
he_polybench_fixed_cholesky
he_polybench_fixed_correlation
he_polybench_fixed_floyd-warshall
he_polybench_fixed_gemm
he_polybench_fixed_gemver
he_polybench_fixed_gesummv
he_polybench_fixed_jacobi-2d
he_polybench_fixed_lu
he_polybench_fixed_seidel-2d
he_polybench_fixed_symm
he_polybench_fixed_syr2k
he_polybench_fixed_trmm
he_polybench_floyd-warshall
he_polybench_gemver
he_polybench_jacobi-2d
he_polybench_nussinov
he_polybench_seidel-2d
he_rosetta_optical_flow__outer_product
he_rosetta_spam_filter__computeGradient
""".split()
print(f"{'task':<42} {'round':<6} {'rc':<4} failure")
for name in names:
    trace = root / name / "s0" / "trace.jsonl"
    rows = [json.loads(line) for line in trace.read_text().splitlines() if line.strip()]
    cs = [row for row in rows if row.get("tool") == "csynth"]
    if not cs:
        print(f"{name:<42} no csynth")
        continue
    for row in cs:
        print(f"{name:<42} {row.get('round')!s:<6} {row.get('rc')!s:<4} {row.get('failure')}")
PY
