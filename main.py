# Copyright (c) 2025, Marco Noce <nce.marco@gmail.com>
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import re
import json
import time
import io
import zipfile
import requests
from threading import Thread
from flask import Flask
from github import Github

app = Flask(__name__)

@app.route("/")
def home():
    return "3A2DEV Bot is alive!", 200

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
REPO_NAME = "3A2DEV/a2dev.general"
PROCESSED_FILE = "processed.json"

g = Github(GITHUB_TOKEN)
repo = g.get_repo(REPO_NAME)

processed = set()
if os.path.exists(PROCESSED_FILE):
    with open(PROCESSED_FILE) as f:
        try:
            processed = set(json.load(f))
        except Exception as e:
            print(f"⚠️ Failed to load processed.json: {e}")

error_markers = [
    "FAILED", "failed", "ERROR", "Traceback", "SyntaxError",
    "ImportError", "ModuleNotFoundError", "assert",
    "ERROR! ", "fatal:", "task failed", "collection failure",
    "Test failures:", "ansible-test sanity", "invalid-documentation-markup",
    "non-existing option", "The test 'ansible-test sanity", "sanity failure",
    "test failed", "invalid value"
]

skip_patterns = re.compile(
    r"coverage:|##\[group\]|shell:|Cleaning up orphan processes|core-github-repository-slug|pull-request-change-detection",
    re.IGNORECASE
)

def extract_first_real_error(lines):
    for i, line in enumerate(lines):
        lower = line.lower()
        if any(marker in lower for marker in [m.lower() for m in error_markers]):
            if not skip_patterns.search(lower):
                return "\n".join(lines[max(0, i-3):i+7])
    return None

def check_ci_errors_and_comment(pr):
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
    jobs_url = f"https://api.github.com/repos/{REPO_NAME}/actions/runs/{latest_run.id}/jobs"
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
        return

    job_logs = {}
    seen_jobs = set()
    with zipfile.ZipFile(io.BytesIO(r.content)) as zip_file:
        for file_name in zip_file.namelist():
            if not file_name.endswith(".txt"):
                continue

            folder = file_name.split("/")[0]
            base_name = re.sub(r"^\d+_", "", folder).replace(".txt", "").strip()
            normalized = re.sub(r"[^a-z0-9]", "_", base_name.lower())
            matched_job = next((job_lookup[k] for k in job_lookup if normalized in k), None)

            if not matched_job or matched_job in seen_jobs:
                continue

            with zip_file.open(file_name) as f:
                lines = f.read().decode("utf-8", errors="ignore").splitlines()
                snippet = extract_first_real_error(lines)
                if snippet:
                    job_logs[matched_job] = snippet
                    seen_jobs.add(matched_job)

    if not job_logs:
        print("❌ Some jobs failed, but no valid error snippets found.")
        return

    comment_body = "🚨 **CI Test Failures Detected**\n\n"
    for job, snippet in job_logs.items():
        comment_body += f"### ⚙️ {job}\n```
{snippet[:1000]}
```\n\n"

    pr.create_issue_comment(comment_body)
    print("💬 Posted CI error comment")

def parse_component_name(body):
    match = re.search(r"###\s*Component Name\s*\n+([a-zA-Z0-9_]+)", body)
    return match.group(1) if match else None

def file_exists(path):
    try:
        repo.get_contents(path)
        return True
    except:
        return False

def comment_with_link(issue, path):
    url = f"https://github.com/{REPO_NAME}/blob/main/{path}"
    body = f"""Files identified in the description:

- [**{path}**]({url})"""
    issue.create_comment(body)
    print(f"✅ Commented on #{issue.number} with module path")

def add_label(item, label):
    if label not in [l.name for l in item.labels]:
        item.add_to_labels(label)

def remove_label(item, label):
    if label in [l.name for l in item.labels]:
        item.remove_from_labels(label)

def get_unprocessed_items():
    issues = repo.get_issues(state="open", sort="created", direction="desc")
    return [i for i in issues if i.number not in processed or any(l.name in ["success", "stale_ci", "needs_revision"] for l in i.labels)]

def bot_loop():
    global processed
    print("🤖 Bot loop started...")
    while True:
        for item in get_unprocessed_items():
            print(f"🔄 Processing #{item.number}...")
            if item.pull_request:
                pr = repo.get_pull(item.number)
                check_ci_errors_and_comment(pr)

            body = item.body or ""
            component = parse_component_name(body)
            if component:
                path = f"plugins/modules/{component}.py"
                if file_exists(path):
                    comment_with_link(item, path)

            processed.add(item.number)

        with open(PROCESSED_FILE, "w") as f:
            json.dump(list(processed), f)

        print("⏳ Sleeping for 3 minutes...")
        time.sleep(180)

def start_bot():
    Thread(target=bot_loop).start()

start_bot()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
