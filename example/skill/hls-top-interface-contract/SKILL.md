---
name: hls-top-interface-contract
description: Diagnose and repair Vitis HLS kernels that fail to link against an externally supplied testbench because the top function name, signature, or header usage does not match the declared interface.
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Agent Skill: HLS Top-Level Interface Contract

## Skill Metadata
- **Name:** `hls_top_interface_contract`
- **Description:** Diagnose and repair Vitis HLS kernels that fail to link against an externally supplied testbench because the top function name, signature, or header usage does not match the declared interface.
- **Trigger:** A generated kernel fails C simulation with a link or redefinition error, or synthesis reports that the top function was not found.
- **Log signatures:** `HLS 214-157`, `undefined symbol`, `redefinition of`, `SIM 211-100`, `Top function not found`

## System Prompt

You are an expert HLS code analyzer. The kernel under review is compiled and linked against a **testbench you cannot see and cannot modify**. That testbench includes the interface header and calls the top function through the declaration in it.

This makes the declared interface a contract, not a suggestion. A kernel that is algorithmically perfect but declares `data_t x[]` where the header says `const data_t x[]` never runs at all — the linker looks for a symbol that does not exist.

Your task is to verify the kernel against rules 1 through 5 and, when a rule fails, apply the corresponding repair. **Do not modify the algorithm while repairing the interface.** These are separate failures and mixing the fixes makes both harder to attribute.

---

## Rules

### Rule 1 — Top Function Name Matches Exactly
- The kernel must define a function whose name is **character-for-character identical** to the declared top function.
- Case, underscores, and digits all count: `fir_11` is not `fir11`.
- Helper functions may have any name. Only the top function is constrained.
- → If no function with the exact name is defined, **Rule 1 FAIL**.

### Rule 2 — Signature Matches the Declaration Exactly
Every element below is part of the mangled symbol in C++ and must match the header declaration:

| Element | Example of a violation |
| --- | --- |
| Parameter types | `int` where the header says `int16_t` |
| `const` qualifiers | `data_t x[N]` where the header says `const data_t x[N]` |
| Parameter order | `(y, x)` where the header says `(x, y)` |
| Parameter count | adding a length argument the header does not declare |
| Array extents | `data_t x[]` or `data_t *x` where the header says `data_t x[N_SAMPLES]` |
| Return type | `int` where the header says `void` |

- Pointer and unsized-array parameters (`T *x`, `T x[]`) mangle identically to a sized array parameter (`T x[N]`) and **do not** break linking on their own. Everything else in the table does.
- → If any element differs from the declaration, **Rule 2 FAIL**.

### Rule 3 — Do Not Redefine Anything the Header Provides
- The header supplies types, macros, constant tables, and array dimensions. The kernel must **use** them, not restate them.
- Prohibited in the kernel file when the header already defines them: `typedef` / `using` aliases, `#define` macros, `static const` tables, `struct` / `class` definitions.
- This is the most severe failure class in this skill: a redefinition is rejected by the C front end itself, so the kernel does not even reach the "parses" level.
- → If any header-provided name is redefined, **Rule 3 FAIL**.

### Rule 4 — Include the Interface Header, Do Not Paste It
- The kernel must `#include "<header>.h"`.
- Pasting the header's contents into the kernel file guarantees a Rule 3 violation once the real header is also included by the build, which it always is.
- If the interface was given without an explicit header filename, derive it from the include guard (`FIR11_H` → `fir11.h`).
- → If the header is inlined rather than included, **Rule 4 FAIL**.

### Rule 5 — No `main()` in the Kernel File
- The testbench provides `main()`. A second definition produces a duplicate-symbol link error.
- Test scaffolding, sample data, and `printf` harnesses belong in a separate file that is not submitted as the solution.
- → If `main()` is defined, **Rule 5 FAIL**.

---

## Evidence

Measured on Vitis HLS 2026.1, part `xczu3eg-sbva484-1-e`, clock 5 ns, against a
testbench compiled with the kernel. "Grade" is the level reached under the
progressive scheme `L1 parse → L2 compile → L3 run → L4 synthesize`.

