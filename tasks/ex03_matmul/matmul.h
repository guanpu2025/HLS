#ifndef MATMUL_H
#define MATMUL_H

#include <stdint.h>

#define DIM_M 16
#define DIM_K 16
#define DIM_N 16

typedef int16_t data_t;
typedef int32_t acc_t;

void matmul(const data_t a[DIM_M][DIM_K],
            const data_t b[DIM_K][DIM_N],
            acc_t c[DIM_M][DIM_N]);

#endif  // MATMUL_H
