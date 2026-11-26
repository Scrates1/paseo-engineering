---
name: paseo-engineering
description: >-
  通用根源诊断与 Paseo 异构多 Agent 隔离开发与审查工作流。处理缺陷修复、性能优化、架构重构、核心功能开发或新方向技术调研时使用：主会话专职总诊协调（不直接写业务代码），经只读本质分流剥离表象与病根后，按三档流转在“守门员状态机 `scripts/flow.py` + Paseo 原生受管 Worktree”下调度独立开发与跨模型家族异构红队/审查，验证闭环后无冲突串行合入。
---

# Paseo 异构多 Agent 根源诊断与隔离工程工作流

本工作流通过 **职责分离 + Paseo 原生受管 Worktree 代码隔离 + 跨模型家族异构制衡**，并由**守门员状态机 `scripts/flow.py`** 对关键节点做确定性硬拦截（而非仅靠提示词自觉），杜绝“表象贴膏药”“单模型思维盲区”与“自写自审放水”。

## 1. 适用边界与子 Agent 防套娃守则

- **纯问答 / 状态核查**：直接回答，不创建 worktree，不派生子 Agent。
- **纯机械改字**（改指定文案、重命名指定常量等无逻辑判断与因果链的操作）：主会话直接修改并校验。
- **被委派子 Agent 铁律**：若当前处于子任务上下文（存在 `PASEO_PARENT_AGENT_ID`，或任务提示词明确限定为 `[Triage]` / `[Explorer]` / `[Red-Team]` / `[Worker]` / `[Reviewer]` 角色），**只执行本次受托的单一角色职责，严禁再次启动顶层协调流或继续向下套娃派单**。
- **Paseo 通道发现**：优先使用环境注入的 Paseo MCP（可用时参考 `paseo` 技能了解 schema）；无 MCP 时使用本机 `paseo` CLI（以 `paseo --help`、`paseo run --help` 为准）。当前会话若无 `PASEO_AGENT_ID` 且用户要求 Paseo 会话可见，先通过 Paseo 启动协调会话，禁止伪造父 Agent ID。

## 2. 六大角色体系与异构模型制衡铁律

除纯机械改字外，**主会话严禁既当调度裁判又直接下场写业务代码**，所有工程任务按以下六类角色分工协同：

| 角色代号 | 核心职责 | 工作区与读写红线 | 交付物 | 模型家族选型要求 |
| :--- | :--- | :--- | :--- | :--- |
| **`Coordinator`<br>总诊协调官**（主会话） | 意图识别、管理运行账本、快照主工作区、驱动守门员 `scripts/flow.py`、切分受管 worktree、派发与回收 Paseo 子会话、无冲突串行合入与最终集成验证 | 主工作区只读锚定与无冲突合入；**严禁直接编写业务代码或手工解合并冲突** | 派单指令、合入代码与最终验证报告 | 当前主会话模型 |
| **`[Triage]`<br>本质分流官** | 顺因果链剥离“症状点 `X`”与“不变量首次破坏源头 `Y`”，全仓同源普查，复合问题切片定档 | **只读约束**（禁改代码、禁在主目录跑产生副产物的构建；由协调官快照校验） | 《本质诊断与派单卡》 | 线索聚焦时由协调官只读兼任；跨度大时派独立长上下文/高推理子会话 |
| **`[Explorer]`<br>正交探路员** | Gear 2 沿三正交范式发散方案；Gear 3 按“外部路线横评 × 内部硬样本”双线摸底 | **只读约束** | 候选方案集或技术路线横评 | 当主机在线模型家族数 `N ≥ 2` 时，并行发散最多使用 `N-1` 个家族（预留 ≥1 个异构家族供红队使用） |
| **`[Red-Team]`<br>异构红队官** | 对照最新源码/字节码专门挑刺证伪候选方案（查重、找绕过漏口、算端到端上限）或做事前验尸 | **只读约束** | 证伪反例清单与淘汰建议 | **强制与被审候选方案的 `[Explorer]` 作者跨模型家族** |
| **`[Worker]`<br>隔离执行员** | `1 Worker = 1 独立分支 = 1 独立 Worktree`；首步先动态实证根因假设（不成立则退单），再完成源头实现、反例测试（或 PoC 探针）并在隔离分支完成提交 | **仅限所绑定的受管 worktree（`--workspace <workspaceId> --cwd <wt>`）及隔离包缓存内读写**；禁碰主工作区、禁写全局包缓存、禁 `git push` | 干净的隔离分支提交（commits）、反例测试与实测日志 | 按任务选强编码/强推理模型 |
| **`[Reviewer]`<br>异构审查与审计官** | 方案双预审、隔离分支 `git diff` 代码双后审（Gear 1/2）、探针与基准原始数据终审（Gear 2/3）；`BLOCKING` 须附可构造反例 | **只读约束**（直接审隔离 worktree 原件、diff 与原始日志，禁听口头摘要；审查前后核验 worktree `HEAD` 未被篡改） | 分级审查结论（`PASS` / `BLOCKING`） | **强制与对应 `[Worker]` 跨模型家族** |

