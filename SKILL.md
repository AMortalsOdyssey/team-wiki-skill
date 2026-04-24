---
name: team-wiki-skill
description: 使用固定的 config.json、显式 branch、schema 路由、强制按提交时间写月度 log、index 挂链、项目级 Change Log 和外部内容导入来管理基于 Git 的团队 Wiki。Use this skill whenever 用户需要下载、克隆、配置、同步、推送、更新、整理或总结存放在 Git 仓库中的团队 Wiki；必须遵守 config.json 唯一配置入口、branch 写入配置或从带分支链接自动识别、所有 Wiki 操作只通过 Git clone/pull/push 实现、推送前先 pull --rebase、log 用户名来自 git config user.name、log 文件按提交月份写入且 log/ 下不创建 index.md。
---

# team-wiki-skill

当用户希望操作存放在 Git 仓库中、以 Markdown 管理的团队内部 Wiki 时，使用这个 skill。

## Hard Rules

下面这些规则优先级最高。执行 Wiki 任务时先检查它们，再执行具体命令。

1. 配置文件固定使用 `<skill-path>/config.json`。当用户让你“下载 Wiki”“配置 Wiki”“初始化 Wiki 配置”时，更新这个文件；不要新建临时 JSON、项目专属 JSON 或其他配置文件。
2. 每个 Wiki 配置都应该显式包含 `branch`。如果用户给的是带分支链接，例如 `https://gitlab.../-/tree/all/projects/kizuna`，自动识别 `branch=all` 并写入 `config.json`。
3. 只有测试或用户明确指定隔离配置时，才允许传 `--config <other-file>`。正常使用一律用默认 `config.json` 或显式 `--config config.json`。
4. Wiki 相关操作一律通过 Git 实现：`clone`、`pull --rebase`、`push`。不要下载压缩包，因为压缩包不包含分支信息，也无法跟踪远端。
5. `log/` 目录只保存按提交月份划分的日志文档，例如 `log/2026/2026-04.md`。不要在 `log/` 下创建 `index.md`，也不要给 `log/` 维护导航索引。
6. 写入 `log/` 的用户名必须来自当前用户的 Git 用户名，也就是 `git config user.name`。不要凭空填写 `operator`、`agent`、`Codex`、人名占位符或你猜测的名字。
7. log 归属只看提交当时的日期，不看正文内容描述的计划月份。如果 4 月 23 日提交一篇“5 月计划”，log 也只能写入 4 月的日志文件，例如 `log/2026/2026-04.md`。
8. 配置里如果已经指定了 branch，后续同步和推送都必须围绕这个 branch 执行。推送前必须先 `pull --rebase origin <branch>`，以减少冲突。
9. 任何写操作都必须追加 log；只读查询可以跳过 log。

## First-time Setup

首次使用时，先检查 `<skill-path>/config.json`。

这个 skill 的安装不应该因为缺少 Git 而被阻塞。

但如果用户机器上还没有 Git，装完 skill 之后要主动提醒用户：

1. 先安装 Git
2. 再通过 Git clone 拉取或同步 Wiki 仓库
3. 然后补齐 `config.json`
4. 最后再继续执行 `sync-wiki`、`write-page` 等实际操作

建议先检查：

```bash
git --version
```

如果 `git --version` 不可用，不要假设 Agent 会静默帮用户安装；先明确提醒用户当前缺少 Git 这个前置依赖，并说明“skill 已经装好了，但拉代码和后续 Wiki 操作要先装 Git”。

如果 `config.json` 不存在，或者 `wikis[]` 为空，就不要直接继续执行 `sync-wiki`、`write-page` 之类的命令；先提醒用户补齐第一个 Wiki 项目的信息。

必须按下面这些信息向用户收集：

1. Git 的 URL 或带分支的页面链接是什么
2. 本地路径在哪里
3. 项目名称（Name）
4. 分支（Branch）是什么；如果链接里已经带了分支，就自动提取
5. 项目描述（Description）

建议直接让用户按这个模板回复：

```markdown
请把第一个 Wiki 项目的信息发给我：

1. Git URL：
2. 本地路径：
3. Name：
4. Branch（如果链接已带分支可省略）：
5. Description：
```

用户回复后，优先直接生成 `<skill-path>/config.json`，而不是只把模板丢给用户自己处理。

不要为了某个 Wiki 项目额外创建 `xxx-wiki-config.json`、`tmp/config.json` 或其他配置文件。这个 skill 的长期配置入口就是 `config.json`。

推荐命令：

```bash
python3 scripts/team_wiki.py init-config \
  --config config.json \
  --url "<git-url>" \
  --local-dir "<local-path>" \
  --name "<wiki-name>" \
  --branch "<branch>" \
  --description "<wiki-description>"
```

这一步只需要做一次。后续再操作 Wiki 时，继续复用这个配置。

