# Copyright (c) 2025, Marco Noce <nce.marco@gmail.com>
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

import re
import io
import zipfile
import requests
from github_client import repo
from config import GITHUB_TOKEN

def clean_line(line):
    """
    Remove a leading ISO timestamp and ANSI escape sequences (including replacement characters)
    from a log line.
    """
    cleaned = re.sub(r"^\s*\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s*", "", line)
    cleaned = re.sub(r"(?:\x1b|�)\[[0-9;]*[mK]", "", cleaned)
    return cleaned.strip()

def extract_error_snippets(lines):
    """
    Extracts all error lines from the log that start with FAILED, FATAL, or ERROR.
    """
    candidates = []
    for line in lines:
        cleaned = clean_line(line)
        if re.match(r'^(FAILED|FATAL|fatal|ERROR|error|WARNING|warning)', cleaned):
            candidates.append(cleaned)
    return candidates

def match_job_for_log(normalized_folder, job_lookup):
    """
    Matches a normalized folder name from the log to a job in job_lookup.
    """
    for key, job in job_lookup.items():
        if normalized_folder in key or key in normalized_folder:
            return job
    return None

def check_ci_errors_and_comment(pr, add_label, remove_label, post_comment, archive_comment):
    """
    Check CI logs for the PR, extract error snippets, post a comment with details,
    and update labels accordingly.
    """
    print(f"🔎 Checking CI logs for PR #{pr.number}...")
    runs = repo.get_workflow_runs(event="pull_request", head_sha=pr.head.sha)
    if runs.totalCount == 0:
        print("❌ No CI runs found.")
        return

    latest_run = runs[0]
    if latest_run.status != "completed":
        print("⏳ CI is still running...")
        return

    logs_url = latest_run.logs_url
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    r = requests.get(logs_url, headers=headers)
    if r.status_code != 200:
        print("⚠️ Failed to download logs")
        return

    job_lookup = {}
    failed_jobs = set()
    jobs_url = f"https://api.github.com/repos/{repo.full_name}/actions/runs/{latest_run.id}/jobs"
    jr = requests.get(jobs_url, headers=headers)
    if jr.status_code == 200:
        for job in jr.json().get("jobs", []):
            name = job["name"]
            if job["conclusion"] == "failure":
                key = re.sub(r"[^a-z0-9]", "_", name.lower())
                job_lookup[key] = name
                failed_jobs.add(name)
    else:
        print("⚠️ Failed to fetch job list")
        return

    if not failed_jobs:
        print(f"✅ All jobs passed for PR #{pr.number}.")
        archive_comment(pr)
        remove_label(pr, "stale_ci")
        remove_label(pr, "needs_revision")
        add_label(pr, "success")
        return

    job_logs = {}
    with zipfile.ZipFile(io.BytesIO(r.content)) as zip_file:
        for file_name in zip_file.namelist():
            if not file_name.endswith(".txt"):
                continue
            folder = file_name.split("/")[0]
            normalized_folder = re.sub(r"^\d+_", "", folder).replace(".txt", "").strip().lower()
            normalized_folder = re.sub(r"[^a-z0-9]", "_", normalized_folder)
            matched_job = match_job_for_log(normalized_folder, job_lookup)
            if not matched_job or matched_job in job_logs:
                continue
            with zip_file.open(file_name) as f:
                try:
                    content = f.read().decode("utf-8", errors="ignore")
                except Exception as ex:
                    print(f"⚠️ Error reading {file_name}: {ex}")
                    continue
                lines = content.splitlines()
                snippets = extract_error_snippets(lines)
                if snippets:
                    combined_snippets = "\n\n---\n\n".join(snippets)
                    job_logs[matched_job] = combined_snippets

    if not job_logs:
        print("❌ Some jobs failed, but no valid error snippets found.")
        return

    comment_body = "🚨 **CI Test Failures Detected**\n\n"
    for job, combined_snippet in job_logs.items():
        comment_body += f"### ⚙️ {job}\n"
        comment_body += f"```bash\n{combined_snippet[:1000]}\n```\n\n"

    post_comment(pr, comment_body)
    remove_label(pr, "success")
    remove_label(pr, "stale_ci")
    remove_label(pr, "needs_revision")
    add_label(pr, "stale_ci")
    add_label(pr, "needs_revision")
