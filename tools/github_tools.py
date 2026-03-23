"""GitHub API 툴 — Issues, PRs, 레포 정보 조회 및 관리."""

import os
from functools import lru_cache

from github import Auth, Github
from github.GithubException import GithubException


@lru_cache(maxsize=1)
def _client() -> Github:
    """GitHub 클라이언트를 반환한다. 토큰 없으면 예외 발생."""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN 환경변수가 설정되지 않았습니다.")
    return Github(auth=Auth.Token(token))


def _me() -> str:
    return _client().get_user().login


def list_my_issues(state: str = "open", limit: int = 20) -> str:
    """내가 담당한 GitHub 이슈 목록을 반환한다.

    Args:
        state: 이슈 상태 ("open" | "closed" | "all"), 기본값 "open"
        limit: 최대 반환 개수, 기본값 20

    Returns:
        이슈 목록 (번호, 제목, 레포, URL)
    """
    try:
        issues = _client().search_issues(
            f"assignee:{_me()} is:issue state:{state}",
        )
        results = []
        for i, issue in enumerate(issues):
            if i >= limit:
                break
            repo_name = issue.repository.full_name
            results.append(f"[{repo_name}#{issue.number}] {issue.title}\n  {issue.html_url}")
        return "\n\n".join(results) if results else f"담당 이슈 없음 (state={state})"
    except GithubException as e:
        return f"GitHub API 오류: {e}"


def list_my_prs(state: str = "open", limit: int = 20) -> str:
    """내가 작성한 GitHub PR 목록을 반환한다.

    Args:
        state: PR 상태 ("open" | "closed" | "merged" | "all"), 기본값 "open"
        limit: 최대 반환 개수, 기본값 20

    Returns:
        PR 목록 (번호, 제목, 레포, 상태, URL)
    """
    try:
        query = f"author:{_me()} is:pr"
        if state == "merged":
            query += " is:merged"
        elif state != "all":
            query += f" state:{state}"

        prs = _client().search_issues(query)
        results = []
        for i, pr in enumerate(prs):
            if i >= limit:
                break
            repo_name = pr.repository.full_name
            pr_info = pr.pull_request
            label = "merged" if (pr_info and pr_info.merged_at) else state
            results.append(f"[{repo_name}#{pr.number}] ({label}) {pr.title}\n  {pr.html_url}")
        return "\n\n".join(results) if results else f"해당하는 PR 없음 (state={state})"
    except GithubException as e:
        return f"GitHub API 오류: {e}"


def get_issue(repo: str, issue_number: int) -> str:
    """GitHub 이슈 상세 내용을 반환한다.

    Args:
        repo: 레포 이름 (예: "owner/repo-name")
        issue_number: 이슈 번호

    Returns:
        이슈 제목, 본문, 댓글 목록
    """
    try:
        issue = _client().get_repo(repo).get_issue(issue_number)
        lines = [
            f"# [{repo}#{issue_number}] {issue.title}",
            f"상태: {issue.state} | 작성자: {issue.user.login}",
            f"URL: {issue.html_url}",
            "",
            issue.body or "(본문 없음)",
        ]

        comments = list(issue.get_comments())
        if comments:
            lines.append(f"\n--- 댓글 {len(comments)}개 ---")
            for c in comments[:10]:
                lines.append(f"\n@{c.user.login}:\n{c.body}")

        return "\n".join(lines)
    except GithubException as e:
        return f"GitHub API 오류: {e}"


def create_issue(repo: str, title: str, body: str = "", labels: str = "") -> str:
    """GitHub 이슈를 생성한다.

    Args:
        repo: 레포 이름 (예: "owner/repo-name")
        title: 이슈 제목
        body: 이슈 본문 (마크다운 지원)
        labels: 레이블 목록 (쉼표 구분, 예: "bug,enhancement")

    Returns:
        생성된 이슈 URL
    """
    try:
        label_list = [lbl.strip() for lbl in labels.split(",") if lbl.strip()] if labels else []
        repository = _client().get_repo(repo)
        gh_labels = [repository.get_label(lbl) for lbl in label_list] if label_list else []
        issue = repository.create_issue(title=title, body=body, labels=gh_labels)
        return f"이슈 생성 완료: {issue.html_url}"
    except GithubException as e:
        return f"GitHub API 오류: {e}"


def comment_on_issue(repo: str, issue_number: int, body: str) -> str:
    """GitHub 이슈 또는 PR에 댓글을 작성한다.

    Args:
        repo: 레포 이름 (예: "owner/repo-name")
        issue_number: 이슈 또는 PR 번호
        body: 댓글 내용 (마크다운 지원)

    Returns:
        작성된 댓글 URL
    """
    try:
        issue = _client().get_repo(repo).get_issue(issue_number)
        comment = issue.create_comment(body)
        return f"댓글 작성 완료: {comment.html_url}"
    except GithubException as e:
        return f"GitHub API 오류: {e}"


def list_repo_issues(repo: str, state: str = "open", limit: int = 20) -> str:
    """특정 레포의 이슈 목록을 반환한다.

    Args:
        repo: 레포 이름 (예: "owner/repo-name")
        state: 이슈 상태 ("open" | "closed" | "all"), 기본값 "open"
        limit: 최대 반환 개수, 기본값 20

    Returns:
        이슈 목록
    """
    try:
        issues = _client().get_repo(repo).get_issues(state=state)
        results = []
        for i, issue in enumerate(issues):
            if i >= limit:
                break
            assignees = ", ".join(a.login for a in issue.assignees) or "없음"
            results.append(f"#{issue.number} {issue.title}\n  담당: {assignees} | {issue.html_url}")
        return "\n\n".join(results) if results else f"이슈 없음 (state={state})"
    except GithubException as e:
        return f"GitHub API 오류: {e}"