这个 skill 的默认前提：

- Wiki 由 Git 承载
- 本地路由只由 `<skill-path>/config.json` 控制
- 每个 Wiki 都应该有明确的 `branch`
- 结构规则来自 `schema.json`
- `index.md` 和 `log/` 是最小固定骨架
- 任何写操作都必须追加一条 log
- `log/` 下没有 index，只保留按提交月份划分的日志文件
- log 里的用户名必须来自 `git config user.name`
- clone / pull / push 都围绕配置里的 branch 执行
- 链接使用标准 Markdown 相对路径，不使用 Obsidian 双链

## When to Use This Skill

当用户要求以下操作时，调用这个 skill：

- 同步或初始化团队 Wiki
- 创建或更新 Wiki 页面
- 更新或挂载 `index.md`
- 追加必需的 `log` 记录
- 在项目目录下维护发布版 Change Log
- 将飞书 Markdown 或外部文档内容导入 Wiki
- 基于本地配置操作多 Wiki 场景

## 本地必需文件

- `config.json`
- 可选 `schema.json`

如果它们还不存在，请从下面的示例文件开始：

- `config.example.json`
- `schema.example.json`

不要提交 `config.json` 或 `schema.json`。

## 主流程

### 1. 读取本地配置

先读取 `config.json`。

- 在真正执行任何 Git 相关操作前，先检查 `git --version`
- 如果机器没装 Git，提醒用户先安装 Git；不要把“缺少 Git”理解成 skill 安装失败
- 如果用户要求“下载 Wiki”或“配置 Wiki”，优先维护 `<skill-path>/config.json`；不要新建其他 JSON 配置
- 如果用户给的是带分支链接，自动提取 branch 并写入 `config.json`
- 如果缺少 `config.json`，或者里面还没有第一个 Wiki 项目配置，先进入上面的 First-time Setup，不要继续往下执行
- 从 `wikis[]` 中确定目标 Wiki
- 如果是多 Wiki 场景且目标不够明确，必须向用户确认
- 如果用户已经明确指定目标 Wiki，就不要重复确认

### 2. 读取 schema

优先读取 `schema.json`；如果不存在，就回退到 `schema.example.json`。

把 schema 视为当前项目自己的结构约定。

- `index.md` 是路由层
- `log/` 是必需的记录层，但不是导航层；不要创建 `log/index.md`
- 其他目录由项目自己定义，不要在 skill 里写死

### 3. 写入前先同步

在创建或编辑内容前，先同步本地 Wiki 仓库。默认行为是 clone 指定 branch，并在后续始终使用这个 branch：

```bash
python3 scripts/team_wiki.py sync-wiki --config config.json --wiki <name>
```

如果仓库还是空的，且用户想创建一套新的 Wiki 骨架：

```bash
python3 scripts/team_wiki.py sync-wiki --config config.json --wiki <name> --bootstrap-if-empty
```

当用户说“安装 / 下载 / 克隆 Wiki”时，默认动作也是这个流程，也就是 Git clone，而不是下载压缩包。

### 4. 默认导航规则

在回答问题或定位内容时，遵循下面的顺序：

1. 先读目标 Wiki 的 `README.md`
2. 再读顶层或最近的 `index.md`
3. 根据链接进入相关主题页
4. 最后再读叶子内容

不要在读 `README.md` 和 `index.md` 之前，就盲目扫描整个 Wiki。

### 5. 写操作

实际文件操作统一走 CLI。

创建或更新页面：

```bash
python3 scripts/team_wiki.py write-page \
  --config config.json \
  --wiki <name> \
  --path docs/example.md \
  --title "示例页面" \
  --content-file /tmp/content.md \
  --message "新增示例文档"
```

不要手填 `--actor`。CLI 会从目标 Wiki 仓库读取 `git config user.name`，并把这个值写进 log。只有在你已经确认传入值与 `git config user.name` 完全一致时，才可以显式传 `--actor`。

追加 log 记录：

```bash
python3 scripts/team_wiki.py record-log \
  --config config.json \
  --wiki <name> \
  --message "更新若干页面" \
  --link docs/example.md \
  --link index.md
```

显式更新某个 index：

```bash
python3 scripts/team_wiki.py update-index \
  --config config.json \
  --wiki <name> \
  --index-path index.md \
  --link-path docs/example.md \
  --label "示例页面"
```

### 6. Change Log 与 Log 的边界

这个 skill 现在默认区分两类记录：

- `log/`：记录用户操作、开发进度、页面调整、导入过程等日常动作
- `projects/<project>/changelog.md`：只记录面向用户可感知的发布版本

不要把日常推进、临时修复、讨论过程写进 Change Log。

`log/` 的文件选择规则：

