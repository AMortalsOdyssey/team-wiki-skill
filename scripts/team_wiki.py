#!/usr/bin/env python3
"""用于操作 Git 驱动团队 Wiki 的 CLI。"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
from urllib.parse import urlparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent


def fail(message: str) -> None:
    print(f"错误：{message}", file=sys.stderr)
    raise SystemExit(1)


def git_dependency_message() -> str:
    return "\n".join(
        [
            "当前机器还没有安装 Git。",
            "",
            "team-wiki-skill 可以先安装，不需要因为缺少 Git 而阻塞安装流程。",
            "但在真正执行下面这些操作前，请先安装 Git：",
            "- 拉取或 clone Wiki 仓库",
            "- sync-wiki",
            "- write-page / ingest-feishu / record-release / record-change",
            "",
            "建议顺序：",
            "1. 先安装 Git",
            "2. 再拉取 Wiki 仓库",
            "3. 然后补齐 config.json",
            "4. 最后继续执行 Wiki 操作",
        ]
    )


def ensure_git_available() -> None:
    if shutil.which("git"):
        return
    fail(git_dependency_message())


def git_user_name(repo_dir: Optional[Path] = None) -> str:
    candidates = []
    if repo_dir and repo_dir.exists():
        candidates.append((["git", "config", "user.name"], repo_dir))
    candidates.append((["git", "config", "--global", "user.name"], None))

    for cmd, cwd in candidates:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
        )
        value = proc.stdout.strip()
        if proc.returncode == 0 and value:
            return value

    fail(
        "\n".join(
            [
                "无法读取 Git 用户名。",
                "写入 Wiki log 时，用户名必须来自用户自己的 Git 配置，不能由 Agent 随便填写。",
                "请先执行：git config --global user.name \"你的 Git 用户名\"",
            ]
        )
    )


def resolve_log_actor(provided_actor: Optional[str], repo_dir: Optional[Path] = None) -> str:
    expected_actor = git_user_name(repo_dir)
    if provided_actor and provided_actor != expected_actor:
        fail(
            "\n".join(
                [
                    "log 用户名必须使用当前用户的 Git 用户名。",
                    f"当前 Git 用户名：{expected_actor}",
                    f"收到的 --actor：{provided_actor}",
                    "请不要随意填写 --actor；建议省略 --actor，让 CLI 自动读取 git config user.name。",
                ]
            )
        )
    return expected_actor


def normalize_repo_url(raw_url: str) -> str:
    value = raw_url.strip()
    if not value:
        fail("Git URL 不能为空")
    if value.endswith(".git"):
        return value
    if "/-/" in value:
        value = value.split("/-/", 1)[0]
    elif "/tree/" in value:
        value = value.split("/tree/", 1)[0]
    elif "/blob/" in value:
        value = value.split("/blob/", 1)[0]
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return value.rstrip("/") + ".git"
    return value


def extract_branch_from_repo_url(raw_url: str) -> Optional[str]:
    value = raw_url.strip().rstrip("/")
    if "/-/" in value:
        _, tail = value.split("/-/", 1)
        parts = tail.split("/")
        if len(parts) >= 2 and parts[0] in {"tree", "blob"}:
            return parts[1]
    for marker in ("/tree/", "/blob/"):
        if marker in value:
            tail = value.split(marker, 1)[1]
            branch = tail.split("/", 1)[0]
            if branch:
                return branch
    return None


def run(cmd: List[str], cwd: Optional[Path] = None, check: bool = True) -> str:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        if cmd and cmd[0] == "git":
            fail(git_dependency_message())
        fail(f"命令不存在：{exc.filename or cmd[0]}")
    if check and proc.returncode != 0:
        stderr = proc.stderr.strip()
        stdout = proc.stdout.strip()
        detail = stderr or stdout or "命令执行失败"
        fail(f"{' '.join(cmd)}: {detail}")
    return proc.stdout.strip()


def load_json(path: Path) -> dict:
    if not path.exists():
        fail(f"缺少文件：{path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def config_onboarding_message(config_path: Path) -> str:
    sample = {
        "wikis": [
            {
                "url": "https://git.example.com/example-org/team-wiki.git",
                "local_dir": "/path/to/local/wiki",
                "name": "team-wiki",
                "branch": "main",
                "description": "示例团队 Wiki 仓库",
            }
        ]
    }
    sample_json = json.dumps(sample, ensure_ascii=False, indent=2)
    return "\n".join(
        [
            f"还没有可用的 Wiki 配置，请先补齐 {config_path}。",
            "",
            "首次使用这个 skill 时，先向用户收集第一个 Wiki 项目的信息。",
            "如果用户直接给了带分支的页面链接，例如 /-/tree/all/...，就自动识别 branch=all 并写入 config.json。",
            "",
            "至少要确认这 5 项：",
            "1. Git 的 URL 是什么",
            "2. 本地路径在哪里",
            "3. 项目名称（Name）",
            "4. 分支（Branch）是什么；如果 URL 里带了分支，就自动提取",
            "5. 项目描述（Description）",
            "",
            "用户回复后，可以直接执行：",
            "python3 scripts/team_wiki.py init-config \\",
            "  --config config.json \\",
            '  --url "<git-url>" \\',
            '  --local-dir "<local-path>" \\',
            '  --name "<wiki-name>" \\',
            '  --branch "<branch>" \\',
            '  --description "<wiki-description>"',
            "",
            "正常使用只维护 skill 目录下的 config.json，不要新建其他 JSON 配置文件。",
            "",
            "或者手动写入下面这个 config.json 模板：",
            sample_json,
        ]
    )


def load_wiki_config(config_path: Path) -> dict:
    if not config_path.exists():
        fail(config_onboarding_message(config_path))
    data = load_json(config_path)
    wikis = data.get("wikis")
    if not isinstance(wikis, list) or not wikis:
        fail(config_onboarding_message(config_path))
    required = ("url", "local_dir", "name", "description")
    for idx, item in enumerate(wikis):
        if not isinstance(item, dict):
            fail(f"{config_path} 中第 {idx + 1} 个 wiki 配置不是对象")
        missing = [field for field in required if not str(item.get(field, "")).strip()]
        if missing:
            missing_text = "、".join(missing)
            fail(
                "\n".join(
                    [
                        f"{config_path} 中第 {idx + 1} 个 wiki 配置缺少字段：{missing_text}",
                        "",
                        config_onboarding_message(config_path),
                    ]
                )
            )
    return data


def init_config_file(
    config_path: Path,
    url: str,
    local_dir: str,
    name: str,
    description: str,
    branch: Optional[str] = None,
    force: bool = False,
) -> Path:
    branch = (branch or extract_branch_from_repo_url(url) or "main").strip()
    normalized_url = normalize_repo_url(url)
    if config_path.exists() and not force:
        fail(f"配置文件已存在：{config_path}。如需覆盖，请加 --force")
    payload = {
        "wikis": [
            {
                "url": normalized_url,
                "local_dir": local_dir,
                "name": name,
                "branch": branch,
                "description": description,
            }
        ]
    }
    save_text(config_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return config_path


def save_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def append_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(content)


def today(now: Optional[dt.datetime] = None) -> dt.datetime:
    return now or dt.datetime.now()


def rel_link(from_path: Path, to_path: Path, label: Optional[str] = None) -> str:
    rel = os.path.relpath(to_path, start=from_path.parent).replace(os.sep, "/")
    link_label = label or to_path.stem
    return f"[{link_label}]({rel})"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", text.strip()).strip("-")
    return slug.lower() or "页面"


def is_release_version(text: str) -> bool:
    value = text.strip()
    return bool(re.fullmatch(r"v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", value))


@dataclass
class WikiConfig:
    name: str
    url: str
    local_dir: Path
    branch: str
    description: str


class TeamWiki:
    def __init__(self, root: Path, config_path: Path, schema_path: Optional[Path] = None):
        self.root = root
        self.config_path = config_path
        self.schema_path = schema_path
        self.config = load_wiki_config(config_path)
        default_schema = root / "schema.example.json"
        self.schema = load_json(schema_path if schema_path else default_schema)

    def get_wiki(self, name: str) -> WikiConfig:
        for item in self.config.get("wikis", []):
            if item.get("name") == name:
                return WikiConfig(
                    name=item["name"],
                    url=item["url"],
                    local_dir=Path(item["local_dir"]).expanduser(),
                    branch=item.get("branch") or "main",
                    description=item.get("description", ""),
                )
        fail(f"在 {self.config_path} 中找不到 Wiki '{name}'")

    def index_filename(self) -> str:
        return self.schema.get("index_filename", "index.md")

    def readme_filename(self) -> str:
        return self.schema.get("readme_filename", "README.md")

    def log_path_for_date(self, wiki: WikiConfig, when: dt.datetime) -> Path:
        base_dir = self.schema.get("log", {}).get("base_dir", "log")
        year = when.strftime("%Y")
        ym = when.strftime("%Y-%m")
        pattern = self.schema.get("log", {}).get("file_pattern", "{YYYY}/{YYYY-MM}.md")
        rel = pattern.replace("{YYYY}", year).replace("{YYYY-MM}", ym)
        return wiki.local_dir / base_dir / rel

    def log_base_dir(self, wiki: WikiConfig) -> Path:
        base_dir = self.schema.get("log", {}).get("base_dir", "log")
        return wiki.local_dir / base_dir

    def nearest_index(self, wiki: WikiConfig, page_path: Path, skip: Optional[Path] = None) -> Path:
        name = self.index_filename()
        cur = page_path.parent
        while True:
            candidate = cur / name
            if candidate.exists() and candidate != skip:
                return candidate
            if cur == wiki.local_dir:
                break
            if cur.parent == cur:
                break
            cur = cur.parent
        return wiki.local_dir / name

    def resolve_wiki_path(self, wiki: WikiConfig, path: Path) -> Path:
        return path if path.is_absolute() else wiki.local_dir / path

    def default_link_label(self, wiki: WikiConfig, path: Path) -> str:
        resolved = self.resolve_wiki_path(wiki, path)
        if resolved.name == self.index_filename():
            return "index" if resolved.parent == wiki.local_dir else resolved.parent.name
        return resolved.stem

    def ensure_repo(self, wiki: WikiConfig) -> None:
        if (wiki.local_dir / ".git").exists():
            return
        wiki.local_dir.parent.mkdir(parents=True, exist_ok=True)
        if self.remote_has_branch(wiki.url, wiki.branch):
            run(["git", "clone", "--branch", wiki.branch, "--single-branch", wiki.url, str(wiki.local_dir)])
            return
        run(["git", "clone", wiki.url, str(wiki.local_dir)])
        if not self.repo_has_commits(wiki.local_dir):
            run(["git", "checkout", "-B", wiki.branch], cwd=wiki.local_dir)
            return
        fail(f"远端仓库 {wiki.url} 不存在分支：{wiki.branch}")

    def remote_has_branch(self, repo_url: str, branch: str) -> bool:
        proc = subprocess.run(
            ["git", "ls-remote", "--heads", repo_url, branch],
            text=True,
            capture_output=True,
        )
        return proc.returncode == 0 and bool(proc.stdout.strip())

    def ensure_branch(self, wiki: WikiConfig) -> None:
        current = run(["git", "branch", "--show-current"], cwd=wiki.local_dir)
        if current == wiki.branch:
            return

        local_branch = subprocess.run(
            ["git", "rev-parse", "--verify", wiki.branch],
            cwd=str(wiki.local_dir),
            text=True,
            capture_output=True,
        )
        if local_branch.returncode == 0:
            run(["git", "switch", wiki.branch], cwd=wiki.local_dir)
            return

        remote_branch = subprocess.run(
            ["git", "rev-parse", "--verify", f"origin/{wiki.branch}"],
            cwd=str(wiki.local_dir),
            text=True,
            capture_output=True,
        )
        if remote_branch.returncode == 0:
            run(["git", "switch", "-c", wiki.branch, "--track", f"origin/{wiki.branch}"], cwd=wiki.local_dir)
            return

        fail(f"本地仓库缺少配置要求的分支：{wiki.branch}")

    def pull_branch(self, wiki: WikiConfig) -> None:
        proc = subprocess.run(
            ["git", "pull", "--rebase", "origin", wiki.branch],
            cwd=str(wiki.local_dir),
            text=True,
            capture_output=True,
        )
        if proc.returncode == 0:
            return
        detail = (proc.stderr or proc.stdout).strip() or "git pull --rebase 失败"
        fail(
            "\n".join(
                [
                    f"同步分支 {wiki.branch} 失败：{detail}",
                    "",
                    "处理原则：",
                    "1. Wiki 一律通过 Git clone，不下载压缩包。",
                    "2. 推送前必须先 pull --rebase 对应分支，以减少冲突。",
                    "3. 如果 rebase 冲突，优先保留更准确的最新内容，手动解决冲突后再继续。",
                    f"4. 解决后重新执行：git pull --rebase origin {wiki.branch}",
                ]
            )
        )

    def repo_has_commits(self, repo_dir: Path) -> bool:
        proc = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=str(repo_dir),
            text=True,
            capture_output=True,
        )
        return proc.returncode == 0

    def sync_wiki(self, wiki: WikiConfig, bootstrap_if_empty: bool = False) -> None:
        self.ensure_repo(wiki)
        self.ensure_branch(wiki)
        if not self.repo_has_commits(wiki.local_dir):
            if bootstrap_if_empty:
                self.bootstrap_wiki(wiki)
            return
        run(["git", "fetch", "--all", "--prune"], cwd=wiki.local_dir)
        if self.remote_has_branch(wiki.url, wiki.branch):
            self.pull_branch(wiki)
        elif bootstrap_if_empty:
            self.bootstrap_wiki(wiki)

    def push_wiki(self, wiki: WikiConfig) -> None:
        self.sync_wiki(wiki, bootstrap_if_empty=False)
        proc = subprocess.run(
            ["git", "push", "origin", f"HEAD:{wiki.branch}"],
            cwd=str(wiki.local_dir),
            text=True,
            capture_output=True,
        )
        if proc.returncode == 0:
            return
        detail = (proc.stderr or proc.stdout).strip() or "git push 失败"
        fail(
            "\n".join(
                [
                    f"推送分支 {wiki.branch} 失败：{detail}",
                    "",
                    "请确认：",
                    f"- 当前 Wiki 约定分支是 {wiki.branch}",
                    "- 你已经先完成 pull --rebase",
                    "- 如果有冲突，先解决冲突再重新推送",
                ]
            )
        )

    def bootstrap_wiki(self, wiki: WikiConfig, when: Optional[dt.datetime] = None) -> None:
        when = today(when)
        readme = wiki.local_dir / self.readme_filename()
        index = wiki.local_dir / self.index_filename()
        log = self.log_path_for_date(wiki, when)
        if not readme.exists():
            template = (self.root / "templates" / "readme.template.md").read_text(encoding="utf-8")
            save_text(readme, template.format(wiki_name=wiki.name, description=wiki.description or "团队内部 Wiki"))
        if not index.exists():
            template = (self.root / "templates" / "index.template.md").read_text(encoding="utf-8")
            save_text(index, template)
        if not log.exists():
            template = (self.root / "templates" / "log-month.template.md").read_text(encoding="utf-8")
            save_text(log, template.format(year_month=when.strftime("%Y-%m")))

    def update_index(self, wiki: WikiConfig, index_path: Path, link_path: Path, label: Optional[str] = None) -> None:
        resolved_index_path = index_path if index_path.is_absolute() else wiki.local_dir / index_path
        try:
            resolved_index_path.relative_to(self.log_base_dir(wiki))
        except ValueError:
            pass
        else:
            fail("log/ 目录只保存按提交月份划分的日志文档，不创建或维护 index.md")

        index_path.parent.mkdir(parents=True, exist_ok=True)
        if not index_path.exists():
            save_text(index_path, "# Index\n")
        link = rel_link(index_path, link_path, label)
        content = index_path.read_text(encoding="utf-8")
        existing_paths = {
            match.group("target")
            for match in re.finditer(r"\[[^\]]+\]\((?P<target>[^)]+)\)", content)
        }
        target_rel = os.path.relpath(link_path, start=index_path.parent).replace(os.sep, "/")
        if target_rel not in existing_paths and link not in content:
            if not content.endswith("\n"):
                content += "\n"
            content += f"- {link}\n"
            save_text(index_path, content)

    def project_dir_for_path(self, path: Path) -> Optional[Path]:
        parts = path.parts
        if len(parts) >= 2 and parts[0] == "projects":
            return Path(parts[0]) / parts[1]
        return None

    def project_changelog_path(self, project_dir: Path) -> Path:
        return project_dir / "changelog.md"

    def project_display_name(self, wiki: WikiConfig, project_dir: Path) -> str:
        project_index = wiki.local_dir / project_dir / self.index_filename()
        if project_index.exists():
            content = project_index.read_text(encoding="utf-8")
            for line in content.splitlines():
                if line.startswith("# "):
                    return line[2:].strip() or project_dir.name
        return project_dir.name

    def ensure_project_changelog(self, wiki: WikiConfig, project_dir: Path) -> Path:
        changelog_path = wiki.local_dir / self.project_changelog_path(project_dir)
        if changelog_path.exists():
            return changelog_path
        project_name = self.project_display_name(wiki, project_dir)
        template = (self.root / "templates" / "project-changelog.template.md").read_text(encoding="utf-8")
        save_text(
            changelog_path,
            template.format(project_name=project_name),
        )
        return changelog_path

    def ensure_project_scaffold(self, wiki: WikiConfig, page_path: Path) -> None:
        project_dir = self.project_dir_for_path(page_path)
        if not project_dir:
            return

        project_index = wiki.local_dir / project_dir / self.index_filename()
        if not project_index.exists():
            project_title = self.project_display_name(wiki, project_dir)
            save_text(
                project_index,
                "\n".join(
                    [
                        f"# {project_title}",
                        "",
                        "## 页面",
                        "",
                    ]
                ),
            )
            self.update_index(wiki, wiki.local_dir / self.index_filename(), project_index, project_title)

        changelog_path = self.ensure_project_changelog(wiki, project_dir)
        self.update_index(wiki, project_index, changelog_path, "Change Log")

    def record_log(
        self,
        wiki: WikiConfig,
        actor: str,
        message: str,
        links: Iterable[Path],
        when: Optional[dt.datetime] = None,
    ) -> Path:
        when = today(when)
        log_path = self.log_path_for_date(wiki, when)
        if not log_path.exists():
            self.bootstrap_wiki(wiki, when=when)
        rendered_links = []
        seen = set()
        for item in links:
            resolved = self.resolve_wiki_path(wiki, item)
            key = str(resolved)
            if key in seen:
                continue
            seen.add(key)
            rendered_links.append(rel_link(log_path, resolved, self.default_link_label(wiki, resolved)))
        suffix = ""
        if rendered_links:
            suffix = " | " + " | ".join(rendered_links)
        entry = f"- {when.strftime('%Y-%m-%d')} | {actor} | {message}{suffix}\n"
        append_text(log_path, entry)
        return log_path

    def write_page(
        self,
        wiki: WikiConfig,
        page_path: Path,
        title: Optional[str],
        content: str,
        actor: str,
        message: str,
        link_index: bool = True,
    ) -> None:
        self.ensure_project_scaffold(wiki, page_path)
        full_path = wiki.local_dir / page_path
        if title and not content.lstrip().startswith("#"):
            content = f"# {title}\n\n{content.strip()}\n"
        elif not content.endswith("\n"):
            content += "\n"
        save_text(full_path, content)
        project_dir = self.project_dir_for_path(page_path)
        if project_dir and full_path == wiki.local_dir / project_dir / self.index_filename():
            self.update_index(wiki, full_path, wiki.local_dir / self.project_changelog_path(project_dir), "Change Log")
        if link_index:
            skip = full_path if full_path.name == self.index_filename() else None
            index = self.nearest_index(wiki, full_path, skip=skip)
            self.update_index(wiki, index, full_path, title or full_path.stem)
            self.record_log(wiki, actor, message, [index, full_path])
        else:
            self.record_log(wiki, actor, message, [full_path])

    def summarize_git_range(self, repo_dir: Path, from_ref: Optional[str], to_ref: str) -> tuple[str, List[str], List[str]]:
        if not self.repo_has_commits(repo_dir):
            fail(f"源仓库没有提交记录：{repo_dir}")
        if not from_ref:
            upstream = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "@{upstream}"],
                cwd=str(repo_dir),
                text=True,
                capture_output=True,
            )
            if upstream.returncode == 0:
                from_ref = upstream.stdout.strip()
            else:
                from_ref = run(["git", "rev-parse", "HEAD^"], cwd=repo_dir)
        compare = f"{from_ref}..{to_ref}"
        commits = run(["git", "log", "--format=%s", compare], cwd=repo_dir).splitlines()
        files = run(["git", "diff", "--name-only", compare], cwd=repo_dir).splitlines()
        return compare, commits[:5], files[:8]

    def record_change(
        self,
        wiki: WikiConfig,
        source_repo: Path,
        target_path: Path,
        actor: str,
        title: Optional[str],
        from_ref: Optional[str],
        to_ref: str,
    ) -> None:
        compare, commits, files = self.summarize_git_range(source_repo, from_ref, to_ref)
        auto_title = title or (commits[0] if commits else f"来自 {compare} 的变更")
        lines = [
            f"## {auto_title}",
            "",
            f"- 比较范围：{compare}",
            f"- 提交：{'; '.join(commits) if commits else '无'}",
            f"- 文件：{', '.join(files) if files else '无'}",
            f"- 摘要：{auto_title}",
            "",
        ]
        full_path = wiki.local_dir / target_path
        existing = full_path.read_text(encoding="utf-8") if full_path.exists() else f"# {target_path.stem}\n\n"
        if not existing.endswith("\n"):
            existing += "\n"
        save_text(full_path, existing + "\n".join(lines))
        index = self.nearest_index(wiki, full_path)
        self.update_index(wiki, index, full_path, target_path.stem)
        self.record_log(wiki, actor, f"记录变更: {auto_title}", [index, full_path])

    def record_release(
        self,
        wiki: WikiConfig,
        project_path: Path,
        actor: str,
        version: str,
        items: List[str],
        title: Optional[str] = None,
        when: Optional[dt.datetime] = None,
    ) -> Path:
        if not is_release_version(version):
            fail(f"版本号格式不合法：{version}")
        if not items:
            fail("发布 Change Log 至少需要一条发布内容")

        when = today(when)
        project_dir = self.project_dir_for_path(project_path)
        if not project_dir:
            fail("project_path 必须位于 projects/<project>/... 下")

        self.ensure_project_scaffold(wiki, project_dir / self.index_filename())
        changelog_path = wiki.local_dir / self.project_changelog_path(project_dir)
        project_index = wiki.local_dir / project_dir / self.index_filename()

        heading = title or version
        lines = [
            f"## {heading} · {when.strftime('%Y-%m-%d')}",
            "",
            *[f"- {item}" for item in items],
            "",
        ]
        existing = changelog_path.read_text(encoding="utf-8") if changelog_path.exists() else ""
        if not existing:
            existing = f"# {project_dir.name} Change Log\n\n"
        if not existing.endswith("\n"):
            existing += "\n"
        save_text(changelog_path, existing + "\n".join(lines))
        self.update_index(wiki, project_index, changelog_path, "Change Log")
        self.record_log(wiki, actor, f"记录版本发布: {version}", [project_index, changelog_path])
        return changelog_path

    def ingest_feishu(
        self,
        wiki: WikiConfig,
        target_path: Path,
        title: str,
        source_url: str,
        content: str,
        actor: str,
    ) -> None:
        body = "\n".join(
            [
                f"# {title}",
                "",
                f"> 来源：{source_url}",
                "",
                "## 摘要",
                "",
                content.strip().splitlines()[0] if content.strip() else "导入内容。",
                "",
                "## 导入内容",
                "",
                content.strip(),
                "",
            ]
        )
        self.write_page(
            wiki=wiki,
            page_path=target_path,
            title=None,
            content=body,
            actor=actor,
            message=f"导入 Feishu 内容: {title}",
        )


def parse_path(value: str) -> Path:
    return Path(value)


def add_common_args(parser: argparse.ArgumentParser, *, with_defaults: bool) -> None:
    config_kwargs = {"default": str(ROOT_DIR / "config.json")} if with_defaults else {"default": argparse.SUPPRESS}
    schema_kwargs = {"default": None} if with_defaults else {"default": argparse.SUPPRESS}
    parser.add_argument("--config", **config_kwargs)
    parser.add_argument("--schema", **schema_kwargs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="操作基于 Git 的团队 Wiki")
    add_common_args(parser, with_defaults=True)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init-config")
    add_common_args(init, with_defaults=False)
    init.add_argument("--url", required=True)
    init.add_argument("--local-dir", required=True)
    init.add_argument("--name", required=True)
    init.add_argument("--branch")
    init.add_argument("--description", required=True)
    init.add_argument("--force", action="store_true")

    sync = sub.add_parser("sync-wiki")
    add_common_args(sync, with_defaults=False)
    sync.add_argument("--wiki", required=True)
    sync.add_argument("--bootstrap-if-empty", action="store_true")

    push = sub.add_parser("push-wiki")
    add_common_args(push, with_defaults=False)
    push.add_argument("--wiki", required=True)

    write = sub.add_parser("write-page")
    add_common_args(write, with_defaults=False)
    write.add_argument("--wiki", required=True)
    write.add_argument("--path", required=True)
    write.add_argument("--title")
    write.add_argument("--content")
    write.add_argument("--content-file")
    write.add_argument("--actor")
    write.add_argument("--message", required=True)

    log = sub.add_parser("record-log")
    add_common_args(log, with_defaults=False)
    log.add_argument("--wiki", required=True)
    log.add_argument("--actor")
    log.add_argument("--message", required=True)
    log.add_argument("--link", action="append", default=[])

    upd = sub.add_parser("update-index")
    add_common_args(upd, with_defaults=False)
    upd.add_argument("--wiki", required=True)
    upd.add_argument("--index-path", required=True)
    upd.add_argument("--link-path", required=True)
    upd.add_argument("--label")

    change = sub.add_parser("record-change")
    add_common_args(change, with_defaults=False)
    change.add_argument("--wiki", required=True)
    change.add_argument("--source-repo", required=True)
    change.add_argument("--target-path", required=True)
    change.add_argument("--actor")
    change.add_argument("--title")
    change.add_argument("--from-ref")
    change.add_argument("--to-ref", default="HEAD")

    release = sub.add_parser("record-release")
    add_common_args(release, with_defaults=False)
    release.add_argument("--wiki", required=True)
    release.add_argument("--project-path", required=True)
    release.add_argument("--actor")
    release.add_argument("--version", required=True)
    release.add_argument("--title")
    release.add_argument("--item", action="append", default=[])

    ingest = sub.add_parser("ingest-feishu")
    add_common_args(ingest, with_defaults=False)
    ingest.add_argument("--wiki", required=True)
    ingest.add_argument("--target-path", required=True)
    ingest.add_argument("--title", required=True)
    ingest.add_argument("--source-url", required=True)
    ingest.add_argument("--content")
    ingest.add_argument("--content-file")
    ingest.add_argument("--actor")

    return parser


def read_content(args: argparse.Namespace) -> str:
    if getattr(args, "content", None):
        return args.content
    if getattr(args, "content_file", None):
        return Path(args.content_file).read_text(encoding="utf-8")
    fail("必须提供 --content 或 --content-file 其中之一")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "init-config":
        path = init_config_file(
            config_path=Path(args.config),
            url=args.url,
            local_dir=args.local_dir,
            name=args.name,
            description=args.description,
            branch=args.branch,
            force=args.force,
        )
        print(f"已初始化配置：{path}")
        return

    ensure_git_available()
    manager = TeamWiki(ROOT_DIR, Path(args.config), Path(args.schema) if args.schema else None)
    wiki = manager.get_wiki(args.wiki)

    if args.command == "sync-wiki":
        manager.sync_wiki(wiki, bootstrap_if_empty=args.bootstrap_if_empty)
        print(f"已同步 Wiki：{wiki.name} @ {wiki.branch}")
        return

    if args.command == "push-wiki":
        manager.push_wiki(wiki)
        print(f"已推送 Wiki：{wiki.name} @ {wiki.branch}")
        return

    manager.ensure_repo(wiki)

    if args.command == "write-page":
        actor = resolve_log_actor(args.actor, wiki.local_dir)
        manager.write_page(
            wiki=wiki,
            page_path=parse_path(args.path),
            title=args.title,
            content=read_content(args),
            actor=actor,
            message=args.message,
        )
        print(f"已写入页面：{args.path}")
        return

    if args.command == "record-log":
        actor = resolve_log_actor(args.actor, wiki.local_dir)
        links = [parse_path(item) for item in args.link]
        path = manager.record_log(wiki, actor, args.message, links)
        print(f"已更新 log：{path}")
        return

    if args.command == "update-index":
        manager.update_index(
            wiki,
            wiki.local_dir / args.index_path,
            wiki.local_dir / args.link_path,
            args.label,
        )
        print(f"已更新 index：{args.index_path}")
        return

    if args.command == "record-change":
        actor = resolve_log_actor(args.actor, wiki.local_dir)
        manager.record_change(
            wiki=wiki,
            source_repo=Path(args.source_repo),
            target_path=parse_path(args.target_path),
            actor=actor,
            title=args.title,
            from_ref=args.from_ref,
            to_ref=args.to_ref,
        )
        print(f"已记录变更：{args.target_path}")
        return

    if args.command == "record-release":
        actor = resolve_log_actor(args.actor, wiki.local_dir)
        path = manager.record_release(
            wiki=wiki,
            project_path=parse_path(args.project_path),
            actor=actor,
            version=args.version,
            title=args.title,
            items=args.item,
        )
        print(f"已记录发布版本：{path.relative_to(wiki.local_dir)}")
        return

    if args.command == "ingest-feishu":
        actor = resolve_log_actor(args.actor, wiki.local_dir)
        manager.ingest_feishu(
            wiki=wiki,
            target_path=parse_path(args.target_path),
            title=args.title,
            source_url=args.source_url,
            content=read_content(args),
            actor=actor,
        )
        print(f"已导入内容：{args.target_path}")
        return

    fail(f"未知命令：{args.command}")


if __name__ == "__main__":
    main()
