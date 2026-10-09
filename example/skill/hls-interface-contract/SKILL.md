---
name: hls-interface-contract
description: Repair a kernel whose top function name, signature, or header include does not match the declared interface.
---

# Agent Skill: HLS Interface Contract

## Skill Metadata
- **Name:** `hls_interface_contract`
- **Description:** Repair a kernel whose top function name, signature, or header include does not match the declared interface.
- **Trigger:** Synthesis cannot find the top function, or the interface header file is missing.
- **Log signatures:** `Top function not found`, `HLS 214-157`, `file not found`, `redefinition of`

## Rule

The header in the interface section is a contract. Keep helper functions, but the top function must be a separate definition whose name and signature match the header exactly.

```cpp
// header says: void SubBytes(state_t *state);
// wrong: the only function is the helper
uint8_t getSBoxValue(uint8_t num) { ... }

// right
uint8_t getSBoxValue(uint8_t num) { ... }
void SubBytes(state_t *state) { ... }
```

1. Copy the top function name character for character. `getSBoxValue` is not `SubBytes`, and `kernel_2mm` is not `kernel_2mm_`.
2. Copy the parameter types, `const`, order, and array extents from the header.
3. `#include` the header named on the `// header:` line. Do not paste the header into the kernel, and do not redefine its typedefs, macros, or constant tables.
4. Do not define `main`.

Leave the arithmetic alone. Output one ```cpp block.
