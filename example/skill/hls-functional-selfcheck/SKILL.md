---
name: hls-functional-selfcheck
description: Repair a kernel whose host self-check reports dut versus ref mismatch. Change the update formula, not pragmas.
---

# Agent Skill: Functional Self-Check Repair

## Skill Metadata
- **Name:** `hls_functional_selfcheck`
- **Description:** Repair a kernel whose host self-check reports dut versus ref mismatch. Change the update formula, not pragmas.
- **Trigger:** The log contains `self-check failed` and `dut=` / `ref=` lines. There is no HLS `ERROR:`.
- **Log signatures:** `self-check failed`, `dut=`, `ref=`

## Steps

1. Read `inputs`, then the first `dut=` / `ref=` pair. `ref` is the local reference on the same inputs. Match `ref`.
2. Change the recurrence, loop bounds, or pairing condition that produces that output. Do not retune `#pragma HLS`.
3. Do not fix only the named element. If `tmp` is wrong, the statement that writes every `tmp[i][j]` is wrong.
4. If two rounds print the same `dut` for the same `ref`, the last edit did not touch that value. Rewrite that assignment.
5. Do not emit the previous file unchanged.

## Evidence

Vitis HLS 2025.2, part `xczu3eg-sbva484-1-e`, 5 ns, host g++ self-check vs `reference/*.cpp`.

- `he_polybench_fixed_2mm`: `tmp dut=19.44 ref=29.16` with `alpha=1.5`. The second matrix product must include `alpha` once, not skip it and not apply it twice.
- `he_polybench_fixed_nussinov`: `seq` values in `0..3`, `table dut=0 ref=1` when `seq[i]+seq[j]==3`. ASCII `'A'`/`'T'` pairing fails the official testbench. After the formula change, official level went L2 to L4.
- Repeating the same kernel (`event=identical`) on `fft_strided` never moved `dut`. Temperature 0.5 alone did not help.

## Behavioral Constraints

Do not paste a stored golden dump. Do not add `ARRAY_PARTITION complete` while repairing arithmetic.
