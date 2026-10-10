# SPDX-License-Identifier: BUSL-1.1
# Licensed under the Business Source License 1.1 (see LICENSE); Change Date: four
# years from publication; Change License: Apache-2.0
# Copyright (c) 2026 Empower Agile
from billing.daily_rates import DailyRates
from billing.rate_table_converter import RateTableConverter


def test_euro_stays_euro():
    assert RateTableConverter(DailyRates()).convert(4599, "EUR") == 4599


def test_francs_at_todays_rate():
    assert RateTableConverter(DailyRates()).convert(10000, "CHF") == 9300


def test_pounds_at_todays_rate():
    assert RateTableConverter(DailyRates()).convert(20000, "GBP") == 17000
