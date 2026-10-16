# HLS track 设计报告（填写示范）

> 模型与推理栈数据与 `model/MODEL.md`、`manifest.json` 一致。
> 失败分析与增益表仍需按实测补全（评分细则 2.8）。
>
> 空白模板见仓库根目录的 [REPORT_TEMPLATE.md](../REPORT_TEMPLATE.md)。

| 项目 | 内容 |
| ---- | ---- |
| Track    | HLS             |

---

## 1. 方案总体架构

```
  prompt.txt ─┐
              ├─► 提示词组装 ──► LLM ──► 代码抽取 ──► kernel.cpp
 interface.txt┘        ▲                                  │
                       │                                  ▼
                  技能注入 ◄── 触发词匹配 ◄── 日志压缩 ◄── csynth
                       ▲                                  │
                       └────────── 最多 6 轮 ◄── selfcheck ──┘
                                                          ▼
                                          solution.cpp + trace.jsonl
```

### 1.1 设计依据

工具反馈为 host g++ selfcheck 与 `csynth`。selfcheck 失败的中间轮跳过 csynth；
最后一轮强制 csynth。官方测试台不下发，综合通过不能说明功能正确。

这个判断只在「重生成的成功率不低」时成立。若后续实测发现失败集中在功能错误而非
综合失败，结论会反转。

---

## 2. 模型选择

### 2.1 最终选用

见 [model/MODEL.md](./model/MODEL.md)，本节数据须与之一致。

| 项           | 内容        |
| ------------ | ----------- |
| 模型         | Arkha7/Qwen3.8-27B-Coder390-…（服务别名 `Coder390-Q6_K`） |
| 量化方式     | GGUF Q6_K |
| 实测显存占用 | 21.1 GB（V100S 32GB，`nvidia-smi`） |
| `max_model_len` | 16384    |
| 单次输出上限 | 8192        |
| Hub revision | `d602255311fbdf0852161dc33ccfbecb80e7c7ce` |
| 权重 sha256  | `302597c53d1b00f7230b53a8a050831390a4371e92a80c1ac644fa920af76ab1` |

### 2.2 评估过并放弃的候选

| 候选模型 | 放弃原因 |
| -------- | -------- |
| 同仓库 Q8_0 GGUF | 约 29 GB，32 GB 卡上 KV 过紧 |
| 上游 BF16 / FP8 | 装不进 32 GB + 当前 llama.cpp 栈 |
| Qwen3.8-27B-Q6_K（无 Coder SFT） | 早期配对增益接近 1.0；一发更稳但增益项弱 |

### 2.3 是否微调

本队未额外微调。所用权重为上游已开源的 SFT+RLOO 衍生模型，见 `model/MODEL.md` 第 5 节。

---

## 3. 推理栈

| 项           | 内容               |
| ------------ | ------------------ |
| 推理后端     | llama.cpp llama-server |
| 版本         | 0.6.0-dev commit `781dbc5` |
| 关键启动参数 | 见 `serve/llama.sh` |
| 并发策略     | 每卡一实例，`--parallel 1` |

---

## 4. 智能体设计

### 4.1 控制流

见 `agent/main.py::solve_agent`。每轮：组装提示词 → 调模型 → 抽代码 → host g++ selfcheck
→ csynth。上限 6 轮。`run.sh` 导出 `AGENT_SELF_CHECK=1`、`LLM_MAX_TOKENS=8192`、
`LLM_CTX=16384`。输出被截断（代码块未闭合，或 `tokens_out` 打满本轮上限）时，下一轮只续写尾部，
不把整份残片再贴进上下文。

### 4.2 重试与回退策略

候选按等级保留，只有新候选等级严格更高才替换。同等级留下先出现的那份。

| 等级 | 条件 |
| ---: | --- |
| 3 | selfcheck 通过且 csynth 通过。达到 3 就结束 |
| 2 | csynth 通过。selfcheck 失败或宿主编译被跳过也算 |
| 1 | selfcheck 能编过（rc 为 0 或 1），还没综合成功 |
| 0 | 其余 |

第 1 轮即使 selfcheck 失败也综合。selfcheck 失败时，非最后一轮可以不做 csynth，但不能因此丢掉已经综合过的核。续写拼出来的代码如果宿主编不过，不能覆盖已编译候选。

