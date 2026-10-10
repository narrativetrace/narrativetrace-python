# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
def fee_for(days_late: int) -> int:
    """The late fee, in cents, for an invoice paid ``days_late`` days after it was due: 150 cents
    a day, nothing when it is on time."""
    if days_late <= 0:
        return 0
    return days_late * 150
