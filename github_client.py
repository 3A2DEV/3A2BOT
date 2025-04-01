# Copyright (c) 2025, Marco Noce <nce.marco@gmail.com>
# GNU General Public License v3.0+
# SPDX-License-Identifier: GPL-3.0-or-later

from github import Github
from config import GITHUB_TOKEN, REPO_NAME

g = Github(GITHUB_TOKEN)
repo = g.get_repo(REPO_NAME)
