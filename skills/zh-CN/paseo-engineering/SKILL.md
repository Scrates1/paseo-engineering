---
name: paseo-engineering
description: >-
  通用根源诊断与 Paseo 异构多 Agent 隔离开发与审查工作流。处理缺陷修复、性能优化、架构重构、核心功能开发或新方向技术调研时使用：主会话专职总诊协调（不直接写业务代码），经只读本质分流剥离表象与病根后，按三档流转调度 Paseo 独立 Git worktree 开发与跨模型家族异构红队/审查，验证闭环后无冲突串行合入。
---

# Paseo 异构多 Agent 根源诊断与隔离工程工作流

本工作流通过 **职责分离 + 独立 Git Worktree 代码隔离 + 跨模型家族异构制衡**，杜绝“表象贴膏药”“单模型思维盲区”与“自写自审放水”。

## 1. 适用边界与子 Agent 防套娃守则

- **纯问答 / 状态核查**：直接回答，不创建 worktree，不派生子 Agent。
- **纯机械改字**（改指定文案、重命名指定常量等无逻辑判断与因果链的操作）：主会话直接修改并校验。
- **被委派子 Agent 铁律**：若当前处于子任务上下文（存在 `PASEO_PARENT_AGENT_ID`，或任务提示词明确限定为 `[Triage]` / `[Explorer]` / `[Red-Team]` / `[Worker]` / `[Reviewer]` 角色），**只执行本次受托的单一角色职责，严禁再次启动顶层协调流或继续向下套娃派单**。
- **Paseo 通道发现**：优先使用环境注入的 Paseo MCP（可用时参考 `paseo` 技能了解 schema）；无 MCP 时使用本机 `paseo` CLI（以 `paseo --help`、`paseo run --help` 为准）。当前会话若无 `PASEO_AGENT_ID` 且用户要求 Paseo 会话可见，先通过 Paseo 启动协调会话，禁止伪造父 Agent ID。

## 2. 六大角色体系与异构模型制衡铁律

除纯机械改字外，**主会话严禁既当调度裁判又直接下场写业务代码**，所有工程任务按以下六类角色分工协同：

| 角色代号 | 核心职责 | 工作区与读写红线 | 交付物 | 模型家族选型要求 |
| :--- | :--- | :--- | :--- | :--- |
| **`Coordinator`<br>总诊协调官**（主会话） | 意图识别、管理运行账本、快照主工作区、切分独立 worktree、派发与回收 Paseo 子会话、无冲突串行合入与最终集成验证 | 主工作区只读锚定与无冲突合入；**严禁直接编写业务代码或手工解合并冲突** | 派单指令、合入代码与最终验证报告 | 当前主会话模型 |
| **`[Triage]`<br>本质分流官** | 顺因果链剥离“症状点 `X`”与“不变量首次破坏源头 `Y`”，全仓同源普查，复合问题切片定档 | **只读约束**（禁改代码、禁在主目录跑产生副产物的构建；由协调官快照校验） | 《本质诊断与派单卡》 | 线索聚焦时由协调官只读兼任；跨度大时派独立长上下文/高推理子会话 |
| **`[Explorer]`<br>正交探路员** | Gear 2 沿三正交范式发散方案；Gear 3 按“外部路线横评 × 内部硬样本”双线摸底 | **只读约束** | 候选方案集或技术路线横评 | 当主机在线模型家族数 `N ≥ 2` 时，并行发散最多使用 `N-1` 个家族（预留 ≥1 个异构家族供红队使用） |
| **`[Red-Team]`<br>异构红队官** | 对照最新源码/字节码专门挑刺证伪候选方案（查重、找绕过漏口、算端到端上限）或做事前验尸 | **只读约束** | 证伪反例清单与淘汰建议 | **强制与被审候选方案的 `[Explorer]` 作者跨模型家族** |
| **`[Worker]`<br>隔离执行员** | `1 Worker = 1 独立分支 = 1 独立 Worktree`；首步先动态实证根因假设（不成立则退单），再完成源头实现、反例测试（或 PoC 探针）并在隔离分支完成提交 | **仅限所绑定的独立 `--cwd` worktree 及隔离包缓存内读写**；禁碰主工作区、禁写全局包缓存、禁 `git push` | 干净的隔离分支提交（commits）、反例测试与实测日志 | 按任务选强编码/强推理模型 |
| **`[Reviewer]`<br>异构审查与审计官** | 方案双预审、隔离分支 `git diff` 代码双后审（Gear 1/2）、探针与基准原始数据终审（Gear 2/3）；`BLOCKING` 须附可构造反例 | **只读约束**（直接审隔离 worktree 原件、diff 与原始日志，禁听口头摘要；审查前后核验 worktree `HEAD` 未被篡改） | 分级审查结论（`PASS` / `BLOCKING`） | **强制与对应 `[Worker]` 跨模型家族** |

