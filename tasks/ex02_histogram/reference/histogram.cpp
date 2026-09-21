// Reference solution for ex02_histogram.
//
// Pipeline validation only. Do not feed it to your agent.
//
// The accumulator dependency is broken the standard way: keep the last bin and
// its value in registers, and add 1 or 2 depending on whether this pixel hits
// the same bin as the previous one. Without this, II=1 is not schedulable
// because the read-modify-write of hist[] takes two cycles.

#include "histogram.h"

void histogram(const pix_t in[N_PIX], hist_t hist[N_BINS]) {
#pragma HLS INTERFACE mode = ap_memory port = in
#pragma HLS INTERFACE mode = ap_memory port = hist

CLEAR_LOOP:
    for (int b = 0; b < N_BINS; ++b) {
#pragma HLS PIPELINE II = 1
        hist[b] = 0;
    }

    pix_t prev_bin = 0;
    hist_t prev_val = 0;
    bool have_prev = false;

ACC_LOOP:
    for (int i = 0; i < N_PIX; ++i) {
#pragma HLS PIPELINE II = 1
#pragma HLS DEPENDENCE variable = hist inter false
        pix_t bin = in[i];
        hist_t val;
        if (have_prev && bin == prev_bin) {
            val = prev_val + 1;
        } else {
            val = hist[bin] + 1;
        }
        hist[bin] = val;
        prev_bin = bin;
        prev_val = val;
        have_prev = true;
    }
}
