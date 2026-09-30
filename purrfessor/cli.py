"""purrfessor — command line. 命令行。

  purrfessor init             one-time setup in your copy of the template (asks a few questions, sets GitHub secrets)
                              一次性配置：回答几个问题，自动设置 GitHub Secrets、开启 Pages、触发第一次部署
  purrfessor build ...        build the page (same as python -m purrfessor.build)
  purrfessor config-upload    after editing purrfessor.toml: upload it as the PURRFESSOR_CONFIG secret and redeploy
  purrfessor snapshot ...     used by the workflow (fetch / add)
  purrfessor lock-args        used by the workflow: Staticrypt password-page texts in the configured language
  purrfessor ci-env ...       used by the workflow: where the page goes ([site] path) and the Staticrypt salt

Secrets are read with getpass (never echoed) and handed to `gh secret set` on stdin. 口令和 token 不回显，经 stdin 交给 gh。
Running init again keeps the secrets you already set (press Enter). 再次运行 init 时，已设置的 secret 回车即可保留。
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .config import PKG, load, presets

CONFIG = Path("purrfessor.toml")
EXAMPLE = PKG / "templates" / "purrfessor.example.toml"
KEEP = " (already set — Enter keeps it / 已设置，回车保留)"


def ask(prompt: str, default: str = "") -> str:
    got = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
    return got or default


def gh(*args: str, stdin: str | None = None, check: bool = True) -> str:
    r = subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"gh {' '.join(args[:3])} failed: {r.stderr.strip()[:300]}")
    return r.stdout.strip()


def gh_ok(*args: str) -> bool:
    return subprocess.run(["gh", *args], capture_output=True, text=True).returncode == 0


def canvas_whoami(base: str, token: str) -> str | None:
    req = urllib.request.Request(f"{base.rstrip('/')}/api/v1/users/self", headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.load(r).get("name")
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None


def set_secret(repo: str, name: str, value: str) -> None:
    gh("secret", "set", name, "-R", repo, stdin=value)
    print(f"  ✓ secret {name}")


def init() -> None:
    if not shutil.which("gh"):
        raise SystemExit("Please install the GitHub CLI (https://cli.github.com) and run `gh auth login` first.\n"
                         "请先安装 GitHub CLI 并登录（gh auth login）。")
    repo = gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner", check=False)
    if not repo:
        raise SystemExit("Run this inside your copy of the Purrfessor template (a GitHub repo).\n"
                         "请在你用模板创建的 GitHub 仓库目录里运行。")
    print(f"🧙🐱 Purrfessor · 喵教授 — setting up {repo}\n")

    if CONFIG.exists() and ask(f"Use the existing {CONFIG}? / 使用现有的 {CONFIG}？ (Y/n)", "y").lower() != "n":
        S = load(CONFIG)
        preset, base = S.preset, S.canvas_url
        print(f"  ✓ {S.school} · {S.language} · {S.name}")
    else:
        preset, base = write_config()

    existing = set(gh("secret", "list", "-R", repo, "--json", "name", "-q", ".[].name", check=False).split())
    while True:
        token = getpass.getpass("Canvas token (Account → Settings → New Access Token; hidden / 不显示)"
                                + (KEEP if "CANVAS_TOKEN" in existing else "") + ": ").strip()
        if not token and "CANVAS_TOKEN" in existing:
            print("  ✓ keeping the current Canvas token / 保留现有 token")
            break
        who = canvas_whoami(base, token) if token else None
        if who:
            print(f"  ✓ Canvas: {who}")
            break
        print("  ✗ That token doesn't work with this Canvas. Try again. / token 不可用，请重试。")
    while True:
        pw = getpass.getpass("Site password / 网站口令 (hidden / 不显示)" + (KEEP if "SITE_PASSWORD" in existing else "") + ": ")
        if not pw and "SITE_PASSWORD" in existing:
            print("  ✓ keeping the current password / 保留现有口令")
            break
        if pw and pw == getpass.getpass("Again / 再输一次: "):
            break
        print("  ✗ Didn't match. / 两次不一致。")
    gemini = getpass.getpass("Gemini API key (optional / 可选; hidden)"
                             + (KEEP if "GEMINI_API_KEY" in existing else " (Enter to skip / 回车跳过)") + ": ").strip()

    if token:
        set_secret(repo, "CANVAS_TOKEN", token)
    if pw:
        set_secret(repo, "SITE_PASSWORD", pw)
    if gemini:
        set_secret(repo, "GEMINI_API_KEY", gemini)
    set_secret(repo, "PURRFESSOR_CONFIG", CONFIG.read_text(encoding="utf-8"))
    gh("variable", "set", "PURRFESSOR_ENABLED", "-R", repo, "--body", "true")
    print("  ✓ variable PURRFESSOR_ENABLED=true")
    pages = f"repos/{repo}/pages"
    if gh("api", pages, "--jq", ".build_type", check=False) == "workflow" or \
            gh_ok("api", "-X", "POST", pages, "-f", "build_type=workflow") or \
            gh_ok("api", "-X", "PUT", pages, "-f", "build_type=workflow"):
        print("  ✓ GitHub Pages → GitHub Actions")
    else:
        print(f"  ! Please enable Pages by hand: https://github.com/{repo}/settings/pages → Source: GitHub Actions\n"
              "    请手动开启：Settings → Pages → Source 选 GitHub Actions")

    gh("workflow", "run", "deploy.yml", "-R", repo, check=False)
    print("  ✓ deploy started (takes ~3 min) / 已触发部署（约 3 分钟）")
    S = load(CONFIG)
    if preset == "generic" and not (S.term.get("week1_monday") and S.classes):
        print("\n  ! Set [term] week1_monday / last_class_day and your [[classes]] in purrfessor.toml,\n"
              "    then run `purrfessor config-upload`. / 请在 purrfessor.toml 里填写学期日期和课表，再运行 config-upload。")
    owner, _, rest = repo.partition("/")
    print(f"\nYour page / 你的页面: https://{owner.lower()}.github.io/{rest}/{S.page_path}  🎉")


def write_config() -> tuple[str, str]:
    """Ask for preset, school, language and name; write purrfessor.toml from the example. → (preset, Canvas URL)"""
    names = presets()
    print("School presets / 学校预设: " + ", ".join(names) + "  (generic = any Canvas school / 其他 Canvas 学校)")
    preset = ask("Preset / 预设", "ucr" if "ucr" in names else "generic")
    school = {}
    if preset == "generic":
        school = {"name": ask("School name / 学校名称", "My School"),
                  "canvas_url": ask("Canvas URL (e.g. https://canvas.myschool.edu)"),
                  "timezone": ask("Time zone / 时区", "America/New_York")}
    language = ask("Language / 语言 (zh = 中文, en = English)", "zh").lower()
    language = language if language in ("zh", "en") else "en"
    name = ask("Your name on the page / 页面上显示的名字", "Me")
    text = EXAMPLE.read_text(encoding="utf-8")
    text = (text.replace('preset = "ucr"', f'preset = "{preset}"').replace('language = "zh"', f'language = "{language}"')
                .replace('name = "Alex"', f'name = "{name}"'))
    if school:
        text += "\n[school]\n" + "".join(f'{k} = "{v}"\n' for k, v in school.items())
    CONFIG.write_text(text, encoding="utf-8")
    print(f"  ✓ wrote {CONFIG} (private — git-ignored / 私密，不进仓库)")
    return preset, school.get("canvas_url") or _preset_canvas(preset)


def _preset_canvas(preset: str) -> str:
    import tomllib
    with open(PKG / "presets" / f"{preset}.toml", "rb") as f:
        return tomllib.load(f).get("school", {}).get("canvas_url", "")


def config_upload() -> None:
    repo = gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner")
    set_secret(repo, "PURRFESSOR_CONFIG", CONFIG.read_text(encoding="utf-8"))
    gh("workflow", "run", "deploy.yml", "-R", repo)
    print("  ✓ redeploy started / 已触发重新部署")


def lock_args(argv: list[str]) -> None:
    """One Staticrypt argument per line, for `mapfile -t ARGS < <(purrfessor lock-args)` in the workflow."""
    from .i18n import T
    path = argv[argv.index("--config") + 1] if "--config" in argv else CONFIG
    S = load(path)
    t = T(S.language)
    for flag, key in [("--template-title", "lock_title"), ("--template-instructions", "lock_instructions"),
                      ("--template-button", "lock_button"), ("--template-placeholder", "lock_placeholder"),
                      ("--template-remember", "lock_remember"), ("--template-error", "lock_error")]:
        print(flag)
        print(t(key, name=S.name))
    print("--template-color-primary")
    print("#2f6fd6")


def site_salt(repo_id: str, config: Path = Path(".staticrypt.json")) -> str:
    """The Staticrypt salt. Normally a hash of the repo id: stable across updates (so "remember me" keeps working)
    and different for every copy. A committed .staticrypt.json wins, so a site moved over from plain Staticrypt keeps
    its salt: old snapshots still decrypt and nobody has to log in again.
    盐：通常是仓库 id 的哈希；如果仓库里有 .staticrypt.json（从已有的 Staticrypt 网站迁移过来），就沿用它的盐。"""
    if config.exists():
        salt = str(json.loads(config.read_text(encoding="utf-8")).get("salt", ""))
        if re.fullmatch(r"[0-9a-f]{32}", salt):
            return salt
    return hashlib.sha256(f"purrfessor-{repo_id}".encode()).hexdigest()[:32]


def ci_env(argv: list[str]) -> None:
    """KEY=value lines for $GITHUB_ENV. PAGE is "" (site root) or "today/" ([site] path)."""
    ap = argparse.ArgumentParser(prog="purrfessor ci-env")
    ap.add_argument("--config", default=str(CONFIG))
    ap.add_argument("--base-url", required=True, help="the Pages URL, from actions/configure-pages")
    ap.add_argument("--repo-id", required=True)
    args = ap.parse_args(argv)
    S = load(args.config)
    page, base = S.page_path, args.base_url.rstrip("/")
    root = urllib.parse.urlparse(base).path.rstrip("/")
    if not page and Path("site/index.html").exists():
        print("::warning::site/index.html is replaced by the dashboard; set [site] path to keep both", file=sys.stderr)
    print(f"SALT={site_salt(args.repo_id)}")
    print(f"PAGE={page}")
    print(f"PAGE_URL={base}/{page}")
    print(f"ARCHIVE_BASE={root}/{page}archive/")
    print(f"HOME_URL={root + '/' if S.site.get('home') else ''}")


def main(argv: list[str] | None = None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    cmd, rest = (argv[0], argv[1:]) if argv else ("help", [])
    if cmd == "init":
        init()
    elif cmd == "build":
        from .build import main as build
        build(rest)
    elif cmd == "config-upload":
        config_upload()
    elif cmd == "lock-args":
        lock_args(rest)
    elif cmd == "ci-env":
        ci_env(rest)
    elif cmd == "snapshot":
        from .snapshot import cli as snapshot
        snapshot(rest)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
