# Gear 2 · 深度工程攻坚流（1 → N：已知系统内的硬骨头）

适用于根因隐蔽、多路径架构权衡、跨模块/跨上游仓库耦合、历史反复修补未果，或具有严格性能/精度/稳定性要求的攻坚任务。全程通过 Paseo 显式调度 **`[Explorer]`、`[Red-Team]`、`[Worker]`、`[Reviewer]`** 四类子会话协同，并同步挂载对应 `lens-*.md` 硬约束卡。

---

## 前半段：多 Agent 正交探源、异构红队证伪与人机拍板

### Step 1 · 事实与不变量锚定（Coordinator / `[Triage]` 只读）

只建立客观事实基线，不出拍脑袋方案：

- 梳理真实运行链路、数据流/状态机现状、历史相关提交或曾撤回的失败实验，并执行 `python3 <skill-dir>/scripts/flow.py --task-id <task-id> init --repo <repo-root>` 与 `triage --symptom <X> --root <Y> --gear 2`，由守门员在 `$PASEO_HOME/runs/<task-id>/`（缺省 `~/.paseo/runs/<task-id>/`）原子维护 `state.json` + `status.md` 运行账本。
- 明确不可破坏的**核心不变量（Invariants）**与专项卡要求的定量基线/分母，重述真正要解的核心矛盾。

### Step 2 · 正交三范式并行探源（Paseo `[Explorer]` 只读子会话）

对跨模块或高复杂度问题，通过 Paseo 并行启动 2～3 个只读 `[Explorer]` 子会话（标题如 `[Explorer-A] Incremental`、`[Explorer-B] Structural`、`[Explorer-C] Boundary-Shift`；跨模型并行时控制使用不超过 `N-1` 个可用模型家族，确保留出至少 1 个异构家族供红队使用），沿三个正交范式发掘解空间，并用 `record-explore --author-models <csv> --summary <text>` 登记（`TRIAGED` → `EXPLORED`）：

- **范式 A · 渐进/局部路径**：最小变更半径，复用现有扩展点与机制，风险最低但须核算理论上限。
- **范式 B · 结构/模型路径**：重构数据结构、索引、状态机或职责抽象，从机制上消除整类问题而非逐点特判。
- **范式 C · 边界外移/消解路径**：跳出当前模块——检查能否在输入生产端、内部上游二方依赖库（必要时反编译或拉取上游源码）、构建工具链或协议层直接消解复杂度。

### Step 3 · 跨模型异构红队证伪（Paseo `[Red-Team]` 只读子会话）

协调官汇总候选方案后，启动**与各候选方案作者 `[Explorer]` 不同模型家族的只读 `[Red-Team]` 子会话**，传入候选方案与最新源码路径，唯一职责是“挑刺证伪”。每轮用 `record-redteam --model <provider/model> --summary <text>` 登记（`EXPLORED` → `FALSIFIED`）；守门员要求对每个产出候选方案的模型家族，至少有一个异族红队模型（仅经核实的 `--single-family-host` 可例外）：

1. **前提真伪与查重**：依赖的代码假设是否真实成立？最新主干是否已有等价实现或冲突逻辑？
2. **漏口与反例构造**：全仓搜索绕过该方案的隐藏入口、锁序反转、缓存失效遗漏、异常/降级吞咽或缺失依赖（`Phantom`/未解析符号）退化陷阱。
3. **收益-复杂度拷问**：真实端到端效果是否配得上引入的维护负担？（淘汰低上限补丁与过度工程化抽象。）
4. **未知假设探针验证（不增加人工停顿）**：若某方案卡在静态看代码无法定论的单一运行时假设上，协调官可直接创建临时隔离 worktree（`isolate --kind probe`，仅限 `EXPLORED` / `FALSIFIED` 状态）派 1 个 `[Worker]` 跑一次 10 分钟级可丢弃微探针取证（不进入 [mode-explore-spike.md](mode-explore-spike.md) 的人工停顿流程），将实测事实直接喂入 Step 4。