- **跨模型家族异构定义（强制执行）**：委派前先通过 Paseo MCP 或 `paseo provider ls` / `paseo provider models <provider>` 查询当前在线模型家族数 `N`（如 `OpenAI Codex/GPT` 族、`Anthropic Claude` 族、`Google Gemini` 族）。**凡成对制衡角色（候选方案作者 `Explorer ↔ Red-Team`、`Worker ↔ Reviewer`）必须分属不同模型家族**（同家族大小号如 `Opus` 审 `Sonnet` **不算**异构；仅当整机 `N = 1` 时才允许同族降级并在交付报告中明示）。Provider 若提供物理只读沙箱模式则优先启用；否则通过角色提示词加协调官前后双快照（主工作区快照 + 隔离树 `HEAD` 快照）强制核验。

## 3. Stage 00 · 前置只读本质分流与三档路由

严禁按“预计改几行”给任务定性。动任何业务代码前必须先产出 **《本质诊断与派单卡》**，并**登记到守门员状态机**（`<skill-dir>` 为技能安装目录，如 `~/.paseo/skills/paseo-engineering`）：

```bash
python3 <skill-dir>/scripts/flow.py --task-id <task-id> init --repo <repo-root>
python3 <skill-dir>/scripts/flow.py --task-id <task-id> triage --symptom <X> --root <Y> --gear <1|2|3> [--lenses <csv>] [--slices <csv>] [--summary <text>]
```

派单卡不再只是文字约定：`triage` 会拒绝空的症状点/源头，且当 `X == Y` 时必须附带非空 `--same-site-justified <理由>`，用代码强制落实“禁贴膏药”红线。

1. **剥离表象与病根**：锁定症状点 `X` 与不变量首次被破坏的真实源头 `Y`，写明红线：**“禁止在症状点 `X` 做判空短路/吞异常等表象掩盖，必须在源头 `Y` 修复”**。
2. **同源普查与复合切片**：全仓检索同源模式一并纳入范围；混合型需求拆成正交子切片分别定档与排期。
3. **按本质挂入三档工作流**（并按问题属性叠加专项硬约束卡：性能必读 [references/lens-performance.md](references/lens-performance.md)，缺陷/漏误报必读 [references/lens-bug-precision.md](references/lens-bug-precision.md)，重构/架构必读 [references/lens-refactor-arch.md](references/lens-refactor-arch.md)）：
   - **Gear 1 · 源头快修（本质 A：源头唯一明确、无多方案分歧）** → **0 次人工停顿**，`triage --gear 1` 直达 `EXECUTION_READY`，随后走第 4 节隔离开发与异构快审闭环（`1 隔离 Worker + 1 异构 Reviewer`，省去发散与预审）。若构建/测试（`record-verify-fail`）或异构审查（`record-review --verdict BLOCKING`）连续 **2 轮**未通过，或发现跨层耦合，守门员**自动熔断升入 Gear 2**（`MUST_ESCALATE_GEAR2`；绝不带 `BLOCKING` 合入，也不在 Gear 1 原地拉锯）。
   - **Gear 2 · 深度攻坚（本质 B：多路径权衡、跨模块/跨上游库、严苛性能或精度要求）** → 读取 [references/mode-deep-solve.md](references/mode-deep-solve.md)（`Explorer` 三范式发散 → `Red-Team` 异构证伪 → **停顿 1 次与用户拍板** → 双视角预审 → 隔离并行 `Worker` → 双视角异构 `Reviewer` 与数据审计）。守门员路径：`triage` → `record-explore` → `record-redteam` → `align` → `record-prereview` → `EXECUTION_READY`。
   - **Gear 3 · 探索立项（本质 C：现有机制空白、`0 → 1` 路线未知）** → 读取 [references/mode-explore-spike.md](references/mode-explore-spike.md)（内外双线 `Explorer` → `Red-Team` 事前验尸 → **停顿 1 定 PoC 契约** → 隔离 `Worker` 跑轻量探针 + 强制异构 `[Reviewer-Audit]` 审计探针原始数据 → **停顿 2 定 Go/Pivot/Kill**；Go 后丢弃草稿探针并转入 Gear 2 后半段正式生产级落地）。守门员路径：`triage` → `record-explore` → `record-redteam` → `align --spike-hypothesis ... --spike-samples ... --go-criteria ...` → `EXECUTION_READY` → `isolate --kind spike` → … → `decide-spike --decision go --slices <prod-slices>`（随后 Gear 2 `record-prereview` + `isolate --kind production`）。
