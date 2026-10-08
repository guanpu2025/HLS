---
name: hls-array-typedef
description: Repair kernels that use an HLS typedef array as a scalar, struct, or assignable value.
---

# Agent Skill: HLS Array Typedef

## Skill Metadata
- **Name:** `hls_array_typedef`
- **Description:** Repair kernels that use an HLS typedef array as a scalar, struct, or assignable value.
- **Trigger:** Synthesis says an array type is not assignable, a subscript is not an integer, or a binary operator is applied to an array.
- **Log signatures:** `is not assignable`, `array subscript is not an integer`, `is not a structure or union`, `invalid operands to binary expression`, `from incompatible type`, `cannot initialize a variable of type`

## Rule

Read the header. A line like `typedef uint8_t state_t[4][4];` makes `state_t` an array type, not a struct and not an integer. The same applies to `round_t`, `des_block_t`, `block_t`, and `present_key_t` when the header defines them as arrays.

Do not assign, copy, xor, or pass the whole array as one value. Do not use `.member` on it. Index the element.

```cpp
typedef uint8_t state_t[4][4];
void MixColumns(state_t *state);

// wrong
uint8_t x = *state;
*state = tmp;
state->col = 1;

// right
uint8_t x = (*state)[row][col];
(*state)[row][col] = x;
```

Keep the top-level signature unchanged. Repair only the array accesses, then output one ```cpp block.
