from backend.common import refresh_progress


def teardown_function(_fn):
    # Reset shared module state so tests don't leak into each other.
    refresh_progress.finish()


def test_snapshot_starts_idle():
    refresh_progress.start(0)
    refresh_progress.finish()
    assert refresh_progress.snapshot() == {
        "running": False,
        "total": 0,
        "completed": 0,
        "current_ticker": None,
    }


def test_start_then_update_reports_progress():
    refresh_progress.start(3)
    refresh_progress.update("ABC.L", 1)
    snap = refresh_progress.snapshot()
    assert snap == {
        "running": True,
        "total": 3,
        "completed": 1,
        "current_ticker": "ABC.L",
    }


def test_finish_clears_running_and_current_ticker():
    refresh_progress.start(2)
    refresh_progress.update("ABC.L", 1)
    refresh_progress.finish()
    snap = refresh_progress.snapshot()
    assert snap["running"] is False
    assert snap["current_ticker"] is None
    # total/completed are left as-is so a final poll can still show "2/2".
    assert snap["total"] == 2


def test_update_is_a_noop_when_not_running():
    refresh_progress.finish()
    refresh_progress.update("ABC.L", 1)
    snap = refresh_progress.snapshot()
    assert snap["running"] is False
    assert snap["current_ticker"] is None


def test_update_clamps_completed_to_total():
    """The bar can never report more than 100% (#8046)."""
    refresh_progress.start(2)
    refresh_progress.update("ABC.L", 5)
    snap = refresh_progress.snapshot()
    assert snap["completed"] == 2
    assert snap["total"] == 2


def test_second_start_overwrites_the_single_slot():
    """Documented single-slot tradeoff: a concurrent second refresh replaces
    the first's progress rather than being tracked separately (#8074)."""
    refresh_progress.start(3)
    refresh_progress.update("FIRST.L", 2)
    refresh_progress.start(5)
    refresh_progress.update("SECOND.L", 1)
    assert refresh_progress.snapshot() == {
        "running": True,
        "total": 5,
        "completed": 1,
        "current_ticker": "SECOND.L",
    }


def test_snapshot_is_a_copy():
    refresh_progress.start(1)
    snap = refresh_progress.snapshot()
    snap["completed"] = 99
    assert refresh_progress.snapshot()["completed"] == 0