### Step 4 · 权衡收敛与人机拍板（全流程唯一默认停顿点）

- 协调官淘汰被证伪方案（保留一句话淘汰原因），输出幸存方案对比表：**根源位置（含跨仓说明） | 核心机制 | 预期收益上限 | 红队已排雷边界与 Trade-off**。
- **停顿与用户探讨拍板**本轮实施切片（若用户已授权全自动推进则记录 `align --auto-authorized` 直通；若证伪后发现实为简单漏配则经 `triage --re-triage` 降回 Gear 1），并用 `align --slices <csv> --summary <text>` 登记拍板后的切片（`FALSIFIED` → `ALIGNED`）。

---

## 后半段：守门员状态机 + Paseo 原生受管 Worktree 隔离开发与异构双审闭环（拍板后自动推进）

后半段由守门员 `scripts/flow.py` 驱动（详见 `SKILL.md` 第 4 节）。`<skill-dir>` 为技能安装目录；下列命令均需带 `--task-id <task-id>`（或 `--run-dir <dir>`），乱序调用会被拒绝。

### Stage 1 · 双视角异构方案预审（2 个并行 Paseo `[Reviewer]` 只读子会话）

动代码前编写可证伪实施规格（不变量、反例清单、精确文件范围、验证口径），通过 Paseo 并行启动两个独立只读预审会话（至少其一与后续 `[Worker]` 跨模型家族）：

- **`[Reviewer-Pre-A]`（语义与不变量视角）**：审业务/分析语义守恒、状态生命周期、并发安全、异常与退化守恒、兼容性。
- **`[Reviewer-Pre-B]`（可验证性与隔离视角）**：审反例测试能否真正拦截错误实现、worktree 与本地依赖缓存零污染方案、实证对比口径公平性。
- **准入门禁**：全部带实证的 `BLOCKING` 项收敛进修订版规格后，执行 `record-prereview --reviewer-a-model <m1> --reviewer-b-model <m2> --planned-worker-models <csv> --blockers <n>`。仅当 `blockers == 0` 且**两位**预审员的模型家族都异于所有计划 `[Worker]` 家族时，守门员才会把 `ALIGNED` 推进到 `EXECUTION_READY`（仅整机在线只有单一家族时，经核实的 `--single-family-host` 才可例外）。

### Stage 2 · 独立 Worktree 并行实现与反例先行（Paseo `[Worker]` 隔离会话）

- `init` 已固定 `BASE_SHA` 与主工作区快照（`main_diff_hash`）。按正交子切片创建 Paseo 原生受管 Worktree（切片 `id` 必须在 `align --slices` 列表中）：
  ```bash
  python3 <skill-dir>/scripts/flow.py --task-id <task-id> isolate --slice <slice> --branch <new-branch> --kind production [--backend auto|paseo|git] [--apply-dirty-patch]
  ```
  `auto` 后端依次执行 `paseo project create` + `paseo workspace create --isolation worktree --mode branch-off --new-branch <new-branch> --base <BASE_SHA>`，并记录 `workspaceId`、`cwd` 与 `slice_base`；仅外部仓库或 Paseo 不可用时才回退 `git worktree add -b`。若依赖主工作区未提交补丁，`--apply-dirty-patch` 会将其单独提交为前置 `SLICE_BASE`（之后须用 `integrate --into-worktree` 合入）。凡涉及写入包缓存或修改二方库均配置独立本地缓存目录。
- 以 **Workspace + 目录双重绑定**启动 `[Worker]`（`paseo run --no-wait -q --provider <p> --model <m> --workspace <workspaceId> --cwd <wt> --title "[Worker] <slice>"`；并发写会话默认 ≤ 2 个），并登记：`assign-worker --slice <slice> --model <provider/model> --agent-id <id>`。
- **实证退单权**：`[Worker]` 先验证根因假设，若动态实证推翻假设则立即停工退回协调官（随后 `triage --re-triage`）。
- **反例测试先行与干净提交**：除常规回归外，`[Worker]` 必须将 Step 3 与 Stage 1 识别的全部边界陷阱写成自动化反例单测并在隔离分支内跑绿（重型测试按宿主机负载串行执行），最后在隔离分支完成干净的本地 Git 提交。构建/测试失败轮次经 `record-verify-fail --slice <slice> --summary <text>` 记账。

