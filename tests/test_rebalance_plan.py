"""Tests for asset-class drift and per-account trade planning (#9446)."""

import json
import random

import pytest

from backend.common.allocation_policy import (
    AllocationPolicy,
    SettingsUnreadableError,
    load_allocation_policy,
    parse_policy,
    save_allocation_policy,
)
from backend.common.portfolio_loader import ACCOUNT_STEM_KEY
from backend.common.rebalance_plan import (
    UNCLASSIFIED,
    _water_fill,
    bucket_holdings,
    build_plan,
    split_classes,
    suggest_account_trades,
    suggest_new_cash,
)


def _h(ticker, value, asset_class=None, instrument_type=None):
    return {
        "ticker": ticker,
        "market_value_gbp": value,
        "asset_class": asset_class,
        "instrument_type": instrument_type,
    }


def _portfolio(*accounts):
    # The route builds portfolios with include_account_stem=True; the stem
    # (here the lower-cased name) is each account's stable id (#9496).
    return {
        "accounts": [
            {"account_type": name, ACCOUNT_STEM_KEY: name.lower(), "holdings": list(holdings)}
            for name, holdings in accounts
        ]
    }


def _policy(tolerance=5.0, **targets):
    return AllocationPolicy(targets={k.replace("_", "-"): v for k, v in targets.items()}, tolerance_pct=tolerance)


def _by_account(trades):
    grouped = {}
    for trade in trades:
        grouped.setdefault(trade["account"], []).append(trade)
    return grouped


# ----------------------------------------------------------------- policy


def test_parse_policy_normalises_aliases_and_drops_zero_targets():
    policy = parse_policy({"targets": {"Equities": 60, "Fixed Income": 40, "cash": 0}, "tolerance_pct": 3})
    assert policy.targets == {"equity": 60.0, "bond": 40.0}
    assert policy.tolerance_pct == 3.0


@pytest.mark.parametrize(
    "data, match",
    [
        ({"targets": {"equity": 60, "bond": 30}}, "total 100"),
        ({"targets": {"equity": -10, "bond": 110}}, "between 0% and 100%"),
        ({"targets": {"fund": 100}}, "Unknown asset class"),
        ({"targets": {"equity": 50, "equities": 50}}, "more than once"),
        ({"targets": {"equity": 100}, "tolerance_pct": -1}, "tolerance_pct"),
    ],
)
def test_parse_policy_rejects_invalid(data, match):
    with pytest.raises(ValueError, match=match):
        parse_policy(data)


def test_parse_policy_reads_other_commodities_without_gold():
    # The #9718 key is an exact sub-class match: no gold sibling needed.
    policy = parse_policy({"targets": {"equity": 90, "other_commodities": 10}})
    assert policy.targets == {"equity": 90.0, "other_commodities": 10.0}


def test_parse_policy_reads_legacy_commodities_beside_gold_as_the_sub_class():
    # Pre-#9718 "commodities" beside gold was the "other commodities" sub-class (#9653).
    policy = parse_policy({"targets": {"equity": 85, "gold": 7.5, "commodities": 7.5}})
    assert policy.targets == {"equity": 85.0, "gold": 7.5, "other_commodities": 7.5}


@pytest.mark.parametrize("key", ["commodities", "Commodities", " commodities "])
def test_parse_policy_reads_lone_commodities_as_the_whole_class(key):
    # Without another commodity sub-class beside it, "commodities" keeps its
    # pre-#9653 meaning (the Commodity class, gold included), so a policy sent
    # through the API or hand-edited before the change is not reinterpreted.
    policy = parse_policy({"targets": {"equity": 80, key: 20}})
    assert policy.targets == {"equity": 80.0, "commodity": 20.0}


def test_parse_policy_zero_gold_still_marks_commodities_as_the_sub_class():
    policy = parse_policy({"targets": {"equity": 90, "gold": 0, "commodities": 10}})
    assert policy.targets == {"equity": 90.0, "other_commodities": 10.0}


def test_parse_policy_rejects_legacy_and_new_other_commodities_together():
    with pytest.raises(ValueError, match="more than once"):
        parse_policy({"targets": {"equity": 80, "commodities": 10, "other_commodities": 10}})


def test_saved_legacy_sub_class_policy_loads_and_saves_with_the_new_key(tmp_path):
    (tmp_path / "alex").mkdir()
    legacy = {"allocation_policy": {"targets": {"equity": 85, "gold": 7.5, "commodities": 7.5}, "tolerance_pct": 5}}
    (tmp_path / "alex" / "settings.json").write_text(json.dumps(legacy))
    policy = load_allocation_policy("alex", tmp_path)
    assert policy.targets == {"equity": 85.0, "gold": 7.5, "other_commodities": 7.5}
    stored = json.loads((tmp_path / "alex" / "settings.json").read_text())["allocation_policy"]["targets"]
    assert "commodities" in stored  # read-side migration only
    save_allocation_policy("alex", policy, tmp_path)
    stored = json.loads((tmp_path / "alex" / "settings.json").read_text())["allocation_policy"]["targets"]
    assert stored == {"equity": 85.0, "gold": 7.5, "other_commodities": 7.5}


