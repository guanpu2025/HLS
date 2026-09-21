#ifndef HISTOGRAM_H
#define HISTOGRAM_H

#include <stdint.h>

#define N_PIX 1024
#define N_BINS 256

typedef uint8_t pix_t;
typedef uint32_t hist_t;

void histogram(const pix_t in[N_PIX], hist_t hist[N_BINS]);

#endif  // HISTOGRAM_H