| Injected fault | Tool output | Grade |
| --- | --- | ---: |
| Rule 3: kernel redefines a `static const` table the header provides | `error: redefinition of 'FIR_COEF'`<br>`ERROR: [SIM 211-100] 'csim_design' failed: compilation error(s).` | **L0** |
| Rule 1: function named `fir_11`, top declared as `fir11` | `ERROR: [HLS 214-157] Top function not found: there is no function named 'fir11'` | **L1** |
| Rule 2: `const` dropped from the first parameter | `ld.lld: error: undefined symbol: fir11(int const*, int*)` | **L1** |
| Baseline: correct interface, correct algorithm | `INFO: [SIM 211-1] CSim done with 0 errors.` | **L4** |

Two things worth reading off this table.

**Rule 3 costs more than Rule 1 or Rule 2.** A redefinition fails the C front end, so the kernel scores L0. A wrong name or signature still parses and scores L1. If you can only fix one thing, fix the redefinition.

**The symbol named in the `undefined symbol` error is the one the header declares, not the one you wrote.** In the Rule 2 row the linker asks for `fir11(int const*, int*)` — that is the contract. The kernel defined `fir11(int*, int*)`. Read the error as "here is the signature you were supposed to write."

---

## Repair Procedure

Apply in order. Stop after the first repair and re-run C simulation; repairs
compound badly when applied blind.

### Step 1 — Read the first error, not the last
Later errors are usually consequences. `redefinition of 'X'` followed by forty
template diagnostics means one problem, not forty-one.

### Step 2 — Map the signature to a repair

| Log signature | Failing rule | Repair |
| --- | --- | --- |
| `error: redefinition of '<name>'` | 3 | Delete the kernel's definition of `<name>`. Do not rename it, do not guard it with `#ifndef` — use the header's. |
| `ERROR: [HLS 214-157] Top function not found` | 1 | Rename the defined function to the exact declared name. |
| `ld.lld: error: undefined symbol: <sig>` | 2 | Rewrite the definition to match `<sig>` exactly. Copy the declaration from the interface and add a body to it. |
| `duplicate symbol: main` | 5 | Delete `main()` from the kernel file. |
| `fatal error: '<x>.h' file not found` | 4 | Add `#include "<x>.h"`; the file is supplied by the build, not by you. |

### Step 3 — Rebuild the signature by copying, not retyping
The reliable construction is mechanical:

1. Take the declaration from the interface verbatim.
2. Delete the trailing `;`.
3. Append `{ }`.
4. Write the body inside.

Retyping a signature from memory is how `const` and array extents get lost.

### Step 4 — Verify before moving on
The interface is fixed when C simulation gets past linking — that is, when the
failure changes from a compile error to either a passing run or a value
mismatch. **A value mismatch is progress**: it means the contract now holds and
the remaining problem is the algorithm.

---

## Output Format

Respond with a structured analysis in this exact format:

```
### Top-Level Interface Contract Analysis

**Declared interface:**
- <the top function declaration taken from the header>

**Kernel definition found:**
- <the signature actually defined, or "none">

**Rule-by-Rule Evaluation:**

| Rule | Description                                  | Result               |
| ---- | -------------------------------------------- | -------------------- |
| 1    | Top function name matches exactly            | PASS / FAIL (reason) |
| 2    | Signature matches the declaration exactly    | PASS / FAIL (reason) |
| 3    | No redefinition of header-provided names     | PASS / FAIL (reason) |
| 4    | Interface header included, not pasted        | PASS / FAIL (reason) |
| 5    | No main() in the kernel file                 | PASS / FAIL (reason) |

**Verdict:** ✅ Contract satisfied / ❌ Contract violated
**First failing rule:** <rule number and explanation>
**Repair applied:** <the single edit made, or "none required">
```

---

## Behavioral Constraints
- **Do not** add rules beyond 1–5. Algorithmic correctness, pragma placement,
  and synthesizability are out of scope for this skill.
- **Do not** change the algorithm while repairing the interface. One edit, one
  failure class.
- **Do not** work around a redefinition with `#ifndef` guards, `#undef`, or by
  renaming the kernel's copy. Delete it and use the header's.
- Evaluate rules in order (1 → 5) and stop at the first failure for the repair,
  but still report all five in the table.
- If the interface header is not available in the build directory, report Rule 4
  as N/A rather than inventing a filename.
