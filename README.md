# team-wiki-skill

`team-wiki-skill` 是一个用于管理 Git 驱动团队 Wiki 的通用 Agent skill。

## 首次使用

新用户第一次装好 skill 后，第一步不是直接 `sync-wiki`，而是先补齐第一个 Wiki 项目的配置。

配置入口固定是 skill 目录下的 `config.json`。当用户让 Agent 下载 Wiki、配置 Wiki 或初始化 Wiki 时，Agent 应该更新这个文件，不要新建 `xxx-config.json`、临时 JSON 或项目专属 JSON。

每个 Wiki 配置都应该显式包含 `branch`。如果用户发来的是带分支的链接，例如 `https://gitlab.../-/tree/all/projects/kizuna`，skill 应该自动识别 `all` 并写进 `config.json`，不要再把“分支是什么”丢回给用户理解。

配置里的 `branch` 一旦确定，后续 clone / pull / push 都应该围绕这个分支执行。多人协作时，推送前先 `pull --rebase`，不要直接把本地内容硬推上去。

如果用户电脑上还没有 Git，也不要阻碍 skill 安装本身。更合适的流程是：

1. skill 先正常安装
2. 安装后提醒用户先安装 Git
3. 然后再去拉取 / 同步 Wiki 仓库
4. 再继续补配置和执行后续 Wiki 操作

可以先检查：

```bash
git --version
```

如果这一步失败，说明缺少前置依赖 Git。此时应该提示用户“skill 已安装成功，但后续拉代码和实际 Wiki 操作需要先安装 Git”。

Agent 应该先向用户收集这 4 项信息：

1. Git 的 URL 是什么
2. 本地路径在哪里
3. 项目名称（Name）
4. 项目描述（Description）

推荐直接让用户按下面这个模板回复：

```markdown
请把第一个 Wiki 项目的信息发给我：

1. Git URL：
2. 本地路径：
3. Name：
4. Description：
```

收到信息后，Agent 可以直接运行：

```bash
python3 scripts/team_wiki.py init-config \
  --config config.json \
  --url "<git-url>" \
  --local-dir "<local-path>" \
  --name "<wiki-name>" \
  --description "<wiki-description>"
```

如果 `config.json` 缺失或为空，CLI 也会输出同样的 onboarding 提示。

## 强制规则

- 正常使用只维护 `config.json`，不要创建额外 JSON 配置文件。
- 为每个 Wiki 配置 `branch`；如果用户给的是带分支链接，就自动提取。
- Wiki 相关操作一律通过 Git `clone / pull / push` 完成，不要下载压缩包。
- 当用户说“安装 / 下载 / 克隆 Wiki”时，默认动作统一是 `git clone` 到配置路径，不是下载 zip。
- `log/` 目录只保存按提交月份划分的日志文件，例如 `log/2026/2026-04.md`。
- 不要在 `log/` 下创建 `index.md`，也不要给 `log/` 做导航索引。
- log 里的用户名必须来自用户自己的 Git 用户名，也就是 `git config user.name`。
- 写 log 时只看提交当时的日期。比如 4 月 23 日提交“5 月计划”，log 也必须写入 4 月日志文件。
- 如果 `config.json` 已经指定了 `branch`，后续 pull / push 都必须围绕这个分支执行，推送前先 `pull --rebase`。

核心能力：

- 本地同步 Wiki 仓库
- 初始化 `README.md`、`index.md` 和月度 `log/`
- 在项目目录下维护项目级 `Change Log`
- 创建或更新页面
- 追加必需的 log 记录
- 自动挂到最近的 `index.md`
- 在发布版本时记录用户可感知的 `Change Log`
- 将飞书导出的 Markdown 或外部内容导入 Wiki
- 通过本地 `config.json` 支持多 Wiki 路由

仓库结构：

- `SKILL.md`：skill 入口
- `REFERENCE.md`：详细操作说明
- `FORMS.md`：可复用 Markdown 模板
- `scripts/team_wiki.py`：skill 实际调用的 CLI
- `tests/test_team_wiki.py`：自动化测试
- `config.example.json`：本地配置示例
- `schema.example.json`：schema 示例

以下文件仅供本地使用，不应提交：

- `config.json`
- `schema.json`
