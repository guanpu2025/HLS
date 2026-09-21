# 接口契约

评测当天，赛事方从外部向各队的服务投题。**这是唯一赛前固定、之后一个字都不能改的东西。**

本文所列格式最终以赛前公告为准，但结构不会变。按本文实现的服务在正式评测中可直接使用。

---

## 一、这件事在做什么

现行的做法是队伍把整套方案打包交给赛事方，赛事方在自己的机器上重建容器逐队运行。
远程评测换一个方式：**队伍在自己的机器上把服务跑起来，赛事方从外面投题。**

```
  ① 队伍那边跑一个程序，它一直不退出，守着一个端口
  ② 赛事方发一个 HTTP 请求过去，内容是一段 JSON，把题面送过去
  ③ 队伍的程序收到后，调用自己的智能体去解题
  ④ 解完，把代码照样写成 JSON 返回
```

需要理解的只有三个词：

| 词         | 是什么                                        | 为什么需要                                     |
| ---------- | --------------------------------------------- | ---------------------------------------------- |
| **端点**   | 一个网址，如 `https://xxx.example.com/v1/solve` | 赛事方照着这个地址投题                       |
| **令牌**   | 一串密码字符串，随请求一起发过去              | 端点网址是公开的，没有令牌任何人都能投题       |
| **同步**   | 发出请求后不挂断，一直等到答案回来            | 计时才准，中间那段时间不会算不清               |

**题目在第 ② 步才第一次离开赛事方的机器，而且一次只走一道。** 队伍从头到尾拿不到完整
题集，也不知道下一题是什么。

---

## 二、`GET /v1/health`

赛事方在投题前调用，确认服务与模型就绪。

**请求**

```
GET /v1/health
Authorization: Bearer <令牌>
```

**响应**

```json
{
  "ready": true,
  "track": "hls",
  "model": "Qwen/Qwen3-8B",
  "vram_gb": 21.4
}
```

| 字段      | 说明                                                  |
| --------- | ----------------------------------------------------- |
| `ready`   | 模型已加载、智能体可用时为 `true`                     |
| `track`   | **必须是 `"hls"`**，投题机会核对，不符即拒投    |
| `model`   | 与 `MODEL.md` 中声明的模型一致                        |
| `vram_gb` | 当前实测显存占用                                      |

**`track` 这一项是实测中一次事故加上的。** 曾出现 HLS 的投题服务因端口被占启动失败、
而 RTL 服务仍在应答的情形，投题机照常投题，24 个 HLS 样本全部收到 Verilog，产物
文件名是投题机按自己的 track 命名的，**表面上看不出任何异常**，直到判定时全部落在 L1
才暴露。健康检查的意义就是挡住这类「服务活着但不对」的状态。

---

## 三、`POST /v1/solve`

**请求**

```
POST /v1/solve
Authorization: Bearer <令牌>
Content-Type: application/json
```

```json
{
  "task_id":    "eval-0007",
  "nonce":      "T042-eval-0007-3-1763251200123456789",
  "mode":       "agent",
  "prompt":     "实现一个 11 抽头的定点 FIR 滤波器 ...",
  "interface":  "// header: fir11.h\n#ifndef FIR11_H\n#define FIR11_H\n#define N_SAMPLES 64\ntypedef int32_t data_t;\nstatic const data_t FIR_COEF[11] = {-3, 7, ...};\nvoid fir11(const data_t x[N_SAMPLES], data_t y[N_SAMPLES]);\n#endif\n",
  "deadline_s": 360
}
```

**响应**

```json
{
  "task_id":   "eval-0007",
  "solution":  "#include \"fir11.h\"\nvoid fir11(...) { ... }\n",
  "trace":     "{\"tool\":\"csynth\",\"ts\":...}\n{...}\n",
  "elapsed_s": 214.3
}
```

