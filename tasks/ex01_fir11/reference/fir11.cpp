// Reference solution for ex01_fir11.
//
// Only purpose: proving the judging pipeline reaches L4 on a known-good input.
// Do not feed it to your agent -- a self-test that passes because the answer was
// in the prompt measures nothing.

#include "fir11.h"

void fir11(const data_t x[N_SAMPLES], data_t y[N_SAMPLES]) {
#pragma HLS INTERFACE mode = ap_memory port = x
#pragma HLS INTERFACE mode = ap_memory port = y

    data_t shift[N_TAPS];
#pragma HLS ARRAY_PARTITION variable = shift complete dim = 1

    for (int i = 0; i < N_TAPS; ++i) {
#pragma HLS UNROLL
        shift[i] = 0;
    }

SAMPLE_LOOP:
    for (int n = 0; n < N_SAMPLES; ++n) {
#pragma HLS PIPELINE II = 1
        for (int k = N_TAPS - 1; k > 0; --k) {
#pragma HLS UNROLL
            shift[k] = shift[k - 1];
        }
        shift[0] = x[n];

        acc_t acc = 0;
    TAP_LOOP:
        for (int k = 0; k < N_TAPS; ++k) {
#pragma HLS UNROLL
            acc += (acc_t)FIR_COEF[k] * (acc_t)shift[k];
        }
        y[n] = (data_t)acc;
    }
}