4. **重诊（Re-Triage）**：`[Worker]` 实证推翻根因假设或触发升档时，执行 `triage ... --re-triage`；它会作废此前的探路/红队/预审凭证与已对齐切片，并把所有未合入切片标记为 `SUPERSEDED`（只能丢弃，不能再合入）。

## 4. 守门员状态机与 Paseo 原生隔离五步闭环

### 4.1 软协议 + 硬守门员

本技能是**软协议**（角色、判断力、专项卡）；`scripts/flow.py` 是**硬守门员**：仅依赖标准库（Python 3.8+）的状态机，在 `$PASEO_HOME/runs/<task-id>/`（缺省 `~/.paseo/runs/<task-id>/`，文件权限 `0600`；可用 `--run-dir <dir>` 覆盖，`--paseo-home <dir>` 指向非默认 Paseo 主目录）下原子维护 `state.json` + `status.md`。**所有关键节点必须过守门员，严禁手改 `state.json`。** 以下 5 类违规由确定性代码硬拦截，而非靠提示词自觉：

| # | 被拦截的违规 | 守门员如何强制 |
| :--- | :--- | :--- |
| 1 | **同族互审**（自写自审放水） | `enter-review` 拒绝与该切片 `[Worker]` 归一化模型家族相同的审查员；`record-prereview` / `record-redteam` 对计划 Worker / 探路员同理。`--single-family-host` 并非免费自报：若在线探测到 ≥ 2 个模型家族则**直接驳回**。 |
| 2 | **未 commit，或审后追加未审 commit** | `enter-review` 要求隔离树干净且 `rev-list --count <SLICE_BASE>..HEAD > 0`，并拒绝对刚被驳回的同一 `HEAD` 原样重提；`record-review` 复核 `HEAD == wt_head_sha`；`integrate` 要求隔离树与分支引用都等于 `approved_head_sha`。 |
| 3 | **主目录被篡改**（含未跟踪文件字节篡改） | 每个节点都把 `HEAD` **与** `main_diff_hash`（`git status -uall`、`git diff --binary HEAD`，外加每个未跟踪文件字节与权限位的 SHA-256）同记录快照比对。 |
| 4 | **绕过 2 轮封顶** | `review_rounds` / `verify_fail_rounds` 记录在 `state.json`：Gear 1 满 2 轮 → `MUST_ESCALATE_GEAR2`；Gear 2/3 满 2 轮 → `ROUND_CAP_REACHED`，此后只能走 `resolve-dispute`（重诊 / 丢弃 / 升级用户）；这些状态下 `assign-worker` 一律拒绝。 |
| 5 | **带病 / 有冲突合入，或合并 `spike` / `probe` 分支** | `integrate` 要求 `kind == production`、`state == REVIEW_PASSED`、`open_blockers == 0` 且存在固定的 `approved_head_sha`；先试合并，冲突则中止并置 `NEEDS_REBASE`（之后 `mark-rebased` 会强制完整异构重审）。 |