def test_saved_whole_commodity_target_keeps_its_meaning(tmp_path):
    # Saves have always stored the canonical class key ("commodity"), never the
    # "commodities" alias, so reading "commodities" as the sub-class (#9653)
    # cannot change a policy saved by the app.
    (tmp_path / "alex").mkdir()
    save_allocation_policy("alex", parse_policy({"targets": {"Equity": 80, "Commodity": 20}}), tmp_path)
    stored = json.loads((tmp_path / "alex" / "settings.json").read_text())["allocation_policy"]["targets"]
    assert stored == {"equity": 80.0, "commodity": 20.0}
    assert load_allocation_policy("alex", tmp_path).targets == {"equity": 80.0, "commodity": 20.0}


def test_parse_policy_allows_empty_targets():
    assert parse_policy({}).targets == {}


def test_policy_round_trips_and_preserves_other_settings(tmp_path):
    owner_dir = tmp_path / "alex"
    owner_dir.mkdir()
    (owner_dir / "settings.json").write_text(json.dumps({"hold_days_min": 30}))

    save_allocation_policy("alex", _policy(4, equity=70, bond=30), tmp_path)

    stored = json.loads((owner_dir / "settings.json").read_text())
    assert stored["hold_days_min"] == 30
    loaded = load_allocation_policy("alex", tmp_path)
    assert loaded.targets == {"equity": 70.0, "bond": 30.0}
    assert loaded.tolerance_pct == 4.0


def test_load_policy_ignores_invalid_stored_policy(tmp_path):
    owner_dir = tmp_path / "alex"
    owner_dir.mkdir()
    (owner_dir / "settings.json").write_text(json.dumps({"allocation_policy": {"targets": {"equity": 10}}}))
    assert load_allocation_policy("alex", tmp_path).targets == {}


def test_save_policy_refuses_to_overwrite_corrupt_settings(tmp_path):
    owner_dir = tmp_path / "alex"
    owner_dir.mkdir()
    settings = owner_dir / "settings.json"
    settings.write_text('{"hold_days_min": 30,')  # truncated JSON

    with pytest.raises(SettingsUnreadableError):
        save_allocation_policy("alex", _policy(5, equity=100), tmp_path)
    assert settings.read_text() == '{"hold_days_min": 30,'
    # Reads degrade to "no policy" instead of failing the page.
    assert load_allocation_policy("alex", tmp_path).targets == {}


def test_load_policy_missing_owner_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_allocation_policy("nobody", tmp_path)


# ----------------------------------------------------------------- bucketing


def test_bucket_holdings_cash_unclassified_and_unpriced():
    holdings = bucket_holdings(
        _portfolio(
            (
                "ISA",
                [
                    _h("CASH.GBP", 100, instrument_type="Cash"),
                    _h("AAA", 300, "Equity"),
                    _h("ZZZ", None, "equity"),
                ],
            ),
            ("SIPP", [_h("BBB", 200, "bond"), _h("QQQ", 50, None)]),
        )
    )
    assert holdings.total == pytest.approx(650)
    assert holdings.class_total("cash") == pytest.approx(100)
    assert holdings.class_total("equity") == pytest.approx(300)
    assert holdings.class_total(UNCLASSIFIED) == pytest.approx(50)
    assert holdings.unpriced == ["ZZZ"]
    assert holdings.accounts[0].cash == pytest.approx(100)


def test_account_ids_are_stable_when_accounts_are_reordered():
    isa = ("ISA", [_h("EQ1", 700, "equity"), _h("BD1", 100, "bond")])
    sipp = ("SIPP", [_h("EQ2", 200, "equity"), _h("BD2", 100, "bond")])
    first = bucket_holdings(_portfolio(isa, sipp))
    reordered = bucket_holdings(_portfolio(sipp, isa))

    assert [a.id for a in first.accounts] == ["isa", "sipp"]
    assert {a.id: a.label for a in reordered.accounts} == {"isa": "ISA", "sipp": "SIPP"}

    # A new-cash request made with the id from the first plan still targets
    # the SIPP after the order changes.
    policy = _policy(5, equity=60, bond=40)
    result = suggest_new_cash(reordered, policy, 500, first.accounts[1].id)
    assert result["account"] == "SIPP"
    assert {t["ticker"] for t in result["trades"]} <= {"EQ2", "BD2"}


