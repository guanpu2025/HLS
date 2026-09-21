// Official testbench for ex01_fir11.
//
// NOT handed to the agent -- this is what decides L3. Returns 0 on pass,
// nonzero on failure, which is what csim_design keys on.

#include <cstdio>
#include "fir11.h"

static void golden(const data_t x[N_SAMPLES], data_t y[N_SAMPLES]) {
    for (int n = 0; n < N_SAMPLES; ++n) {
        acc_t acc = 0;
        for (int k = 0; k < N_TAPS; ++k) {
            int idx = n - k;
            if (idx >= 0) acc += (acc_t)FIR_COEF[k] * (acc_t)x[idx];
        }
        y[n] = (data_t)acc;
    }
}

int main() {
    data_t x[N_SAMPLES];
    data_t y_dut[N_SAMPLES];
    data_t y_ref[N_SAMPLES];

    // Deterministic stimulus: an impulse, a step and a pseudo-random tail, so a
    // kernel that only handles the steady state still fails.
    for (int i = 0; i < N_SAMPLES; ++i) x[i] = 0;
    x[0] = 1000;
    for (int i = 8; i < 20; ++i) x[i] = 500;
    unsigned seed = 12345u;
    for (int i = 20; i < N_SAMPLES; ++i) {
        seed = seed * 1103515245u + 12345u;
        x[i] = (data_t)((int)((seed >> 16) & 0x7FF) - 1024);
    }

    for (int i = 0; i < N_SAMPLES; ++i) y_dut[i] = 0;
    golden(x, y_ref);
    fir11(x, y_dut);

    int errors = 0;
    for (int i = 0; i < N_SAMPLES; ++i) {
        if (y_dut[i] != y_ref[i]) {
            if (errors < 10) {
                std::printf("MISMATCH at %2d: got %d, expected %d\n",
                            i, (int)y_dut[i], (int)y_ref[i]);
            }
            ++errors;
        }
    }

    if (errors) {
        std::printf("FAIL: %d/%d samples differ\n", errors, N_SAMPLES);
        return 1;
    }
    std::printf("PASS: %d/%d samples match\n", N_SAMPLES, N_SAMPLES);
    return 0;
}
