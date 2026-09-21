// Official testbench for ex03_matmul.
//
// Values are large enough that a kernel accumulating in int16_t overflows and
// fails, which is the point of stating the accumulator width in the task.

#include <cstdio>
#include "matmul.h"

int main() {
    static data_t a[DIM_M][DIM_K];
    static data_t b[DIM_K][DIM_N];
    static acc_t c_dut[DIM_M][DIM_N];
    static acc_t c_ref[DIM_M][DIM_N];

    unsigned seed = 24680u;
    for (int i = 0; i < DIM_M; ++i)
        for (int k = 0; k < DIM_K; ++k) {
            seed = seed * 1103515245u + 12345u;
            a[i][k] = (data_t)((int)((seed >> 16) & 0x3FF) - 512);
        }
    for (int k = 0; k < DIM_K; ++k)
        for (int j = 0; j < DIM_N; ++j) {
            seed = seed * 1103515245u + 12345u;
            b[k][j] = (data_t)((int)((seed >> 16) & 0x3FF) - 512);
        }

    for (int i = 0; i < DIM_M; ++i)
        for (int j = 0; j < DIM_N; ++j) {
            acc_t acc = 0;
            for (int k = 0; k < DIM_K; ++k)
                acc += (acc_t)a[i][k] * (acc_t)b[k][j];
            c_ref[i][j] = acc;
            c_dut[i][j] = (acc_t)0x5A5A5A5A;   // garbage: c must be fully written
        }

    matmul(a, b, c_dut);

    int errors = 0;
    for (int i = 0; i < DIM_M; ++i)
        for (int j = 0; j < DIM_N; ++j)
            if (c_dut[i][j] != c_ref[i][j]) {
                if (errors < 10) {
                    std::printf("MISMATCH at (%2d,%2d): got %d, expected %d\n",
                                i, j, (int)c_dut[i][j], (int)c_ref[i][j]);
                }
                ++errors;
            }

    if (errors) {
        std::printf("FAIL: %d/%d elements differ\n", errors, DIM_M * DIM_N);
        return 1;
    }
    std::printf("PASS: %d/%d elements match\n", DIM_M * DIM_N, DIM_M * DIM_N);
    return 0;
}