### Stage 3 · 双视角异构代码后审、实证审计与无冲突串行合入

- **异构双视角后审（同一 commit 上的双透镜，禁止自审代替他审）**：先执行 `enter-review --slice <slice> --reviewer-model <provider/model> --lens A`；守门员核验主工作区仍与快照一致、`git -C <wt> status --porcelain` 为空、`<SLICE_BASE>..HEAD` 有提交、审查员模型家族异于 `[Worker]`、且 `HEAD` 不是上次被驳回的那个，随后记录 `wt_head_sha`。再在**同一个 `wt_head_sha`** 上以 `enter-review ... --lens B` 追加第二位审查员。并行启动**与 `[Worker]` 不同模型家族**的两个只读后审会话（以 `--workspace <workspaceId> --cwd <wt>` 绑定），直传隔离 worktree 路径、`git diff <SLICE_BASE>...HEAD` 与测试日志：
  - **`[Reviewer-Post-A]`（`--lens A`）**：逐行审完整 diff 的语义等价性、并发/锁序与边界退化；
  - **`[Reviewer-Post-B]`（`--lens B`）**：审反例测试真实覆盖度、构建产物条目级纯净度及主工作区/全局缓存零污染。
  - 各审查员结论经 `record-review --slice <slice> --verdict PASS|BLOCKING --blockers <n> --lens A|B [--counterexample <text>]` 登记，它会复核 `HEAD == wt_head_sha` 且隔离树干净（审查员无法篡改）。**仅当 `A` 与 `B` 在同一 `wt_head_sha` 上都 `PASS`**，切片才进入 `REVIEW_PASSED` 并固定 `approved_head_sha`。
  - `BLOCKING` 必须附非空可构造反例，派回原隔离 `[Worker]` 修复提交（`CHANGES_REQUESTED`），并经新的 `enter-review` 由**同一异构 `[Reviewer]` 同时复核增量修复与完整 `git diff <SLICE_BASE>...HEAD`** 直至 `0 BLOCKING`。满 **2 轮**被驳回后切片进入 `ROUND_CAP_REACHED`：只能走 `resolve-dispute --action re-triage|discard|user-escalate --reason <text>`，严禁带有效 `BLOCKING` 合入。
- **受控实证对比与独立数据审计**：按所挂 `lens-*.md` 执行前后实证对比；涉及基准测量或大规模对比数据时，另派独立只读 `[Reviewer-Audit]` 复核原始日志与统计计算。
- **无冲突串行合入或干净丢弃**：全部门禁通过后，由**协调官**串行执行 `integrate --slice <slice> [--into-worktree <干净树>]`，不得手改冲突。守门员要求 `REVIEW_PASSED`、`0` 个未决 blocker，且隔离树与分支引用仍等于 `approved_head_sha`；优先 `--ff-only`，否则先试合并，冲突则中止并置 `NEEDS_REBASE`。此时由原 `[Worker]` 在隔离树内 `rebase` 到新目标顶端并重跑测试，协调官登记 `mark-rebased --slice <slice> --new-slice-base <sha>`（会清除此前审批），须对新的 `git diff <SLICE_BASE>...HEAD` 重新走完整异构复审后才能再次 `integrate`。
- **集成终验与归档**：全部已对齐切片 `INTEGRATED` 后，任务进入 `MERGED_PENDING_VERIFY`。在最终合并树上执行 `verify-integration --cmd "<集成验证命令>"`：仅当退出码为 `0`，才对每个已合入切片执行 `paseo workspace archive <workspaceId>`（或 `git worktree remove`）、确认目录已消失、删除临时分支，并将任务置为 `COMPLETED`。若实证未达门槛，先完整归档证据，再 `discard-slice --slice <slice> --reason <text>` 干净移除受管 worktree 与分支。