墙钟按剩余时间和实测解码速率折成本轮 `max_tokens`，低于 `AGENT_MIN_TOKENS`（默认 256）就停止生成，交出现有候选。每轮候选都会原子写入 `solution.cpp`，避免进程被硬结束时文件还是空的。

### 4.3 上下文管理

`tools.py::summarize_log()` 保留含 `ERROR:` / `CRITICAL WARNING:` / `Finished C
synthesis` 等关键词的行，截断到 2 KB。一份 csynth 日志有数万行，整份回灌会吃满上下文
并把唯一有用的那一行埋掉。

### 4.4 自我验证

有 host g++ selfcheck：用题目目录里的参考实现做对照，官方测试台不下发。selfcheck 报失败不等于官方 csim 会失败。`coder390_pair2` 里 `correlation`、`gemver`、`gramschmidt`、`signaling_nan` 都是第 1 轮 selfcheck 失败后被改写，最后交上去的核低于同一轮 baseline。第 4.2 节的等级保留就是针对这件事。selfcheck 编不过（例如 `hls_stream`、部分定点 typedef）时，该轮只做 csynth，不把「没查到」当成「查过了并且是对的」。

---

## 5. 技能包

### 5.1 技能清单

| 技能名称                      | 解决什么问题                     | 适用条件                              | 已验证有效的场景 |
| ----------------------------- | -------------------------------- | ------------------------------------- | ---------------- |
| `hls-top-interface-contract`  | 顶层签名不符、重复定义头文件内容 | 日志有 `HLS 214-157` / `undefined symbol` / `redefinition of` | 见 5.3 |

采用 AMD 官方技能格式，正文英文，可与官方技能混放，见 `skill/README.md`。

### 5.2 提炼过程

该技能针对的是本赛道特有的一个约束：**官方测试台不下发**，它包含接口头文件并按
头文件中的声明调用顶层函数，故该声明构成接口契约。算法实现即使正确，只要 `const`
丢了一个，链接器找的就是一个不存在的符号。

从早期失败样本中归纳出五类违约（函数名、签名、重复定义、头文件粘贴、多余的
`main()`），每一类对应一条可机械判定的规则。

### 5.3 有效性验证

在 Vitis HLS 2026.1 / `xczu3eg-sbva484-1-e` / 5 ns 上逐条注入故障实测：

| 注入的故障                       | 工具输出                                          | 判定等级 |
| -------------------------------- | ------------------------------------------------- | -------: |
| 重复定义头文件提供的常量表       | `error: redefinition of 'FIR_COEF'`               | **L0** |
| 函数名写成 `fir_11`              | `ERROR: [HLS 214-157] Top function not found`     | **L1** |
| 第一个参数丢掉 `const`           | `ld.lld: error: undefined symbol: fir11(int const*, int*)` | **L1** |
| 接口与算法均正确（对照）         | `INFO: [SIM 211-1] CSim done with 0 errors.`      | **L4** |

两个可直接用于排序修复优先级的结论：**重复定义比签名错更贵**（L0 对 L1，因为它连
C 前端均无法通过）；`undefined symbol` 中的符号即为所需签名，链接器要求的
`fir11(int const*, int*)` 正是应当写出的签名。

*说明：本节数据为本仓库实测。填写实证数据时须标注工具版本、器件与测量口径，同一次
SHA-256 优化按 csynth 估算是 T_exec 提升 37.7%，按 post-route 实测只有 12.0%，
换个口径结论差三倍。*

---

## 6. 实测结果

数据集：本地导入的 HLS-Eval 125 题（公开代理集，不是决赛隐藏题）。采样次数：1。
模型：Coder390-Q6_K。判定：本地 Vitis HLS 2025.2，`selftest/judge.py` 默认容差。
来源：`selftest/out/coder390_pair2/score.json`，baseline 与 agent 同一次运行。
增益满分线 2.5 为 `score.py` 占位值。

| 级别      | 方案题数 | 基线题数 |
| --------- | -------: | -------: |
| L0 未通过 |        0 |        2 |
| L1 可解析 |        4 |       11 |
| L2 可编译 |       44 |       44 |
| L3 可运行 |        0 |        5 |
| L4 可综合 |       77 |       60 |
| 题集得分  |   0.6896 |   0.6057 |