def test_accounts_with_the_same_type_get_distinct_ids():
    portfolio = {
        "accounts": [
            {"account_type": "ISA", ACCOUNT_STEM_KEY: "isa", "holdings": [_h("EQ1", 100, "equity")]},
            {"account_type": "ISA", ACCOUNT_STEM_KEY: "isa_2", "holdings": [_h("EQ2", 100, "equity")]},
        ]
    }
    assert [a.id for a in bucket_holdings(portfolio).accounts] == ["isa", "isa_2"]


def test_missing_account_id_raises_instead_of_using_the_index():
    with pytest.raises(ValueError, match="include_account_stem"):
        bucket_holdings({"accounts": [{"account_type": "ISA", "holdings": []}]})


def test_duplicate_account_id_raises():
    portfolio = {
        "accounts": [
            {"account_type": "ISA", ACCOUNT_STEM_KEY: "isa", "holdings": []},
            {"account_type": "SIPP", ACCOUNT_STEM_KEY: "isa", "holdings": []},
        ]
    }
    with pytest.raises(ValueError, match="Duplicate account id 'isa'"):
        bucket_holdings(portfolio)


def test_plan_without_policy_shows_current_weights_only():
    plan = build_plan(_portfolio(("ISA", [_h("AAA", 750, "equity"), _h("CASH.GBP", 250)])), AllocationPolicy())
    rows = {row["asset_class"]: row for row in plan["classes"]}
    assert rows["equity"]["current_pct"] == 75.0
    assert rows["equity"]["target_pct"] is None
    assert rows["equity"]["in_band"] is None
    assert plan["trades"] == []


def test_unclassified_bucket_is_reported_not_dropped():
    plan = build_plan(
        _portfolio(("ISA", [_h("AAA", 800, "equity"), _h("QQQ", 200, None)])),
        _policy(equity=100),
    )
    assert plan["unclassified_value"] == 200.0
    assert plan["unclassified_pct"] == 20.0
    assert any("no asset class" in note for note in plan["notes"])


def test_unclassified_holdings_listed_for_classify_page():
    # #9495: the classify page lists each unclassified instrument once, summed
    # across accounts, largest first, with the symbol/exchange to save it under.
    plan = build_plan(
        _portfolio(
            ("ISA", [_h("AAA.L", 500, "equity"), _h("QQQ.N", 100, None), _h("ZZZ", 300, None)]),
            ("SIPP", [_h("QQQ.N", 150, None), _h("CASH.GBP", 50)]),
        ),
        _policy(equity=100),
    )
    assert plan["unclassified_holdings"] == [
        {"ticker": "ZZZ", "symbol": "ZZZ", "exchange": None, "name": None, "value": 300.0},
        {"ticker": "QQQ.N", "symbol": "QQQ", "exchange": "N", "name": None, "value": 250.0},
    ]
    assert plan["unclassified_value"] == 550.0


# ----------------------------------------------------------------- trades


def test_in_band_classes_produce_no_trades():
    holdings = bucket_holdings(_portfolio(("ISA", [_h("AAA", 620, "equity"), _h("BBB", 380, "bond")])))
    result = suggest_account_trades(holdings, _policy(5, equity=60, bond=40))
    assert result["trades"] == []


def test_out_of_band_trades_stay_within_each_account():
    holdings = bucket_holdings(
        _portfolio(
            ("ISA", [_h("EQ1", 800, "equity"), _h("BD1", 200, "bond")]),
            ("SIPP", [_h("EQ2", 800, "equity"), _h("BD2", 200, "bond")]),
        )
    )
    trades = suggest_account_trades(holdings, _policy(5, equity=60, bond=40))["trades"]

    by_account = _by_account(trades)
    assert set(by_account) == {"ISA", "SIPP"}
    for account_trades in by_account.values():
        sells = sum(t["amount"] for t in account_trades if t["action"] == "sell")
        buys = sum(t["amount"] for t in account_trades if t["action"] == "buy")
        assert sells == pytest.approx(200)
        assert buys == pytest.approx(sells)
    isa = {(t["action"], t["asset_class"]): t for t in by_account["ISA"]}
    assert isa[("sell", "equity")]["ticker"] == "EQ1"
    assert isa[("buy", "bond")]["ticker"] == "BD1"


