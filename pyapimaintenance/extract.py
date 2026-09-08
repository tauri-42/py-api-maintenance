import re
import json
import urllib.request

from pyapimaintenance.llm_connector import extract_rules_from_changelog
from pyapimaintenance.rules_store import load_state, save_state, write_rules


def parse_requirements(path: str) -> list[tuple[str, str | None]]:
    libs = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            line = line.split(";")[0].strip()  
            match = re.match(r"^([A-Za-z0-9_.\-]+)\s*(==\s*([A-Za-z0-9_.\-]+))?", line)
            if not match:
                continue
            name, _, pinned = match.groups()
            libs.append((name, pinned))
    return libs


def get_pypi_info(library: str) -> dict:
    url = f"https://pypi.org/pypi/{library}/json"
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.load(resp)


def get_latest_version(library: str) -> str | None:
    try:
        info = get_pypi_info(library)
        return info["info"]["version"]
    except Exception:
        return None


def find_changelog_url(pypi_info: dict) -> str | None:
    project_urls = (pypi_info.get("info", {}) or {}).get("project_urls") or {}
    for key, url in project_urls.items():
        if "changelog" in key.lower() or "release" in key.lower():
            return url
    for key, url in project_urls.items():
        if "github.com" in (url or ""):
            return url.rstrip("/") + "/releases"
    return None


def fetch_github_releases_text(github_releases_url: str, max_releases: int = 15) -> str:
    m = re.search(r"github\.com/([^/]+)/([^/]+)", github_releases_url)
    if not m:
        return ""
    owner, repo = m.group(1), m.group(2).removesuffix(".git")
    api_url = f"https://api.github.com/repos/{owner}/{repo}/releases?per_page={max_releases}"
    req = urllib.request.Request(api_url, headers={"Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            releases = json.load(resp)
    except Exception:
        return ""
    chunks = []
    for r in releases:
        tag = r.get("tag_name", "")
        body = r.get("body") or ""
        chunks.append(f"## {tag}\n{body}")
    return "\n\n".join(chunks)


def get_changelog_text(pypi_info: dict) -> str:
    url = find_changelog_url(pypi_info)
    if url and "github.com" in url:
        text = fetch_github_releases_text(url)
        if text:
            return text
    return pypi_info.get("info", {}).get("description", "") or ""


def update_rules_for_repo(repo_path: str, requirements_filename: str = "requirements.txt") -> dict:
    req_path = f"{repo_path.rstrip('/')}/{requirements_filename}" if repo_path != "." \
        else requirements_filename
    libs = parse_requirements(req_path)
    state = load_state(repo_path)

    report = {"updated": [], "unchanged": [], "unknown": [], "errors": []}

    for name, pinned in libs:
        try:
            pypi_info = get_pypi_info(name)
        except Exception as e:
            report["errors"].append({"library": name, "error": str(e)})
            continue

        latest = pypi_info["info"]["version"]
        current_version = pinned or latest  
        last_known = state.get(name)

        if last_known == current_version:
            report["unchanged"].append({"library": name, "version": current_version})
            continue

        if pinned is None:
            report["unknown"].append({"library": name, "latest": latest})

        changelog_text = get_changelog_text(pypi_info)
        if not changelog_text.strip():
            report["errors"].append({
                "library": name,
                "error": f"no changelog found (version={current_version})",
            })
            continue

        raw_output = extract_rules_from_changelog(changelog_text)
        out_path = write_rules(name, raw_output)
        state[name] = current_version
        report["updated"].append({
            "library": name,
            "from": last_known,
            "to": current_version,
            "rules_path": out_path,
        })

    save_state(repo_path, state)
    return report


def format_report(report: dict) -> str:
    lines = []
    if report["updated"]:
        lines.append("Rules regenerated:")
        for item in report["updated"]:
            frm = item["from"] or "(new)"
            lines.append(f"  {item['library']}: {frm} -> {item['to']} ({item['rules_path']})")
    if report["unchanged"]:
        names = ", ".join(i["library"] for i in report["unchanged"])
        lines.append(f"Already current, skipped: {names}")
    if report["errors"]:
        lines.append("Errors:")
        for item in report["errors"]:
            lines.append(f"  {item['library']}: {item['error']}")
    return "\n".join(lines) if lines else "Nothing to do."