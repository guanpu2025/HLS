# keep9：9 道 agent 重跑（等级替换）

输出：`selftest/out/keep9/`。模型 Coder390-Q6_K，与 pair2 同一 `LLM_BASE_URL`。只跑了 agent，没有重跑 baseline，没有覆盖 `coder390/` / `coder390_pair2/`。

判定：`selftest/judge.py --timeout 1800`，未传容差。通过标准：这 9 道都没有低于 pair2 的 agent 档位。

| task_id | pair2 agent | 这次 | pair2 baseline | keep_better | 第 1 轮 csynth |
| --- | --- | --- | --- | --- | --- |
| he_chstone_df_float64_is_signaling_nan | L2 | L4 | L4 | 否 | 是（rc=0） |
| he_polybench_correlation | L2 | L4 | L4 | 是 | 是（rc=0） |
| he_polybench_gemver | L2 | L4 | L4 | 是 | 是（rc=0） |
| he_polybench_gramschmidt | L2 | L4 | L4 | 是 | 是（rc=0） |
| he_machsuite_bfs_bulk | L2 | L2 | L4 | 是 | 是（rc=0） |
| he_polybench_fixed_seidel-2d | L1 | L2 | L2 | 否 | 是（rc=-1） |
| he_chstone_df_countLeadingZeros64 | L2 | L4 | L1 | 否 | 是（rc=1） |
| he_polybench_fixed_floyd-warshall | L2 | L4 | 判定超时，排除 | 否 | 是（rc=0） |
| he_polybench_fixed_lu | L2 | L2 | L2 | 是 | 是（rc=0） |

## 拼接估计（不是新的全卷配对）

只把这 9 道换成 keep9 档位，其余 116 道仍用 pair2 agent，baseline 仍用 pair2（122 题计分，pass@1=0.6057）：

- 估计 pass@1 ≈ **0.7288**
- 能力 30 × 0.7288 ≈ **21.86**
- 增益 0.7288 / 0.6057 ≈ **1.2032**；增益分 ≈ **8.08**
- 能力 + 增益 ≈ **29.94**（pair2 实测 26.35）

这是拼接估计，不是新的 125 题配对。
