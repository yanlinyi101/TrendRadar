# TrendRadar 打分与分类优化方案

> 灵感来自数字生命卡兹克的 AIHOT 平台
> （文章: https://finance.sina.com.cn/cj/2026-05-07/doc-inhwzrtr5282684.shtml ；
>  产品: https://aihot.virxact.com/ ）
>
> 核心思想一句话：**AI 给"事实"打分，代码定"排名"** —— 用确定性的代码权重把
> 大模型的主观评分锚定到信源权威性、内容类型、时效衰减等可量化的维度上。

---

## 0. 当前 TrendRadar 的打分链路（基线）

```
news (热榜/RSS) ──► AI 兴趣分类 (filter.py)
                    │  最高分标签的 relevance_score ∈ [0,1]
                    ▼
                ai_filter.min_score 阈值 ──► 入选 / 落选
                    │
                    ▼
                展示排序 = priority_sort_enabled ? 标签优先级 : 标签命中条数
                标签内排序 = relevance_score DESC
```

**短板**:

| 问题 | 表现 |
|---|---|
| 信源不分级 | OpenAI 官博与某 KOL 转发的二手解读拿到同样的 0.8 分 |
| 单一阈值 | `min_score=0.7` 一刀切，导致一手信源被误杀、KOL 噪音被放过 |
| 无事件聚合 | 同一新闻被 5 个号转发就出现 5 次，重复消耗注意力 |
| AI 单维度 | 只算"相关度"，不区分"重要性 / 新颖性 / 深度 / 可操作性 / 争议性" |

---

## 1. 新增信源分级（T1 / T1.5 / T2）

### 1.1 分级定义

| Tier | 含义 | 权重 | 推送阈值（建议） | 例子 |
|---|---|---|---|---|
| **T1** | 一手信息（官方博客/官方新闻稿/CEO 个人 blog） | **1.50** | 0.55 | OpenAI Blog, Anthropic Newsroom, DeepMind Blog, Apple ML Research, NVIDIA, Hugging Face, Cloudflare, Sam Altman 个人博客 |
| **T1.5** | 一手二手之间（官方 X / 官方账号转发） | **1.20** | 0.65 | @OpenAI, @AnthropicAI, @GeminiApp, @Replit, @xai, @perplexity_ai, @TencentHunyuan, 智谱/Kimi/MiniMax 官推 |
| **T2** | KOL 个人观点 / 综合资讯站 / 公众号 | **1.00** | 0.70 | Karpathy, Marc Andreessen, swyx, Ethan Mollick, 量子位/新智元/机器之心, IT之家, Hacker News, The Decoder, freeCodeCamp |

**为什么这样定**：
- 一手信源的 0.55 分通常已经很值钱（信息密度高、噪音少），可以放低阈值；
- KOL 转发评测同一件事会被 0.85 分淹没榜单，提高门槛能逼出真正高分内容。

### 1.2 配置层 schema 改动（建议）

`config/config.yaml`：每个 RSS feed 与 platform source 加可选 `tier` 字段。

```yaml
rss:
  feeds:
    - id: "openai-blog"
      name: "OpenAI Blog"
      url: "https://openai.com/news/rss.xml"
      tier: "T1"           # 新增，缺省时按 source_tier_default 处理
      max_age_days: 3

    - id: "openai-twitter"
      name: "OpenAI (@OpenAI)"
      url: "https://rsshub.app/twitter/user/OpenAI"
      tier: "T1.5"
      max_age_days: 3

    - id: "kimmonismus"
      name: "Chubby (kimmonismus)"
      url: "https://rsshub.app/twitter/user/kimmonismus"
      tier: "T2"
      max_age_days: 3
```

新增全局段：

```yaml
# 信源分级与权重（新增）
source_tier:
  enabled: true
  default_tier: "T2"               # 没有标 tier 的信源默认值
  weights:
    T1: 1.50
    T1.5: 1.20
    T2: 1.00
  # 不同 tier 使用不同的推送阈值（覆盖 ai_filter.min_score）
  per_tier_min_score:
    T1: 0.55
    T1.5: 0.65
    T2: 0.70
```