| 字段         | 说明                                                                   |
| ------------ | ---------------------------------------------------------------------- |
| `task_id`    | 题号。返回时必须原样带回，用于对账                                     |
| `nonce`      | 一次性随机串，每次请求都不同                                           |
| `mode`       | `agent` 走完整方案，`baseline` 绕过智能体与技能包                      |
| `prompt`     | 题面，纯文本                                                           |
| `interface`  | **题目头文件的全文**，首行是标出文件名的注释（见下）。**签名不得改动**，否则测试台无法调用 |
| `deadline_s` | 单题墙钟上限，队伍应在此之前自行停止                                   |
| `solution`   | 产出的 HLS C++ 代码。**做不出来返回空字符串，不要报错**           |
| `trace`      | 工具调用记录，JSONL 格式，见第五节                                     |
| `elapsed_s`  | 队伍自报耗时。**不用于计分**，仅与赛事方计时交叉核对             |

---

## 四、几条硬约定

- **单题墙钟以赛事方发出请求到收到响应为准**，队伍自报的 `elapsed_s` 不作数
- 赛事方侧超时设为 `deadline_s + 20` 秒，超时该题按 L0
- **任何失败一律按 L0，不重试。** 超时、连接断开、返回格式错，同等对待
- **服务须能连续处理数百次请求，中途不得重启**
- 方案与基线走同一个端点，用 `mode` 区分，保证两者出自同一次运行、同一个服务、
  同一份配置
- **服务须绑 `127.0.0.1`，不是 `0.0.0.0`**；对外由平台的 `rc-tunnel` 转发，见第七节

关于「做不出来返回空串而不是报错」：这样能让「没做出来」和「服务坏了」在协议层可区分。
前者是正常的 L0，后者要排查。

### `interface` 是一份完整的头文件，不是一行签名

智能体拿不到题目目录，只有 `prompt` 与 `interface` 两段文本。所以 `interface` 里
装的是**这道题头文件的全文**，首行是一条标出文件名的注释：

```
// header: fir11.h
#ifndef FIR11_H
#define FIR11_H
#define N_SAMPLES 64
#define N_TAPS 11
typedef int32_t data_t;
typedef int64_t acc_t;
static const data_t FIR_COEF[N_TAPS] = { -3, 7, -15, 34, 92, 128, 92, 34, -15, 7, -3 };
void fir11(const data_t x[N_SAMPLES], data_t y[N_SAMPLES]);
#endif
```

**为什么不是一行签名。** 头文件里的 `typedef`、数组长度宏、常量系数表这些东西，
题面用文字描述不出来 —— 写出来就等于把答案的一部分放进题面。而判定时测试台
`#include` 这个头文件并按其中的类型调用待测函数，模型自己另起一套 typedef
或者自己编一组系数，L2 就编不过。

**由此有一条必须做的事：智能体要把这段内容写回成文件**，文件名取首行注释里的那个，
和生成的代码放在同一个目录，才能自己跑通编译检查。不还原的话，`v++` 必然报

```
ERROR: [HLS 207-974] 'fir11.h' file not found
```

首行固定是 `// header: <文件名>`，本仓库自带的示例题与评测题集**逐字同形**。
`example/agent/main.py` 的 `split_interface()` 是一份可直接用的解析实现；它同时
兼容把文件名写在中文注释里的旧写法，但不要依赖这一点。

---

## 五、`trace.jsonl` 里应当有什么

每行一个 JSON 对象，记录智能体做过的每一次工具调用与模型调用。

```json
{"ts": 1763251200.12, "tool": "llm", "tokens_in": 2841, "tokens_out": 512}
{"ts": 1763251203.45, "tool": "csynth", "rc": 1, "excerpt": "ERROR: [HLS 200-70] Compilation errors ... 'data_t' does not name a type"}
{"ts": 1763251260.01, "tool": "llm", "tokens_in": 3402, "tokens_out": 488}
{"ts": 1763251302.77, "tool": "csynth", "rc": 0, "excerpt": "Finished C synthesis. II=1, Latency=1034"}
```

建议字段：

| 字段         | 说明                                       |
| ------------ | ------------------------------------------ |
| `ts`         | Unix 时间戳，浮点秒                        |
| `tool`       | 工具名，如 `llm` / `csim` / `csynth`       |
| `rc`         | 返回码，0 为成功                           |
| `excerpt`    | 输出摘要，建议截断到 2 KB 以内             |
| `tokens_in`  | 模型调用的输入 token 数                    |
| `tokens_out` | 模型调用的输出 token 数                    |

这一项同时喂三个用途：**工程质量评定（20 分）、作弊复核（生成产物与工具调用能否对上）、
失败分析。** 属必需项，不是可选。