- **跨模型家族异构定义（强制执行）**：委派前先通过 Paseo MCP 或 `paseo provider ls` / `paseo provider models <provider>` 查询当前在线模型家族数 `N`（如 `OpenAI Codex/GPT` 族、`Anthropic Claude` 族、`Google Gemini` 族）。**凡成对制衡角色（候选方案作者 `Explorer ↔ Red-Team`、`Worker ↔ Reviewer`）必须分属不同模型家族**（同家族大小号如 `Opus` 审 `Sonnet` **不算**异构；仅当整机 `N = 1` 时才允许同族降级并在交付报告中明示）。Provider 若提供物理只读沙箱模式则优先启用；否则通过角色提示词加协调官前后双快照（主工作区快照 + 隔离树 `HEAD` 快照）强制核验。

## 3. Stage 00 · 前置只读本质分流与三档路由

严禁按“预计改几行”给任务定性。动任何业务代码前必须先产出 **《本质诊断与派单卡》**：

1. **剥离表象与病根**：锁定症状点 `X` 与不变量首次被破坏的真实源头 `Y`，写明红线：**“禁止在症状点 `X` 做判空短路/吞异常等表象掩盖，必须在源头 `Y` 修复”**。
2. **同源普查与复合切片**：全仓检索同源模式一并纳入范围；混合型需求拆成正交子切片分别定档与排期。
3. **按本质挂入三档工作流**（并按问题属性叠加专项硬约束卡：性能必读 [references/lens-performance.md](references/lens-performance.md)，缺陷/漏误报必读 [references/lens-bug-precision.md](references/lens-bug-precision.md)，重构/架构必读 [references/lens-refactor-arch.md](references/lens-refactor-arch.md)）：
   - **Gear 1 · 源头快修（本质 A：源头唯一明确、无多方案分歧）** → **0 次人工停顿**，直接走第 4 节隔离开发与异构快审闭环（`1 隔离 Worker + 1 异构 Reviewer`，省去发散与预审）。若构建/测试或异构审查连续 **2 轮**未通过，或发现跨层耦合，**一律自动熔断升入 Gear 2**（绝不带 `BLOCKING` 合入，也不在 Gear 1 原地拉锯）。
   - **Gear 2 · 深度攻坚（本质 B：多路径权衡、跨模块/跨上游库、严苛性能或精度要求）** → 读取 [references/mode-deep-solve.md](references/mode-deep-solve.md)（`Explorer` 三范式发散 → `Red-Team` 异构证伪 → **停顿 1 次与用户拍板** → 双视角预审 → 隔离并行 `Worker` → 双视角异构 `Reviewer` 与数据审计）。
   - **Gear 3 · 探索立项（本质 C：现有机制空白、`0 → 1` 路线未知）** → 读取 [references/mode-explore-spike.md](references/mode-explore-spike.md)（内外双线 `Explorer` → `Red-Team` 事前验尸 → **停顿 1 定 PoC 契约** → 隔离 `Worker` 跑轻量探针 + 强制异构 `[Reviewer-Audit]` 审计探针原始数据 → **停顿 2 定 Go/Pivot/Kill**；Go 后丢弃草稿探针并转入 Gear 2 后半段正式生产级落地）。