def test_trades_carry_the_hinted_instrument_name():
    named = {**_h("EQ1", 800, "equity"), "name": "  Equity Fund One  "}
    unnamed = _h("BD1", 200, "bond")
    holdings = bucket_holdings(_portfolio(("ISA", [named, unnamed])))
    trades = suggest_account_trades(holdings, _policy(5, equity=60, bond=40))["trades"]

    by_key = {(t["action"], t["asset_class"]): t for t in trades}
    assert by_key[("sell", "equity")]["name"] == "Equity Fund One"
    assert by_key[("buy", "bond")]["ticker"] == "BD1"
    assert by_key[("buy", "bond")]["name"] is None


def test_trade_without_ticker_hint_has_no_name():
    holdings = bucket_holdings(
        _portfolio(("ISA", [{**_h("EQ1", 900, "equity"), "name": "Eq"}, _h("CASH.GBP", 100, instrument_type="Cash")]))
    )
    trades = suggest_account_trades(holdings, _policy(5, equity=60, bond=40))["trades"]
    bond_buy = next(t for t in trades if t["asset_class"] == "bond")
    assert bond_buy["ticker"] is None
    assert bond_buy["name"] is None


def test_buys_never_exceed_account_cash_plus_sells():
    # ISA has the spare cash; SIPP has nothing to fund a buy with.
    holdings = bucket_holdings(
        _portfolio(
            ("ISA", [_h("CASH.GBP", 400, instrument_type="Cash"), _h("EQ1", 300, "equity")]),
            ("SIPP", [_h("EQ2", 300, "equity")]),
        )
    )
    result = suggest_account_trades(holdings, _policy(5, equity=100))
    by_account = _by_account(result["trades"])
    assert "SIPP" not in by_account
    isa_buys = sum(t["amount"] for t in by_account["ISA"] if t["action"] == "buy")
    assert isa_buys == pytest.approx(400)
    assert result["unfunded_amount"] == 0.0


def test_cash_is_never_sold_and_only_excess_cash_is_deployed():
    holdings = bucket_holdings(
        _portfolio(("ISA", [_h("CASH.GBP", 300, instrument_type="Cash"), _h("EQ1", 700, "equity")]))
    )
    trades = suggest_account_trades(holdings, _policy(5, equity=90, cash=10))["trades"]
    assert all(not (t["asset_class"] == "cash" and t["action"] == "sell") for t in trades)
    assert all(not t["ticker"] or not t["ticker"].startswith("CASH") for t in trades)
    buys = [t for t in trades if t["action"] == "buy"]
    # Equity needs +200 to reach 900; cash above its 10% target is exactly 200.
    assert buys == [
        {
            "account_id": "isa",
            "account": "ISA",
            "asset_class": "equity",
            "action": "buy",
            "amount": 200.0,
            "ticker": "EQ1",
            "name": None,
        }
    ]


def test_unfunded_when_only_buy_side_is_out_of_band():
    holdings = bucket_holdings(
        _portfolio(("ISA", [_h("EQ1", 840, "equity"), _h("PR1", 100, "property"), _h("BD1", 60, "bond")]))
    )
    # equity +4pp and property +2pp are inside a 5pp band, so nothing is sold;
    # bond is -6pp (out of band, needs +60) and there is no cash to fund it.
    result = suggest_account_trades(holdings, _policy(5, equity=80, property=8, bond=12))
    assert result["trades"] == []
    assert result["unfunded_amount"] == pytest.approx(60.0)


def test_both_sides_out_of_band_are_traded_and_funded():
    holdings = bucket_holdings(_portfolio(("ISA", [_h("EQ1", 900, "equity"), _h("BD1", 100, "bond")])))
    assert suggest_account_trades(holdings, _policy(2, equity=88, bond=12))["trades"] == []
    result = suggest_account_trades(holdings, _policy(1, equity=88, bond=12))
    assert result["unfunded_amount"] == 0.0
    assert sorted((t["action"], t["asset_class"], t["amount"]) for t in result["trades"]) == [
        ("buy", "bond", 20.0),
        ("sell", "equity", 20.0),
    ]


def test_cash_class_fund_is_sold_only_to_fund_buys():
    # A money-market fund classified as cash is a sellable instrument, not
    # literal cash: it must be sold before its value can fund a buy.
    holdings = bucket_holdings(_portfolio(("ISA", [_h("MMF1", 500, "cash", "ETF"), _h("EQ1", 500, "equity")])))
    assert holdings.accounts[0].cash == 0.0
    trades = suggest_account_trades(holdings, _policy(5, equity=90, cash=10))["trades"]
    assert sorted((t["action"], t["asset_class"], t["amount"], t["ticker"]) for t in trades) == [
        ("buy", "equity", 400.0, "EQ1"),
        ("sell", "cash", 400.0, "MMF1"),
    ]

    # Nothing to buy: the fund is left alone even though cash is over target.
    assert suggest_account_trades(holdings, _policy(50, equity=90, cash=10))["trades"] == []


