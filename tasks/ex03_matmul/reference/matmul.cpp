// Reference solution for ex03_matmul.
//
// Pipeline validation only. Do not feed it to your agent.

#include "matmul.h"

void matmul(const data_t a[DIM_M][DIM_K],
            const data_t b[DIM_K][DIM_N],
            acc_t c[DIM_M][DIM_N]) {
#pragma HLS INTERFACE mode = ap_memory port = a
#pragma HLS INTERFACE mode = ap_memory port = b
#pragma HLS INTERFACE mode = ap_memory port = c

#pragma HLS ARRAY_PARTITION variable = a complete dim = 2
#pragma HLS ARRAY_PARTITION variable = b complete dim = 1

ROW_LOOP:
    for (int i = 0; i < DIM_M; ++i) {
    COL_LOOP:
        for (int j = 0; j < DIM_N; ++j) {
#pragma HLS PIPELINE II = 1
            acc_t acc = 0;
        MAC_LOOP:
            for (int k = 0; k < DIM_K; ++k) {
#pragma HLS UNROLL
                acc += (acc_t)a[i][k] * (acc_t)b[k][j];
            }
            c[i][j] = acc;
        }
    }
}