## 4. Paseo 隔离代码管理与异构审查五步闭环

Gear 1 与 Gear 2 的生产代码交付均严格执行以下五步闭环（Gear 3 探针阶段复用第 1～3 步做隔离实验，并以异构数据审计替代生产代码风格审查）：

1. **快照主工作区与切分独立 Worktree（Snapshot & Isolate）**
   - 协调官先记录基线 `BASE_SHA` 并对主工作区工作树内容做快照 `MAIN_DIFF_HASH`（`git status --porcelain` 与未提交改动的补丁内容哈希，不绑定 `HEAD` 以便后续串行合入刷新），原样保留用户已有未提交改动。
   - 为每个写入切片创建独立分支与物理隔离目录：`git worktree add -b <slice-branch> <isolated-worktree-path> <BASE_SHA>`，默认审查基线 `SLICE_BASE = BASE_SHA`。若本次任务明确依赖主工作区未提交改动，先将该补丁在隔离树单独提交为一个前置基线 commit 并将 `SLICE_BASE` 更新为该前置 commit（使后续审查只审 `Worker` 自身增量，且合入前须由用户确认如何处置主工作区原未提交改动，严禁静默代用户提交）。凡执行任何会写入包缓存的命令（如 `mvn install`、`pip install` 或修改上游二方库），必须配置隔离本地缓存目录（如独立 `-Dmaven.repo.local` / 独立虚拟环境），严禁污染全局共享缓存。
2. **显式启动 Paseo 角色子会话（Dispatch）**
   - 通过 Paseo MCP 或 CLI（如 `paseo run --no-wait -q --provider <p> --model <m> --cwd <独立worktree绝对路径> --title "[Worker] <slice>"`）在参数级物理绑定工作目录，使每个角色的会话、模型与日志在 Paseo 面板独立可查（Windows 下子任务每次命令须显式 `Set-Location -LiteralPath '<worktree路径>'`；跨 Host 时核实可达 Host、代码与模型并维护 `{serverId, agentId, workspaceId, cwd}` 映射）。
   - 委派指令须包含：目标与验收口径、《本质诊断与派单卡》（源头 `Y` 与禁贴膏药红线）、挂载的 `lens-*.md` 路径、可修改范围及验证命令。
3. **隔离分支内“动态实证 → 源头实现 → 反例测试 → 本地提交”（Implement & Commit）**
   - **`[Worker]` 退单权**：第一步先用最小测试或运行探针证实派单卡的根因假设；若动态实证推翻假设或修改 `Y` 会破坏既有契约，**严禁强行硬改交差**，必须附实证数据退回协调官重诊（Re-triage）或升档。
   - 假设证实后，在隔离 worktree 内完成源头修复、同源点收敛与自动化反例/回归测试，并在隔离分支内完成干净的本地 Git 提交（不留未跟踪构建垃圾）。
