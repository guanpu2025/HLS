---
name: hls-ieee-softfloat-nan
description: Repair IEEE-754 bit-level NaN and compare helpers so Inf is not classified as NaN.
---

# Agent Skill: IEEE Soft-Float NaN

## Skill Metadata
- **Name:** `hls_ieee_softfloat_nan`
- **Description:** Repair IEEE-754 bit-level NaN and compare helpers so Inf is not classified as NaN.
- **Trigger:** Self-check mismatch on a 64-bit pattern that looks like Inf or NaN (`0x7ff...`).
- **Log signatures:** `0x7ff0000000000000`, `0x7ff8000000000000`, `0xfff0000000000000`, `float64`

## Rule

A `float64` is NaN iff the exponent is all ones **and** the fraction is nonzero. Inf has exponent all ones and fraction zero.

After `bits << 1` (sign bit shifted out):

- Inf becomes `0xFFE0000000000000`
- NaN is strictly greater than `0xFFE0000000000000`

```cpp
// wrong: treats Inf as NaN
flag = ((a << 1) > 0x7FF0000000000000ULL);

// right (Berkeley softfloat / polybench-style)
flag = (0xFFE0000000000000ULL < (bits64)(a << 1));
```

Quiet vs signaling NaN is the fraction MSB after the exponent, not the Inf pattern.

## Evidence

Vitis HLS 2025.2, host self-check filling 64-bit integers with Inf/NaN bit patterns, then official `hls-judge` csim.

- `he_chstone_df_float64_is_nan`: first-round `a=0x7ff0000000000000` (Inf) gave `dut=1 ref=0`. After using the `0xFFE...` test, official level went L2 to L4 in 14 s.
- Filling integers with `0..15` instead of Inf/NaN patterns made this helper pass the host check and fail the official testbench.

## Behavioral Constraints

Keep the top signature. Do not switch the kernel to `double` arithmetic if the interface is integer bit patterns.
