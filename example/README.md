# example/ — 最小示范方案

这是一套能完整跑起来的参赛方案，可直接复制成 `<team_name>-agent/` 作为起点。

它能跑通，但不具竞争力：智能体只有三轮「生成 → 综合 → 读错误 → 重新生成」的循环，
技能包只有一条。提供它是为了让队伍在第一天就有一条通的链路，而不是拿它直接提交。

---

## 一、这个目录里有什么

标「**要改**」的是竞赛需要队伍投入的部分，标「不改」的照原样带上即可。

| 文件 / 目录 | 作用 | 是否需要改 |
| --- | --- | --- |
| `run.sh` | 单题入口。赛事方投一道题，就调它一次 | 不改 |
| `run_baseline.sh` | 基线入口 | **不得修改** |
| `baseline.py` | 赛事方提供的基线脚本，用于计算增益项的分母 | **不得修改** |
| `agent/main.py` | 智能体主流程：几轮循环、时间预算、写 `trace.jsonl` | **要改** |
| `agent/tools.py` | 调用 Vitis HLS 做综合，并压缩日志 | **要改** |
| `agent/llm.py` | 调用大模型的封装 | 一般不改 |
| `agent/skills.py` | 技能包的加载与挑选 | 视需要 |
| `agent/prompts/system.md` | 主提示词，告诉模型该怎么写 HLS C++ | **要改** |
| `agent/prompts/repair.md` | 报错后让模型改错用的提示词 | **要改** |
| `skill/` | 技能包，现在只有一条示范 | **要改** |
| `model/MODEL.md` | 模型声明。不如实填写，增益项 40 分不得分 | **必须填** |
| `serve/vllm.sh` | 启动本地推理服务 | 按所选模型改 |
| `serve/serve_api.py` | 赛事方投题用的 HTTP 接口，监听 `127.0.0.1:7860` | 一般不改 |
| `REPORT.md` | 设计报告 | **必须写** |
| `Dockerfile` | 基于官方基础镜像构建 | 按需要改 |
| `manifest.json` | 机器可读的方案声明 | **必须填** |

一句话概括：**改 `agent/`、`skill/`、`prompts/`，填 `MODEL.md` 与 `REPORT.md`，
其余照原样带上。`baseline.py` 与 `run_baseline.sh` 绝对不要动。**

---

## 二、怎么跑起来

三步，建议按顺序做。第一步不需要 GPU，也不需要装 Vitis。

### 第 1 步：桩模式，先确认链路是通的

```bash
pip install -r requirements.txt
LLM_BACKEND=mock ./run.sh ../tasks/ex01_fir11 /tmp/out
cat /tmp/out/solution.cpp
```

`mock` 是假模型，不联网、不要 key。它返回一个签名正确的空壳函数。
这一步只验证「读题目 → 写文件」这条路通不通，不验证解题能力。

看到 `/tmp/out/` 下生成了 `solution.cpp` 和 `trace.jsonl`，就算成功。

### 第 2 步：接上真模型，看看能不能解题

开发阶段可以用自己买的商用 API：

```bash
export LLM_BACKEND=openai
export LLM_BASE_URL=https://api.deepseek.com/v1
export LLM_API_KEY=sk-xxxxxxxx
export LLM_MODEL=deepseek-coder
./run.sh ../tasks/ex01_fir11 /tmp/out
```

任何 OpenAI 兼容的端点都可以。**这条路径只能用于开发调试，不能用于提交。**

### 第 3 步：换成本地模型（正式提交必须是这个）

```bash
MODEL=/models/Qwen3-8B ./serve/vllm.sh &     # 先起本地推理服务

export LLM_BACKEND=openai
export LLM_BASE_URL=http://localhost:8000/v1
export LLM_API_KEY=dummy
export LLM_MODEL=Qwen3-8B
./run.sh ../tasks/ex01_fir11 /tmp/out
```

第 2 步和第 3 步的区别只有环境变量，智能体代码一行都不用改。

### 另外：跑一次基线

```bash
./run_baseline.sh ../tasks/ex01_fir11 /tmp/base
```

基线用同一个推理服务、同一个模型，但绕过智能体与技能包，单次直接生成。
它是增益项 40 分的分母，必须能跑通，否则这 40 分不得分。

---

## 三、智能体用的工具

`agent/tools.py` 只封装了一个工具 `csynth()`，调用 `v++` 做 HLS 综合，数十秒返回。
它能发现不可综合的写法、顶层签名不符，以及调度失败（II 达不成、数组端口冲突等）。

综合通过只说明代码能变成硬件，**不说明算得对**。功能是否正确要靠队伍自己想办法验证，
这正是下一节第一条要讲的事。

未安装 Vitis HLS 时，`csynth()` 返回 `rc=-1` 并说明原因，智能体退化为单次生成，
不会在没真正综合的情况下报告综合通过。

---

## 四、环境变量

常用的几个：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LLM_BACKEND` | `mock` | 填 `mock` 或 `openai` |
| `LLM_BASE_URL` | 无 | 模型服务地址，用 `openai` 后端时必填 |
| `LLM_API_KEY` | 空 | 本地 vLLM 可填任意值 |
| `LLM_MODEL` | `mock-model` | 模型名 |
| `AGENT_MAX_ROUNDS` | `3` | 最多重试几轮 |

其余用于微调行为，一般不必改动：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LLM_MAX_TOKENS` | `4096` | 单次输出上限，须与 `MODEL.md` 一致 |
| `LLM_TEMPERATURE` | `0.2` | 采样温度 |
| `LLM_TIMEOUT_S` | `180` | 单次模型调用超时 |
| `AGENT_DEADLINE_S` | `360` | 单题时间预算，评测时由投题参数覆盖 |
| `AGENT_RESERVE_S` | `20` | 留给写出结果的余量 |
| `AGENT_TMP` | `/tmp` | 临时目录，须为本地盘 |
| `VITIS_HLS_CMD` | 自动探测 | 指定 `v++` 的路径 |
| `HLS_PART` | `xczu3eg-sbva484-1-e` | 判定器件 |
| `HLS_PERIOD_NS` | `5` | 时钟约束 |
| `FPGACHINA_TOKEN` | 无 | 投题令牌，`serve_api.py` 必填 |

---

## 五、接下来可以做什么

示范方案的每一处简化都是留给队伍的工作。按预期收益排序，前两项最值得先做。

**一、让智能体自己判断算得对不对。** 这是 L2 到 L3 的主要距离，也是分级表中跨度最大的
一级（系数从 0.2 升到 0.8）。官方测试台不下发，综合通过不能说明功能正确。
可行方向：让模型自己写一个测试台、从题面推导出不变量并施加断言、或写一份简化的
C 参考实现来对拍。

**二、把接口与可综合性的常见错误整理成技能。** HLS 侧最常见的失败是顶层签名与题目
给定的不一致，以及用了不可综合的写法（动态分配、递归、运行时边界、不支持的 STL）。
这几类每一类都够写成一条技能。

**三、把技能包做厚。** 现在只有一条，有竞争力的提交通常有 5 到 15 条。`SKILL.md` 用的
是 AMD 官方技能格式，官方技能库（https://github.com/amd/skills ）里的技能可以原样复制
到 `skill/` 直接使用，加载器对两者通用。可综合性、pragma 作用域、dataflow、循环展平
这些官方已经覆盖，建议直接取用，把精力放在没覆盖的地方。

改进方向的取舍过程与实测数据，写进 `REPORT.md` 就是工程质量项的得分点。