def test_literal_cash_is_spent_before_cash_class_funds_are_sold():
    holdings = bucket_holdings(
        _portfolio(
            (
                "ISA",
                [
                    _h("CASH.GBP", 100, instrument_type="Cash"),
                    _h("MMF1", 400, "cash", "ETF"),
                    _h("EQ1", 500, "equity"),
                ],
            )
        )
    )
    trades = suggest_account_trades(holdings, _policy(5, equity=90, cash=10))["trades"]
    by_key = {(t["action"], t["asset_class"]): t for t in trades}
    assert by_key[("sell", "cash")]["amount"] == 300.0
    assert by_key[("sell", "cash")]["ticker"] == "MMF1"
    assert by_key[("buy", "equity")]["amount"] == 400.0
    assert not any(t["ticker"] and t["ticker"].startswith("CASH") for t in trades)


def _assert_accounts_self_funded(holdings, trades):
    """Every account's buys are covered by its own sales plus its own literal cash."""
    for account in holdings.accounts:
        mine = [t for t in trades if t["account_id"] == account.id]
        buys = sum(t["amount"] for t in mine if t["action"] == "buy")
        sells = sum(t["amount"] for t in mine if t["action"] == "sell")
        assert buys <= sells + account.cash + 0.01 * (len(mine) + 1), (account.label, mine)
        for t in mine:
            if t["action"] == "sell":
                assert t["amount"] <= account.class_values.get(t["asset_class"], 0.0) + 0.01


def test_cash_in_one_account_never_funds_a_buy_in_another():
    # ISA has spare cash; SIPP has none. Whatever SIPP buys must come from
    # SIPP's own sales, never from the ISA's cash.
    holdings = bucket_holdings(
        _portfolio(
            ("ISA", [_h("CASH.GBP", 400, instrument_type="Cash"), _h("EQ1", 600, "equity")]),
            ("SIPP", [_h("EQ2", 1000, "equity")]),
        )
    )
    trades = suggest_account_trades(holdings, _policy(5, equity=70, bond=20, cash=10))["trades"]
    _assert_accounts_self_funded(holdings, trades)
    sipp = [t for t in trades if t["account"] == "SIPP"]
    sipp_sold = sum(t["amount"] for t in sipp if t["action"] == "sell")
    sipp_bought = sum(t["amount"] for t in sipp if t["action"] == "buy")
    assert sipp_bought == pytest.approx(sipp_sold, abs=0.02)


def test_buys_are_self_funded_per_account_across_random_portfolios():
    rng = random.Random(9446)
    classes = ["equity", "bond", "property", "commodity", "cash"]
    for _ in range(300):
        accounts = []
        for name in ("ISA", "SIPP", "GIA")[: rng.randint(1, 3)]:
            holdings = [_h(f"{name}-{c}", rng.choice([0, rng.uniform(1, 5000)]), c) for c in classes]
            holdings.append(_h(f"CASH.{name}", rng.choice([0, rng.uniform(1, 3000)]), instrument_type="Cash"))
            accounts.append((name, holdings))
        weights = [rng.choice([0, rng.randint(1, 10)]) for _ in classes] or [1]
        if not any(weights):
            weights[0] = 1
        total = sum(weights)
        targets = {c: w * 100 / total for c, w in zip(classes, weights) if w}
        drift = sum(targets.values()) - 100
        targets[next(iter(targets))] -= drift
        policy = AllocationPolicy(targets=targets, tolerance_pct=rng.choice([0.5, 2, 5, 10]))

        holdings = bucket_holdings(_portfolio(*accounts))
        trades = suggest_account_trades(holdings, policy)["trades"]
        _assert_accounts_self_funded(holdings, trades)
        assert not any(t["ticker"] and t["ticker"].startswith("CASH.") for t in trades)


def test_held_class_without_target_is_sold_when_out_of_band():
    holdings = bucket_holdings(_portfolio(("ISA", [_h("EQ1", 800, "equity"), _h("GLD", 200, "commodity")])))
    trades = suggest_account_trades(holdings, _policy(5, equity=100))["trades"]
    assert {(t["action"], t["asset_class"], t["amount"]) for t in trades} == {
        ("sell", "commodity", 200.0),
        ("buy", "equity", 200.0),
    }


# ----------------------------------------------------------------- new cash


def test_water_fill_tops_up_largest_gaps_first():
    assert _water_fill({"a": 100, "b": 40, "c": 10}, 50) == {"a": pytest.approx(50)}
    allocation = _water_fill({"a": 100, "b": 40, "c": 10}, 80)
    assert allocation == {"a": pytest.approx(70), "b": pytest.approx(10)}
    assert _water_fill({"a": -5}, 10) == {}


