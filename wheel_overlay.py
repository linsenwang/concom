"""Radial (wheel) menu overlay drawn with AppKit.

The overlay is a borderless, transparent, click-through window that floats above
every other window *without* activating the app, so shortcuts fired from the
wheel (Cmd+W, ...) still reach the frontmost application.

AppKit is optional: when it is unavailable the overlay degrades to a no-op and
callers fall back to console output.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

try:
    import objc
    from AppKit import (
        NSApplication,
        NSApplicationActivationPolicyAccessory,
        NSAttributedString,
        NSBackingStoreBuffered,
        NSBezierPath,
        NSColor,
        NSEvent,
        NSDate,
        NSFont,
        NSFontAttributeName,
        NSForegroundColorAttributeName,
        NSMakeRect,
        NSPointInRect,
        NSRunLoop,
        NSScreen,
        NSScreenSaverWindowLevel,
        NSView,
        NSWindow,
        NSWindowCollectionBehaviorCanJoinAllSpaces,
        NSWindowCollectionBehaviorFullScreenAuxiliary,
        NSWindowCollectionBehaviorIgnoresCycle,
        NSWindowCollectionBehaviorStationary,
        NSWindowStyleMaskBorderless,
    )

    APPKIT_AVAILABLE = True
    IMPORT_ERROR: Optional[Exception] = None
except Exception as exc:  # pragma: no cover - platform dependent
    APPKIT_AVAILABLE = False
    IMPORT_ERROR = exc


# Size of the petal labels; bump this up if the wheel is hard to read.
LABEL_FONT_SIZE = 18.0


# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------

if APPKIT_AVAILABLE:

    def _color(r: float, g: float, b: float, a: float):
        return NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, a)

    COLOR_BACKDROP = _color(0.05, 0.05, 0.07, 0.72)
    COLOR_WEDGE = _color(0.16, 0.16, 0.20, 0.90)
    COLOR_WEDGE_SELECTED = _color(0.95, 0.60, 0.13, 0.95)
    COLOR_CENTER = _color(0.09, 0.09, 0.12, 1.0)
    COLOR_EDGE = _color(1.0, 1.0, 1.0, 0.18)
    COLOR_TEXT = _color(0.92, 0.92, 0.95, 1.0)
    COLOR_TEXT_SELECTED = _color(0.10, 0.08, 0.02, 1.0)


def wheel_spans(weights: Optional[Sequence[float]], count: int) -> list[float]:
    """Angle in degrees for every petal; weights are relative shares.

    Missing, malformed or all-zero weights fall back to an even split, so a
    wheel still works when only some petals carry a custom share.  A share of
    exactly 0 leaves a petal unreachable, which is how you retire a petal.
    """
    if count <= 0:
        return []

    raw: list[float] = []
    for index in range(count):
        try:
            value = float(weights[index])  # type: ignore[index]
        except (TypeError, ValueError, IndexError):
            value = 1.0
        raw.append(value if 0.0 <= value < float("inf") else 1.0)

    total = sum(raw)
    if total <= 0.0:
        raw = [1.0] * count
        total = float(count)
    if all(value == raw[0] for value in raw):
        # Even split: divide exactly like an unweighted wheel does, so a wheel
        # whose shares are all default keeps the old geometry to the last bit.
        return [360.0 / count] * count
    return [value / total * 360.0 for value in raw]


def _petal_starts(spans: Sequence[float]) -> list[float]:
    """Start angle of every petal, in degrees clockwise from the top.

    Petal 0 is centred on top and the rest follow in order, which keeps the
    layout identical to an evenly divided wheel when all shares are equal.
    """
    # fsum keeps every edge exactly rounded instead of drifting by an ulp as
    # the spans are added up one at a time.
    return [-spans[0] / 2.0 + math.fsum(spans[:index]) for index in range(len(spans))]


def wedge_angles(
    index: int, count: int, weights: Optional[Sequence[float]] = None
) -> tuple[float, float]:
    """Return the (start, end) of a wedge, in degrees clockwise from the top."""
    spans = wheel_spans(weights, count)
    if not spans:
        return 0.0, 0.0
    index %= count
    start = _petal_starts(spans)[index]
    return start, start + spans[index]


def direction_to_index(
    dx: float,
    dy: float,
    count: int,
    deadzone: float,
    weights: Optional[Sequence[float]] = None,
) -> int:
    """Map a stick vector (x right, y up) to a wedge index, -1 when centred."""
    if count <= 0:
        return -1
    if math.hypot(dx, dy) < deadzone:
        return -1
    angle = math.degrees(math.atan2(dx, dy)) % 360.0  # 0 = up, clockwise
    spans = wheel_spans(weights, count)
    for index, (start, span) in enumerate(zip(_petal_starts(spans), spans)):
        begin = start % 360.0
        finish = (start + span) % 360.0
        if begin <= finish:
            if begin <= angle < finish:
                return index
        elif angle >= begin or angle < finish:
            return index  # this petal straddles 0 degrees
    return count - 1


if APPKIT_AVAILABLE:

    class _WheelView(NSView):
        """Draws the wheel; holds no state beyond what it paints."""

        def initWithFrame_(self, frame):
            self = objc.super(_WheelView, self).initWithFrame_(frame)
            if self is None:
                return None
            self._labels: list[str] = []
            self._selected = -1
            self._radius = 170.0
            self._inner_radius = 62.0
            self._weights: tuple[float, ...] = ()
            return self

        # -- state ---------------------------------------------------------

        @objc.python_method
        def set_wheel_content(
            self, labels, selected, radius, inner_radius, weights=()
        ) -> None:
            self._labels = list(labels)
            self._selected = selected
            self._radius = radius
            self._inner_radius = inner_radius
            self._weights = tuple(weights)

        def isOpaque(self) -> bool:
            return False

        def acceptsFirstResponder(self) -> bool:
            return False

        # -- drawing helpers ----------------------------------------------

        @objc.python_method
        def _text(self, text: str, cx: float, cy: float, size: float, bold: bool, color):
            if not text:
                return
            font = (
                NSFont.boldSystemFontOfSize_(size)
                if bold
                else NSFont.systemFontOfSize_(size)
            )
            attrs = {NSFontAttributeName: font, NSForegroundColorAttributeName: color}
            s = NSAttributedString.alloc().initWithString_attributes_(text, attrs)
            sz = s.size()
            s.drawAtPoint_((cx - sz.width / 2.0, cy - sz.height / 2.0))

        @objc.python_method
        def _wedge(self, cx: float, cy: float, r: float, start: float, end: float):
            # Angles are given clockwise from the top; AppKit angles are
            # counter-clockwise from +x, hence the 90 - angle conversion.
            ns_start = 90.0 - start
            ns_end = 90.0 - end
            path = NSBezierPath.bezierPath()
            path.moveToPoint_((cx, cy))
            path.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
                (cx, cy), r, ns_start, ns_end, True
            )
            path.closePath()
            return path

        # -- painting ------------------------------------------------------

        def drawRect_(self, _rect) -> None:
            size = self.bounds().size
            cx, cy = size.width / 2.0, size.height / 2.0
            r = self._radius
            count = len(self._labels)

            backdrop = NSBezierPath.bezierPathWithOvalInRect_(
                NSMakeRect(cx - r - 16, cy - r - 16, 2 * (r + 16), 2 * (r + 16))
            )
            COLOR_BACKDROP.set()
            backdrop.fill()

            if count == 0:
                return

            for i, label in enumerate(self._labels):
                start, end = wedge_angles(i, count, self._weights)
                selected = i == self._selected
                path = self._wedge(cx, cy, r, start, end)
                (COLOR_WEDGE_SELECTED if selected else COLOR_WEDGE).set()
                path.fill()
                COLOR_EDGE.set()
                path.setLineWidth_(1.0)
                path.stroke()

                mid = math.radians((start + end) / 2.0)
                tx = cx + math.sin(mid) * r * 0.74
                ty = cy + math.cos(mid) * r * 0.74
                self._text(
                    label,
                    tx,
                    ty,
                    LABEL_FONT_SIZE,
                    selected,
                    COLOR_TEXT_SELECTED if selected else COLOR_TEXT,
                )

            # Centre hub; the highlighted wedge already says what is selected.
            center = NSBezierPath.bezierPathWithOvalInRect_(
                NSMakeRect(
                    cx - self._inner_radius,
                    cy - self._inner_radius,
                    2 * self._inner_radius,
                    2 * self._inner_radius,
                )
            )
            COLOR_CENTER.set()
            center.fill()
            COLOR_EDGE.set()
            center.setLineWidth_(1.0)
            center.stroke()


class RadialWheelOverlay:
    """A reusable wheel overlay window; create once, then show/hide."""

    def __init__(
        self,
        radius: float = 170.0,
        inner_radius: float = 62.0,
        weights: Optional[Sequence[float]] = None,
    ) -> None:
        self._radius = radius
        self._inner_radius = inner_radius
        self._weights: tuple[float, ...] = tuple(weights) if weights is not None else ()
        self._window = None
        self._view = None
        self._visible = False
        self._last_key: Optional[tuple] = None

    @property
    def available(self) -> bool:
        return APPKIT_AVAILABLE

    # -- window plumbing ---------------------------------------------------

    def _screen_frame(self):
        """Frame of the screen holding the mouse pointer (falls back to main)."""
        point = NSEvent.mouseLocation()
        for screen in NSScreen.screens():
            frame = screen.frame()
            if NSPointInRect(point, frame):
                return frame
        return NSScreen.mainScreen().frame()

    def _ensure_window(self):
        if self._window is not None:
            return self._window

        # Accessory apps never become frontmost, so the app under the pointer
        # keeps focus and receives the shortcuts the wheel fires.
        app = NSApplication.sharedApplication()
        try:
            app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        except Exception:
            pass

        side = 2.0 * (self._radius + 20.0)
        frame = self._screen_frame()
        rect = NSMakeRect(
            frame.origin.x + (frame.size.width - side) / 2.0,
            frame.origin.y + (frame.size.height - side) / 2.0,
            side,
            side,
        )
        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, NSWindowStyleMaskBorderless, NSBackingStoreBuffered, False
        )
        window.setOpaque_(False)
        window.setBackgroundColor_(NSColor.clearColor())
        window.setHasShadow_(False)
        window.setIgnoresMouseEvents_(True)
        window.setLevel_(NSScreenSaverWindowLevel)
        window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | NSWindowCollectionBehaviorIgnoresCycle
        )
        window.setReleasedWhenClosed_(False)

        view = _WheelView.alloc().initWithFrame_(NSMakeRect(0, 0, side, side))
        window.setContentView_(view)

        self._window = window
        self._view = view
        return window

    def _pump_run_loop(self, seconds: float = 0.0) -> None:
        """Service whatever AppKit has pending, without waiting for more.

        This runs on the controller's polling thread, so blocking here *is*
        input latency: a 10 ms pump measured ~11 ms and froze pointer control
        for that long on every repaint, 20 ms when the wheel opened.  A
        zero-length pump drains the pending work and returns immediately; the
        repaint itself is forced synchronously by ``displayIfNeeded``, so
        nothing is left deferred.
        """
        try:
            NSRunLoop.currentRunLoop().runUntilDate_(
                NSDate.dateWithTimeIntervalSinceNow_(seconds)
            )
        except Exception:
            pass

    # -- public API --------------------------------------------------------

    def show(self, labels: Sequence[str], selected: int) -> None:
        if not APPKIT_AVAILABLE:
            return

        window = self._ensure_window()
        if not self._visible:
            window.orderFrontRegardless()
            self._visible = True
            self._pump_run_loop()

        key = (tuple(labels), selected, self._weights)
        if key == self._last_key:
            return
        self._last_key = key

        self._view.set_wheel_content(
            labels, selected, self._radius, self._inner_radius, self._weights
        )
        self._view.setNeedsDisplay_(True)
        window.displayIfNeeded()
        self._pump_run_loop()

    def hide(self) -> None:
        if not APPKIT_AVAILABLE or self._window is None:
            return
        if self._visible:
            self._window.orderOut_(None)
            self._visible = False
            self._pump_run_loop()
        self._last_key = None
