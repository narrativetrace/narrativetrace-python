# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
"""Logging for the recipe scenarios -- the one piece of project configuration they share.

``checkout_log_handler`` is this build's own plumbing (it points the handler at the file a recipe
page embeds); the three lines below it are what a project writes -- the ``logging`` setup the
add-logging page shows.
"""

import logging
import os
import sys

from examples.recipes.checkout.env import LOG_FILE_ENV
from narrativetrace import NarrativeContextFilter


def checkout_log_handler() -> logging.Handler:
    """The file named by ``NARRATIVETRACE_RECIPE_LOG`` (rewritten each run), else stdout."""
    target = os.environ.get(LOG_FILE_ENV)
    if target:
        return logging.FileHandler(target, mode="w", encoding="utf-8")
    return logging.StreamHandler(sys.stdout)


handler = checkout_log_handler()
# snippet:begin logging
handler.addFilter(NarrativeContextFilter())  # makes traceName available to the format below
logging.basicConfig(
    level=logging.DEBUG,  # the bridge logs every call at DEBUG; INFO would hide all of it
    format="%(levelname)-5s [%(traceName)s] [%(name)s] - %(message)s",
    handlers=[handler],
)
# snippet:end logging