---

## 2. 最终分数公式（核心改动）

### 2.1 公式

```
final_score = ai_relevance × tier_weight × freshness_decay
```

其中：

- `ai_relevance` ∈ [0, 1] —— 现有 AIFilter 输出
- `tier_weight` ∈ {1.50, 1.20, 1.00}
- `freshness_decay = 0.5 ^ (age_hours / half_life_hours)`，`half_life_hours` 默认 24

> 半衰期机制让"昨天的 0.85 分"和"今早的 0.62 分"自然区分开，避免日报里一直挂着隔夜内容。

### 2.2 入选规则

```
入选 = ai_relevance >= per_tier_min_score[tier]
```

注意阈值用的是**原始 ai_relevance**，不是 final_score。这样保证：
- 阈值的语义稳定（"AI 觉得相关度 ≥ X"），便于调参；
- final_score 只用于**入选后的排序**。

### 2.3 实现位置

| 改动点 | 文件 | 工作量 |
|---|---|---|
| Feed/Platform 配置加载 `tier` 字段 | `trendradar/core/config.py`（或 `context.py` 装载处） | 小 |
| Filter 入选阈值改为 per-tier | `trendradar/ai/filter.py` 或 `context.py:1002` | 小 |
| 排序时算 final_score | `context.py:895` 周边（聚合阶段） | 中 |
| SQLite schema 加列 `final_score` | `storage/sqlite_mixin.py:1534` | 中（带 migration） |

> ⚠️ schema 变更建议放第二阶段；第一阶段先在内存中算 final_score，用它替代现在 ORDER BY relevance_score DESC 的排序键即可，不动数据库。

---

## 3. 多维 AI 评分（5 个维度）

把 `ai_filter` 的提示词从"输出一个 score"改成"输出 5 个分量"，再用代码加权得到 `ai_relevance`。

### 3.1 维度

| 维度 | 含义 | 权重建议 |
|---|---|---|
| `importance` | 这件事在领域里值不值得知道 | 0.30 |
| `novelty` | 是否新颖、过去 7 天是否被充分报道过 | 0.25 |
| `depth` | 是不是带数据/代码/实验的硬内容 | 0.20 |
| `actionable` | 用户能不能拿来直接用（API/工具/教程） | 0.15 |
| `controversy` | 是否引起社区讨论（弱信号） | 0.10 |

```
ai_relevance = Σ (dim_score × dim_weight)
```

### 3.2 提示词改动

`config/ai_filter/prompt.txt`，输出 JSON 改为：

```jsonc
[
  {
    "id": 12,
    "tag_id": 3,
    "scores": {
      "importance": 0.85,
      "novelty":    0.70,
      "depth":      0.60,
      "actionable": 0.40,
      "controversy":0.20
    }
  }
]
```

`filter.py:_parse_classify_response` 需兼容新旧格式：检测到 `scores` 时按维度加权，否则回退到旧 `score` 字段。**这一步建议作为第三阶段**，第一阶段先把分级权重落地，效果验证再投资改 prompt。

---

## 4. 事件聚类（同一新闻只出现一次）

AIHOT 的做法：**embedding 相似度聚簇 + 簇内按权威度选主条**。

### 4.1 简化版方案（不引入向量数据库）

第一阶段用便宜方案：**标题文本 SimHash / MinHash**：

1. 抓取后对每条标题做 SimHash（64-bit）；
2. 24 小时窗口内汉明距离 ≤ 6 的视为同一事件簇；
3. 簇内按 tier 选 representative（T1 > T1.5 > T2），同 tier 看 ai_relevance；
4. 非 representative 的条目折叠（数据库保留，展示时合并成"另有 N 条相关报道"）。

### 4.2 进阶版（embedding）

待事件量上来后再做：
- 用 OpenAI `text-embedding-3-small` 或本地 `bge-small-zh` 把标题+摘要前 200 字向量化；
- pgvector / SQLite-VSS / 内存 KNN，cosine ≥ 0.85 视为同事件；
- 每天清缓存，避免向量库无限膨胀。

