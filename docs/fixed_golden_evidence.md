# Polybench fixed（ap_fixed<32,16>）金标取证

本地测量口径。新增 `tb_data_hls.txt` 只影响本仓库 `selftest/judge.py` 走
`hls-judge` 的 `GOLDEN_NAMES` 优先顺序，**不进入提交物、不改官方判定器、
不改 `tb_data.txt` / 参考解 / 容差**。

判定器：`selftest/judge.py` → `selftest/judge/hls-judge`，默认
`--rel-tol 1e-6 --abs-tol 1e-9`，本次未传入任何容差参数。

## 1. 现象

`tasks/` 中 28 道 `he_polybench_fixed_*`，类型为 `ap_fixed<32,16>`。
此前 agent / baseline 两侧约 25 道稳定停在 L2（可编译，csim 金标比对失败）。

用**题目自带参考解**（`task.json` 的 `reference` 字段）在同一判定器上复现：

- 阶段 1（原 `tb_data.txt`）：**25/28 为 L2**，note 均为「N/M 个数值超出容差」；
  **3/28 为 L4**（`floyd-warshall`、`heat-3d`、`nussinov`）。
- 题集 pass@1 = **0.286**（见 `selftest/out/fixed_ref/score.json`）。

参考解过不了题目自带测试台。这不是选手实现错误。

## 2. 根因

这些题的 `tb_data.txt` 由 kernel 的 **float 版本**生成，题目实现却是定点。
`ap_fixed<32,16>` 小数 16 bit，1 LSB = 2⁻¹⁶ ≈ 1.526×10⁻⁵。float 金标里的十进制
字面量多数落在两个可表示定点值之间，默认 1e-6 / 1e-9 容差远小于定点量化误差。

### 2.1 gemm 量化证据（任务说明中已核验的数字）

`he_polybench_fixed_gemm`，4200 个输出，按 `%.6f` 比较：

| 对照 | 与 `tb_data.txt` 匹配 |
| --- | --- |
| float64 计算 | 4200/4200 |
| 题目自带 `reference/gemm.cpp`（ap_fixed） | 0/4200 |

- 最大绝对误差约 **1.67×10⁻³** ≈ **109 LSB**
- 金标中的 `0.020000` 在 Q16 中不可表示；最近两个可表示值为
  `0.019989013671875` 与 `0.0200042724609375`

本次阶段 1 用官方判定器跑同一参考解，note 为 **4197/4200 个数值超出容差**
（3 个点落在默认容差内，与「4200/4200 按 %.6f 全不匹配」的离线统计口径略有差别，
判定结论同为 L2）。

### 2.2 为何不能调容差

正确定点实现相对 float 金标约 **109 LSB**。把标量系数挪出括号、或用更宽中间累加器
的错误实现，与正确定点实现只差 **55–64 LSB**。

任何 ≥109 LSB、能让正确代码通过的容差，都会同时放过这些错误代码。因此禁止改
`--rel-tol` / `--abs-tol`。

正确做法：用参考解自己的 csim 输出作为 HLS 金标（`tb_data_hls.txt`），保留
`tb_data.txt` 不动。`hls-judge` 优先读 `tb_data_hls.txt`。

## 3. 四道金标本来正确的题

任务指定下列四题**不生成**新金标（Q16 可精确表示，或失败原因不是金标）：

| 题 | 阶段 1 参考解档位 | 说明 |
| --- | --- | --- |
| `he_polybench_fixed_floyd-warshall` | **L4** | 金标与定点参考一致，csynth 通过 |
| `he_polybench_fixed_heat-3d` | **L4** | 同上 |
| `he_polybench_fixed_nussinov` | **L4** | 参考解达到 L4。此前 agent 停在 L2 属于实现问题，不是金标 |
| `he_polybench_fixed_correlation` | **L2**（6320/6400 超出容差） | 按任务要求视为算法问题、不覆盖金标。参考解同样 L2 |

与任务背景的差异：背景写 nussinov「与 correlation 相同停在 L2」。本次**参考解**
判定 nussinov 为 L4，说明其 `tb_data.txt` 对参考实现是匹配的。

## 4. 阶段 2 做了什么

对阶段 1 中「金标比对失败且未达 L3/L4」、且不在上述四题中的 **24 题**：

