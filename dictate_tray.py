#!/usr/local/bin/python3
"""
Clever Dictate — Desktop App (macOS)
Opens a window showing transcription history. Click any entry to copy it.
Watches ~/.local/share/dictate/history.json for new entries.
"""
import json, os, subprocess, signal

# ── Kill any other tray instances before starting ────────────────────────────
_my_pid = os.getpid()
try:
    result = subprocess.run(['pgrep', '-f', 'dictate_tray.py'], capture_output=True, text=True)
    for pid_str in result.stdout.strip().split('\n'):
        if pid_str and int(pid_str) != _my_pid:
            os.kill(int(pid_str), signal.SIGKILL)
except Exception:
    pass
from datetime import datetime, timezone

import objc
from Foundation import NSObject, NSTimer, NSMakeRect, NSMakeSize
from AppKit import (
    NSApplication, NSWindow, NSWindowStyleMaskTitled,
    NSWindowStyleMaskClosable, NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable, NSBackingStoreBuffered,
    NSApplicationActivationPolicyAccessory,
    NSApplicationActivationPolicyRegular,
    NSFont, NSColor, NSTextField, NSTextAlignmentLeft,
    NSTextAlignmentCenter, NSScrollView, NSView,
    NSPasteboard, NSStringPboardType, NSCursor,
    NSNotificationCenter, NSWindowDidResizeNotification,
    NSBox, NSButton, NSBezelStyleRounded,
    NSStatusBar, NSImage, NSVariableStatusItemLength,
    NSBezierPath, NSGraphicsContext, NSCompositingOperationSourceOver,
    NSSlider, NSTextAlignmentRight, NSAppearance,
)
import math

# ── Menubar Icon ─────────────────────────────────────────────────────────

def make_speaking_icon():
    """Draw a person-head silhouette with speech waves for the menubar."""
    size = 18  # standard menubar icon height
    img = NSImage.alloc().initWithSize_((size + 6, size))  # extra width for waves
    img.lockFocus()

    NSColor.blackColor().setFill()
    NSColor.blackColor().setStroke()

    # Head — circle
    head_r = 4.0
    head_cx, head_cy = 7.0, 12.0
    head = NSBezierPath.bezierPathWithOvalInRect_(
        NSMakeRect(head_cx - head_r, head_cy - head_r, head_r * 2, head_r * 2)
    )
    head.fill()

    # Shoulders — arc below head
    shoulders = NSBezierPath.bezierPath()
    shoulders.moveToPoint_((0.5, 2.0))
    shoulders.curveToPoint_controlPoint1_controlPoint2_(
        (13.5, 2.0), (2.0, 7.0), (12.0, 7.0)
    )
    shoulders.lineToPoint_((13.5, 0.0))
    shoulders.lineToPoint_((0.5, 0.0))
    shoulders.closePath()
    shoulders.fill()

    # Speech waves — 2 arcs emanating from mouth area
    for i, offset in enumerate([3.0, 6.0]):
        wave = NSBezierPath.bezierPath()
        wave.setLineWidth_(1.4)
        cx = 12.0 + offset
        cy = 12.0
        r = 2.0 + i * 1.5
        # Arc from roughly -40 to +40 degrees
        wave.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
            (cx - r + 1, cy), r, -35.0, 35.0, False
        )
        wave.stroke()

    img.unlockFocus()
    img.setTemplate_(True)  # adapts to light/dark mode
    return img

