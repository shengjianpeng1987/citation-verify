# citation-verify

核查 AI 生成文档（Word/PDF）里的引用是否真实存在。对于伪造的引用，自动到真实学术数据库里找最合适的替代，再核查，达成一致后才建议替换。

## 架构一览

```
Word/PDF
  ↓ parse_doc.py  (pdfplumber / python-docx)
参考文献段落原始文本
  ↓ codex exec (原子调用 #0 — 结构化解析)
citations.json — 结构化引用列表
  ↓
双通道并行核查，每条引用：
  ├─ Channel A: api_verify.py   (Crossref + OpenAlex + Semantic Scholar)
  └─ Channel B: codex exec       (原子调用 #1 — 独立判定)
  ↓ reconcile
final_label ∈ {valid, partially_valid, hallucinated, uncertain}
  ↓ (只对 hallucinated 走下面)
codex exec (原子调用 #2 — 搜候选 top-5)
  ↓
每个候选 ×  codex exec (原子调用 #3 — 语境契合度评分, 0-10)
  ↓
top_score ≥ 7 的最佳候选 → 再走一次 Channel A+B 核查
  ↓
都 valid → 标记 "confirmed_replacement"
```

**每个 codex 调用都是独立的 `codex exec --ephemeral --json --output-schema ...`，绝不用 `codex resume`。** 原子化是这套方案的核心设计——这样能并行、能失败隔离、每个 prompt 上下文干净。

## 快速开始（一条命令）

```bash
cd "/Users/shengjianpeng/Documents/citation verify/citation-verify"
./verify.sh tests/smoke.docx
```

完事。首次运行会自动：
1. 创建 `.venv/` 虚拟环境（不污染你系统的 Python）
2. 装 4 个 Python 依赖
3. 检测 codex CLI 是否就绪
4. 跑核查管线

之后每次运行直接 `./verify.sh <你的文件>` 即可，不需要 `source activate` 任何东西。

**诊断问题**：`./verify.sh --doctor` 查看 Python / venv / 依赖 / codex / API key 五项状态。

**只做 setup 不跑流程**：`./verify.sh --setup`

## 可选：加速 Channel A（Semantic Scholar 免费 key）

申请一个免费的 Semantic Scholar API key（1 分钟，[链接](https://www.semanticscholar.org/product/api)），然后：

```bash
export SEMANTIC_SCHOLAR_API_KEY="..."
# 如果要永久生效，加到你的 ~/.zshrc
echo 'export SEMANTIC_SCHOLAR_API_KEY="..."' >> ~/.zshrc
```

设了之后 Channel A 每条引用从 5-10 秒 → 1-2 秒。

## Codex 没装？

如果 `./verify.sh --doctor` 显示 "codex CLI not found"，去 [developers.openai.com/codex/cli](https://developers.openai.com/codex/cli) 装一下，然后 `codex login`。如果暂时不想装 codex，可以用 `--api-only` 模式先跑（只用 3 个学术库直接核查，精度略低但能用）：

```bash
./verify.sh tests/smoke.docx --api-only
```

## 完整参数

```bash
./verify.sh <input.pdf|input.docx> \
    --output-dir ./out \      # 输出目录，默认 <文件名>.citation-verify/
    --parallel 4 \            # 并发数，默认 4
    --limit 10                # 只处理前 N 条，调试用
    --api-only                # 跳过所有 codex 调用（没装 codex 时用）
    --no-replace              # 只核查，不找替代
```

输出目录结构：

```
<input-stem>.citation-verify/
├── citations.json       # 结构化引用
├── verdicts.json        # 每条的双通道核查结果 + 最终标签
├── replacements.json    # 替代方案（仅 hallucinated）
├── report.md            # 给人看的报告
└── _work/               # 中间文件（可删）
```

## 核心文件

| 文件 | 作用 |
|---|---|
| `SKILL.md` | Cowork/Claude 读取的 skill 规范；包含完整工作流程和约束 |
| `scripts/orchestrate.py` | 主编排器，串起整个管线 |
| `scripts/parse_doc.py` | 从 PDF/DOCX 提取参考文献段落 |
| `scripts/api_verify.py` | Channel A：直接调 Crossref/OpenAlex/S2 三个 API |
| `scripts/codex_atom.sh` | Codex 原子调用包装器（ephemeral + json + schema） |
| `scripts/render_report.py` | 生成 Markdown 报告 |
| `prompts/parse_references.md` | 原子任务：把参考文献文本变成结构化 JSON |
| `prompts/verify_citation.md` | 原子任务：核查单条引用真伪 |
| `prompts/find_alternatives.md` | 原子任务：为假引用找 top-5 真实候选 |
| `prompts/score_context_fit.md` | 原子任务：打分候选和上下文的契合度 |
| `schemas/*.json` | 每个原子任务的 `--output-schema`，保证 LLM 输出结构稳定 |

## 设计边界

- **只针对英文学术文献**。中文文献的覆盖面在 OpenAlex/Crossref 里有限；CNKI/万方没有免费 API，本 skill 不处理。遇到明显的中文引用会标 `out_of_scope`。
- **保守替换**。只有当 hallucinated 被双通道一致确认、候选 fit_score ≥ 7、而且候选本身再核查通过时，才标记 `confirmed_replacement`。`uncertain`（双通道分歧）的引用 **永远不会** 被自动替换。
- **证据驱动**。报告里每条 verdict 都带 DOI 链接或"在 X 库中未找到"的明确说明，不发表未支持的结论。
- **不修改你的原文档**。默认只产出报告；若要生成替换后的文档版本，未来可加 `--apply-replacements`（目前 v0 先不自动写回，避免破坏原件）。

## 已知限制

1. 参考文献段落定位靠启发式规则（找 "References" / "Bibliography" 等标题）。如果你的文档用了非标准标题，会 fallback 到"取最后 25%"——会在报告里给出 warning。
2. 双通道核查可能被 Crossref 的 API 限流（50 req/s）影响；如果 `--parallel` 调得很高可能需要退避重试。
3. Codex 的 `--json` 事件流在不同版本下事件 schema 有变化；`codex_atom.sh` 里已经做了兼容尝试，如果将来 codex 再升级 schema，调整 `codex_atom.sh` 末尾的 python 解析段即可。

## 反馈

如果遇到解析不对的情况，把 `_work/stage*_input_*.json` 附带一起反馈，可以复现具体那条原子任务。
