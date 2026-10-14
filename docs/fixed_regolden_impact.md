# Coder390 解在修正金标后的重新测量

同一批 `selftest/out/coder390/{agent,baseline}/*/s0/solution.cpp`，
用当前题目目录里的 `tb_data_hls.txt` 覆盖（见 `docs/fixed_golden_evidence.md`）
再跑官方 `selftest/judge.py`。没有重新生成任何解，没有调用模型。

旧结果备份在 `selftest/out/coder390/results.old_golden/`。
97 道非 `he_polybench_fixed_*` 的 json 未改动（SHA-256 与备份一致）。

判定命令未传 `--rel-tol` / `--abs-tol`。`--timeout 1800` 未调高。

## 1. 这不是能力提升

下表里的 pass@1、能力分、增益，都是**同一批解**在两种测量口径下的数字。
agent / baseline 的 `solution.cpp` 字节未变。口径变了（25 道定点题的
HLS 金标从 float 版 `tb_data.txt` 换成参考解 csim 输出），所以档位变了。
不要把差值读成「agent 变强了」或「分数提高了」。

## 2. 新旧聚合（125 题）

来源：`selftest/out/coder390/score.old_golden.json` 与
`selftest/out/coder390/score.json`（`selftest/score.py` 默认满分线 2.5）。

| | 旧金标 | 修正金标后 |
| --- | ---: | ---: |
| agent pass@1 | 0.6248 | 0.6760 |
| baseline pass@1 | 0.5740 | 0.6066 |
| 能力分 30×pass@1 | 18.74 | 20.28 |
| 增益倍数 agent/baseline | 1.0885 | 1.1144 |
| 增益分 40×log(gain)/log(2.5) | 3.70 | 4.73 |
| 能力+增益合计 | 22.44 | 25.01 |

agent 分级：旧 L1=5 / L2=53 / L4=67 → 新 L1=5 / L2=45 / L4=75（+8 道 L4）。
这 +8 道全部来自下方 25 道补过 `tb_data_hls.txt` 的题，原金标下它们是 L2。

baseline 侧 `score.py` 把带 `tool_error` 的样本排除出平均：

- 旧：排除 floyd-warshall、`he_rosetta_optical_flow__outer_product`（均为判定超时），123/125 计分。
- 新：上述两题加上 `he_polybench_fixed_gesummv`（判定超时 >1800s），122/125 计分。

`he_polybench_fixed_gesummv` 的 baseline 解在独占 Vitis 下 csynth 仍超过 1800s。
按任务要求未调超时。该题从旧口径的 L2（计分）变成环境失败（不计分）。

## 3. 56 次重判逐题结果

未补金标的三题（floyd-warshall / heat-3d / nussinov）也重判了，档位与旧结果相同。

