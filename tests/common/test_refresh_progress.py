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
