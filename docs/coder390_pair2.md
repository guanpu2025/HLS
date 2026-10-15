# Coder390 pair2（新 harness 新解）

来源：`selftest/out/coder390_pair2/score.json`（`scripts/run_coder390_pair.sh` 跑完后由 `selftest/score.py` 写出）。
同一模型 Coder390-Q6_K、同一轮 baseline + agent，125 题。未把本轮 agent 和 `selftest/out/coder390/` 的旧 baseline 混算。

这是新 harness 重新生成的解，不是对 `selftest/out/coder390/` 同一批 `solution.cpp` 的重判。

## 题集得分

| | pass@1 | 计分题数 | 排除的 tool_error |
| --- | ---: | ---: | --- |
| agent | 0.6896 | 125 / 125 | 无 |
| baseline | 0.6057 | 122 / 125 | `he_polybench_fixed_floyd-warshall`、`he_polybench_fixed_gesummv`、`he_rosetta_optical_flow__outer_product`（均为判定超时 >1800s） |

agent 分级：L1=4 / L2=44 / L4=77。

## 能力与增益

满分线倍数 2.5（`score.py` 默认，与 25.01 那次相同）。

- 能力分 30 × 0.6896 = **20.69**
- 增益倍数 0.6896 / 0.6057 = **1.1385**
- 增益分 40 × log(1.1385) / log(2.5) = **5.66**
- 能力 + 增益 = **26.35**

相对 25.01（旧解在修正金标下重判：agent 0.6760 / baseline 0.6066 / 能力 20.28 / 增益 1.1144 / 增益分 4.73 / 122 题计分）差 **+1.34**。

## agent 档位低于本轮 baseline

note 取自本轮 agent 的 `results/agent.*.s0.json`。

| task_id | agent | baseline | note |
| --- | --- | --- | --- |
| he_chstone_df_float64_is_signaling_nan | L2 | L4 | 测试台返回非零退出码 1 |
| he_machsuite_bfs_bulk | L2 | L4 | 测试台返回非零退出码 -6 |
| he_polybench_correlation | L2 | L4 | 784/784 个数值超出容差 |
| he_polybench_fixed_seidel-2d | L1 | L2 | 待测源码可解析，但未能与测试台编译出 csim.exe |
| he_polybench_gemver | L2 | L4 | 40/40 个数值超出容差 |
| he_polybench_gramschmidt | L2 | L4 | 833/1500 个数值超出容差 |

## continue 轮 tokens_in ≥ 8000

扫描 `selftest/out/coder390_pair2/agent/*/s0/trace.jsonl`：continue 事件 6 次（des、overlapping、dfmul×2、fixed_durbin×2）；所有 LLM 轮 `tokens_in` 最大值 6445，**没有** ≥8000 的题。
