---
name: hls-csynth-timeout-partition
description: When csynth times out, delete ARRAY_PARTITION complete and UNROLL on large arrays. Keep the algorithm.
---

# Agent Skill: Csynth Timeout Partition Strip

## Skill Metadata
- **Name:** `hls_csynth_timeout_partition`
- **Description:** When csynth times out, delete ARRAY_PARTITION complete and UNROLL on large arrays. Keep the algorithm.
- **Trigger:** The log says `csynth timed out`, or the previous round used the whole leftover deadline on one csynth.
- **Log signatures:** `csynth timed out`, `timed out after`

## Steps

1. Delete every `#pragma HLS ARRAY_PARTITION ... complete`.
2. Delete `#pragma HLS UNROLL` on loops whose trip count is greater than 16.
3. Move any `#pragma HLS PIPELINE` to the innermost loop only.
4. Do not change the math, the top signature, or array extents.
5. Output the full file.

A kernel that already matches the reference will usually reach L4 once csynth finishes. Timeout is a budget failure, not a numeric one.

## Evidence

Vitis HLS 2025.2, `xczu3eg-sbva484-1-e`, 5 ns, official `hls-judge`.

- Original full run: `he_polybench_fixed_floyd-warshall` and `heat-3d` were L3 (csim pass, csynth timeout or error). Later runs with simpler pragmas were L4.
- verify11: six former L3 tasks (`cusums`, `spmv_ellpack`, `stencil3d`, float `floyd-warshall`, `optical_flow__outer_product`, `gemm_ncubed`) all reached L4 after the timeout repair path stripped heavy pragmas. Coefficient +0.2 each.

## Behavioral Constraints

Do not replace the algorithm in a timeout round. Do not add DATAFLOW to "make it faster" after a timeout.