- 按提交动作发生时的日期选择文件
- 文件名由当前提交日期所属月份决定，默认形如 `log/YYYY/YYYY-MM.md`
- 不要根据正文内容里提到的计划月份来选择 log 文件
- 不要在 `log/` 下创建 index 或导航文档

示例：如果当前提交时间是 2026-04-23，即使页面内容写的是“2026 年 5 月计划”，也必须把 log 追加到 `log/2026/2026-04.md`。

当用户明确是在记录一个发布版本时，使用：

```bash
python3 scripts/team_wiki.py record-release \
  --config config.json \
  --wiki <name> \
  --project-path projects/<project>/index.md \
  --version 1.0.0 \
  --item "UI 初稿完成" \
  --item "对话演绎 Bug 修复和优化"
```

这个命令会：

- 校验版本号是否像一个发布版本
- 自动定位项目级 `Change Log`
- 仅把面向用户的发布内容写入 `Change Log`
- 自动补一条月度 `log`

如果只是想从某个 Git 仓库生成一段 diff 摘要，可以继续使用：

```bash
python3 scripts/team_wiki.py record-change \
  --config config.json \
  --wiki <name> \
  --source-repo /path/to/repo \
  --target-path notes/releases/2026-04-summary.md \
  --title "某次版本更新"
```

这个命令只是一段“变更摘要生成工具”，不是默认的项目发布 Change Log。

它会：

- 检查 Git refs 和变更文件
- 生成一段精简的 changelog 内容
- 写入或追加到目标页面
- 如有需要，更新最近的 index
- 自动补上必需的 log 记录

### 7. 飞书 / 外部内容导入

导入导出的 Markdown 或外部内容：

```bash
python3 scripts/team_wiki.py ingest-feishu \
  --config config.json \
  --wiki <name> \
  --target-path sources/feishu/2026-04/example.md \
  --title "会议纪要" \
  --source-url "https://example.feishu.cn/..." \
  --content-file /tmp/feishu.md
```

### 8. 推送规则

如果 `config.json` 已经为某个 Wiki 指定了 `branch`，后续推送必须推送到这个 branch。

优先使用：

```bash
python3 scripts/team_wiki.py --config config.json push-wiki --wiki <name>
```

这个命令会先：

- `fetch --all --prune`
- 切到配置里的 branch
- `pull --rebase origin <branch>`
- 再执行 `push origin HEAD:<branch>`

如果 rebase 冲突：

- 不要硬推覆盖别人
- 优先保留更准确的最新内容
- 解决冲突后继续 `pull --rebase`
- 确认无冲突后再推送

## Examples

### 示例 1：初始化空 Wiki 仓库

```bash
python3 scripts/team_wiki.py sync-wiki \
  --config config.json \
  --wiki group-wiki \
  --bootstrap-if-empty
```

### 示例 2：创建设计页并自动挂链

```bash
python3 scripts/team_wiki.py write-page \
  --config config.json \
  --wiki group-wiki \
  --path design/api-overview.md \
  --title "接口概览" \
  --content "接口设计摘要" \
  --message "新增 API 设计页"
```

## 不可违反的规则

- 使用标准 Markdown 相对路径链接
- 不要使用 Obsidian 双链
- 不要新建额外 JSON 配置，正常使用只维护 `<skill-path>/config.json`
- 不要忽略 branch；配置里应显式写 branch，或从带分支链接自动识别
- 不要下载 zip 包来操作 Wiki；一律使用 Git clone / pull / push
- 不要在 `log/` 下创建 `index.md`
- 不要手填或猜测 log 用户名；必须使用 `git config user.name`
- 不要根据内容计划月份选择 log 文件；只根据提交当时日期选择月度 log 文件
- 推送前必须先 pull --rebase 配置分支
- 新建文档后，尽量挂到最近的相关 `index.md`
- 每次写操作都必须补一条 `log`
- 如果一次动作改了多个页面，可以写一条摘要 log，但不能不写 log
- 只有纯只读查询可以跳过 log

## 验收清单

- [ ] `config.json` 指向正确的 Wiki
- [ ] `config.json` 为目标 Wiki 配置了正确的 `branch`
- [ ] 没有新建额外 JSON 配置
- [ ] 目标 Wiki 仓库已在本地同步
- [ ] 当前 clone / pull / push 都围绕配置里的 branch 执行
- [ ] `README.md` 和 `index.md` 可正常读取
- [ ] `log/` 下没有 `index.md`
- [ ] log 用户名来自 `git config user.name`
- [ ] log 写入提交当时所属月份的文件
- [ ] 新建或更新页面使用标准 Markdown 链接
- [ ] 被修改的页面可以从某个 `index.md` 到达
- [ ] 写操作已经追加 `log` 记录

## 参考

更详细的说明见 `REFERENCE.md`：

- CLI 命令细节
- config/schema 行为
- 初始化行为
- 项目级 Change Log 发布流程
- 测试流程