---

## 5. 实施分阶段（建议落地顺序）

| 阶段 | 工作量 | 价值 | 风险 |
|---|---|---|---|
| **Phase 1：信源分级 + tier 权重 + per-tier 阈值** | 0.5 天 | ⭐⭐⭐⭐ 立刻把噪音 KOL 压到底 | 低（纯加法） |
| Phase 2：freshness 半衰期 | 0.5 天 | ⭐⭐⭐ 隔夜内容自然衰减 | 低 |
| Phase 3：事件聚类（SimHash 简化版） | 1 天 | ⭐⭐⭐⭐ 减少重复，干净度↑ | 中（需要 dedupe 逻辑测试） |
| Phase 4：5 维 AI 评分 | 1.5 天 | ⭐⭐⭐ 长期更精细 | 中（prompt 调优 + token 成本↑） |
| Phase 5：embedding 聚类 | 2+ 天 | ⭐⭐⭐ 跨语言/同义事件聚合 | 高（依赖外部服务） |

---

## 6. 已经在 config.yaml 落地的事

- ✅ 新增 17 个借鉴 AIHOT 的信源（Apple ML / NVIDIA / The Decoder / IT之家 / Interconnects / swyx / op7418 / vista8 / emollick / kimmonismus / rohanpaul_ai / shao__meng / AYi_AInotes / Perplexity / GeminiApp / xAI / TencentHunyuan / Replit）
- ✅ Phase 1：source_tier 配置段（T1=1.5 / T1.5=1.2 / T2=1.0 权重 + per-tier 阈值 0.55/0.65/0.70）
- ✅ Phase 2：freshness_decay 配置段（half_life_hours=24，min_decay=0.05）
- ✅ Phase 3：event_clustering 配置段（SimHash 64-bit，threshold=16）
- ✅ Phase 4：prompt_multi_dim.txt + dim_weights 配置段

## 8. Phase 4 阈值校准（重要！）

切到 5 维评分后，relevance_score 是 5 个维度的加权平均：

```
ai_relevance = 0.30×importance + 0.25×novelty + 0.20×depth
             + 0.15×actionable + 0.10×controversy
```

经验值：一条**很重要、很新、但深度一般**的新闻（importance=0.9, novelty=0.8,
depth=0.4, actionable=0.3, controversy=0.2）聚合后 ≈ **0.615**。

也就是说，**5 维下的 0.6 ≈ 旧单分模式的 0.8**。如果你直接套旧的阈值
(T1≥0.55 / T1.5≥0.65 / T2≥0.70)，会把 90% 的好内容误杀。

**建议第一周先把所有阈值砍掉一档**：

```yaml
source_tier:
  per_tier_min_score:
    T1: 0.40    # 原 0.55
    T1.5: 0.50  # 原 0.65
    T2: 0.55    # 原 0.70
```

跑 3-5 天后看 `output/trendradar.log` 里 "tier 命中" 行的分布，按需微调。

如果嫌 5 维评分让分数不够"聚拢"，可以调整 dim_weights 让重要性权重更高：

```yaml
ai_filter:
  dim_weights:
    importance: 0.45    # 原 0.30
    novelty: 0.25
    depth: 0.15
    actionable: 0.10
    controversy: 0.05
```

---

## 7. 验收口径

跑完 Phase 1 后，在日报里观察：
1. T1 信源（OpenAI Blog 等）即便 AI 给 0.6 也能进榜（验证 per-tier 阈值生效）；
2. T2 KOL 互相转发的同一事件，分数明显被压低、排在 T1 之后（验证 tier_weight 生效）；
3. 总入选条数与之前持平或略减（说明门槛"更严但更准"，不是单纯放水）。

如果出现 T1 内容被淹没在尾部，说明 tier_weight 还要再放大；如果 T2 KOL 完全消失，说明阈值过严，把 T2 的 min_score 从 0.70 降回 0.65。
