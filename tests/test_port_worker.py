"""Execution scheduling uses real threads and event barriers, with no provider."""
import importlib
import logging
import threading
import time

import pytest

import port_worker as W


def test_import_and_construction_do_not_start_work(monkeypatch):
    def forbidden_start(_thread):
        pytest.fail("Import or construction started a thread")

    monkeypatch.setattr(threading.Thread, "start", forbidden_start)
    importlib.reload(W)
    calls = []
    worker = W.PortExecutionWorker(lambda: calls.append(True))
    worker.wake()
    assert worker.stop()
    assert calls == []


@pytest.mark.parametrize("interval", [0, -1, float("inf"), float("nan")])
def test_invalid_polling_interval_is_rejected(interval):
    with pytest.raises(ValueError):
        W.PortExecutionWorker(lambda: None, poll_seconds=interval)


def test_worker_runs_immediately_and_periodically_without_wakes():
    condition = threading.Condition()
    starts = []

    def cycle():
        with condition:
            starts.append(time.monotonic())
            condition.notify_all()

    worker = W.PortExecutionWorker(cycle, poll_seconds=0.025)
    try:
        assert worker.start()
        with condition:
            assert condition.wait_for(lambda: len(starts) >= 3, timeout=1)
        assert worker.stop(timeout=1)
        assert starts[1] - starts[0] >= 0.02
        assert starts[2] - starts[1] >= 0.02
    finally:
        worker.stop(timeout=1)


def test_repeated_starts_and_wakes_never_overlap_cycles():
    entered = threading.Event()
    release = threading.Event()
    next_cycle = threading.Event()
    guard = threading.Lock()
    counts = {"calls": 0, "active": 0, "maximum": 0}

    def cycle():
        with guard:
            counts["calls"] += 1
            call = counts["calls"]
            counts["active"] += 1
            counts["maximum"] = max(counts["maximum"], counts["active"])
        try:
            if call == 1:
                entered.set()
                release.wait(2)
            else:
                next_cycle.set()
        finally:
            with guard:
                counts["active"] -= 1

    worker = W.PortExecutionWorker(cycle, poll_seconds=60)
    try:
        assert worker.start()
        assert entered.wait(1)
        for _ in range(10):
            assert not worker.start()
            worker.wake()
        with guard:
            assert counts["calls"] == 1
        release.set()
        assert next_cycle.wait(1), "Wake during work must survive until that work finishes"
        assert worker.stop(timeout=1)
        assert counts == {"calls": 2, "active": 0, "maximum": 1}
    finally:
        release.set()
        worker.stop(timeout=1)


def test_cycle_failure_is_sanitized_and_later_polling_continues(caplog):
    recovered = threading.Event()
    calls = []

    def cycle():
        calls.append(True)
        if len(calls) == 1:
            raise RuntimeError("private account details must stay out of logs")
        recovered.set()

    worker = W.PortExecutionWorker(cycle, poll_seconds=0.01)
    try:
        with caplog.at_level(logging.WARNING, logger="port_worker"):
            assert worker.start()
            assert recovered.wait(1)
            assert worker.stop(timeout=1)
        assert len(calls) >= 2
        assert "PORT execution cycle failed" in caplog.text
        assert "private account" not in caplog.text
        assert all(record.exc_info is None for record in caplog.records)
    finally:
        worker.stop(timeout=1)


def test_stop_waits_for_inflight_work_then_prevents_more_cycles():
    entered = threading.Event()
    release = threading.Event()
    completed = threading.Event()
    stop_started = threading.Event()
    stop_finished = threading.Event()
    results = []
    calls = []

    def cycle():
        calls.append(True)
        entered.set()
        release.wait(2)
        completed.set()

    worker = W.PortExecutionWorker(cycle, poll_seconds=0.01)

    def shutdown():
        stop_started.set()
        results.append(worker.stop(timeout=1))
        stop_finished.set()

    stopper = threading.Thread(target=shutdown, daemon=True)
    try:
        assert worker.start()
        assert entered.wait(1)
        worker.wake()
        stopper.start()
        assert stop_started.wait(1)
        assert not stop_finished.wait(0.025)
        release.set()
        assert stop_finished.wait(1)
        assert completed.is_set()
        assert results == [True]
        assert calls == [True]
        assert worker.stop(timeout=1)
    finally:
        release.set()
        worker.stop(timeout=1)
        if stopper.ident is not None:
            stopper.join(1)


def test_stop_timeout_reports_failure_and_a_later_stop_can_finish(caplog):
    entered = threading.Event()
    release = threading.Event()

    def cycle():
        entered.set()
        release.wait(2)

    worker = W.PortExecutionWorker(cycle, poll_seconds=60)
    try:
        assert worker.start()
        assert entered.wait(1)
        with caplog.at_level(logging.WARNING, logger="port_worker"):
            assert not worker.stop(timeout=0)
        assert "PORT execution worker did not stop before its timeout." in caplog.text
        assert not worker.start(), "A timed-out callback must not get a second worker"
        release.set()
        assert worker.stop(timeout=1)
        assert worker.stop(timeout=0)
    finally:
        release.set()
        worker.stop(timeout=1)


def test_completed_worker_can_restart_once():
    completed = threading.Event()
    calls = []

    def cycle():
        calls.append(True)
        completed.set()

    worker = W.PortExecutionWorker(cycle, poll_seconds=60)
    try:
        for expected_calls in (1, 2):
            completed.clear()
            assert worker.start()
            assert completed.wait(1)
            assert worker.stop(timeout=1)
            worker.wake()  # Stopped workers stay stopped.
            assert len(calls) == expected_calls
    finally:
        worker.stop(timeout=1)
