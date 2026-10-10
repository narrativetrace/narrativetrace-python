# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from billing.late_fees import fee_for


def test_no_fee_on_time():
    assert fee_for(0) == 0


def test_a_fee_per_day_late():
    assert fee_for(3) == 450