def make_app_icon():
    """Draw a 128x128 speaking-person icon for the app/window icon."""
    s = 128
    img = NSImage.alloc().initWithSize_((s, s))
    img.lockFocus()

    # Background — rounded rect, Clever Profits navy #040B4D
    bg = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(0, 0, s, s), 24, 24
    )
    NSColor.colorWithCalibratedRed_green_blue_alpha_(4/255, 11/255, 77/255, 1.0).setFill()
    bg.fill()

    NSColor.whiteColor().setFill()
    NSColor.whiteColor().setStroke()

    # Head — circle
    head_r = 18.0
    head_cx, head_cy = 40.0, 78.0
    head = NSBezierPath.bezierPathWithOvalInRect_(
        NSMakeRect(head_cx - head_r, head_cy - head_r, head_r * 2, head_r * 2)
    )
    head.fill()

    # Shoulders — arc below head
    shoulders = NSBezierPath.bezierPath()
    shoulders.moveToPoint_((6, 38))
    shoulders.curveToPoint_controlPoint1_controlPoint2_(
        (74, 38), (14, 55), (66, 55)
    )
    shoulders.lineToPoint_((74, 16))
    shoulders.lineToPoint_((6, 16))
    shoulders.closePath()
    shoulders.fill()

    # Speech waves — 3 arcs from mouth area
    for i in range(3):
        wave = NSBezierPath.bezierPath()
        wave.setLineWidth_(4.0 - i * 0.5)
        r = 12.0 + i * 10.0
        cx = 58.0 + i * 8.0
        cy = 78.0
        wave.appendBezierPathWithArcWithCenter_radius_startAngle_endAngle_clockwise_(
            (cx, cy), r, -35.0, 35.0, False
        )
        wave.stroke()

    img.unlockFocus()
    return img

# ── Config ────────────────────────────────────────────────────────────────

HISTORY_DIR    = os.path.expanduser("~/.local/share/dictate")
HISTORY_FILE   = os.path.join(HISTORY_DIR, "history.json")
SETTINGS_FILE  = os.path.join(HISTORY_DIR, "settings.json")
ROW_HEIGHT_MIN = 56
TEXT_FONT_SIZE = 13
TS_HEIGHT      = 20   # timestamp + padding above text
WINDOW_W     = 560
WINDOW_H     = 640
COPY_BTN_W   = 70
COPY_BTN_H   = 24
PADDING      = 16

# ── History I/O ───────────────────────────────────────────────────────────

def load_history():
    """Load transcriptions, filtering out entries before cleared_before timestamp."""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r") as f:
            data = json.load(f)
        entries = data.get("transcriptions", [])
        cleared = data.get("cleared_before")
        if cleared:
            entries = [e for e in entries if e.get("timestamp", "") > cleared]
        return entries
    except (json.JSONDecodeError, OSError):
        return []

def format_timestamp(ts_str):
    try:
        dt = datetime.fromisoformat(ts_str)
        # Convert UTC to local time
        dt_local = dt.astimezone()
        return dt_local.strftime("%I:%M %p").lstrip("0")
    except (ValueError, TypeError):
        return ""

def load_settings():
    try:
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"cleanup_level": 25}

def save_settings(settings):
    os.makedirs(HISTORY_DIR, exist_ok=True)
    tmp = SETTINGS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(settings, f, indent=2)
    os.replace(tmp, SETTINGS_FILE)

def level_label(val):
    if val == 0:
        return "Raw (no cleanup)"
    elif val <= 25:
        return "Light (punctuation + remove ums)"
    elif val <= 50:
        return "Medium (+ remove filler phrases)"
    elif val <= 75:
        return "Heavy (+ fix grammar & false starts)"
    else:
        return "Full (restructure for clarity)"

def copy_to_clipboard(text):
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, NSStringPboardType)

def _calc_row_height(text, width):
    """Calculate row height needed for wrapped text."""
    text_w = width - COPY_BTN_W - PADDING * 3
    font = NSFont.systemFontOfSize_(TEXT_FONT_SIZE)
    # Use a temp text field to measure
    tf = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, text_w, 10000))
    tf.setStringValue_(text)
    tf.setFont_(font)
    tf.setLineBreakMode_(0)  # word wrap
    tf.setMaximumNumberOfLines_(0)
    cell = tf.cell()
    needed = cell.cellSizeForBounds_(NSMakeRect(0, 0, text_w, 10000))
    text_h = needed.height + 4  # small padding
    return max(ROW_HEIGHT_MIN, text_h + TS_HEIGHT + 8)

# ── Row View ─────────────────────────────────────────────────────────────

