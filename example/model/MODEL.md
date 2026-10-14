# MODEL.md

> 所填内容须与 `manifest.json`、`REPORT.md` 第 2 节一致。
>
> **本文件未如实填写时，增益项 40 分不得分**（评分细则 2.4）。

---

## 1. 模型

| 项           | 内容                                    |
| ------------ | --------------------------------------- |
| 模型名称     | Arkha7/Qwen3.8-27B-Coder390-EfficientThink-Opus5.5-GPT6Astra-Grok4.7-DSV4Pro-K3-SFT-RLOO-MTP-DFlash2 |
| 来源         | https://huggingface.co/Arkha7/Qwen3.8-27B-Coder390-EfficientThink-Opus5.5-GPT6Astra-Grok4.7-DSV4Pro-K3-SFT-RLOO-MTP-DFlash2 |
| 版本号 / SHA | Hub commit `d602255311fbdf0852161dc33ccfbecb80e7c7ce`（2026-10-08） |
| 权重校验和   | GGUF Q6_K：`sha256:302597c53d1b00f7230b53a8a050831390a4371e92a80c1ac644fa920af76ab1`（23177516384 bytes） |
| 参数量       | 27B（Qwen3.8 族） |
| 许可证       | Apache-2.0 |
| 服务别名     | `Coder390-Q6_K` |

提交使用的文件：

`GGUF/Qwen3.8-27B-Coder390-EfficientThink-Q6_K-MTP.gguf`

**必须是可本地部署的开源权重。** 决赛在断网沙箱中运行，商用 API 在评分细则 2.1 与
2.3 两条上均不成立，全部运行类得分无法产生。

本队未再训练。权重为 HuggingFace 已发布的 SFT+RLOO 衍生模型，基座谱系为 Qwen3.8-27B
（card 声明 `base_model`: `nerkyor/Qwen3.8-27B-EfficientThink-Uncensored-K3-Opus5-Grok4.6-GPT5.6Sol-SFT-SimPO-DFlash2`）。

## 2. 量化与显存

| 项           | 内容                        |
| ------------ | --------------------------- |
| 量化方式     | GGUF Q6_K（文件名带 MTP 头；llama.cpp 将 `blk.64` nextn 张量标为 unused，不参与生成） |
| 量化工具与版本 | 上游仓库提供的 Q6_K GGUF |
| **实测显存占用** | 21.1 GB（21558 MiB，单卡，加载后稳态） |
| 测量方式     | `nvidia-smi --query-gpu=memory.used` |
| 测量硬件     | NVIDIA Tesla V100S 32GB |

**上限单卡 32 GB，不允许跨卡。** 验证阶段的云资源有 48 GB，但超出 32 GB 的配置在决赛
无法复现，风险自负。

Q8_0 GGUF 约 29 GB，加上 KV 在 32 GB 卡上过紧，故选用 Q6_K。

## 3. 上下文配置

| 项                 | 值    |
| ------------------ | ----- |
| `max_model_len`    | 16384 |
| 单次输出上限       | 8192 |
| RoPE 外推方式      | 无（llama.cpp `--ctx-size 16384`） |

**本项不受统一约束，但必须如实声明。**

基线 `example/baseline.py` 的 `MAX_TOKENS = 8192`。agent 的 `LLM_MAX_TOKENS` 取同一值，
由 `run.sh` 导出。思考型模型输出窗口过小会截断；本模型单轮实测可达 5k+ token。

**基线运行必须使用与方案完全相同的上下文配置**，否则增益项的分子与分母不可比。

## 4. 推理栈

| 项           | 内容                    |
| ------------ | ----------------------- |
| 后端         | llama.cpp `llama-server` |
| 版本         | llama.cpp 0.6.0-dev，commit `781dbc5` |
| 关键启动参数 | 见 `serve/llama.sh`：`--ctx-size 16384 --parallel 1 --gpu-layers all --jinja --reasoning off --reasoning-format deepseek` |
| 并发策略     | 每卡一实例，`--parallel 1` |
| 端点         | `http://127.0.0.1:8000/v1`（OpenAI `/chat/completions`） |

## 5. 微调

本队未额外微调。所用权重为第三方已开源的 SFT+RLOO 衍生模型，开源地址即第 1 节来源链接。

| 项             | 内容 |
| -------------- | ---- |
| 基座模型       | Qwen3.8-27B 谱系（见 card `base_model`） |
| 微调方式       | 上游声明 SFT + RLOO；本队未训练 |
| 训练数据来源   | 见上游 model card；本队未收集或再训 |
| 训练数据规模   | 上游未在本提交中复述 |
| **微调权重开源地址** | https://huggingface.co/Arkha7/Qwen3.8-27B-Coder390-EfficientThink-Opus5.5-GPT6Astra-Grok4.7-DSV4Pro-K3-SFT-RLOO-MTP-DFlash2 |

## 6. 声明

- [x] 上述模型为可本地部署的开源权重，非商用 API
- [x] 实测显存占用不超过 32 GB，单卡运行
- [x] `run_baseline.sh` 使用与 `run.sh` 完全相同的模型、量化方式与上下文配置
- [x] 若经微调，权重已开源且链接可达（本队未再训，上游权重已开源）
- [x] 本文件内容与 `manifest.json`、`REPORT.md` 一致
