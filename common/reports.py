"""Recent operation reports of this session — kept after the tooltip is gone.

Settings → Diagnostyka lists them and can repeat the failed notes. In memory
only and cleared when the profile closes: note ids belong to one collection.
"""
import time
from collections import deque

_REPORTS: deque = deque(maxlen=20)
_seq = 0


def record_report(title: str, text: str, retry=None, failed: int = 0) -> None:
    """`retry()` repeats only the failed notes; None when nothing can be repeated."""
    global _seq
    _seq += 1
    _REPORTS.appendleft({"id": _seq, "time": time.strftime("%H:%M:%S"), "title": title,
                         "text": text, "retry": retry if failed else None, "failed": failed})


def recent_reports() -> list:
    return list(_REPORTS)


def take_retry(report_id: int):
    """The report's retry, handed out once — the rerun records its own report."""
    for report in _REPORTS:
        if report["id"] == report_id:
            retry, report["retry"] = report["retry"], None
            return retry
    return None


def reports_seq() -> int:
    return _seq


def clear_reports() -> None:
    global _seq
    _REPORTS.clear()
    _seq += 1


def live_parent(widget):
    """`widget` while it exists, else the main window — a retry may outlive its Browser."""
    from aqt import mw
    from aqt.qt import sip
    return widget if widget is not None and not sip.isdeleted(widget) else mw
