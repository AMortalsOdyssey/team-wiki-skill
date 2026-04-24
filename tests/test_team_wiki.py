import io
import datetime as dt
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from scripts.team_wiki import (
    ROOT_DIR,
    TeamWiki,
    ensure_git_available,
    extract_branch_from_repo_url,
    init_config_file,
    normalize_repo_url,
    resolve_log_actor,
    run,
)


class TeamWikiTests(unittest.TestCase):
    ACTOR = "operator"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.remote = self.base / "remote.git"
        self.local_wiki = self.base / "wiki"
        self.source_repo = self.base / "source-repo"
        run(["git", "init", "--bare", str(self.remote)])

        self.config = self.base / "config.json"
        self.config.write_text(
            json.dumps(
                {
                    "wikis": [
                        {
                            "url": str(self.remote),
                            "local_dir": str(self.local_wiki),
                            "name": "test-wiki",
                            "description": "测试 Wiki",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        self.manager = TeamWiki(ROOT_DIR, self.config)
        self.wiki = self.manager.get_wiki("test-wiki")

    def tearDown(self):
        self.tmp.cleanup()

    def _init_source_repo(self):
        run(["git", "init", str(self.source_repo)])
        run(["git", "config", "user.name", "tester"], cwd=self.source_repo)
        run(["git", "config", "user.email", "tester@example.com"], cwd=self.source_repo)
        (self.source_repo / "a.txt").write_text("one\n", encoding="utf-8")
        run(["git", "add", "."], cwd=self.source_repo)
        run(["git", "commit", "-m", "feat: initial"], cwd=self.source_repo)
        (self.source_repo / "a.txt").write_text("two\n", encoding="utf-8")
        (self.source_repo / "b.md").write_text("# B\n", encoding="utf-8")
        run(["git", "add", "."], cwd=self.source_repo)
        run(["git", "commit", "-m", "feat: update source"], cwd=self.source_repo)

    def _seed_remote_branch(self, branch: str = "all"):
        seed_repo = self.base / f"seed-{branch}"
        run(["git", "init", str(seed_repo)])
        run(["git", "config", "user.name", "tester"], cwd=seed_repo)
        run(["git", "config", "user.email", "tester@example.com"], cwd=seed_repo)
        run(["git", "switch", "-c", branch], cwd=seed_repo)
        (seed_repo / "README.md").write_text("# Seed\n", encoding="utf-8")
        run(["git", "add", "."], cwd=seed_repo)
        run(["git", "commit", "-m", "chore: seed"], cwd=seed_repo)
        run(["git", "remote", "add", "origin", str(self.remote)], cwd=seed_repo)
        run(["git", "push", "origin", f"HEAD:{branch}"], cwd=seed_repo)

    def test_sync_bootstrap_creates_skeleton(self):
        self.manager.sync_wiki(self.wiki, bootstrap_if_empty=True)
        self.assertTrue((self.local_wiki / "README.md").exists())
        self.assertTrue((self.local_wiki / "index.md").exists())
        self.assertTrue(any((self.local_wiki / "log").rglob("*.md")))
        self.assertFalse((self.local_wiki / "log" / "index.md").exists())
        self.assertFalse((self.local_wiki / "changelog").exists())

    def test_sync_uses_configured_branch(self):
        self._seed_remote_branch("all")
        branch_config = self.base / "branch-sync-config.json"
        branch_config.write_text(
            json.dumps(
                {
                    "wikis": [
                        {
                            "url": str(self.remote),
                            "local_dir": str(self.base / "branch-wiki"),
                            "name": "branch-wiki",
                            "branch": "all",
                            "description": "分支 Wiki",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        manager = TeamWiki(ROOT_DIR, branch_config)
        wiki = manager.get_wiki("branch-wiki")
        manager.sync_wiki(wiki)
        current_branch = run(["git", "branch", "--show-current"], cwd=wiki.local_dir)
        self.assertEqual(current_branch, "all")

    def test_record_log_uses_submission_month(self):
        self.manager.sync_wiki(self.wiki, bootstrap_if_empty=True)
        log_path = self.manager.record_log(
            wiki=self.wiki,
            actor=self.ACTOR,
            message="记录五月计划",
            links=[],
            when=dt.datetime(2026, 4, 23, 12, 0, 0),
        )
        self.assertEqual(log_path.relative_to(self.local_wiki), Path("log/2026/2026-04.md"))
        self.assertIn("记录五月计划", log_path.read_text(encoding="utf-8"))

    def test_init_config_creates_first_wiki_config(self):
        config_path = self.base / "new-config.json"
        init_config_file(
            config_path=config_path,
            url="https://git.example.com/example-org/team-wiki.git",
            local_dir="/tmp/team-wiki",
            name="team-wiki",
            description="示例团队 Wiki 仓库",
        )
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(
            payload,
            {
                "wikis": [
                    {
                        "url": "https://git.example.com/example-org/team-wiki.git",
                        "local_dir": "/tmp/team-wiki",
                        "name": "team-wiki",
                        "branch": "main",
                        "description": "示例团队 Wiki 仓库",
                    }
                ]
            },
        )

    def test_init_config_extracts_branch_from_tree_url(self):
        config_path = self.base / "branch-config.json"
        init_config_file(
            config_path=config_path,
            url="https://gitlab.example.com/group/wiki/-/tree/all/projects/demo",
            local_dir="/tmp/wiki",
            name="demo-wiki",
            description="Demo Wiki",
        )
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["wikis"][0]["url"], "https://gitlab.example.com/group/wiki.git")
        self.assertEqual(payload["wikis"][0]["branch"], "all")

    def test_url_helpers_normalize_branch_links(self):
        self.assertEqual(
            normalize_repo_url("https://gitlab.example.com/group/wiki/-/tree/all/projects/demo"),
            "https://gitlab.example.com/group/wiki.git",
        )
        self.assertEqual(
            extract_branch_from_repo_url("https://gitlab.example.com/group/wiki/-/tree/all/projects/demo"),
            "all",
        )

    def test_missing_config_shows_onboarding_prompt(self):
        missing = self.base / "missing-config.json"
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT_DIR / "scripts" / "team_wiki.py"),
                "--config",
                str(missing),
                "sync-wiki",
                "--wiki",
                "demo",
            ],
            text=True,
            capture_output=True,
            cwd=str(ROOT_DIR),
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Git 的 URL 是什么", proc.stderr)
        self.assertIn("本地路径在哪里", proc.stderr)
        self.assertIn("项目名称（Name）", proc.stderr)
        self.assertIn("项目描述（Description）", proc.stderr)
        self.assertIn("init-config", proc.stderr)

    def test_missing_git_shows_dependency_prompt(self):
        with mock.patch("scripts.team_wiki.shutil.which", return_value=None):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                with self.assertRaises(SystemExit):
                    ensure_git_available()
        message = stderr.getvalue()
        self.assertIn("当前机器还没有安装 Git", message)
        self.assertIn("team-wiki-skill 可以先安装", message)
        self.assertIn("先安装 Git", message)

    def test_resolve_log_actor_uses_git_user_name(self):
        self.manager.sync_wiki(self.wiki, bootstrap_if_empty=True)
        run(["git", "config", "user.name", self.ACTOR], cwd=self.local_wiki)
        self.assertEqual(resolve_log_actor(None, self.local_wiki), self.ACTOR)
        self.assertEqual(resolve_log_actor(self.ACTOR, self.local_wiki), self.ACTOR)

    def test_resolve_log_actor_rejects_non_git_user_name(self):
        self.manager.sync_wiki(self.wiki, bootstrap_if_empty=True)
        run(["git", "config", "user.name", self.ACTOR], cwd=self.local_wiki)
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            with self.assertRaises(SystemExit):
                resolve_log_actor("someone-else", self.local_wiki)
        self.assertIn("log 用户名必须使用当前用户的 Git 用户名", stderr.getvalue())

    def test_write_page_updates_index_and_log(self):
        self.manager.sync_wiki(self.wiki, bootstrap_if_empty=True)
        self.manager.write_page(
            wiki=self.wiki,
            page_path=Path("design/plan.md"),
            title="Plan",
            content="Content body",
            actor=self.ACTOR,
            message="新增 plan",
        )
        page = self.local_wiki / "design/plan.md"
        self.assertTrue(page.exists())
        index = self.local_wiki / "design/index.md"
        if not index.exists():
            index = self.local_wiki / "index.md"
        self.assertIn("[Plan]", index.read_text(encoding="utf-8"))
        log = next((self.local_wiki / "log").rglob("*.md"))
        log_text = log.read_text(encoding="utf-8")
        self.assertIn(self.ACTOR, log_text)
        self.assertIn("(../../index.md)", log_text)
        self.assertIn("(../../design/plan.md)", log_text)

    def test_write_sub_index_links_parent_index_and_log(self):
        self.manager.sync_wiki(self.wiki, bootstrap_if_empty=True)
        self.manager.write_page(
            wiki=self.wiki,
            page_path=Path("projects/team-wiki-skill/index.md"),
            title="team-wiki-skill",
            content="Project home",
            actor=self.ACTOR,
            message="初始化项目页",
        )
        top_index = self.local_wiki / "index.md"
        project_index = self.local_wiki / "projects/team-wiki-skill/index.md"
        project_changelog = self.local_wiki / "projects/team-wiki-skill/changelog.md"
        self.assertIn("[team-wiki-skill](projects/team-wiki-skill/index.md)", top_index.read_text(encoding="utf-8"))
        self.assertTrue(project_changelog.exists())
        self.assertIn("[Change Log](changelog.md)", project_index.read_text(encoding="utf-8"))
        log = next((self.local_wiki / "log").rglob("*.md"))
        log_text = log.read_text(encoding="utf-8")
        self.assertIn("[index](../../index.md)", log_text)
        self.assertIn("[team-wiki-skill](../../projects/team-wiki-skill/index.md)", log_text)
        self.assertNotIn("[index](../../projects/team-wiki-skill/index.md)", log_text)
        self.assertTrue(project_index.exists())

    def test_write_page_deduplicates_same_target_path_in_index(self):
        self.manager.sync_wiki(self.wiki, bootstrap_if_empty=True)
        project_index = self.local_wiki / "projects/sample-project/index.md"
        project_index.parent.mkdir(parents=True, exist_ok=True)
        project_index.write_text(
            "\n".join(
                [
                    "# Sample Project",
                    "",
                    "## 页面",
                    "",
                    "- [进展](progress.md)",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        self.manager.write_page(
            wiki=self.wiki,
            page_path=Path("projects/sample-project/progress.md"),
            title="项目进展",
            content="内容",
            actor=self.ACTOR,
            message="更新项目进展",
        )
        index_text = project_index.read_text(encoding="utf-8")
        self.assertEqual(index_text.count("(progress.md)"), 1)

    def test_update_index_rejects_log_index(self):
        self.manager.sync_wiki(self.wiki, bootstrap_if_empty=True)
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            with self.assertRaises(SystemExit):
                self.manager.update_index(
                    self.wiki,
                    self.local_wiki / "log" / "index.md",
                    self.local_wiki / "index.md",
                    "index",
                )
        self.assertIn("log/ 目录只保存按提交月份划分的日志文档", stderr.getvalue())

    def test_record_change_writes_changelog(self):
        self.manager.sync_wiki(self.wiki, bootstrap_if_empty=True)
        self._init_source_repo()
        self.manager.record_change(
            wiki=self.wiki,
            source_repo=self.source_repo,
            target_path=Path("changelog/2026-04.md"),
            actor=self.ACTOR,
            title="四月更新",
            from_ref="HEAD^",
            to_ref="HEAD",
        )
        page = self.local_wiki / "changelog/2026-04.md"
        content = page.read_text(encoding="utf-8")
        self.assertIn("## 四月更新", content)
        self.assertIn("feat: update source", content)

    def test_record_release_writes_project_changelog(self):
        self.manager.sync_wiki(self.wiki, bootstrap_if_empty=True)
        path = self.manager.record_release(
            wiki=self.wiki,
            project_path=Path("projects/sample-project/index.md"),
            actor=self.ACTOR,
            version="1.0.0",
            items=["首个里程碑发布", "交互体验优化"],
        )
        self.assertEqual(path, self.local_wiki / "projects/sample-project/changelog.md")
        content = path.read_text(encoding="utf-8")
        self.assertIn("## 1.0.0 ·", content)
        self.assertIn("- 首个里程碑发布", content)
        self.assertIn("- 交互体验优化", content)
        log = next((self.local_wiki / "log").rglob("*.md"))
        self.assertIn("记录版本发布: 1.0.0", log.read_text(encoding="utf-8"))

    def test_ingest_feishu_creates_page(self):
        self.manager.sync_wiki(self.wiki, bootstrap_if_empty=True)
        self.manager.ingest_feishu(
            wiki=self.wiki,
            target_path=Path("sources/feishu/2026-04/demo.md"),
            title="会议纪要",
            source_url="https://example.feishu.cn/doc/demo",
            content="这是摘要\n\n这是正文",
            actor=self.ACTOR,
        )
        page = self.local_wiki / "sources/feishu/2026-04/demo.md"
        content = page.read_text(encoding="utf-8")
        self.assertIn("> 来源：https://example.feishu.cn/doc/demo", content)
        self.assertIn("## 导入内容", content)


if __name__ == "__main__":
    unittest.main()