`status.md` 始终展示当前任务/切片状态与下一步合法命令；也可用 `flow.py status [--json]` 随时查看。

**有界逃生口**：`--re-triage`（第 3 节）是合规的改道方式。`--user-override "<非空理由>"` **仅能**跳过**工作流路由 / 检查点顺序**（用户明确说“直接跑”时）；**永远不能**绕过物理安全门禁：跨模型家族配对、合入前干净已提交且 0 个未决 blocker 的 `approved_head_sha`、`spike`/`probe` 不可合入、无冲突合入。

### 4.2 子命令地图

| 阶段 | 守门员命令（合法顺序） |
| :--- | :--- |
| 建账与分流 | `init` → `triage` |
| Gear 2 / 3 探源 | `record-explore` → `record-redteam` → `align` → *（仅 Gear 2）* `record-prereview` |
| 隔离与实现 | `isolate` → `assign-worker` → *（构建/测试失败时）* `record-verify-fail` |
| 异构审查 | `enter-review` → `record-review` *（Gear 2：视角 `A` 与 `B` 须在同一 `wt_head_sha` 上都 `PASS`；探针用 `audit`）* → 有争议时 `resolve-dispute` |
| 落地 | `integrate` *（冲突 → Worker rebase → `mark-rebased` → 重新审查）* → `verify-integration` |
| 探针 / 弃置 | `decide-spike --decision go\|pivot\|kill [--slices <prod-slices>]` *（`go` 后用 `--slices` 指定全新生产切片，缺省 `<id>-prod`）* · `discard-slice` |

### 4.3 五步闭环

Gear 1 与 Gear 2 的生产代码交付均严格执行以下五步闭环（Gear 3 探针阶段复用第 1～3 步做隔离实验，并以异构数据审计替代生产代码风格审查）：

1. **快照主工作区与切分 Paseo 原生受管 Worktree（Snapshot & Isolate）**
   - `init` 已记录基线 `BASE_SHA` 与主工作区快照 `MAIN_DIFF_HASH`（即 `main_diff_hash`），原样保留用户已有未提交改动；串行合入后 `integrate` 会刷新两者。
   - 为每个写入切片执行 **`python3 <skill-dir>/scripts/flow.py ... isolate --slice <id> --branch <branch> [--kind production|spike|probe] [--backend auto|paseo|git] [--apply-dirty-patch]`** 创建独立分支与物理目录。同仓切片默认 `auto` 后端依次调用 `paseo project create` + `paseo workspace create --isolation worktree --mode branch-off --new-branch <branch> --base <BASE_SHA>`，产出带独立 `workspaceId` 的 **Paseo 原生受管 Worktree**；它会拒绝已存在的分支名（避免 Paseo 静默改名/忽略基线的陷阱），基线固定为明确的 40 位 `BASE_SHA`（绝不用字面量 `HEAD`），创建后核验分支与 `HEAD`，并记录 `workspaceId`、`cwd` 与 `slice_base`。仅当目标为外部仓库，或 Paseo 缺失/守护进程不可达时，`--backend auto` 才回退为 `git worktree add -b <branch> <dir> <BASE_SHA>`（`--backend paseo` 则直接硬失败）。
   - `kind` 与档位强绑定：`production` 仅限 Gear 1，或 Gear 2 `EXECUTION_READY` 且已对齐的切片；`spike` 仅限 Gear 3 `EXECUTION_READY`；`probe`（可丢弃微探针）仅限 Gear 2 `EXPLORED`/`FALSIFIED`。
   - 若本次任务明确依赖主工作区未提交改动，传 `--apply-dirty-patch`：补丁会在隔离树内单独提交为前置基线 commit，`SLICE_BASE` 更新为该 commit 并固定其 SHA-256，使后续审查只审 `Worker` 自身增量；此类切片合入时必须使用 `integrate --into-worktree <干净树>`，严禁静默代用户在脏主目录提交。凡执行任何会写入包缓存的命令（如 `mvn install`、`pip install` 或修改上游二方库），必须配置隔离本地缓存目录（如独立 `-Dmaven.repo.local` / 独立虚拟环境），严禁污染全局共享缓存。
