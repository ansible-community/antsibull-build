# Author: Felix Fontein <felix@fontein.de>
# GNU General Public License v3.0+ (see LICENSES/GPL-3.0-or-later.txt or
# https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: Ansible Project, 2024

"""
Code to reformat build data.
"""

from __future__ import annotations

from antsibull_core import app_context

from .changelog import ChangelogData


def reformat_build_data() -> int:
    """Reformat build data."""
    app_ctx = app_context.app_ctx.get()

    data_dir: str = app_ctx.extra["data_dir"]

    # Reformat changelog.yaml
    changelog = ChangelogData.ansible(directory=data_dir)
    changelog.save()

    return 0
