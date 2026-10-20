"""根据任务日志的最新反馈判断状态。

从最后一行往前看，第一条能对上的结果生效。同一行里取更靠后的关键词。
手动改过的状态不在这里覆盖，调用方自己决定要不要采纳。
"""
import re

FAIL_RE = re.compile(
    r"(失败|异常|报错|超时|中断|出错|崩溃|"
    r"\b(?:error|errors|exception|traceback|failed|failure|timeout|timed out)\b|"
    r"exit(?:\s+code)?\s*[:=]?\s*[1-9]\d*\b)",
    re.I,
)
DONE_RE = re.compile(
    r"(已完成|完成了|成功|已结束|跑完|"
    r"\b(?:success(?:ful)?|succeeded|finished|completed|complete|done)\b|"
    r"exit(?:\s+code)?\s*[:=]?\s*0\b)",
    re.I,
)
RUN_RE = re.compile(
    r"(进行中|执行中|正在跑|开始执行|处理中|"
    r"\b(?:running|processing|started|starting)\b)",
    re.I,
)
NEG_FAIL_RE = re.compile(r"(no error|0 errors|without error|没有报错|无异常|未报错|没有异常)", re.I)
NEG_DONE_RE = re.compile(
    r"(incomplete|not\s+complete|uncompleted|未完成|没完成|没有完成|尚未完成)",
    re.I,
)

STATUS_LABEL = {
    "pending": "未开始",
    "running": "进行中",
    "failed": "失败",
    "done": "已完成",
}


def _hits(pattern, line):
    return [(match.start(), match.group(0)) for match in pattern.finditer(line)]


def _done_hits(line):
    hits = []
    negations = list(NEG_DONE_RE.finditer(line))
    for pos, word in _hits(DONE_RE, line):
        if any(item.start() <= pos < item.end() for item in negations):
            continue
        prefix = line[max(0, pos - 6):pos]
        if re.search(r"(未|没|没有|尚未|not\s+|in|un)$", prefix, re.I):
            continue
        hits.append((pos, word))
    return hits


def classify_line(line):
    candidates = []
    if not NEG_FAIL_RE.search(line):
        candidates.extend((pos, "failed", word) for pos, word in _hits(FAIL_RE, line))
    candidates.extend((pos, "done", word) for pos, word in _done_hits(line))
    candidates.extend((pos, "running", word) for pos, word in _hits(RUN_RE, line))
    if not candidates:
        return None
    _pos, status, word = max(candidates, key=lambda item: item[0])
    return status, word


def decide_from_log(log_text):
    text = (log_text or "").strip()
    if not text:
        return "pending", "还没有日志，先记为未开始"

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "pending", "还没有日志，先记为未开始"

    for line in reversed(lines[-80:]):
        hit = classify_line(line)
        if not hit:
            continue
        status, word = hit
        label = STATUS_LABEL[status]
        preview = line if len(line) <= 80 else line[:80] + "…"
        return status, f"最新日志出现「{word}」，判断为{label}：{preview}"

    return "pending", "最近日志里没有完成、失败或进行中的明确结果，先记为未开始"