class HistoryRow(NSView):
    def initWithFrame_text_timestamp_(self, frame, text, timestamp):
        self = objc.super(HistoryRow, self).initWithFrame_(frame)
        if self is None:
            return None
        self._full_text = text
        w = frame.size.width
        h = frame.size.height

        # Timestamp — top left
        ts_label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(PADDING, h - 20, 100, 14)
        )
        ts_label.setStringValue_(timestamp)
        ts_label.setFont_(NSFont.monospacedDigitSystemFontOfSize_weight_(10, 0))
        ts_label.setTextColor_(NSColor.secondaryLabelColor())
        ts_label.setBezeled_(False)
        ts_label.setDrawsBackground_(False)
        ts_label.setEditable_(False)
        ts_label.setSelectable_(False)
        self.addSubview_(ts_label)

        # Copy button — native NSButton, right side, vertically centered
        btn_x = w - COPY_BTN_W - PADDING
        btn_y = (h - COPY_BTN_H) / 2
        self._copyBtn = NSButton.alloc().initWithFrame_(
            NSMakeRect(btn_x, btn_y, COPY_BTN_W, COPY_BTN_H)
        )
        self._copyBtn.setTitle_("Copy")
        self._copyBtn.setBezelStyle_(NSBezelStyleRounded)
        self._copyBtn.setFont_(NSFont.systemFontOfSize_(11))
        self._copyBtn.setTarget_(self)
        self._copyBtn.setAction_(objc.selector(self.copyClicked_, signature=b'v@:@'))
        self._copyBtn.setAutoresizingMask_(0b100000)  # pin right
        self.addSubview_(self._copyBtn)

        # Text — left side, single line, no overlap with button
        text_w = w - COPY_BTN_W - PADDING * 3
        text_label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(PADDING, 4, text_w, h - 24)
        )
        text_label.setStringValue_(text)
        text_label.setFont_(NSFont.systemFontOfSize_(13))
        text_label.setTextColor_(NSColor.labelColor())
        text_label.setBezeled_(False)
        text_label.setDrawsBackground_(False)
        text_label.setEditable_(False)
        text_label.setSelectable_(True)
        text_label.setLineBreakMode_(0)  # word wrap
        text_label.setMaximumNumberOfLines_(0)
        text_label.setAutoresizingMask_(0b000010)  # flex width
        self.addSubview_(text_label)

        # Separator
        sep = NSBox.alloc().initWithFrame_(NSMakeRect(PADDING, 0, w - PADDING * 2, 1))
        sep.setBoxType_(1)  # NSSeparator
        sep.setAutoresizingMask_(0b000010)
        self.addSubview_(sep)

        return self

    def copyClicked_(self, sender):
        copy_to_clipboard(self._full_text)
        self._copyBtn.setTitle_("Copied!")
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.6, self, objc.selector(self._resetCopy_, signature=b'v@:@'), None, False
        )

    def _resetCopy_(self, timer):
        self._copyBtn.setTitle_("Copy")

# ── App Delegate ──────────────────────────────────────────────────────────

class AppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, notification):
        # ── App icon (window title bar) ──────────────────────────────────
        NSApplication.sharedApplication().setApplicationIconImage_(make_app_icon())

        # ── Menubar icon ─────────────────────────────────────────────────
        self.statusItem = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength
        )
        icon = make_speaking_icon()
        self.statusItem.button().setImage_(icon)
        self.statusItem.button().setTarget_(self)
        self.statusItem.button().setAction_(
            objc.selector(self.statusBarClicked_, signature=b'v@:@')
        )

        # ── History window ───────────────────────────────────────────────
        frame = NSMakeRect(200, 200, WINDOW_W, WINDOW_H)
        style = (NSWindowStyleMaskTitled |
                 NSWindowStyleMaskClosable |
                 NSWindowStyleMaskMiniaturizable |
                 NSWindowStyleMaskResizable)
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, NSBackingStoreBuffered, False
        )
        self.window.setTitle_("Clever Dictate")
        self.window.setMinSize_((400, 400))
        self.window.setAppearance_(NSAppearance.appearanceNamed_("NSAppearanceNameAqua"))

        content = self.window.contentView()
        w = frame.size.width
        h = frame.size.height

        # White background for the whole window
        bgBox = NSBox.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
        bgBox.setBoxType_(4)  # NSBoxCustom
        bgBox.setFillColor_(NSColor.whiteColor())
        bgBox.setBorderWidth_(0)
        bgBox.setAutoresizingMask_(0b010010)
        content.addSubview_(bgBox)

        # ── Blue header bar — Clever Profits navy #040B4D ────────────
        HEADER_H = 56
        headerBar = NSBox.alloc().initWithFrame_(
            NSMakeRect(0, h - HEADER_H, w, HEADER_H)
        )
        headerBar.setBoxType_(4)  # NSBoxCustom
        headerBar.setFillColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(
                4/255, 11/255, 77/255, 1.0
            )
        )
        headerBar.setBorderWidth_(0)
        headerBar.setAutoresizingMask_(0b010010)  # flex width + pin top
        content.addSubview_(headerBar)

        # Title — white text on navy header
        title = NSTextField.alloc().initWithFrame_(NSMakeRect(20, 12, w - 140, 32))
        title.setStringValue_("Dictation History")
        title.setFont_(NSFont.boldSystemFontOfSize_(22))
        title.setAlignment_(NSTextAlignmentLeft)
        title.setTextColor_(NSColor.whiteColor())
        title.setBezeled_(False)
        title.setDrawsBackground_(False)
        title.setEditable_(False)
        title.setSelectable_(False)
        title.setAutoresizingMask_(0b000010)
        headerBar.addSubview_(title)

        # Restart button on navy header
        self._restartBtn = NSButton.alloc().initWithFrame_(
            NSMakeRect(w - 190, 16, 70, 24)
        )
        self._restartBtn.setTitle_("Restart")
        self._restartBtn.setBezelStyle_(NSBezelStyleRounded)
        self._restartBtn.setFont_(NSFont.systemFontOfSize_(11))
        self._restartBtn.setTarget_(self)
        self._restartBtn.setAction_(objc.selector(self.restartApp_, signature=b'v@:@'))
        self._restartBtn.setAutoresizingMask_(0b100000)  # pin right
        headerBar.addSubview_(self._restartBtn)

        # Clear All button on navy header
        self._clearBtn = NSButton.alloc().initWithFrame_(
            NSMakeRect(w - 100, 16, 80, 24)
        )
        self._clearBtn.setTitle_("Clear All")
        self._clearBtn.setBezelStyle_(NSBezelStyleRounded)
        self._clearBtn.setFont_(NSFont.systemFontOfSize_(11))
        self._clearBtn.setTarget_(self)
        self._clearBtn.setAction_(objc.selector(self.clearAll_, signature=b'v@:@'))
        self._clearBtn.setAutoresizingMask_(0b100000)  # pin right
        headerBar.addSubview_(self._clearBtn)

        # ── Settings panel — cleanup slider + VS Code focus toggle ──
        SETTINGS_H = 90
        settingsPanel = NSBox.alloc().initWithFrame_(
            NSMakeRect(0, h - HEADER_H - SETTINGS_H, w, SETTINGS_H)
        )
        settingsPanel.setBoxType_(4)  # NSBoxCustom
        settingsPanel.setFillColor_(
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.96, 0.96, 0.97, 1.0)
        )
        settingsPanel.setBorderWidth_(0)
        settingsPanel.setAutoresizingMask_(0b010010)  # flex width + pin top
        content.addSubview_(settingsPanel)

        settings = load_settings()
        current_level = settings.get("cleanup_level", 25)

        # ── Cleanup slider row (top) ──────────────────────────────
        cleanupLabel = NSTextField.alloc().initWithFrame_(NSMakeRect(PADDING, 60, 70, 20))
        cleanupLabel.setStringValue_("Cleanup:")
        cleanupLabel.setFont_(NSFont.boldSystemFontOfSize_(11))
        cleanupLabel.setTextColor_(NSColor.labelColor())
        cleanupLabel.setBezeled_(False)
        cleanupLabel.setDrawsBackground_(False)
        cleanupLabel.setEditable_(False)
        cleanupLabel.setSelectable_(False)
        settingsPanel.addSubview_(cleanupLabel)

        self._slider = NSSlider.alloc().initWithFrame_(
            NSMakeRect(80, 62, w - 200, 20)
        )
        self._slider.setMinValue_(0)
        self._slider.setMaxValue_(100)
        self._slider.setIntValue_(current_level)
        self._slider.setTarget_(self)
        self._slider.setAction_(objc.selector(self.sliderChanged_, signature=b'v@:@'))
        self._slider.setAutoresizingMask_(0b000010)  # flex width
        settingsPanel.addSubview_(self._slider)

        self._levelLabel = NSTextField.alloc().initWithFrame_(
            NSMakeRect(PADDING, 42, w - PADDING * 2, 14)
        )
        self._levelLabel.setStringValue_(level_label(current_level))
        self._levelLabel.setFont_(NSFont.systemFontOfSize_(10))
        self._levelLabel.setTextColor_(NSColor.secondaryLabelColor())
        self._levelLabel.setBezeled_(False)
        self._levelLabel.setDrawsBackground_(False)
        self._levelLabel.setEditable_(False)
        self._levelLabel.setSelectable_(False)
        self._levelLabel.setAlignment_(NSTextAlignmentCenter)
        self._levelLabel.setAutoresizingMask_(0b000010)
        settingsPanel.addSubview_(self._levelLabel)

        # ── VS Code focus toggle (bottom) ────────────────────────
        focus_enabled = settings.get("focus_vscode", False)
        self._focusBtn = NSButton.alloc().initWithFrame_(NSMakeRect(PADDING, 10, 200, 24))
        self._focusBtn.setButtonType_(3)  # NSSwitchButton (checkbox)
        self._focusBtn.setTitle_("Bring VS Code to front on dictate")
        self._focusBtn.setFont_(NSFont.systemFontOfSize_(11))
        self._focusBtn.setState_(1 if focus_enabled else 0)
        self._focusBtn.setTarget_(self)
        self._focusBtn.setAction_(objc.selector(self.focusToggled_, signature=b'v@:@'))
        settingsPanel.addSubview_(self._focusBtn)

        # Scroll view — white background (adjusted for settings panel)
        self.scrollView = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 40, w, h - HEADER_H - SETTINGS_H - 40))
        self.scrollView.setHasVerticalScroller_(True)
        self.scrollView.setBorderType_(0)
        self.scrollView.setAutoresizingMask_(0b010010)

        self.containerView = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, w, 0))
        self.scrollView.setDocumentView_(self.containerView)
        content.addSubview_(self.scrollView)

        # Status bar
        self.statusLabel = NSTextField.alloc().initWithFrame_(NSMakeRect(20, 10, w - 40, 20))
        self.statusLabel.setFont_(NSFont.systemFontOfSize_(11))
        self.statusLabel.setTextColor_(NSColor.tertiaryLabelColor())
        self.statusLabel.setBezeled_(False)
        self.statusLabel.setDrawsBackground_(False)
        self.statusLabel.setEditable_(False)
        self.statusLabel.setSelectable_(False)
        self.statusLabel.setAutoresizingMask_(0b000010)
        content.addSubview_(self.statusLabel)

        self._last_mtime = 0
        self._entries = []
        self._windowShown = True
        self._refresh()

        self.window.center()
        self.window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        # Delayed re-activate — ensures window reaches foreground after app finishes launching
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.3, self, objc.selector(self._bringToFront_, signature=b'v@:@'), None, False
        )

        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0, self, objc.selector(self.pollHistory_, signature=b'v@:@'), None, True
        )
        NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            self, objc.selector(self.windowResized_, signature=b'v@:@'),
            NSWindowDidResizeNotification, self.window
        )
        self.window.setDelegate_(self)

        # Engine is started by the app launcher script, not by the tray.

    def windowShouldClose_(self, sender):
        """Called when the X button is clicked. Hide instead of close."""
        self.window.orderOut_(None)
        self._windowShown = False
        return False  # prevent actual close — just hide

    def focusToggled_(self, sender):
        enabled = sender.state() == 1
        settings = load_settings()
        settings["focus_vscode"] = enabled
        save_settings(settings)

    def sliderChanged_(self, sender):
        val = int(self._slider.intValue())
        self._levelLabel.setStringValue_(level_label(val))
        settings = load_settings()
        settings["cleanup_level"] = val
        save_settings(settings)

    # No mode toggle — Qwen auto-triggers based on recording duration

    def restartApp_(self, sender):
        """Kill dictate engine + relaunch both tray app and engine from scratch."""
        # Kill the dictate engine
        subprocess.run(["pkill", "-f", "dictate.py"], capture_output=True)
        # Relaunch both — engine first, then tray app replaces this process
        subprocess.Popen([
            "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3",
            os.path.expanduser("~/.local/bin/dictate.py"),
        ], stdout=open("/tmp/dictate.log", "w"), stderr=subprocess.STDOUT)
        subprocess.Popen([
            "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3",
            os.path.expanduser("~/.local/bin/dictate_tray.py"),
        ], stderr=open("/tmp/dictate_tray.log", "w"))
        NSApplication.sharedApplication().terminate_(None)

    def clearAll_(self, sender):
        """Cosmetic clear — sets cleared_before timestamp, data stays in file."""
        os.makedirs(HISTORY_DIR, exist_ok=True)
        try:
            with open(HISTORY_FILE, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError, FileNotFoundError):
            data = {"transcriptions": []}
        data["cleared_before"] = datetime.now(timezone.utc).isoformat()
        tmp_path = HISTORY_FILE + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, HISTORY_FILE)
        self._refresh()

    def windowResized_(self, notification):
        self._buildRows()

    def pollHistory_(self, timer):
        try:
            if os.path.exists(HISTORY_FILE):
                mtime = os.path.getmtime(HISTORY_FILE)
                if mtime != self._last_mtime:
                    self._last_mtime = mtime
                    self._refresh()
        except OSError:
            pass

    def _refresh(self):
        self._entries = load_history()
        self._buildRows()

    def _buildRows(self):
        for subview in list(self.containerView.subviews()):
            subview.removeFromSuperview()

        entries = self._entries
        if not entries:
            self.statusLabel.setStringValue_("No dictations yet. Hold Right Control to speak.")
            self.containerView.setFrameSize_(NSMakeSize(WINDOW_W, 50))
            return

        entries_reversed = list(reversed(entries))
        container_w = self.scrollView.contentSize().width

        # Calculate dynamic row heights
        row_heights = []
        for entry in entries_reversed:
            text = entry.get("text", "")
            row_heights.append(_calc_row_height(text, container_w))

        total_height = sum(row_heights)
        self.containerView.setFrameSize_(NSMakeSize(container_w, total_height))

        y_cursor = total_height
        for i, entry in enumerate(entries_reversed):
            ts = format_timestamp(entry.get("timestamp", ""))
            text = entry.get("text", "")
            rh = row_heights[i]
            y_cursor -= rh
            row = HistoryRow.alloc().initWithFrame_text_timestamp_(
                NSMakeRect(0, y_cursor, container_w, rh), text, ts
            )
            row.setAutoresizingMask_(0b000010)
            self.containerView.addSubview_(row)

        self.statusLabel.setStringValue_(
            f"{len(entries)} dictation{'s' if len(entries) != 1 else ''}"
        )

        # Scroll to top (newest entries)
        self.containerView.scrollPoint_((0, total_height))

    def statusBarClicked_(self, sender):
        """Toggle the history window when menubar icon is clicked."""
        if self._windowShown:
            self.window.orderOut_(None)
            self._windowShown = False
        else:
            self._refresh()
            self.window.setLevel_(3)
            self.window.makeKeyAndOrderFront_(None)
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            self._windowShown = True
            NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.5, self, objc.selector(self._normalizeLevel_, signature=b'v@:@'), None, False
            )

    def _bringToFront_(self, timer):
        self.window.setLevel_(3)  # NSFloatingWindowLevel — temporarily above all
        self.window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        # Drop back to normal level after 0.5s so it behaves like a regular window
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.5, self, objc.selector(self._normalizeLevel_, signature=b'v@:@'), None, False
        )

    def _normalizeLevel_(self, timer):
        self.window.setLevel_(0)  # NSNormalWindowLevel

    def applicationShouldHandleReopen_hasVisibleWindows_(self, sender, flag):
        """Called when Dock icon is clicked. Show the window."""
        self._refresh()
        self.window.setLevel_(3)
        self.window.makeKeyAndOrderFront_(None)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self._windowShown = True
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.5, self, objc.selector(self._normalizeLevel_, signature=b'v@:@'), None, False
        )
        return True

    def applicationShouldTerminateAfterLastWindowClosed_(self, sender):
        return False  # keep running in menubar when window is closed

# ── Main ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.activateIgnoringOtherApps_(True)
    app.run()