2. **显式启动 Paseo 角色子会话（Dispatch）**
   - 通过 Paseo MCP 或 CLI，**同时绑定受管 Workspace 与物理目录**启动各角色：`paseo run --no-wait -q --provider <p> --model <m> --workspace <workspaceId> --cwd <独立worktree绝对路径> --title "[Worker] <slice>"`。只传 `--cwd` 可能让会话仍挂在父级 `workspaceId` 上跑偏；双重绑定可彻底堵住。随后用 `assign-worker --slice <id> --model <provider/model> [--agent-id <id>]` 登记，状态机会记录归一化 `worker_family` 并把切片推进到 `IMPLEMENTING`（Windows 下子任务每次命令须显式 `Set-Location -LiteralPath '<worktree路径>'`；跨 Host 时核实可达 Host、代码与模型并维护 `{serverId, agentId, workspaceId, cwd}` 映射）。
   - 委派指令须包含：目标与验收口径、《本质诊断与派单卡》（源头 `Y` 与禁贴膏药红线）、挂载的 `lens-*.md` 路径、可修改范围及验证命令。
3. **隔离分支内“动态实证 → 源头实现 → 反例测试 → 本地提交”（Implement & Commit）**
   - **`[Worker]` 退单权**：第一步先用最小测试或运行探针证实派单卡的根因假设；若动态实证推翻假设或修改 `Y` 会破坏既有契约，**严禁强行硬改交差**，必须附实证数据退回协调官重诊（Re-triage）或升档。
   - 假设证实后，在隔离 worktree 内完成源头修复、同源点收敛与自动化反例/回归测试，并在隔离分支内完成干净的本地 Git 提交（不留未跟踪构建垃圾）。构建/测试失败轮次用 `record-verify-fail --slice <id> --summary <text>` 记账（Gear 1 满 2 轮 ⇒ `MUST_ESCALATE_GEAR2`）。
4. **提交完整性门禁与异构模型原始 Diff 审查（Cross-Model Review）**
   - **`enter-review --slice <id> --reviewer-model <provider/model> [--lens default|A|B|audit]`** 即协调官的前快照：核验 ① 主工作区 `HEAD` + `main_diff_hash` 一致；② `git -C <wt> status --porcelain` 为空；③ `git -C <wt> rev-list --count <SLICE_BASE>..HEAD` 大于 `0`；④ 审查员家族 ≠ Worker 家族；⑤ `HEAD` ≠ 上次被驳回的 `HEAD`，并记录 `wt_head_sha`。Gear 2 的第二视角（`--lens B`）在**同一个** `wt_head_sha` 上追加。
   - 启动**与 `[Worker]` 不同模型家族的只读 `[Reviewer]`**（同样以 `--workspace <workspaceId> --cwd <wt>` 绑定），仅传入隔离 worktree 路径、`git diff <SLICE_BASE>...HEAD`、真实测试日志路径与**中立审查问题**（严禁喂倾向性摘要）。
   - **`record-review --slice <id> --verdict <PASS|BLOCKING> --blockers <n> [--lens ...] [--counterexample <text>]`** 即后快照：再次核验 `HEAD == wt_head_sha`、隔离树干净、主工作区未变，防止无沙箱的审查员误改隔离树。`BLOCKING` 必须 `blockers ≥ 1` 且附非空可构造反例（否则归为 `OPTIONAL`）。
   - **闭环与两轮上限**：有效 `BLOCKING` 交回原隔离 `[Worker]` 修复提交（`CHANGES_REQUESTED`），再经新的 `enter-review` 由**同一异构 `[Reviewer]` 同时复核增量改动与完整 `git diff <SLICE_BASE>...HEAD`**，直至 `0 BLOCKING`：
     - **Gear 1** 满 **2 轮**仍未清零：守门员自动升入 **Gear 2**；
     - **Gear 2** 满 **2 轮**仍未清零（`ROUND_CAP_REACHED`）：使用 `resolve-dispute --action re-triage|discard|user-escalate --reason <text>`。争议绝不会被静默转为 `PASS`：仅当审查方未能给出可构造反例时，才可经记录在案的反驳降级为 `OPTIONAL`（反驳实证记入 `status.md`）；真实架构取舍分歧升级交用户拍板（`AWAITING_USER_RULING`）；若属实现者连续两轮修不好确凿缺陷，则**退回重诊（Re-triage）或归档丢弃该候选切片**——**任何情况下严禁带着未解决的有效 `BLOCKING` 合入**。
