# selftest/ — 本地分级判定

在本地跑一遍与赛事方口径一致的 L0–L4 判定，产出题集得分、pass@1 / pass@5 与增益。

```
L1 可解析  →  L2 可编译  →  L3 可运行  →  L4 可综合
```

逐级递进：前一级不过，后面的级别一律不计。

---

## 用法

```bash
cp env.sh.example env.sh && vi env.sh      # 填自己的 Vitis 安装路径与 LLM 后端

./run_selftest.sh --check                  # 只做环境检查
./run_selftest.sh --reference              # 用参考实现验证判定链路（不需要模型）
./run_selftest.sh                          # 方案 + 基线，各 1 次采样
./run_selftest.sh --samples 5              # 正式评测所用的采样次数
./run_selftest.sh --no-baseline            # 跳过基线，不算增益
./run_selftest.sh --baseline               # 桩模式下也强制跑基线（见下）
```

**桩模式下基线默认被跳过。** `LLM_BACKEND=mock` 只对 `agent/llm.py` 有效，而
`baseline.py` 读的是 `LLM_BASE_URL`、不认这个变量 —— 桩模式下它照样会去连真的推理
服务。连得上就是拿真模型的基线去比 mock 的智能体，连不上就是分母为 0，两种情况算出
的增益都没有意义却看不出异常。所以桩模式 + agent 模式时自动跳过，配置行会打印
「基线 跳过（桩模式，增益不计）」。

`--baseline` 是给「确实起了真端点、只是没改 `LLM_BACKEND`」的人留的出路。

单独判一个文件：

```bash
python3 judge.py --task ../tasks/ex01_fir11 --solution /tmp/out/solution.cpp
# ex01_fir11           L4  PCRS  coeff=1.0  47s
```

`PCRS` 是四级的通过情况（Parse / Compile / Run / Synth），未通过的位置显示 `-`。
需注意 `P--S`（解析与综合均通过，但测试台无法链接）这一组合，其等级为 L1，因为
L2 没过，L4 就不计。这不是 bug，是「逐级递进」的定义。

---

## 需要什么

| 判定级别      | 用到的命令                                        |
| ------------- | ------------------------------------------------- |
| L1 / L4       | `v++ -c --mode hls --config ...`                  |
| L2 / L3       | `vitis-run --mode hls --csim --config ...`        |

四级判定全部依赖 Vitis HLS，无替代路径。未安装时 `run_selftest.sh` 将明确报出未检测到，
仅进行结构检查，不会改用 g++ 等其他工具替代。

Vivado 与 Vitis 的安装由队伍自行完成，本仓库不提供安装指导。判定使用 HLS 综合，不需要
GPU 也不需要 AMD 显卡；目标器件 `xczu3eg-sbva484-1-e` 属于免费档的器件支持范围，
不需要专业版 license。

**没装 Vitis 仍然可以做的事：** 用 `LLM_BACKEND=mock` 跑 `example/run.sh`，验证输入
输出契约和 `trace.jsonl` 格式。

---

## 输出

```
selftest/out/
├── agent/<task>/s<k>/solution.cpp    每次采样的产物
│                    /trace.jsonl
│                    /run.log
├── baseline/...
├── logs/<task>.csynth.log            工具原始日志
│     /<task>.csim.log
├── results/<mode>.<task>.s<k>.json   每个样本的判定结果
└── score.json                        汇总
```

单样本判定结果：

```json
{
  "task_id": "ex01_fir11",
  "level": 4,
  "coefficient": 1.0,
  "stages": {"parse": true, "compile": true, "run": true, "synth": true},
  "tool_error": null,
  "elapsed_s": 47.0
}
```

---

## 计分口径

```
题集得分 = Σ(题目系数) / 题数
能力得分 = 30 × 题集得分
增益     = 方案题集得分 / 基线题集得分
增益得分 = 40 × log(增益) / log(满分线倍数)
```

系数：L0 = 0、L1 = 0.1、L2 = 0.2、L3 = 0.8、L4 = 1.0。

**pass@1 计分，pass@5 只作稳定性诊断。** pass@1 取每题各次采样系数的均值再对题目平均；
pass@5 取每题的最好一次。两者差值大，说明方案对采样运气的依赖高。

`--samples 1` 时 pass@1 与 pass@5 必然相等，这个数没有诊断意义。要看方差就用
`--samples 5`。

**本地无法自评的两项：** 代价（10 分）需要独占环境计时，工程质量（20 分）含人工评定。

增益满分线 `GAIN_FULL_MARK` 默认 2.5，**这是占位值，不是官方值**，正式取值于赛前公告。
本地只用它做纵向比较：同一个满分线下，改动前后的增益得分才有可比性。

---

## 一条使用建议

请先运行 `--reference`。该模式不依赖模型与 key，仅验证一项内容，即本地 Vitis 环境能否将已知
正确的代码判到 L4。** 这一步不过，后面所有分数都不可信。

三道参考实现在 Vitis 2026.1 / `xczu3eg-sbva484-1-e` / 5 ns 下实测均为 L4 PCRS。
