"""Platform-agnostic screen rect shared by the Windows and macOS window
backends - pure arithmetic, no OS calls, so both backends return the same
type and every caller (executor, vision/capture.py, ui/*) stays unaware of
which platform actually produced it."""

from dataclasses import dataclass


@dataclass
class ClientRect:
    x: int
    y: int
    w: int
    h: int

    def to_screen(self, nx: float, ny: float) -> tuple[int, int]:
        """Normalized 0-1 coords -> absolute screen pixels."""
        return int(self.x + nx * self.w), int(self.y + ny * self.h)

    def to_norm(self, sx: int, sy: int) -> tuple[float, float]:
        return (sx - self.x) / self.w, (sy - self.y) / self.h

    def as_tuple(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.w, self.h
