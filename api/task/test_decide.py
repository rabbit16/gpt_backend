from api.task.decide import decide_from_log


def test_empty_log_is_pending():
    status, reason = decide_from_log("")
    assert status == "pending"
    assert "没有日志" in reason


def test_latest_failure_wins_over_earlier_success():
    log = "task started\nbuild success\nTraceback (most recent call last):\nError: boom"
    status, reason = decide_from_log(log)
    assert status == "failed"
    assert "Error" in reason or "失败" in reason


def test_latest_success_wins():
    log = "error while retrying\nretry running\nall checks finished"
    status, _reason = decide_from_log(log)
    assert status == "done"


def test_incomplete_is_not_done():
    status, _reason = decide_from_log("task incomplete, still running")
    assert status == "running"


def test_no_error_is_not_failed():
    status, _reason = decide_from_log("health check: no error")
    assert status == "pending"


def test_exit_code():
    assert decide_from_log("process exit code 0")[0] == "done"
    assert decide_from_log("process exit code 1")[0] == "failed"


def test_chinese_latest_line():
    log = "开始执行\n执行中\n任务已完成"
    assert decide_from_log(log)[0] == "done"
    assert decide_from_log("脚本超时，任务中断")[0] == "failed"
