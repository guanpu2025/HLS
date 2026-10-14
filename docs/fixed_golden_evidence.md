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

### 2.1 gemm 量化证据

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

### 2.3 超差比例并非都是 100%

阶段 1 里，若干题超出容差的点数不是全部输出：

| 题 | 超出容差 |
| --- | --- |
| `he_polybench_fixed_covariance` | 1992/6400 |
| `he_polybench_fixed_bicg` | 239/240 |
| `he_polybench_fixed_gemm` | 4197/4200 |
| `he_polybench_fixed_mvt` | 239/244 |
| `he_polybench_fixed_trisolv` | 118/120 |

同时也有整表超差的题（如 `2mm` 3200/3200、`symm` 4800/4800）。
这说明缺陷是**逐值的定点量化失配**：部分输出恰好落在默认 1e-6 / 1e-9 内，
部分超出。不是算法整体跑偏到另一套结果。

## 3. 三道金标本来正确的题

下列三题**不生成**新金标。阶段 1 参考解已达 L4，`tb_data.txt` 与定点参考一致。

| 题 | 阶段 1 参考解档位 | 说明 |
| --- | --- | --- |
| `he_polybench_fixed_floyd-warshall` | **L4** | 金标与定点参考一致，csynth 通过 |
| `he_polybench_fixed_heat-3d` | **L4** | 同上 |
| `he_polybench_fixed_nussinov` | **L4** | 参考解达到 L4。此前 agent 停在 L2 属于实现问题，不是金标 |

`nussinov` 的排除是必要的：参考解已经通过原金标，覆盖 `tb_data_hls.txt` 没有依据。

### 3.1 correlation：Q16 可表示性不足以判断金标是否正确

`he_polybench_fixed_correlation` 曾被列进「金标本来正确、不要生成新金标」的名单。
该判断不成立，依据如下。

原 `tb_data.txt` 中 6400 个数值**全部是** `1.000000`（另有 DUMP_ARRAYS 标记）。
1.0 在 Q16 中可精确表示。polybench 的初始化让每一列都是同一向量的标量倍，
float 下相关系数恰好处处为 1。

定点量化破坏了列之间的严格正比关系。题目自带 `reference/correlation.cpp`
（`ap_fixed<32,16>`）的 csim 输出不再处处为 1.0，官方判定器 note 为
**6320/6400 个数值超出容差**，档位 **L2**。

因此「金标字面量可被 Q16 表示」不能推出「定点实现应与该金标一致」。
它与其余 24 道是同一个缺陷（float 金标 vs 定点实现），按同一机制覆盖。

## 4. 阶段 2 做了什么

对阶段 1 中「金标比对失败且未达 L3/L4」、且不在第 3 节三题中的 **25 题**
（含 `correlation`）：

- 从结果 json 的 `work_dir` 读取 `<work_dir>/w/csim_stdout.txt`
- **原字节**复制为 `tasks/<tid>/tb_data_hls.txt`
- 无空文件、无缺 csim 输出；未改格式、未改数值

未生成金标的 3 题目录中没有 `tb_data_hls.txt`。

### 4.1 float 套件对照（数据集原状）

在覆盖金标之前的提交 `82b1f38` 上清点：

| 套件 | `tb_data.txt` | `tb_data_hls.txt` | 两者字节相同 |
| --- | ---: | ---: | --- |
| `he_polybench_*`（非 fixed） | 28 | 28 | 28/28 |
| `he_polybench_fixed_*` | 28 | **0** | — |

28 道 float 版 polybench 本来就带 `tb_data_hls.txt`，且与各自 `tb_data.txt`
字节相同。fixed 套件当时一个都没有。以上只陈述文件事实，不推断数据集作者意图。

## 5. 阶段 1 / 阶段 3 完整结果

判定命令（两阶段相同，仅输出目录不同）：

```text
SELFTEST_KEEP_WORK=1 python3 selftest/judge.py \
  --task tasks/$tid \
  --solution tasks/$tid/$ref \
  --outdir <out>/logs --timeout 1800 \
  --json <out>/results/reference.$tid.s0.json
```

未向判定器传入 `--rel-tol` / `--abs-tol`。

| task_id | 阶段1 档位 | 阶段1 note | 是否生成新金标 | 阶段3 档位 |
| --- | --- | --- | --- | --- |
| he_polybench_fixed_2mm | L2 | 3200/3200 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_3mm | L2 | 2800/2800 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_atax | L2 | 124/124 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_bicg | L2 | 239/240 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_cholesky | L2 | 7030/7260 个数值超出容差 | 是 | L4 |
| he_polybench_fixed_correlation | L2 | 6320/6400 个数值超出容差 | 是 | L4 |
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
| 阶段 3 `fixed_regolden` | **1.000** | L4=28 |

原始 json：`selftest/out/fixed_ref/score.json`、
`selftest/out/fixed_regolden/score.json`（目录被 `.gitignore` 忽略，仅本地保留）。

## 6. 阶段 3 结论

**28/28 全部达到 L4**（含 csynth）。无 csim 缺失、无判定超时、无未覆盖却仍失败的题。

`he_polybench_fixed_correlation` 在写入 `tb_data_hls.txt` 后重跑：档位 L4，
耗时 50 s，`parse/compile/run/synth` 全过。

未覆盖金标的三题（`floyd-warshall`、`heat-3d`、`nussinov`）阶段 1 与阶段 3
均为 L4。

## 7. 与最初任务背景不符的发现

1. **gemm 超出容差计数**：阶段 1 为 4197/4200，不是离线 %.6f 的 4200/4200。
   3 个点落在默认 1e-6/1e-9 内。结论仍是 L2。
2. **nussinov 参考解为 L4**，不是 L2。金标对参考实现成立；agent 历史 L2 应算实现问题。
3. **correlation 参考解为 L2**。原名单把它与 floyd-warshall / heat-3d / nussinov
   一并排除，是因为 1.0 可被 Q16 表示；见第 3.1 节，该理由不充分，已按同一缺陷覆盖。
4. 阶段 1 在 L2（csim 失败）时判定器**未再跑 csynth**，单题约 10 s；L4 题约 40–50 s。
   总墙钟远小于「28 道全 csynth」的预估。
5. 若干题超出容差不是 100%，见第 2.3 节。