基线有 3 个样本是判定超时（>1800s），按 `score.py` 排除，分母按 122 题计：`fixed_floyd-warshall`、`fixed_gesummv`、`optical_flow`。

```
增益 = 0.6896 / 0.6057 = 1.1385
能力 + 增益 = 20.69 + 5.66 = 26.35
```

| 指标   |   方案 |   基线 |
| ------ | -----: | -----: |
| pass@1 | 0.6896 | 0.6057 |
| pass@5 | 0.6896 | 0.6057 |

这是 1 次采样，所以 pass@5 与 pass@1 相同。10 月 16 日正在跑的 `coder390_pair3` 使用第 4.2 节的保留规则，跑完前不以拼接估计代替这一行。

---

## 7. 失败分析

### 7.1 仍然做不出来的题目类型

| 题目类型         | 卡在哪一级 | 原因判断                                         |
| ---------------- | ---------- | ------------------------------------------------ |
| `ap_fixed<32,16>` 的 polybench | 本地原金标下停在 L2 | `tb_data.txt` 由 float 核生成，参考解自己对不上。本地用参考解 csim 输出补了 `tb_data_hls.txt`，没有改容差。见 `docs/fixed_golden_evidence.md` |
| 同等级的后一轮改写 | L2，而 baseline 是 L4 | selfcheck 误报后重写，把第 1 轮已经综合过的核换掉。`coder390_pair2` 有 6 道。保留规则在 9 道重跑里收回了 6 个 L4，全卷尚未复测 |
| `des` 的 `des_block_t` | L1 | 类型是 `unsigned char[8]`，模型仍按整数做移位。`hls-array-typedef` 已注入 |
| `bfs_bulk` / `fixed_lu` | L2 | 六轮或第 1 轮都能综合，官方测试台退出码分别为 -6 和 -8。保留规则留住的是这次第 1 轮，不是上一批偶然的 L4 |

### 7.2 尝试过但无效的改进

| 尝试的做法         | 预期效果       | 实际结果       | 为什么无效                       |
| ------------------ | -------------- | -------------- | -------------------------------- |
| 把轮数从 3 提到 6，且后一轮无条件替换 | 通过率上升 | `coder390_pair2` 相对旧解净增约 1.3 分，但 6 道低于本轮 baseline | 多出来的轮次会改掉已经写对的核。有效的是留下更高等级的候选，不是单纯加轮次 |
| 把上下文从 8192 提到 16384，输出上限仍为 8192 | 长核不再截断 | `des`、`dfdiv` 仍会在 8192 token 处截断 | 卡住的是单次输出上限，不是总上下文。再加大输出上限会让一轮解码吃掉单题时限 |

### 7.3 方案的边界

最先崩掉的是**功能正确性**这一维。selfcheck 能看到一部分功能错误，但它对照的是本地参考，不是官方测试台，误报会驱动重写。L2 → L3 这一步（系数从 0.2 到 0.8）仍然主要靠第 1 轮就写对，后轮只在等级严格更高时才替换。

换一个更弱的模型，崩的顺序会变成：先是代码抽取失败（不按格式输出），再是重复定义
头文件类型，最后才轮到功能。这说明在小模型上，格式与接口约束的收益高于算法能力。

---

## 8. 复现说明

### 8.1 构建

```bash
docker build -t example-agent .
```

### 8.2 启动推理服务

```bash
./serve/llama.sh
export LLM_BACKEND=openai LLM_BASE_URL=http://127.0.0.1:8000/v1
export LLM_MODEL=Coder390-Q6_K LLM_API_KEY=dummy
```

`serve/llama.sh` 默认 `--ctx-size 16384 --parallel 1`，别名 `Coder390-Q6_K`。权重路径用 `MODEL` 指向本地 GGUF，不要写 Hub id。

### 8.3 单题运行

```bash
./run.sh <input_dir> <output_dir>
```

### 8.4 基线运行

```bash
./run_baseline.sh <input_dir> <output_dir>
```

### 8.5 已知的环境依赖

- 权重须在断网前落到本地盘，`huggingface-cli download` 在沙箱中会失败
- `AGENT_TMP` 必须指向本地盘。指向 NFS 时 csynth 会慢一个数量级
- Vitis HLS 须在 `PATH` 上，或由 `VITIS_HLS_CMD` 指定
