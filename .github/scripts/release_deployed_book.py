"""Publish changelog releases for the exact commit built by a deployment."""

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from changelog_releases import new_releases, publish, run


def artifact(repository, run_id, name):
    endpoint = f"repos/{repository}/actions/runs/{run_id}/artifacts"
    payload = json.loads(run("gh", "api", endpoint, "--paginate", "--slurp"))
    matches = [
        item for page in payload for item in page["artifacts"]
        if item["name"] == name and not item["expired"]
    ]
    if not matches:
        return None
    with tempfile.TemporaryDirectory(prefix="changelog-artifact-") as directory:
        run("gh", "run", "download", str(run_id), "--repo", repository, "--name", name,
            "--dir", directory)
        path = Path(directory) / f"{name}.json"
        return json.loads(path.read_text(encoding="utf-8"))


def ancestor(first, second):
    result = subprocess.run(["git", "merge-base", "--is-ancestor", first, second],
                            capture_output=True, text=True)
    if result.returncode not in (0, 1):
        raise subprocess.CalledProcessError(result.returncode, result.args, stderr=result.stderr)
    return result.returncode == 0


def find_baseline(repository, branch, current_run):
    runs = json.loads(run("gh", "run", "list", "--repo", repository,
                          "--workflow", "changelog-releases.yml", "--status", "success",
                          "--event", "workflow_run", "--limit", "100", "--json", "databaseId"))
    missing = False
    for candidate in runs:
        run_id = candidate["databaseId"]
        if str(run_id) == str(current_run):
            continue
        saved = artifact(repository, run_id, "changelog-release-baseline")
        if saved and saved.get("branch") == branch:
            return saved["commit"]
        if saved is None:
            jobs = json.loads(run("gh", "api", f"repos/{repository}/actions/runs/{run_id}/jobs"))
            release_jobs = [job for job in jobs["jobs"] if job["name"] == "create-releases"]
            if not release_jobs or any(job["conclusion"] != "skipped" for job in release_jobs):
                missing = True
    if missing or len(runs) == 100:
        raise ValueError("A previous release baseline is unavailable or expired; refusing to guess")
    return None


def initial_baseline(repository, branch, deploy_run, metadata):
    details = json.loads(run("gh", "api", f"repos/{repository}/actions/runs/{deploy_run}"))
    runs = json.loads(run("gh", "run", "list", "--repo", repository,
                          "--workflow", str(details["workflow_id"]), "--status", "completed",
                          "--limit", "100", "--json", "databaseId,createdAt"))
    introduced = datetime.fromisoformat(run(
        "git", "log", "--diff-filter=A", "--format=%cI", "--",
        ".github/scripts/release_deployed_book.py",
    ).strip().splitlines()[-1])
    before = metadata.get("before") if metadata.get("push_branch") == branch else None
    seen_current = False
    reached_start = False
    for candidate in runs:
        if datetime.fromisoformat(candidate["createdAt"].replace("Z", "+00:00")) < introduced:
            reached_start = True
            break
        run_id = candidate["databaseId"]
        if str(run_id) == str(deploy_run):
            seen_current = True
            continue
        if not seen_current:
            continue
        previous = artifact(repository, run_id, "changelog-release-build")
        if previous and previous.get("branch") == branch and previous.get("push_branch") == branch:
            previous_before = previous.get("before")
            if previous_before:
                before = previous_before
    if not seen_current or (len(runs) == 100 and not reached_start):
        raise ValueError("Cannot safely establish the initial baseline from deployment history")
    return before


def process(metadata, baseline, repository, branch, preprocess):
    if metadata.get("branch") != branch:
        raise ValueError(f"Deployment did not record a successful build for {branch!r}")
    commit = metadata.get("commit", "")
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit):
        raise ValueError("Invalid deployment build commit")
    if not baseline:
        raise ValueError("Cannot establish a safe initial baseline for the configured branch")
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", baseline) or set(baseline) == {"0"}:
        raise ValueError("Invalid or new-branch release baseline")
    if baseline == commit:
        return commit
    if ancestor(commit, baseline):
        print(f"Skipping older deployment {commit}", flush=True)
        return None
    if not ancestor(baseline, commit):
        raise ValueError("Deployed commit does not descend from the last processed build")
    for version, _introduced, body in new_releases(baseline, commit):
        publish(version, commit, body, repository, preprocess)
    return commit


def main():
    repository = os.environ["REPOSITORY"]
    branch = os.environ["RELEASE_BRANCH"]
    metadata = artifact(repository, os.environ["DEPLOY_RUN"], "changelog-release-build")
    if metadata is None:
        raise ValueError(f"Deployment did not produce successful build metadata for {branch!r}")
    commit = metadata.get("commit", "")
    if metadata.get("branch") != branch or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit):
        raise ValueError("Invalid deployment build branch or commit")
    run("git", "check-ref-format", "--branch", branch)
    if not ancestor(commit, f"refs/remotes/origin/{branch}"):
        raise ValueError("Deployed commit is not reachable from the configured branch")
    baseline = find_baseline(repository, branch, os.environ["CURRENT_RUN"])
    if baseline is None:
        baseline = os.environ.get("INITIAL_BASELINE") or initial_baseline(
            repository, branch, os.environ["DEPLOY_RUN"], metadata
        )
    branches = os.environ.get("BRANCHES_TO_PREPROCESS", "").split()
    commit = process(metadata, baseline, repository, branch, "*" in branches or branch in branches)
    if commit:
        Path(os.environ["BASELINE_FILE"]).write_text(
            json.dumps({"branch": branch, "commit": commit}) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr, file=sys.stderr, end="")
        print(f"Deployed changelog release failed: {error}", file=sys.stderr)
        sys.exit(1)