---

## 六、最小实现

`example/serve/serve_api.py` 是一份可直接运行的实现，把 `run.sh` 套一层 HTTP 壳。
智能体本身无需改动，仍为读取一个目录并写出一个文件。

```bash
cd example
pip install -r requirements.txt
export FPGACHINA_TOKEN=<赛事方发的令牌>
export MODEL_NAME=Qwen/Qwen3-8B
uvicorn serve.serve_api:app --host 127.0.0.1 --port 7860
```

自测：

```bash
curl -H "Authorization: Bearer $FPGACHINA_TOKEN" http://localhost:7860/v1/health

curl -X POST http://localhost:7860/v1/solve \
  -H "Authorization: Bearer $FPGACHINA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"task_id":"t1","nonce":"n1","mode":"agent","prompt":"实现向量加法","interface":"void vadd(const int a[8], const int b[8], int c[8]);","deadline_s":60}'
```

---

## 七、端口与网络

```
  7860   serve_api.py   投题接口   绑 127.0.0.1，经 rc-tunnel 对外
  8000   vllm.sh        推理服务   绑 127.0.0.1，不暴露
```

### 只能绑 `127.0.0.1`

Radeon Cloud 的对外暴露机制（`rc-tunnel`）**只接管绑在 `127.0.0.1` 上的 HTTP /
WebSocket 服务**，绑 `0.0.0.0` 平台不接管。平台文档原文：

> Only HTTP and WebSocket services bound to `127.0.0.1` inside the notebook
> are supported.

暴露流程，在 notebook 终端里执行：

```bash
/var/run/secrets/frp-self-service/install
"$HOME/.local/bin/rc-tunnel" expose --port 7860
```

绑错地址的后果：服务本身是活的，但外面永远打不进来，**在赛事方那边看起来和挂掉
没有区别**，而失败不重投。

### 只有投题接口需要暴露

平台限制**一个 notebook 同时只能暴露一个端口**。7860 是唯一需要暴露的；vLLM 的
8000 由智能体经 `127.0.0.1` 内部调用，**不要去暴露它**——暴露了既占掉唯一的名额，
也把推理服务开在了公网上。

由此有一条推论：**同时参加 RTL 与 HLS 两个赛道的队伍需要两台 VM。** 一台机器起
两个服务，只能暴露其中一个。

### 网址是公开的，鉴权得自己做

平台分配 `rc-<random>.radeon.firstdg.ai` 形式的域名，不支持自定义，且**平台不为
它加任何业务层鉴权**。因此 `/v1/solve` 与 `/v1/health` 都必须校验
`Authorization: Bearer <令牌>`，`serve_api.py` 里那段令牌校验不可省略。

`/v1/health` 同样要校验——它会报出队伍所用的模型名与显存大小，公网可读等于把这些
情报直接送出去。

### 端口范围

1024–65535，且需避开平台保留端口，7860 与 8000 都在范围内。平台只支持 HTTP 与
WebSocket，不支持 TCP / UDP / SSH / 数据库端口。

### 工程文件落本地盘

工程与中间文件请落在**节点本地盘**（如 `/tmp`），不要落在网络存储上。Vitis HLS 综合会产生
大量小文件，写网络存储极慢。这不是优化建议。

---

## 八、单题入口 `run.sh` 与 `run_baseline.sh`

```
用法    run.sh <task_dir> <out_dir>

读      <task_dir>/prompt.txt        题面
        <task_dir>/interface.txt     头文件全文，首行标出文件名。HLS 题必有

写      <out_dir>/solution.cpp       产出的 HLS C++
        <out_dir>/trace.jsonl        工具调用记录，见第五节

退出码  0    产出了文件
        非0  放弃本题

超时    由赛事方的测试脚本强制，到点发 SIGTERM。收到后须在 10 秒内退出，
        否则 SIGKILL，该题按 L0 计。
        ★ 不要依赖自己计时——计分以赛事方侧测得的墙钟为准
```

`run_baseline.sh` 参数完全相同，但**绕过智能体与技能包**：提示词只含题面本身，
单次生成，不重试，不调用任何工具，**不得挂载任何 MCP server**。

