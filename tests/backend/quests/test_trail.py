import types

import pytest

from backend.quests import trail


@pytest.fixture
def fake_paths(tmp_path, monkeypatch):
    root = tmp_path / "accounts"
    root.mkdir()

    def _fake_resolve_paths(repo_root, accounts_root):
        return types.SimpleNamespace(accounts_root=root)

    monkeypatch.setattr(trail.data_loader, "resolve_paths", _fake_resolve_paths)
    return root


def test_owners_for_user_matches_email_and_viewer(fake_paths, monkeypatch):
    (fake_paths / "owner_email").mkdir()
    (fake_paths / "owner_viewer").mkdir()

    meta = {
        "owner_email": {"email": "investor@example.com"},
        "owner_viewer": {"viewers": ["investor@example.com", "extra"]},
    }

    def _fake_load_person_meta(owner, root):
        assert root == fake_paths
        return meta.get(owner, {})

    monkeypatch.setattr(trail.data_loader, "load_person_meta", _fake_load_person_meta)

    owners = trail._owners_for_user("Investor@example.com")
    assert owners == ["owner_email", "owner_viewer"]


def test_owners_for_user_handles_missing_root(monkeypatch, tmp_path):
    missing = tmp_path / "missing"

    def _fake_resolve_paths(repo_root, accounts_root):
        return types.SimpleNamespace(accounts_root=missing)

    monkeypatch.setattr(trail.data_loader, "resolve_paths", _fake_resolve_paths)
    monkeypatch.setattr(trail.data_loader, "load_person_meta", lambda owner, root: {})

    assert trail._owners_for_user("nobody") == []


def test_owners_for_user_slug_fallback(fake_paths, monkeypatch):
    (fake_paths / "sluguser").mkdir()

    monkeypatch.setattr(trail.data_loader, "load_person_meta", lambda owner, root: {})

    owners = trail._owners_for_user("sluguser@example.com")
    assert owners == ["sluguser"]


def test_build_allowance_and_compliance_tasks(monkeypatch):
    monkeypatch.setattr(trail.allowances, "current_tax_year", lambda: 2024)

    def _fake_remaining(owner, year):
        assert owner == "alice"
        assert year == 2024
        return {
            "isa": {"remaining": 1234.56, "limit": 20000},
            "pension": {"remaining": 0, "limit": 40000},
        }

    monkeypatch.setattr(trail.allowances, "remaining_allowances", _fake_remaining)

    allowance_tasks = trail._build_allowance_tasks(["alice"])
    assert [task.id for task in allowance_tasks] == ["alice_allowance_isa"]
    assert "£1,235" in allowance_tasks[0].commentary
    assert "£20,000" in allowance_tasks[0].commentary

    def _fake_check_owner(owner, accounts_root):
        assert owner == "alice"
        return {
            "warnings": ["Missing W-8BEN", "Upload tax form"],
            "hold_countdowns": {"XYZ": 3, "ABC": 7},
        }

    monkeypatch.setattr(trail.compliance, "check_owner", _fake_check_owner)

    compliance_tasks = trail._build_compliance_tasks(["alice"])
    assert [task.id for task in compliance_tasks] == [
        "alice_compliance_warnings",
        "alice_hold_periods",
    ]
    assert compliance_tasks[0].commentary == "Missing W-8BEN (+1 more)"
    assert compliance_tasks[1].commentary == "XYZ unlocks in 3 days"


def test_once_tasks_custom_threshold_and_push_completion(monkeypatch):
    user = "investor@example.com"
    monkeypatch.setattr(trail.alerts, "_USER_THRESHOLDS", {user: "7%", "other": "5%"})
    monkeypatch.setattr(trail.alerts, "DEFAULT_THRESHOLD_PCT", 5.0)

    class _FakeStorage:
        def __init__(self):
            self.loaded = False

        def load(self):
            self.loaded = True
            return {
                user: {
                    "endpoint": "https://push.example.com/sub",
                    "keys": {"p256dh": "k", "auth": "a"},
                }
            }

    storage = _FakeStorage()
    monkeypatch.setattr(trail.alerts, "_SUBSCRIPTIONS_STORAGE", storage)

    call_log = {"count": 0}

    def _fake_subscription(requested_user):
        call_log["count"] += 1
        assert requested_user == user
        return {
            "endpoint": "https://push.example.com/sub",
            "keys": {"p256dh": "k", "auth": "a"},
        }

    monkeypatch.setattr(trail.alerts, "get_user_push_subscription", _fake_subscription)
    monkeypatch.setattr(trail, "load_goals", lambda current_user: [])

    assert trail._has_custom_threshold(user) is True
    assert trail._has_custom_threshold("someone_else") is False

    user_data = {"once": [], trail._AUTO_ONCE_KEY: []}

    trail._sync_once_completion(user_data, "create_goal", True)
    assert user_data[trail._AUTO_ONCE_KEY] == []

    trail._sync_once_completion(user_data, "auto_task", True)
    assert user_data[trail._AUTO_ONCE_KEY] == ["auto_task"]
    trail._sync_once_completion(user_data, "auto_task", False)
    assert user_data[trail._AUTO_ONCE_KEY] == []

    once_tasks = trail._build_once_tasks(user, user_data)

    assert call_log["count"] == 1
    assert storage.loaded is True
    assert user_data[trail._AUTO_ONCE_KEY] == []

    titles = {task.id: task.title for task in once_tasks}
    assert titles == {
        "create_goal": "Create your first savings goal",
        "set_alert_threshold": "Adjust your alert threshold",
        "enable_push_notifications": "Enable push notifications",
    }
