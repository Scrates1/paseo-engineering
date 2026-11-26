# Gear 3 · 探索与新方向立项流（0 → 1：多 Agent 调研、事前验尸与隔离 PoC）

适用于开辟新方向、引入新机制/新算法、技术路线未定，或核心假设尚未在真实业务样本上被证实的探索任务。核心原则：**通过 Paseo 多 Agent 分工先花 10% 成本完成“双线调研 + 异构事前验尸 + 隔离轻量 PoC + 异构数据审计”，方向证实可行后再切入 Gear 2 生产级门禁**。

---

## Step 1 · 内外双线并行摸底（2 个并行 Paseo `[Explorer]` 只读子会话）

协调官执行 `python3 <skill-dir>/scripts/flow.py --task-id <task-id> init --repo <repo-root>` 与 `triage --symptom <X> --root <Y> --gear 3`，由守门员在 `$PASEO_HOME/runs/<task-id>/`（缺省 `~/.paseo/runs/<task-id>/`）维护 `state.json` + `status.md` 账本后，通过 Paseo 并行启动两个互补的只读调研会话（预留至少 1 个异构模型家族供红队使用），并以 `record-explore --author-models <csv> --summary <text>` 登记（`TRIAGED` → `RECON_DONE`）：

- **`[Explorer-Outward]` · 外部技术路线横评（向外看）**
  - 梳理业界成熟系统、开源实现、标准协议或学术论文中的 2～4 条代表性技术流派。
  - 拒绝宣传话术：提取每条路线的**核心前提假设、能力上限（天然解不了什么）、公认工程坑点与长期维护代价**。
- **`[Explorer-Inward]` · 内部场景与底座盘点（向内看）**
  - 从当前仓库与真实业务数据中提取 **3～5 个最具代表性的硬痛点样本**（而非玩具样例）。
  - 盘点现有架构承接接口、输入特征及 CPU/内存/延迟硬约束。

## Step 2 · 跨模型异构红队事前验尸（Paseo `[Red-Team]` 只读子会话）

启动**与 `[Explorer]` 不同模型家族的只读 `[Red-Team]` 子会话**，执行“事前验尸”，并以 `record-redteam --model <provider/model> --summary <text>` 登记（`RECON_DONE` → `PREMORTEM_DONE`；红队模型与探路员同族会被守门员拒绝，除非经核实的 `--single-family-host`）：

- **审讯视角**：“假设半年后该新方向落地失败被迫废弃，最致命的死因是什么？”
- 拿 `[Explorer-Inward]` 提取的**真实复杂样本与底座硬约束**，逐条碰撞 `[Explorer-Outward]` 的候选路线，抓出精度崩塌、性能爆炸、依赖锁死或架构水土不服的死穴，筛出 1～2 条值得实测的候选路线。

## Step 3 · 第一次拍板：敲定最小可证伪探针契约（Spike Contract）

协调官输出精炼的 **《新方向路线横评与 PoC 契约建议》**，**停顿与用户第一次探讨拍板**：

- 选定 1（或 2）条路线做探针实验；
- 锁定 **Spike 契约**：① 唯一待验证的核心假设；② 测试的真实硬样本清单；③ 定量/定性的 **Go（立项）** 与 **Kill（放弃）** 阈值。*(若仅需调研报告，交付经红队审校的结论后到此结束。)* 以 `python3 <skill-dir>/scripts/flow.py --task-id <task-id> align --slices <spike-slice> --spike-hypothesis <h> --spike-samples <s> --go-criteria <g>` 登记拍板（`PREMORTEM_DONE` → `EXECUTION_READY`），三项契约字段缺一不可。

## Step 4 · 隔离受管 Worktree 轻量 PoC 探针 + 强制异构数据审计

- 守门员 `scripts/flow.py` 已在 `init` 时固定 `BASE_SHA` 与主工作区快照。为每条路线创建独立临时 Paseo 原生受管 Worktree（A/B 双路线对比则建两个切片并行，包缓存独立隔离）：
  ```bash
  python3 <skill-dir>/scripts/flow.py --task-id <task-id> isolate --slice <spike-slice> --branch spike/<topic> --kind spike [--backend auto|paseo|git]
  ```
  `kind spike` 仅限 Gear 3 `EXECUTION_READY` 且切片已在 `align --slices` 中。`auto` 后端使用 `paseo project create` + `paseo workspace create --isolation worktree --mode branch-off --new-branch spike/<topic> --base <BASE_SHA>`（仅外部仓库或 Paseo 不可用时回退 `git worktree add -b`）。用 Workspace + 目录双重绑定启动 `[Worker]`（`paseo run --no-wait -q --workspace <workspaceId> --cwd <wt> --title "[Worker-Spike] <route>"`），并以 `assign-worker --slice <spike-slice> --model <provider/model>` 登记。
- **豁免生产代码打磨，强制异构审计探针数据真实性**：
  - PoC 代码免除全量边界打磨与风格审查，以最快速度在真实硬样本上跑通核心机制并提交在探针分支；
  - **严禁伪造结果**：禁止硬编码样本答案、合成假桩或只挑简单样本报喜；`[Worker]` 完成后，协调官必须启动 **1 个跨模型家族的只读 `[Reviewer-Audit]`** 核验探针代码未作弊、主工作区仍与快照一致且原始日志/耗时/内存/命中统计真实无水分。以 `enter-review --slice <spike-slice> --reviewer-model <provider/model> --lens audit` 把关（隔离树干净已提交，且审查员家族异于 `[Worker]`），并用 `record-review --slice <spike-slice> --verdict PASS|BLOCKING --blockers <n> --lens audit` 登记；`PASS` 后切片进入 `SPIKE_AUDITED`。
- `spike` / `probe` 切片**永远**无法 `integrate`：粗糙原型代码从机制上不可合入。

## Step 5 · 第二次拍板：Go / Pivot / Kill 裁决与流转

协调官汇报经异构审计核实的真实探针表现与天花板，**停顿等待第二次拍板**，并以 `decide-spike --slice <spike-slice> --decision go|pivot|kill [--slices <prod-slices>] --summary <text>` 登记裁决（要求 `SPIKE_AUDITED`）。无论哪种裁决，守门员都会归档探针 workspace（`paseo workspace archive`，或 `git worktree remove`）并删除 `spike/<topic>` 分支：

- **Go（确认立项）**：严禁将粗糙 PoC 直接合入主干。使用 `decide-spike --slice <spike-slice> --decision go --slices <prod-slices> --summary <text>`，其中 `--slices` 指定转入 Gear 2 后**全新的生产切片**列表（省略时默认生成 `<spike-slice>-prod`）。任务转入 Gear 2 `ALIGNED`：先执行 `record-prereview`（双视角异构预审），再 `isolate --kind production` 创建**全新**受管 worktree，无缝切入 [mode-deep-solve.md](mode-deep-solve.md) **后半段（Stage 2 规范实现与反例测试 → Stage 3 跨模型双后审与无冲突串行合入）**。
- **Pivot（切换路线）**：任务回到 `PREMORTEM_DONE`；在 `status.md` 归档本轮实测边界，回到 **Step 3** 与用户确认新路线的 Spike 契约（再次 `align --spike-hypothesis ...`）后再跑下一轮轻量探针。
- **Kill（低成本终止）**：归档不可行实证结论；任务置为 `DISCARDED`，临时探针 worktree 与分支被移除，主工作区保持原状零污染。
