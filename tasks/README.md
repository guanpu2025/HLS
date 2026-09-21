# tasks/ — 示例题目

三道题，格式与评测题集一致，用来确认接口通畅与判定链路可用。

**它们不是自测题集。** 三道题量不出任何有意义的通过率，开发阶段请用
[HLS-Eval](https://github.com/sharc-lab/HLS-Eval)（101 个 kernel，源自 PolyBench /
CHStone / MachSuite / Rosetta），并把实测结果写进设计报告。

---

## 题目

| 题目               | 顶层         | 考察点                                       |
| ------------------ | ------------ | -------------------------------------------- |
| `ex01_fir11`       | `fir11`      | 边界处理（前补零）、累加位宽                 |
| `ex02_histogram`   | `histogram`  | 循环携带依赖、输出数组须自行清零             |
| `ex03_matmul`      | `matmul`     | 累加位宽不得截断、输出须全部写入             |

每道题的测试台都刻意设了陷阱：`ex02` 把 `hist` 预填成 `0xDEADBEEF`（假设调用方已清零
的实现会失败），`ex03` 把 `c` 预填成垃圾值且输入幅度足以让 16 位累加溢出。写得马虎但
恰好能过一个宽松测试台的实现，在这里过不去。

---

## 题面是英文

**评测题集的题面全部是英文**，取自 HLS-Eval 各 kernel 的 `kernel_description.md`。
本目录三道示例题已改写成与它同结构的英文：

```
Kernel Description:
<算法描述，含公式>

---

Top-Level Function: `name`

Complete Function Signature of the Top-Level Function:
`void name(...);`

Inputs:
- `x`: ...

Outputs:
- `y`: ...

Important Data Structures and Data Types:
- `data_t`: ...
```

**为什么不留中文版。** 示例题的作用是照着它开发。题面语言不一致的话，队伍在中文上
调好的提示词与观察到的模型行为，评测当天面对的是另一种语言 —— token 分布不同，模型
表现也未必一样，而这种差异只会在评测当天暴露。

仓库的其余文档仍是中文，只有题面跟着评测题集走。

## 目录格式

```
ex01_fir11/
├── prompt.txt          题面。run.sh 读这个
├── interface.txt       头文件全文，首行 `// header: <文件名>`。run.sh 读这个
│                       与评测题集逐字同形
├── fir11.h             与 interface.txt 正文一致，供测试台 include
│                       评测时智能体收不到这个文件，要自己从 interface 还原
├── fir11_tb.cpp        官方测试台。★ 不下发给智能体，判定 L3 用
├── top.txt             顶层函数名
├── task.json           判定元信息
└── reference/
    └── fir11.cpp       参考实现，仅用于验证判定链路
```

`task.json`：

```json
{
  "task_id": "ex01_fir11",
  "top": "fir11",
  "part": "xczu3eg-sbva484-1-e",
  "period_ns": 5,
  "header": "fir11.h",
  "testbench": "fir11_tb.cpp",
  "extra_files": [],
  "reference": "reference/fir11.cpp"
}
```

---

## 两件要注意的事

**一、`reference/` 不要喂给智能体。** 一个因为答案就在提示词里而通过的自测，什么都
没测到。它存在的唯一目的是证明判定链路能在已知正确的输入上走到 L4：

```bash
cd ../selftest && ./run_selftest.sh --reference
```

**二、`*_tb.cpp` 是判定用的，智能体拿不到。** 正式评测时测试台在赛事方手里，智能体
只能拿到 `prompt` 与 `interface`。

因此不应将测试台接入智能体环内充作自我验证，此种做法会使本地得分虚高，至评测时
那条路径不存在。想在环内自我验证，只能自己写测试台。这是本赛道要解决的问题之一。

---

## 自己加题

按上面的目录格式放进 `tasks/` 即可，`run_selftest.sh` 会自动发现所有含 `task.json`
的目录。

把 HLS-Eval 转成这个格式并不难，它的目录里已有 `kernel_description.md`、`*_tb.cpp`、
`top.txt` 和 `*.h`，对应关系是直接的：

| HLS-Eval                 | 这里             |
| ------------------------ | ---------------- |
| `kernel_description.md`  | `prompt.txt`     |
| `<top>.h`                | `interface.txt` + `<top>.h` |
| `<top>_tb.cpp`           | `<top>_tb.cpp`   |
| `top.txt`                | `top.txt`        |
| `hls_eval_config.toml`   | `task.json`      |

注意 HLS-Eval 的部分题目带 `input.data` / `check.data` 等数据文件，转换时写进
`task.json` 的 `extra_files`，判定时会一并拷进工作目录。
