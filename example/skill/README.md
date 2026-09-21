# 技能包

技能包是领域知识的组织形式。它不是提示词的堆叠，评价标准只有一条：**他人能否照着用。**

本目录只放了一条技能作为格式示范。一份有竞争力的提交通常有 5–15 条，且每一条都能
指出它是从哪些失败样本中总结出来的。

---

## 采用 AMD 官方技能格式

`SKILL.md` 的写法与 AMD 官方的 Vitis HLS 智能体技能一致（`hls-flattenable`、
`hls-line-buffer` 等）。**正文用英文**，与官方保持一致；仓库其余文档仍为中文。

这样做有一个直接好处：**官方技能可以原样拷进 `skill/` 目录直接用**，
`agent/skills.py` 的加载器对两者通用，已实测。官方技能已覆盖可综合性、pragma 作用域、
dataflow 规范形式、burst 推断、循环展平、stencil 与 line buffer 等常见方向，
不必重写；把力气花在官方没覆盖的地方。

官方技能仓库：https://github.com/amd/skills

---

## 目录结构

```
skill/
├── README.md
└── <skill-name>/
    └── SKILL.md
```

一条技能一个目录。目录名与文件名一律英文小写加连字符。

## `SKILL.md` 的格式

````markdown
---
name: hls-top-interface-contract
description: 一行说清楚解决什么问题。单行，不用 YAML 块标量。
---

<!--
Copyright (C) 2026, Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
-->

# Agent Skill: <Title>

## Skill Metadata
- **Name:** `hls_top_interface_contract`
- **Description:** 与 frontmatter 一致
- **Trigger:** 什么情况下该用这条技能（散文）
- **Log signatures:** `HLS 214-157`, `undefined symbol`      ← 见下

## System Prompt
## Rules            ← 判定类技能：Rule 1 … Rule N，逐条可判 PASS/FAIL
## Steps            ← 操作类技能：Step 1 … Step N，逐步给出做法与理由
## Evidence         ← 实测数据，须标注工具版本、器件、测量口径
## Output Format
## Behavioral Constraints
````

frontmatter 只有 `name` 与 `description` 两项，其余信息放正文，这是官方的写法。

### `Log signatures` 是本仓库加的一行，不属于官方格式

官方技能由一个读过技能描述的智能体来挑选；本示范智能体是拿工具输出去匹配的，
而散文式的 Trigger（"User asks whether loops are flattenable"）不会出现在综合日志里。

因此约定：`- **Log signatures:**` 这一行里用反引号括起来的字符串，会被
`agent/skills.py` 逐个拿去在日志里做子串匹配，命中才注入上下文。没有这一行的技能
（包括所有官方技能）照常加载，只是不会因为某条错误而自动触发。

---

## 写技能的四条经验

**一、「何时不用」比「何时用」重要。** 一条不说明边界的技能，模型会在不适用的场合
照搬，引入新的失败。示范技能的 `Behavioral Constraints` 一节就是干这个的：明确写出
哪些做法不许用（例如不许用 `#ifndef` 绕开重复定义）。

**二、记录已证伪的做法。** 「试过 X，无效，因为 Y」这类条目直接节省综合轮次，而综合
轮次就是墙钟，墙钟就是分数。

**三、实测数据必须标注口径。** 一个漂亮的数字没有用，一个标注了工具版本、器件、
测量方式的数字才能被复用。

这一条有过教训：同一次 SHA-256 优化，按 HLS csynth 估算算出来 T_exec 提升 37.7%，
按 post-route 实测仅为 12.0%，估算值在基线上偏悲观 14.6%，在优化版上偏乐观 18.8%，
两者叠加把 12% 放大成三倍。**同一份代码、同一次实验，换个测量口径，结论差三倍。**
所以示范技能的 `Evidence` 一节写明了「Vitis HLS 2026.1，`xczu3eg-sbva484-1-e`，
5 ns，与测试台一并编译」，而不只是给一张表。

**四、技能不必涉及大模型。** 确定性的校验脚本、结构化的踩坑清单、一段能把综合日志
提取成结构化字段的正则，都是技能。评分标准是可复用性，不是是否调用模型。

---

## 几个值得写成技能的方向

以下为 HLS 侧常见的失败聚集处，供参考。该列表不应直接照抄提交，缺少实证支撑的
技能条目在工程质量项上不得分。带 ★ 的官方技能已覆盖，可直接取用。

| 方向               | 典型失败                                     | 官方是否已覆盖 |
| ------------------ | -------------------------------------------- | -------------- |
| 顶层接口契约       | 签名不符、重复定义头文件里的类型             | 否（本目录示范） |
| 可综合性           | STL、动态分配、递归、运行时循环边界          | ★ `hls-synthesizable` |
| pragma 作用域      | pragma 写在错误的层级，静默失效              | ★ `hls-pragma-scope` |
| dataflow 规范形式  | 违反 canonical form，报错或退化为串行        | ★ `hls-dataflow` |
| 循环展平           | 展平条件不满足，II 上不去                    | ★ `hls-flattenable` |
| 滑窗与行缓冲       | 行缓冲写法不对，II 卡在 2                    | ★ `hls-line-buffer` |
| 数组分割与端口冲突 | 调度失败，II 无法达到 1                      | 否             |
| 循环携带依赖       | 依赖分析失败，需要 `DEPENDENCE` 或结构改写   | 否             |
| 定点类型           | `ap_fixed` 位宽与量化模式的选取              | 否             |
| 自我验证           | 拿不到官方测试台时如何判断自己写对了         | 否，且是本赛道最缺的一环 |

最后一行是本赛道 L2 → L3 那 0.6 系数差的所在，官方技能包不覆盖它，因为它不是一个
HLS 问题，是一个智能体设计问题。