4. **提交完整性门禁与异构模型原始 Diff 审查（Cross-Model Review）**
   - **协调官前后双快照校验**：启动审查前，协调官必须核验：① 主工作区未提交内容与 `MAIN_DIFF_HASH` 一致（零误触污染）；② `git -C <wt> status --porcelain` 为空；③ `git -C <wt> rev-list --count <SLICE_BASE>..HEAD` 大于 `0`，并记录隔离树 `WT_HEAD_SHA`。审查结束后再次核验 `git -C <wt> rev-parse HEAD == WT_HEAD_SHA` 且 `status` 为空（防止无沙箱的审查员误改隔离树）。
   - 启动**与 `[Worker]` 不同模型家族的只读 `[Reviewer]`**，仅传入隔离 worktree 路径、`git diff <SLICE_BASE>...HEAD`、真实测试日志路径与**中立审查问题**（严禁喂倾向性摘要）。
   - **闭环与两轮上限**：`BLOCKING` 必须附带具体可构造反例或契约违背证据（无实证偏好归为 `OPTIONAL`）。出现有效 `BLOCKING` 时交回原隔离 `[Worker]` 修复提交，再由**同一异构 `[Reviewer]` 同时复核增量改动与完整 `git diff <SLICE_BASE>...HEAD`**，直至 `0 BLOCKING`：
     - **Gear 1** 满 **2 轮**仍未清零 `BLOCKING`：立即自动升入 **Gear 2**；
     - **Gear 2** 满 **2 轮**仍未清零：若审查方未能给出可构造反例/契约违背证据，协调官可在 `status.md` 记入反驳实证后降级为 `OPTIONAL`；若属真实架构取舍分歧则升级交用户拍板；若属实现者连续两轮修不好确凿缺陷，则**退回重诊（Re-triage）或归档丢弃该候选切片**——**任何情况下严禁带着未解决的有效 `BLOCKING` 合入**。
5. **无冲突串行合入、集成复验与现场清理（Conflict-Free Integrate or Discard）**
   - **严禁协调官手工解代码冲突**：仅当隔离分支满足 **测试全过 + 异构审查 `0 BLOCKING` + 专项卡实证达标** 时，以无冲突方式（`<SLICE_BASE>..HEAD` 范围）串行合入。若后合入切片与已合入的前序切片冲突（或需对齐新目标顶端 `NEW_TARGET_SHA`），协调官**不得亲手改代码解冲突**，必须让该切片原 `[Worker]` 在其隔离树内 `rebase` 到 `NEW_TARGET_SHA`（此时将其 `SLICE_BASE` 更新为 `NEW_TARGET_SHA`）、解冲突并重跑测试，再经对应异构 `[Reviewer]` 针对新 `git diff <SLICE_BASE>...HEAD` 复审通过后合入；每次切片合入后刷新主工作区基线记录（若主工作区原有脏改动阻挡合入，必须先征求用户确认或仅在独立集成 worktree 交付已验证分支，严禁静默把用户未提交改动卷入提交）。
   - 合入后在最终合并树上重跑一次集成验证，随后清理临时 worktree；若候选方案实证未达标或探针判 Kill，先归档完整证据与审查记录，直接删除隔离 worktree 与临时分支。

## 5. 运行态容错、负载互斥与权限红线

- **重负载互斥预算**：读代码、静态审查、独立 worktree 编码可并行（常规同时不超过 2～3 个活跃子会话）；**全量测试、大型编译打包、正式基准测量必须检查宿主机负载并串行/限核执行**。
- **磁盘断点账本与异构接力**：Gear 2 / Gear 3 启动即在 `$PASEO_HOME/runs/<task-id>/status.md`（缺省 `~/.paseo/runs/<task-id>/status.md`）记录派单卡、子会话 ID/模型、worktree 映射、已过门禁与证据路径。服务重启或续跑时先读账本恢复，不重复派工；优先依赖完成通知回收（`paseo wait` / MCP 通知，避免高频轮询）；单模型遇配额上限（Quota）或心跳超时立即切换异构模型接力，禁止原地死循环重试。
- **外部动作收口与坑点沉淀**：任何子 Agent 严禁擅自执行 `git push`、创建/修改 PR/MR/Issue、删除外部已有分支、部署或对外发消息（统一由协调官按当次会话用户明确授权执行）。收尾时若排除了**反直觉的仓库级隐式陷阱**，建议浓缩单行写入项目 `AGENTS.md` 避坑区；最终报告须如实列出根因、工作区/分支、参与的各 Paseo 角色会话与模型、真实执行的测试证据及未执行项。
