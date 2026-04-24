# team-wiki-skill Reference

## Table of Contents

1. 仓库文件
2. 配置
3. 结构约定
4. CLI 命令
5. 测试

## 仓库文件

- `SKILL.md`：skill 入口
- `scripts/team_wiki.py`：主 CLI
- `config.example.json`：本地配置示例
- `schema.example.json`：schema 示例
- `templates/`：初始化模板
- `tests/test_team_wiki.py`：自动化测试

## 配置

依赖说明：

- skill 本身可以先安装，不需要因为机器上还没装 Git 而阻塞安装
- 但在真正拉取 / 同步 Wiki 仓库之前，机器上必须有可用的 Git
- 建议先执行 `git --version` 做一次检查
- 如果 Git 缺失，应先提醒用户安装 Git，再继续后续 Wiki 操作

`config.json` 格式：

```json
{
  "wikis": [
    {
      "url": "https://gitlab.example.com/group/wiki.git",
      "local_dir": "/absolute/path/to/wiki",
      "name": "group-wiki",
      "branch": "main",
      "description": "团队 Wiki"
    }
  ]
}
```

规则：

- `wikis` 必须是数组
- 通过 `name` 匹配目标 Wiki
- CLI 会拒绝未知的 Wiki 名称
- 正常使用固定维护 skill 目录下的 `config.json`
- 每个 Wiki 应显式配置 `branch`
- 如果用户提供的是带分支的 GitLab / GitHub 页面链接，先自动提取 branch，再把 clone URL 和 branch 一起写进配置
- 当用户说“下载 Wiki”“配置 Wiki”“初始化 Wiki 配置”时，不要新建其他 JSON 文件
- 只有测试或用户明确要求隔离配置时，才使用 `--config <other-file>`

首次使用建议流程：

1. 先检查机器上是否有 Git：`git --version`
2. 如果没有 Git，提醒用户先安装 Git；不要把这理解成 skill 安装失败
3. 再向用户收集第一个 Wiki 项目的信息：
   `Git URL 或带分支页面链接`、`本地路径`、`Name`、`Branch`、`Description`
4. 如果链接里已经带了分支，自动提取 branch
5. 把配置写入 skill 目录下的 `config.json`，不要新建其他 JSON
6. 运行：

```bash
python3 scripts/team_wiki.py init-config \
  --config config.json \
  --url "<git-url>" \
  --local-dir "<local-path>" \
  --name "<wiki-name>" \
  --branch "<branch>" \
  --description "<wiki-description>"
```

7. 再继续执行 `sync-wiki`、`write-page` 等实际 Wiki 操作

如果缺少 `config.json`，或者 `wikis[]` 为空 / 字段不完整，CLI 会直接输出 onboarding 提示，提醒先补这 4 项配置。

如果缺少 Git，CLI 会直接输出依赖提示，提醒用户先安装 Git，再回来拉取仓库和继续操作。

## 结构约定

`schema.json` 是可选的。如果缺失，CLI 会回退到 `schema.example.json`。

当前实现只写死了最小约定：

- `index.md`
- `README.md`
- 月度 `log/`
- `projects/<project>/changelog.md`

其余部分都刻意保持灵活。

`log/` 规则：

- `log/` 只保存按提交月份划分的日志文档
- 默认路径是 `log/YYYY/YYYY-MM.md`
- 不创建 `log/index.md`
- 不维护 `log/` 导航索引
- log 文件归属只看提交当时的日期，不看正文内容描述的计划月份
- 例：2026-04-23 提交“2026 年 5 月计划”，log 仍写入 `log/2026/2026-04.md`

log 用户名规则：

- log 条目中的用户名必须来自 `git config user.name`
- CLI 会自动读取目标 Wiki 仓库里的 Git 用户名
- 不要让 Agent 自己填写 `operator`、`agent`、`Codex` 或其他猜测出来的名字
- 如果显式传了 `--actor`，它必须与 `git config user.name` 完全一致，否则 CLI 会拒绝执行

分支与协作规则：

- Wiki 一律通过 Git clone，不下载压缩包
- `sync-wiki` 会围绕配置里的 `branch` 执行 clone / switch / pull
- 推送前必须先 `pull --rebase origin <branch>`，以减少多人协作冲突
- 推荐直接使用 `push-wiki`，不要自己忘记分支
- 如果 rebase 冲突，先解决冲突，再继续 rebase 和 push；不要直接强推覆盖别人