def test_new_cash_is_buy_only_in_chosen_account_and_reduces_drift():
    portfolio = _portfolio(
        ("ISA", [_h("EQ1", 700, "equity"), _h("BD1", 100, "bond")]),
        ("SIPP", [_h("EQ2", 200, "equity"), _h("BD2", 100, "bond")]),
    )
    policy = _policy(5, equity=60, bond=40)
    holdings = bucket_holdings(portfolio)
    result = suggest_new_cash(holdings, policy, 500, "sipp")

    assert result["account"] == "SIPP"
    assert all(t["action"] == "buy" and t["account"] == "SIPP" for t in result["trades"])
    assert sum(t["amount"] for t in result["trades"]) + result["keep_as_cash"] == pytest.approx(500)
    # After the 500 the total is 1600: bond needs 640 (holds 200), equity 960
    # (holds 900). Those gaps sum to exactly 500, so both are fully closed.
    amounts = {t["asset_class"]: (t["amount"], t["ticker"]) for t in result["trades"]}
    assert amounts == {"bond": (440.0, "BD2"), "equity": (60.0, "EQ2")}


def _total_abs_drift(holdings, policy, extra=None):
    extra = extra or {}
    total = holdings.total + sum(extra.values())
    return sum(
        abs((holdings.class_total(c) + extra.get(c, 0.0)) / total * 100 - pct) for c, pct in policy.targets.items()
    )


def test_new_cash_reduces_total_absolute_drift():
    holdings = bucket_holdings(
        _portfolio(("ISA", [_h("EQ1", 900, "equity"), _h("BD1", 50, "bond"), _h("PR1", 50, "property")]))
    )
    policy = _policy(5, equity=60, bond=30, property=10)
    before = _total_abs_drift(holdings, policy)
    result = suggest_new_cash(holdings, policy, 300, "isa")
    bought = {t["asset_class"]: t["amount"] for t in result["trades"]}
    after = _total_abs_drift(holdings, policy, bought)
    assert sum(bought.values()) == pytest.approx(300)
    assert after < before


def test_water_fill_never_allocates_more_than_the_gaps():
    # Amount larger than every positive gap: each gap is filled exactly and
    # the remainder is left unallocated (the caller keeps it as cash).
    assert _water_fill({"a": 100, "b": 40, "c": 10}, 200) == {
        "a": pytest.approx(100),
        "b": pytest.approx(40),
        "c": pytest.approx(10),
    }


def test_new_cash_allocates_to_cash_target_as_keep():
    holdings = bucket_holdings(_portfolio(("ISA", [_h("EQ1", 1000, "equity")])))
    result = suggest_new_cash(holdings, _policy(5, equity=50, cash=50), 400, "isa")
    assert result["trades"] == []
    assert result["keep_as_cash"] == 400.0


@pytest.mark.parametrize(
    "policy, amount, account, match",
    [
        (AllocationPolicy(), 100, "isa", "Set target"),
        (_policy(equity=100), 0, "isa", "positive"),
        (_policy(equity=100), float("nan"), "isa", "positive"),
        (_policy(equity=100), 100, "0", "Unknown account"),
    ],
)
def test_new_cash_rejects_invalid_input(policy, amount, account, match):
    holdings = bucket_holdings(_portfolio(("ISA", [_h("EQ1", 100, "equity")])))
    with pytest.raises(ValueError, match=match):
        suggest_new_cash(holdings, policy, amount, account)


def test_plan_notes_cash_only_when_still_overweight_after_trades():
    deployed = build_plan(
        _portfolio(("ISA", [_h("CASH.GBP", 500, instrument_type="Cash"), _h("EQ1", 500, "equity")])),
        _policy(5, equity=90, cash=10),
    )
    # Equity needs +400, exactly the cash above its 10% target.
    assert [(t["action"], t["amount"]) for t in deployed["trades"]] == [("buy", 400.0)]
    assert not any("Cash would still be" in note for note in deployed["notes"])

    idle = build_plan(
        _portfolio(
            (
                "ISA",
                [
                    _h("CASH.GBP", 600, instrument_type="Cash"),
                    _h("EQ1", 200, "equity"),
                    _h("BD1", 200, "bond"),
                ],
            )
        ),
        _policy(20, equity=40, bond=30, cash=30),
    )
    # Equity -20pp and bond -10pp sit inside the 20pp band, so no trades, but
    # cash is +30pp over target.
    assert idle["trades"] == []
    assert any("Cash would still be 60.00%" in note for note in idle["notes"])


# ----------------------------------------------------------------- sub-classes (#9543)


def _hs(ticker, value, asset_class, sub_asset_class=None):
    return {**_h(ticker, value, asset_class), "sub_asset_class": sub_asset_class}


