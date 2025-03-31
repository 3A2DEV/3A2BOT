# Copyright (c) 2025, Marco Noce <nce.marco@gmail.com>
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

import os
import re
import json
import time
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

# Load processed issues/PRs
if os.path.exists(PROCESSED_FILE):
    with open(PROCESSED_FILE) as f:
        processed = set(json.load(f))
else:
    processed = set()

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
    print(f"✅ Commented on #{issue.number}")

def get_unprocessed_items():
    issues = repo.get_issues(state="open", sort="created", direction="desc")
    return [i for i in issues if i.number not in processed]

def bot_loop():
    global processed
    while True:
        print("🔍 Checking issues and PRs...")
        for item in get_unprocessed_items():
            body = item.body or ""
            component = parse_component_name(body)
            if component:
                path = f"plugins/modules/{component}.py"
                if file_exists(path):
                    comment_with_link(item, path)
            processed.add(item.number)

        with open(PROCESSED_FILE, "w") as f:
            json.dump(list(processed), f)

        print("⏱ Sleeping for 2 minutes...")
        time.sleep(120)

def start_bot():
    thread = Thread(target=bot_loop)
    thread.start()

start_bot()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