## CLI 命令

### `init-config`

根据用户提供的第一个 Wiki 项目信息生成 `config.json`。

示例：

```bash
python3 scripts/team_wiki.py init-config \
  --config config.json \
  --url "https://gitlab.example.com/group/wiki/-/tree/all/projects/demo" \
  --local-dir "/path/to/local/wiki" \
  --name "team-wiki" \
  --branch "all" \
  --description "示例团队 Wiki 仓库"
```

行为：

- 默认生成只包含一个 Wiki 的 `config.json`
- 如果 `--url` 是带分支链接，会自动归一化出仓库 clone URL，并识别 branch
- 如果没有显式传 `--branch`，CLI 会优先从链接里提取，否则默认 `main`
- 如果目标配置已存在，会拒绝覆盖
- 如确需重写，可显式加 `--force`

### `sync-wiki`

克隆或同步目标 Wiki。

示例：

```bash
python3 scripts/team_wiki.py sync-wiki --config config.json --wiki group-wiki
python3 scripts/team_wiki.py sync-wiki --config config.json --wiki group-wiki --bootstrap-if-empty
```

行为：

- 如果 `local_dir` 不存在，就先 clone 配置里的 branch
- 如果仓库已存在，就先切到配置里的 branch，再执行 fetch 和 pull --rebase
- 如果仓库还没有提交且指定了 `--bootstrap-if-empty`，就创建 `README.md`、`index.md` 和当前月份的 log

### `push-wiki`

把本地 Wiki 推送到配置里的 branch。

示例：

```bash
python3 scripts/team_wiki.py --config config.json push-wiki --wiki group-wiki
```

行为：

- 先执行一次 branch-aware 的 `sync-wiki`
- 再执行 `git push origin HEAD:<branch>`
- 如果 pull/rebase 或 push 失败，会给出冲突处理提示

### `write-page`

创建或更新页面，并把它挂到最近的 `index.md`，同时追加一条 log。

不要手填 `--actor`。CLI 会自动读取 `git config user.name` 并写入 log。

如果页面位于 `projects/<project>/` 下，CLI 还会确保：

- 项目目录存在自己的 `index.md`
- 项目目录存在自己的 `changelog.md`
- 项目 `index.md` 默认挂有 `Change Log`

### `record-log`

向当前月份的 log 文件追加一条记录。

支持多个 `--link` 参数。

当前月份指提交动作发生时的月份，不是内容里提到的计划月份。

### `update-index`

如果链接尚不存在，就向某个 index 文件追加标准 Markdown 链接。

### `record-change`

读取源 Git 仓库，并向目标页面写入一段 changelog 风格内容。

注意：

- 这是一个“变更摘要生成工具”
- 它不等于项目发布版 `Change Log`
- 如果是面向用户的版本发布，请优先使用 `record-release`

默认比较策略：

- 如果显式传了 `--from-ref`，就使用它
- 否则如果 upstream 存在，就比较 upstream 分支到 `HEAD`
- 否则比较 `HEAD^..HEAD`

生成内容包含：

- 比较范围
- 提交标题
- 变更文件
- 一行精简摘要

### `record-release`

向 `projects/<project>/changelog.md` 追加一条项目级发布记录。

适用场景：

- 用户可感知的功能发布
- 正式版本号更新
- 需要沉淀成项目发布历史

不适用场景：

- 日常开发推进
- 临时排查过程
- 尚未形成可发布版本的修修补补

### `ingest-feishu`

根据来源 URL 和导入内容创建页面，并自动记录 log。

输入方式：

- `--content-file`
- `--content`

## 测试

运行：

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

建议的端到端验收流程：

1. 克隆一个真实 Wiki 仓库，或把 config 指向它
2. 运行 `sync-wiki --bootstrap-if-empty`
3. 运行 `write-page`
4. 对一个项目运行 `record-release`
5. 对一个源仓库运行 `record-change`
6. 运行 `ingest-feishu`
7. 验证：
   - `README.md`
   - `index.md`
   - 月度 `log`
   - `log/` 下没有 `index.md`
   - log 文件路径是提交当时所属月份
   - log 用户名来自 `git config user.name`
   - `config.json` 中存在正确的 `branch`
   - clone / pull / push 围绕配置 branch 执行
   - 项目级 `Change Log`
   - 标准 Markdown 链接
   - 没有双链