| task_id | mode | 旧档位 | 新档位 | 新 note |
| --- | --- | --- | --- | --- |
| he_polybench_fixed_2mm | agent | L2 | L2 | 3200/3200 个数值超出容差 |
| he_polybench_fixed_2mm | baseline | L2 | L2 | 3200/3200 个数值超出容差 |
| he_polybench_fixed_3mm | agent | L2 | L4 | （空） |
| he_polybench_fixed_3mm | baseline | L2 | L2 | 2800/2800 个数值超出容差 |
| he_polybench_fixed_atax | agent | L2 | L4 | （空） |
| he_polybench_fixed_atax | baseline | L2 | L4 | （空） |
| he_polybench_fixed_bicg | agent | L2 | L4 | （空） |
| he_polybench_fixed_bicg | baseline | L2 | L3 | ERROR: [HLS 200-1715] Encountered problem during source synthesis |
| he_polybench_fixed_cholesky | agent | L2 | L2 | 5123/7260 个数值超出容差 |
| he_polybench_fixed_cholesky | baseline | L2 | L2 | 5123/7260 个数值超出容差 |
| he_polybench_fixed_correlation | agent | L2 | L2 | 测试台返回非零退出码 -8 |
| he_polybench_fixed_correlation | baseline | L2 | L2 | 6400/6400 个数值超出容差 |
| he_polybench_fixed_covariance | agent | L2 | L4 | （空） |
| he_polybench_fixed_covariance | baseline | L2 | L4 | （空） |
| he_polybench_fixed_doitgen | agent | L2 | L2 | 14911/15000 个数值超出容差 |
| he_polybench_fixed_doitgen | baseline | L2 | L2 | 14500/15000 个数值超出容差 |
| he_polybench_fixed_durbin | agent | L1 | L1 | 待测源码可解析，但未能与测试台编译出 csim.exe |
| he_polybench_fixed_durbin | baseline | L0 | L0 | （空解，0 字节） |
| he_polybench_fixed_fdtd-2d | agent | L2 | L2 | 14240/14400 个数值超出容差 |
| he_polybench_fixed_fdtd-2d | baseline | L2 | L2 | 14400/14400 个数值超出容差 |
| he_polybench_fixed_floyd-warshall | agent | L4 | L4 | （空） |
| he_polybench_fixed_floyd-warshall | baseline | L0 | L0 | 判定超时（>1800s） |
| he_polybench_fixed_gemm | agent | L2 | L2 | 3973/4200 个数值超出容差 |
| he_polybench_fixed_gemm | baseline | L2 | L2 | 4200/4200 个数值超出容差 |
| he_polybench_fixed_gemver | agent | L2 | L2 | 120/120 个数值超出容差 |
| he_polybench_fixed_gemver | baseline | L2 | L2 | 120/120 个数值超出容差 |
| he_polybench_fixed_gesummv | agent | L2 | L4 | （空） |
| he_polybench_fixed_gesummv | baseline | L2 | L0 | 判定超时（>1800s） |
| he_polybench_fixed_gramschmidt | agent | L2 | L2 | 测试台返回非零退出码 -8 |
| he_polybench_fixed_gramschmidt | baseline | L2 | L2 | 测试台返回非零退出码 -8 |
| he_polybench_fixed_heat-3d | agent | L4 | L4 | （空） |
| he_polybench_fixed_heat-3d | baseline | L1 | L1 | 待测源码可解析，但未能与测试台编译出 csim.exe |
| he_polybench_fixed_jacobi-1d | agent | L2 | L2 | 118/120 个数值超出容差 |
| he_polybench_fixed_jacobi-1d | baseline | L2 | L2 | 118/120 个数值超出容差 |
| he_polybench_fixed_jacobi-2d | agent | L2 | L2 | 7743/8100 个数值超出容差 |
| he_polybench_fixed_jacobi-2d | baseline | L2 | L2 | 7743/8100 个数值超出容差 |
| he_polybench_fixed_lu | agent | L2 | L4 | （空） |
| he_polybench_fixed_lu | baseline | L2 | L2 | 14042/14400 个数值超出容差 |
| he_polybench_fixed_ludcmp | agent | L2 | L4 | （空） |
| he_polybench_fixed_ludcmp | baseline | L2 | L4 | （空） |
| he_polybench_fixed_mvt | agent | L2 | L4 | （空） |
| he_polybench_fixed_mvt | baseline | L2 | L3 | ERROR: [HLS 200-1715] Encountered problem during source synthesis |
| he_polybench_fixed_nussinov | agent | L2 | L2 | 16021/16290 个数值超出容差 |
| he_polybench_fixed_nussinov | baseline | L2 | L2 | 15664/16290 个数值超出容差 |
| he_polybench_fixed_seidel-2d | agent | L2 | L2 | 13801/14400 个数值超出容差 |
| he_polybench_fixed_seidel-2d | baseline | L2 | L2 | 13924/14400 个数值超出容差 |
| he_polybench_fixed_symm | agent | L2 | L2 | 4719/4800 个数值超出容差 |
| he_polybench_fixed_symm | baseline | L2 | L2 | 4800/4800 个数值超出容差 |
| he_polybench_fixed_syr2k | agent | L2 | L2 | 84/6400 个数值超出容差 |
| he_polybench_fixed_syr2k | baseline | L2 | L2 | 3237/6400 个数值超出容差 |
| he_polybench_fixed_syrk | agent | L2 | L2 | 3240/6400 个数值超出容差 |
| he_polybench_fixed_syrk | baseline | L2 | L2 | 3240/6400 个数值超出容差 |
| he_polybench_fixed_trisolv | agent | L2 | L2 | 93/120 个数值超出容差 |
| he_polybench_fixed_trisolv | baseline | L2 | L2 | 93/120 个数值超出容差 |
| he_polybench_fixed_trmm | agent | L2 | L2 | 4719/4800 个数值超出容差 |
| he_polybench_fixed_trmm | baseline | L2 | L2 | 4800/4800 个数值超出容差 |