def _gilt_portfolio():
    return _portfolio(
        (
            "ISA",
            [
                _hs("EQ1", 400, "equity", "broad_equity"),
                _hs("GLTL.L", 50, "bond", "long_gilts"),
                _hs("IGLT.L", 150, "bond", "intermediate_gilts"),
                _hs("SEGA.L", 100, "bond", "overseas_government"),
                _hs("PHGP.L", 100, "commodity", "gold"),
                _hs("PHSP.L", 50, "commodity", "other_commodities"),
                _h("CASH.GBP", 150, instrument_type="Cash"),
            ],
        )
    )


def test_parse_policy_accepts_sub_class_targets():
    policy = parse_policy(
        {"targets": {"equity": 40, "Long_Gilts": 10, "intermediate_gilts": 10, "short_gilts": 20, "gold": 20}}
    )
    assert policy.targets == {
        "equity": 40.0,
        "long_gilts": 10.0,
        "intermediate_gilts": 10.0,
        "short_gilts": 20.0,
        "gold": 20.0,
    }


@pytest.mark.parametrize(
    "targets, match",
    [
        ({"bond": 50, "long_gilts": 50}, "Bond either as a whole or by sub-class"),
        ({"commodity": 50, "gold": 50}, "Commodity either as a whole or by sub-class"),
        ({"equity": 50, "short_gilt": 50}, "Unknown asset class"),
    ],
)
def test_parse_policy_rejects_mixed_levels_and_unknown_sub_classes(targets, match):
    with pytest.raises(ValueError, match=match):
        parse_policy({"targets": targets})


def test_parse_policy_zero_parent_does_not_conflict_with_sub_classes():
    policy = parse_policy({"targets": {"bond": 0, "long_gilts": 100}})
    assert policy.targets == {"long_gilts": 100.0}


def test_class_level_policy_ignores_sub_classes():
    """A class-level policy plans exactly as before sub-classes existed."""
    policy = _policy(5, equity=40, bond=20, commodity=20, cash=20)
    with_subs = build_plan(_gilt_portfolio(), policy)
    stripped = _portfolio(
        (
            "ISA",
            [
                {k: v for k, v in h.items() if k != "sub_asset_class"}
                for h in _gilt_portfolio()["accounts"][0]["holdings"]
            ],
        )
    )
    without_subs = build_plan(stripped, policy)
    assert with_subs["classes"] == without_subs["classes"]
    assert with_subs["trades"] == without_subs["trades"]
    assert with_subs["notes"] == without_subs["notes"]
    assert [row["asset_class"] for row in with_subs["classes"]] == ["equity", "bond", "cash", "commodity"]
    assert all(row["parent"] is None for row in with_subs["classes"])


def test_sub_class_policy_drift_rows_and_trades():
    policy = AllocationPolicy(
        targets={"equity": 40, "long_gilts": 10, "intermediate_gilts": 10, "short_gilts": 20, "gold": 20},
        tolerance_pct=5,
    )
    plan = build_plan(_gilt_portfolio(), policy)
    rows = {row["asset_class"]: row for row in plan["classes"]}
    assert list(rows) == [
        "equity",
        "long_gilts",
        "intermediate_gilts",
        "short_gilts",
        "overseas_government",
        "cash",
        "gold",
        "other_commodities",
    ]
    assert rows["long_gilts"]["parent"] == "bond"
    assert rows["long_gilts"]["label"] == "Long gilts"
    assert rows["intermediate_gilts"]["drift_pct"] == 5.0
    assert rows["overseas_government"]["target_pct"] == 0.0
    assert rows["gold"]["drift_pct"] == -10.0

    trades = {(t["action"], t["asset_class"]): t for t in plan["trades"]}
    # Untargeted overseas government (10pp over) and cash fund buys.
    assert trades[("sell", "overseas_government")]["amount"] == 100.0
    assert trades[("sell", "overseas_government")]["ticker"] == "SEGA.L"
    assert ("buy", "short_gilts") in trades
    assert trades[("buy", "gold")]["ticker"] == "PHGP.L"
    assert ("sell", "other_commodities") not in trades  # 5pp over: inside the band


def test_split_class_holding_without_sub_class_is_reported_not_dropped():
    portfolio = _portfolio(
        ("ISA", [_hs("EQ1", 500, "equity"), _hs("GLTL.L", 300, "bond", "long_gilts"), _hs("MYST", 200, "bond")])
    )
    plan = build_plan(portfolio, AllocationPolicy(targets={"equity": 50, "long_gilts": 50}, tolerance_pct=5))
    rows = {row["asset_class"]: row for row in plan["classes"]}
    assert plan["total_value"] == 1000.0
    assert rows["bond"]["label"] == "Bond \u2014 no sub-class"
    assert rows["bond"]["parent"] == "bond"
    assert rows["bond"]["current_pct"] == 20.0
    assert rows["bond"]["target_pct"] is None
    assert not any(t["asset_class"] == "bond" for t in plan["trades"])
    assert any("(MYST) has no sub-class" in note for note in plan["notes"])