最后一条要单独强调，因为 MCP 容易被理解成「推理栈」的一部分而在基线里保留。
那样增益项（40 分）的分母被抬高，整项失真。**基线里模型只能拿到题面文本。**

推理服务本身在方案与基线之间必须完全一致——同一个模型、同一份量化、同一套上下文
配置。赛事方的测试脚本会在同一次运行中先后调用两者。

---

## 九、运行环境

赛事方基础镜像里已设好这些变量，**读变量，不要自己拼路径**：

```
XILINX_ROOT     /tools/Xilinx
XILINX_VITIS    /tools/Xilinx/2026.1/Vitis
XILINX_HLS      /tools/Xilinx/2026.1/Vitis
EDA_TMP         /tmp/eda            临时工作区的根
```

两件与早期版本不同、且最容易踩的事：

1. 2026.1 的目录布局是 `/tools/Xilinx/2026.1/Vitis`（**版本在前**），2024.2 及更早
   是 `/tools/Xilinx/Vitis/2024.2`（工具在前）。网上教程里多半是后者。
2. **2026.1 没有 `vitis_hls` 这个可执行文件**，也没有 `Vitis_HLS` 目录。综合用
   `v++ -c --mode hls`，csim 用 `vitis-run --mode hls --csim`。HLS-Eval 等上游
   工具直接调 `vitis_hls`，在本环境里跑不起来，须改写其工具调用方式。

### 什么该写在哪

这是**性能与配额问题，不是风格建议**。写错地方会让单题墙钟翻几倍，或者把配额吃光。

```
/tools/Xilinx/     EDA 工具本体    只读，来自镜像层，同节点多容器共用一份
/workspace/        队伍工作区      ★ 网络存储（NFS），持久，有配额
/tmp/eda/<id>/     HLS 工作目录    ★ 节点本地盘，快，不持久
```

csim 的 build 目录是几万个小文件。在 NFS 上创建几万个小文件是最慢的一种 IO 模式，
而且会吃掉 100 GB 的持久化配额。镜像里提供了 `eda-workdir` 代劳：

```bash
WORK=$(eda-workdir fir11 s3)        # 建 /tmp/eda/fir11-s3-XXXXXX
cd "$WORK"
# ... 跑 v++ / vitis-run ...
cp solution.cpp *.log /workspace/runs/fir11/s3/    # 只把小文件搬回去
```

**每次运行建一个**，不是每题一个。正式评测每题跑 5 次采样，参数里那个 `s3` 就是
采样序号。

`/tmp/eda/` 下**整棵子树**超过两小时没有任何改动的目录，由镜像的后台循环每十分钟
清理一次。判定「有没有改动」看整棵子树而不是顶层目录，所以长时间运行的任务不会被
误删。

---

## 十、已知的环境细节

这几条都是实测撞出来的，每一条不知道都会白花几小时。

**csim 需要辅助数据在 cwd。** 部分题目的测试台用相对路径读数据文件（如
`open("input.data")`），工作目录里必须有这些文件，且 csim 可执行文件的 cwd 要落在
那里。判定器已处理，自己搭流程时要注意。

**工具会往当前目录写东西。** 所以并发跑必须逐样本隔离工作目录，这也是 `eda-workdir`
存在的理由。

**自测脚本不要用 `set -u`。** AMD 的 `.settings64-Vitis.sh` 内部引用了未定义的
`MATLABPATH`，在 `set -u` 下 `source` 它会当场退出：

```
/tools/Xilinx/.../.settings64-Vitis.sh: line 18: MATLABPATH: unbound variable
```

`set -euo pipefail` 是很常见的写法，踩上了症状是脚本在 source 环境那一步就悄悄
断掉，看着像工具装坏了。用 `set -eo pipefail`，或者在 source 前后临时切换。

**授权失败会伪装成「器件选错」。** 2026.1 起 HLS 综合要签出 license，签不出时报的是

```
ERROR: [HLS 200-1023] Part '...' is not supported.
                      It is either unknown, not installed or does not have an appropriate license.
```

看着像器件名写错了。`selftest/judge/` 里的判定器能识别这种情形，产出 `LICENSE_ERROR`
而不是某个级别；自己写检查逻辑时也要区分开，否则环境问题会被记成自己的方案不行。