baseline `he_polybench_fixed_durbin` 的 `solution.cpp` 是 0 字节。任务书写「两侧均非空」，
实测 baseline 侧为空；按判定器规则记 L0，未补生成。

## 4. agent 在定点题上的档位

补过 `tb_data_hls.txt` 的 **25 道**（不含 floyd-warshall / heat-3d / nussinov）：

| 档位 | 题数 | 题 |
| --- | ---: | --- |
| L4 | 8 | 3mm, atax, bicg, covariance, gesummv, lu, ludcmp, mvt |
| L2 | 16 | 2mm, cholesky, correlation, doitgen, fdtd-2d, gemm, gemver, gramschmidt, jacobi-1d, jacobi-2d, seidel-2d, symm, syr2k, syrk, trisolv, trmm |
| L1 | 1 | durbin |
| L3 | 0 | — |

28 道全套：L4=10（上表 8 道加上本就 L4 的 floyd-warshall、heat-3d），L2=17（含 nussinov），L1=1。
agent 达到 L3/L4 的定点题：**10/28**，其中 overlay 25 道里 **8/25**。

两侧比较（28 道，按档位数字，超时/空解记 L0）：

- agent 优于 baseline（8）：3mm（4>2）、bicg（4>3）、durbin（1>0）、floyd-warshall（4>0）、gesummv（4>0）、heat-3d（4>1）、lu（4>2）、mvt（4>3）
- agent 劣于 baseline：无
- 持平：20

## 5. 对「要不要定点 skill」的含义

不是「几乎全部仍停在 L2」，也不是「定点已经够用」。

8/25 在换成参考解 csim 金标之后达到 L4，说明这些解的定点数值已经与题目参考实现一致，
模型并不是写不出可过 HLS 金标的 `ap_fixed` 核。

另外 16/25 仍然停在 L2：多数是相对新金标的逐值超差，correlation / gramschmidt 是测试台非零退出。
nussinov 的 `tb_data.txt` 对参考解本来就是对的，agent 仍为 L2，属于实现问题。

结论：一部分 kernel 上现有定点能力已经够用；其余 kernel 上数值仍对不齐，定点 skill 仍有明确补强对象。
本文件不建议把 8 道 L4 外推成「定点题已解决」。

## 6. 过程备忘

- `he_polybench_fixed_floyd-warshall` baseline 再次判定超时（>1800s），与旧结果相同。
- 该次超时后 Vitis 子进程未随 `hls-judge` 退出。`bicg` / `gesummv` / `mvt` 的 baseline 曾与残留 csynth 重叠，随后在 Vitis 空闲时各重判一次；表中是重判结果。独占条件下：gesummv 仍超时 1800s，bicg 与 mvt 仍为 L3（HLS 200-1715）。
- 未改判定器、容差、题目文件、任何 `solution.cpp` / `trace.jsonl`。