def test_sub_class_from_wrong_parent_falls_back_to_parent():
    portfolio = _portfolio(("ISA", [_hs("ODD", 100, "bond", "gold")]))
    holdings = bucket_holdings(portfolio, frozenset({"bond"}))
    assert holdings.class_total("bond") == pytest.approx(100)
    assert holdings.class_total("gold") == 0


def test_plan_reports_sub_class_breakdown_for_class_level_policy():
    plan = build_plan(_gilt_portfolio(), _policy(5, equity=40, bond=20, commodity=20, cash=20))
    breakdown = {row["asset_class"]: row["current_pct"] for row in plan["sub_classes"]}
    assert breakdown == {
        "broad_equity": 40.0,
        "long_gilts": 5.0,
        "intermediate_gilts": 15.0,
        "overseas_government": 10.0,
        "gold": 10.0,
        "other_commodities": 5.0,
    }


def test_golden_butterfly_drift_splits_equity_by_sub_class():
    portfolio = _portfolio(
        (
            "ISA",
            [
                _hs("VWRL.L", 300, "equity", "broad_equity"),
                _hs("ZPRV.L", 100, "equity", "small_cap_value"),
                _hs("GLTL.L", 200, "bond", "long_gilts"),
                _hs("IGLS.L", 200, "bond", "short_gilts"),
                _hs("PHGP.L", 200, "commodity", "gold"),
            ],
        )
    )
    targets = {"broad_equity": 20, "small_cap_value": 20, "long_gilts": 20, "short_gilts": 20, "gold": 20}
    plan = build_plan(portfolio, AllocationPolicy(targets=targets, tolerance_pct=5))
    rows = {row["asset_class"]: row for row in plan["classes"]}
    assert rows["broad_equity"]["drift_pct"] == 10.0
    assert rows["small_cap_value"]["drift_pct"] == -10.0
    assert rows["small_cap_value"]["parent"] == "equity"


def test_new_cash_fills_sub_class_targets():
    policy = AllocationPolicy(targets={"equity": 40, "long_gilts": 30, "gold": 30}, tolerance_pct=5)
    holdings = bucket_holdings(_gilt_portfolio(), split_classes(policy))
    result = suggest_new_cash(holdings, policy, 500, "isa")
    bought = {t["asset_class"]: t["amount"] for t in result["trades"]}
    # Gaps on the new 1,500 total: long gilts 400, gold 350, equity 200.
    # Water-filling 500 levels them all at 150 short of target.
    assert bought == {"long_gilts": 250.0, "gold": 200.0, "equity": 50.0}
    assert result["trades"][0]["ticker"] == "GLTL.L"


def test_untargeted_no_sub_class_bucket_never_offsets_sub_class_drift():
    # The unresolved bond bucket is 30pp of the portfolio and has no target:
    # it must neither be sold nor count towards long gilts' drift.
    portfolio = _portfolio(
        ("ISA", [_hs("EQ1", 600, "equity"), _hs("GLTL.L", 100, "bond", "long_gilts"), _hs("MYST", 300, "bond")])
    )
    plan = build_plan(portfolio, AllocationPolicy(targets={"equity": 60, "long_gilts": 40}, tolerance_pct=5))
    rows = {row["asset_class"]: row for row in plan["classes"]}
    assert rows["long_gilts"]["drift_pct"] == -30.0
    assert rows["bond"]["in_band"] is None
    assert {t["asset_class"] for t in plan["trades"]} <= {"long_gilts"}


def test_parse_policy_accepts_one_class_whole_and_another_by_sub_class():
    policy = parse_policy({"targets": {"bond": 50, "gold": 50}})
    assert policy.targets == {"bond": 50.0, "gold": 50.0}


def test_sub_class_breakdown_includes_no_sub_class_row():
    portfolio = _portfolio(("ISA", [_hs("GLTL.L", 300, "bond", "long_gilts"), _hs("MYST", 100, "bond")]))
    plan = build_plan(portfolio, AllocationPolicy())
    breakdown = {row["asset_class"]: row for row in plan["sub_classes"]}
    assert breakdown["long_gilts"]["current_pct"] == 75.0
    assert breakdown["bond"]["parent"] == "bond"
    assert breakdown["bond"]["label"] == "Bond \u2014 no sub-class"
    assert breakdown["bond"]["current_pct"] == 25.0
