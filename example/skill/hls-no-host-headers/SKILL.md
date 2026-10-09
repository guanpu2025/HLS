---
name: hls-no-host-headers
description: Remove host C headers and library calls that Vitis HLS cannot synthesize.
---

# Agent Skill: No Host Headers

## Skill Metadata
- **Name:** `hls_no_host_headers`
- **Description:** Remove host C headers and library calls that Vitis HLS cannot synthesize.
- **Trigger:** Synthesis fails on size_t, FILE, sqrt, printf, or an ap_ header the task did not provide.
- **Log signatures:** `struct_FILE.h`, `unknown type name 'size_t'`, `undeclared identifier 'sqrt'`, `ap_decl.h`

## Rule

Include only the header named in the interface. Do not include `<stdio.h>`, `<cstdio>`, `<stdlib.h>`, `<cstdlib>`, `<math.h>`, `<cmath>`, `<ap_int.h>`, or `<hls_math.h>` unless that exact include is already in the task header.

Delete the calls that need those headers: `printf`, `malloc`, `free`, `FILE`, and `sqrt`. Compare squared distances instead of calling `sqrt`. Use the integer types from the task header, not `size_t`.

```cpp
// wrong
#include <stdio.h>
#include <cmath>
FILE *f;
float d = sqrt(dx * dx + dy * dy);

// right
#include "md_grid.h"
float d2 = dx * dx + dy * dy;
```

Keep the top-level signature. Output one ```cpp block.
