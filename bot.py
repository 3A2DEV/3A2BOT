# Copyright (c) 2025, Marco Noce <nce.marco@gmail.com>
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

import time
import json
from threading import Thread
from github_client import repo
from ci_checker import check_ci_errors_and_comment
from github_ops import add_label, remove_label, post_or_update_comment, archive_old_comment
from issue_utils import get_unprocessed_items, parse_component_name, file_exists, comment_with_link
from config import PROCESSED_FILE

processed = set()
try:
    with open(PROCESSED_FILE) as f:
        processed = set(json.load(f))
except Exception as e:
    print(f"⚠️ Failed to load {PROCESSED_FILE}: {e}")

def bot_loop():
    global processed
    print("🤖 Bot loop started...")
    while True:
        for item in get_unprocessed_items(processed):
            print(f"🔄 Processing #{item.number}...")
            if item.pull_request:
                pr = repo.get_pull(item.number)
                check_ci_errors_and_comment(pr, add_label, remove_label, post_or_update_comment, archive_old_comment)
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
