# Copyright (c) 2025, Marco Noce <nce.marco@gmail.com>
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

import os
os.environ["GITHUB_TOKEN"] = "dummy_token"  # Set dummy token early

# Patch the Github class before github_client is imported
import github
from types import SimpleNamespace

def dummy_get_repo(self, repo_name):
    return SimpleNamespace(
        full_name="dummy/repo",
        get_workflow_runs=lambda **kwargs: SimpleNamespace(
            totalCount=0,
            status="completed",
            logs_url="https://dummy.url/logs",
            id=123
        ),
        get_issue_comments=lambda: [],
        get_pull=lambda number: SimpleNamespace(
            number=number,
            head=SimpleNamespace(sha="dummy_sha"),
            get_issue_comments=lambda: []
        )
    )

class DummyGithub:
    def __init__(self, token):
        self.token = token
    get_repo = dummy_get_repo

# Override the Github class with our dummy version
github.Github = DummyGithub

# Remove github_client from sys.modules to force re-import
import sys
if "github_client" in sys.modules:
    del sys.modules["github_client"]

# Now import github_client; it will use our patched github.Github
import github_client