- 从结果 json 的 `work_dir` 读取 `<work_dir>/w/csim_stdout.txt`
- **原字节**复制为 `tasks/<tid>/tb_data_hls.txt`
- 无空文件、无缺 csim 输出；未改格式、未改数值

未生成金标的 4 题目录中没有 `tb_data_hls.txt`。

## 5. 阶段 1 / 阶段 3 完整结果

判定命令（两阶段相同，仅输出目录不同）：

```text
SELFTEST_KEEP_WORK=1 python3 selftest/judge.py \
  --task tasks/$tid \
  --solution tasks/$tid/$ref \
  --outdir <out>/logs --timeout 1800 \
  --json <out>/results/reference.$tid.s0.json
```

| task_id | 阶段1 档位 | 阶段1 note | 是否生成新金标 | 阶段3 档位 |
| --- | --- | --- | --- | --- |
| he_polybench_fixed_2mm | L2 | 3200/3200 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_3mm | L2 | 2800/2800 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_atax | L2 | 124/124 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_bicg | L2 | 239/240 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_cholesky | L2 | 7030/7260 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_correlation | L2 | 6320/6400 个数值超出容差 | 否 | L2 |
| he_polybench_fixed_covariance | L2 | 1992/6400 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_doitgen | L2 | 14500/15000 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_durbin | L2 | 120/120 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_fdtd-2d | L2 | 13598/14400 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_floyd-warshall | L4 | （空） | 否 | L4 |
| he_polybench_fixed_gemm | L2 | 4197/4200 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_gemver | L2 | 120/120 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_gesummv | L2 | 90/90 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_gramschmidt | L2 | 8039/11200 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_heat-3d | L4 | （空） | 否 | L4 |
| he_polybench_fixed_jacobi-1d | L2 | 120/120 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_jacobi-2d | L2 | 7929/8100 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_lu | L2 | 13962/14400 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_ludcmp | L2 | 120/120 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_mvt | L2 | 239/244 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_nussinov | L4 | （空） | 否 | L4 |
| he_polybench_fixed_seidel-2d | L2 | 14092/14400 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_symm | L2 | 4800/4800 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_syr2k | L2 | 6144/6400 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_syrk | L2 | 6285/6400 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_trisolv | L2 | 118/120 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_trmm | L2 | 4784/4800 个数值超出容差 | 是 | L4 |

聚合（`selftest/score.py`，28 题 × 1 样本）：

| | pass@1 | 档位 |
| --- | ---: | --- |
| 阶段 1 `fixed_ref` | **0.286** | L4=3，L2=25 |
| 阶段 3 `fixed_regolden` | **0.971** | L4=27，L2=1 |

原始 json：`selftest/out/fixed_ref/score.json`、
`selftest/out/fixed_regolden/score.json`（目录被 `.gitignore` 忽略，仅本地保留）。

## 6. 阶段 3 未达 L4 的题

**未达到 28/28 L4。** 按任务要求停在此处，等指示。

| task_id | 档位 | note |
| --- | --- | --- |
| `he_polybench_fixed_correlation` | L2 | 6320/6400 个数值超出容差 |

该题按任务要求**未**写入 `tb_data_hls.txt`。参考解与 agent 一样停在金标比对。
若认为应覆盖金标，需要另行指示；当前未做。

其余 27 题参考解在阶段 3 均为 L4（含 csynth）。无 csim 缺失、无判定超时。

## 7. 与任务背景不符的发现

1. **gemm 超出容差计数**：阶段 1 为 4197/4200，不是离线 %.6f 的 4200/4200。
   3 个点落在默认 1e-6/1e-9 内。结论仍是 L2。
2. **nussinov 参考解为 L4**，不是 L2。金标对参考实现成立；agent 历史 L2 应算实现问题。
3. **correlation 参考解为 L2**，与「四道金标正确」中「已达 L4」的预期不完全一致。
   按书面名单未生成新金标，故阶段 3 少 1 道 L4。
4. 阶段 1 在 L2（csim 失败）时判定器**未再跑 csynth**，单题约 10 s；L4 题约 40 s。
   总墙钟远小于「28 道全 csynth」的预估。
5. 若干题超出容差不是 100%（如 covariance 1992/6400、bicg 239/240）。仍全部 L2，
   定点量化误差不是每个输出都超 1e-6。
