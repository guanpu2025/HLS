---
name: hls-no-complete-partition-large
description: Do not ARRAY_PARTITION complete large 2-D arrays. It times out csynth and does not fix functional errors.
---

# Agent Skill: No Complete Partition on Large Arrays

## Skill Metadata
- **Name:** `hls_no_complete_partition_large`
- **Description:** Do not ARRAY_PARTITION complete large 2-D arrays. It times out csynth and does not fix functional errors.
- **Trigger:** Csynth timeout, or a schedule warning about II with ARRAY_PARTITION on a 2-D array whose extents are tens or more.
- **Log signatures:** `csynth timed out`, `ARRAY_PARTITION`, `Lower bound of II`, `complete dim`

## Rule

`#pragma HLS ARRAY_PARTITION variable=A complete dim=1` on arrays such as 40×50, 60×70, or 180×180 makes the first csynth exceed a 300 s cap. The 360 s task deadline then leaves no repair round.

Use at most:

- `#pragma HLS PIPELINE II=1` on the **innermost** loop
- `ARRAY_PARTITION complete` only on 1-D vectors shorter than about 16, or tiny registers

Do not put PIPELINE immediately before the outermost loop of a 3-level nest. Do not add partition pragmas while repairing `dut=`/`ref=` mismatches. g++ ignores pragmas, so they cannot fix a host self-check.

## Evidence

Vitis HLS 2025.2, `xczu3eg-sbva484-1-e`, 5 ns.

- `he_polybench_fixed_2mm` / `3mm`: `ARRAY_PARTITION complete dim=1` on `tmp`/`E`/`F`/`G` plus outer PIPELINE, csynth 319–326 s, then deadline. One generation only, official L2.
- The same 3mm kernel without those pragmas synthesizes in about 70 s. Official still L2 because the golden file is tighter than `ap_fixed<32,16>` (reference vs `tb_data.txt` is 2800/2800). Partition did not cause the numeric fail; it burned the budget.
- verify11: dropping partition/unroll on former L3 kernels (`stencil3d`, `gemm_ncubed`, `spmv_ellpack`, float `floyd-warshall`) produced official L4.

## Behavioral Constraints

If csynth already timed out, delete complete partition and unroll first. Do not add more pragmas.