5. **无冲突串行合入、集成终验与现场清理（Integrate or Discard）**
   - **严禁协调官手工解代码冲突**：**`integrate --slice <id> [--into-worktree <干净树>]`** 仅当 **测试全过 + 异构审查达到 `REVIEW_PASSED`（`0 BLOCKING`、固定 `approved_head_sha`）+ 专项卡实证达标** 时串行合入。优先 `--ff-only`；否则先试合并 `merge --no-commit --no-ff`，冲突即中止并置 `NEEDS_REBASE`。协调官**不得亲手改代码解冲突**，必须让该切片原 `[Worker]` 在其隔离树内 `rebase` 到新目标顶端、解冲突并重跑测试，再执行 `mark-rebased --slice <id> --new-slice-base <sha>`（会清除此前的审批并退回 `IMPLEMENTING`），经完整异构重审后才能再次合入。若主工作区有用户未提交文件，原地合入会被拒绝：改走 `--into-worktree` 交付或先征求用户确认。
   - 全部已对齐切片 `INTEGRATED` 后，任务进入 `MERGED_PENDING_VERIFY`。在最终合并树上执行 **`verify-integration --cmd "<测试或构建命令>"`**：仅当退出码为 `0`，才对每个已合入切片执行 `paseo workspace archive <workspaceId>`（或 `git worktree remove`）、确认目录已消失、删除临时本地分支（`git branch -D`），并将任务置为 `COMPLETED`。
   - 若候选方案实证未达标、切片被弃用或探针判 Kill，先归档完整证据与审查记录，再执行 `discard-slice --slice <id> --reason <text>`（探针用 `decide-spike`，它会归档 workspace 并删除 `spike/probe` 分支）干净移除受管 workspace/worktree 与分支。

## 5. 运行态容错、负载互斥与权限红线

- **重负载互斥预算**：读代码、静态审查、独立 worktree 编码可并行（常规同时不超过 2～3 个活跃子会话）；**全量测试、大型编译打包、正式基准测量必须检查宿主机负载并串行/限核执行**。
- **磁盘断点账本与异构接力**：守门员自 `init` 起在 `$PASEO_HOME/runs/<task-id>/state.json`（机器可信账本）与自动渲染的 `status.md`（缺省 `~/.paseo/runs/<task-id>/`）记录派单卡、子会话 ID/模型、`workspaceId` ↔ worktree 映射、轮次计数、已过门禁与下一步合法命令；证据路径写入各命令的 `--summary`。服务重启或续跑时先执行 `flow.py status` 并读账本恢复，不重复派工；优先依赖完成通知回收（`paseo wait` / MCP 通知，避免高频轮询）；单模型遇配额上限（Quota）或心跳超时立即切换异构模型接力（新 Worker/Reviewer 仍需通过家族门禁），禁止原地死循环重试。
- **守门员裁决为准**：守门员拒绝某条命令时，应修复根本条件（补提交、重审、rebase、换模型家族），严禁手改 `state.json`、伪造参数，除非用户明确授权跳过流程顺序，否则也不要动用 `--user-override`。若运行环境没有 Paseo（或 Python），则手工遵循同一套检查点，并在最终报告中如实声明硬门禁未被机器强制。
- **外部动作收口与坑点沉淀**：任何子 Agent 严禁擅自执行 `git push`、创建/修改 PR/MR/Issue、删除外部已有分支、部署或对外发消息（统一由协调官按当次会话用户明确授权执行）。收尾时若排除了**反直觉的仓库级隐式陷阱**，建议浓缩单行写入项目 `AGENTS.md` 避坑区；最终报告须如实列出根因、工作区/分支、参与的各 Paseo 角色会话与模型、真实执行的测试证据及未执行项。
