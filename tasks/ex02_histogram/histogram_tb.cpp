// Official testbench for ex02_histogram.
//
// Deliberately pre-fills hist with garbage: a kernel that assumes the caller
// zeroed it passes a lazy testbench and fails this one.

#include <cstdio>
#include "histogram.h"

int main() {
    pix_t in[N_PIX];
    hist_t hist_dut[N_BINS];
    hist_t hist_ref[N_BINS];

    unsigned seed = 987654321u;
    for (int i = 0; i < N_PIX; ++i) {
        seed = seed * 1103515245u + 12345u;
        in[i] = (pix_t)((seed >> 16) & 0xFF);
    }
    // Force a hot bin so an off-by-one in the accumulator shows up.
    for (int i = 0; i < 64; ++i) in[i] = 42;

    for (int b = 0; b < N_BINS; ++b) hist_ref[b] = 0;
    for (int i = 0; i < N_PIX; ++i) hist_ref[in[i]]++;

    for (int b = 0; b < N_BINS; ++b) hist_dut[b] = 0xDEADBEEFu;
    histogram(in, hist_dut);

    int errors = 0;
    unsigned total = 0;
    for (int b = 0; b < N_BINS; ++b) {
        total += hist_dut[b];
        if (hist_dut[b] != hist_ref[b]) {
            if (errors < 10) {
                std::printf("MISMATCH bin %3d: got %u, expected %u\n",
                            b, (unsigned)hist_dut[b], (unsigned)hist_ref[b]);
            }
            ++errors;
        }
    }

    if (total != (unsigned)N_PIX) {
        std::printf("FAIL: counts sum to %u, expected %d\n", total, N_PIX);
        return 1;
    }
    if (errors) {
        std::printf("FAIL: %d/%d bins differ\n", errors, N_BINS);
        return 1;
    }
    std::printf("PASS: %d/%d bins match, total %u\n", N_BINS, N_BINS, total);
    return 0;
}
