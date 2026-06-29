"""长耗时求解任务的进度反馈。"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol, TextIO


class ProgressCallback(Protocol):
  def on_start(self, total: int, label: str) -> None: ...
  def on_step(self, current: int, total: int, label: str) -> None: ...
  def on_finish(self, label: str, elapsed_s: float) -> None: ...


@dataclass
class NullProgress:
    """默认空实现，不输出任何内容。"""

    def on_start(self, total: int, label: str) -> None:
        pass

    def on_step(self, current: int, total: int, label: str) -> None:
        pass

    def on_finish(self, label: str, elapsed_s: float) -> None:
        pass


@dataclass
class ConsoleProgress:
    """
    终端进度条：按步数或时间间隔刷新。
    例：  HP=47  [=========>          ] 12345/51000 (24.2%) 12.3/s ETA 52m
    """

    stream: TextIO = field(default_factory=lambda: sys.stderr)
    min_interval_s: float = 0.5
    width: int = 24

    _label: str = ""
    _total: int = 0
    _current: int = 0
    _indeterminate: bool = False
    _t0: float = 0.0
    _last_print: float = 0.0

    def on_start(self, total: int, label: str) -> None:
        self._label = label
        self._indeterminate = total <= 0
        self._total = max(total, 1)
        self._current = 0
        self._t0 = time.perf_counter()
        self._last_print = 0.0
        self._render(force=True)

    def on_step(self, current: int, total: int, label: str) -> None:
        self._current = current
        if total > 0:
            self._indeterminate = False
            self._total = total
        self._label = label
        self._render(force=False)

    def on_finish(self, label: str, elapsed_s: float) -> None:
        self._label = label
        self._render(force=True, done=True, elapsed_s=elapsed_s)
        self.stream.write("\n")
        self.stream.flush()

    def _render(self, *, force: bool, done: bool = False, elapsed_s: float | None = None) -> None:
        now = time.perf_counter()
        if not force and not done and (now - self._last_print) < self.min_interval_s:
            return
        self._last_print = now

        elapsed = elapsed_s if elapsed_s is not None else (now - self._t0)
        rate = self._current / elapsed if elapsed > 0 else 0.0

        if self._indeterminate and not done:
            # 总数未知（DFS 打到击杀）：只显示已处理路线数与速率。
            spin = "=" * (self._current % (self.width + 1))
            line = (
                f"\r{self._label}  [{spin:<{self.width}}] {self._current} 条 "
                f"{rate:6.1f}/s {_format_duration(elapsed)}"
            )
            self.stream.write(line)
            self.stream.flush()
            return

        pct = self._current / self._total
        filled = int(self.width * pct)
        bar = "=" * filled + (">" if filled < self.width and not done else "") + " " * (
            self.width - filled - (1 if filled < self.width and not done else 0)
        )
        if done or rate <= 0:
            eta_s = 0.0
        else:
            eta_s = (self._total - self._current) / rate

        eta_str = _format_duration(eta_s) if not done else "done"
        line = (
            f"\r{self._label}  [{bar}] {self._current}/{self._total} "
            f"({pct * 100:5.1f}%) {rate:5.1f}/s ETA {eta_str}"
        )
        self.stream.write(line)
        self.stream.flush()


def _format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def make_progress(enabled: bool, stream: TextIO | None = None) -> ProgressCallback:
    if not enabled:
        return NullProgress()
    return ConsoleProgress(stream=stream or sys.stderr)
