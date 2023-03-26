import os

from talon import (
    Context,
    Module,
    actions,
    app,
    clip,
    cron,
    ctrl,
    imgui,
    ui,
    noise,
    registry,
    tap,
)
from talon_plugins import eye_zoom_mouse

key = actions.key
self = actions.self
scroll_amount = 0
click_job = None
scroll_job = None
gaze_job = None
cancel_scroll_on_pop = True
control_mouse_forced = False

# Setting for how much percent of the screen you should gaze further from the reference point before scrolling starts.
scroll_offset = 0.12
# Setting for how fast scrolling should be depending on the distance from the reference point.
def scroll_formula(diff):
    return 10 + pow(10 * abs(diff), 3.5)


# Setting for the number of eye locations we should take the average from, increasing this will increase accuracy and increase latency.
eye_avg = 20

default_cursor = {
    "AppStarting": r"%SystemRoot%\Cursors\aero_working.ani",
    "Arrow": r"%SystemRoot%\Cursors\aero_arrow.cur",
    "Hand": r"%SystemRoot%\Cursors\aero_link.cur",
    "Help": r"%SystemRoot%\Cursors\aero_helpsel.cur",
    "No": r"%SystemRoot%\Cursors\aero_unavail.cur",
    "NWPen": r"%SystemRoot%\Cursors\aero_pen.cur",
    "Person": r"%SystemRoot%\Cursors\aero_person.cur",
    "Pin": r"%SystemRoot%\Cursors\aero_pin.cur",
    "SizeAll": r"%SystemRoot%\Cursors\aero_move.cur",
    "SizeNESW": r"%SystemRoot%\Cursors\aero_nesw.cur",
    "SizeNS": r"%SystemRoot%\Cursors\aero_ns.cur",
    "SizeNWSE": r"%SystemRoot%\Cursors\aero_nwse.cur",
    "SizeWE": r"%SystemRoot%\Cursors\aero_ew.cur",
    "UpArrow": r"%SystemRoot%\Cursors\aero_up.cur",
    "Wait": r"%SystemRoot%\Cursors\aero_busy.ani",
    "Crosshair": "",
    "IBeam": "",
}

# todo figure out why notepad++ still shows the cursor sometimes.
hidden_cursor = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), r"Resources\HiddenCursor.cur"
)

mod = Module()
ctx = Context()

mod.list(
    "mouse_button", desc="List of mouse button words to mouse_click index parameter"
)
mod.tag(
    "mouse_cursor_commands_enable", desc="Tag enables hide/show mouse cursor commands"
)
setting_mouse_enable_pop_click = mod.setting(
    "mouse_enable_pop_click",
    type=int,
    default=0,
    desc="Pop noise clicks left mouse button. 0 = off, 1 = on with eyetracker but not with zoom mouse mode, 2 = on but not with zoom mouse mode",
)
setting_mouse_enable_pop_stops_scroll = mod.setting(
    "mouse_enable_pop_stops_scroll",
    type=int,
    default=0,
    desc="When enabled, pop stops continuous scroll modes (wheel upper/downer/gaze)",
)
setting_mouse_wake_hides_cursor = mod.setting(
    "mouse_wake_hides_cursor",
    type=int,
    default=0,
    desc="When enabled, mouse wake will hide the cursor. mouse_wake enables zoom mouse.",
)
setting_mouse_hide_mouse_gui = mod.setting(
    "mouse_hide_mouse_gui",
    type=int,
    default=0,
    desc="When enabled, the 'Scroll Mouse' GUI will not be shown.",
)
setting_mouse_continuous_scroll_amount = mod.setting(
    "mouse_continuous_scroll_amount",
    type=int,
    default=80,
    desc="The default amount used when scrolling continuously",
)
setting_mouse_wheel_down_amount = mod.setting(
    "mouse_wheel_down_amount",
    type=int,
    default=120,
    desc="The amount to scroll up/down (equivalent to mouse wheel on Windows by default)",
)
setting_mouse_wheel_horizontal_amount = mod.setting(
    "mouse_wheel_horizontal_amount",
    type=int,
    default=40,
    desc="The amount to scroll left/right",
)

continuous_scoll_mode = ""


@imgui.open(x=700, y=0)
def gui_wheel(gui: imgui.GUI):
    gui.text(f"Scroll mode: {continuous_scoll_mode}")
    gui.line()
    if gui.button("Wheel Stop [stop scrolling]"):
        actions.user.mouse_scroll_stop()


@mod.action_class
class Actions:
    def mouse_show_cursor():
        """Shows the cursor"""
        show_cursor_helper(True)

    def mouse_hide_cursor():
        """Hides the cursor"""
        show_cursor_helper(False)

    def mouse_wake():
        """Enable control mouse, zoom mouse, and disables cursor"""
        try:
            actions.tracking.control_zoom_toggle(True)
        except Exception as e:
            print(e)
            actions.app.notify(e)
            actions.sleep("500ms")
            # actions.user.talon_restart()

        if setting_mouse_wake_hides_cursor.get() >= 1:
            show_cursor_helper(False)

    def mouse_drag(button: int):
        """Press and hold/release a specific mouse button for dragging"""
        # Clear any existing drags
        if actions.user.mouse_is_dragging():
            self.mouse_drag_end()
        else:
            # Start drag
            ctrl.mouse_click(button=button, down=True)

    def mouse_drag_end():
        """Releases any held mouse buttons"""
        buttons_held_down = list(ctrl.mouse_buttons_down())
        for button in buttons_held_down:
            ctrl.mouse_click(button=button, up=True)

    def mouse_is_dragging():
        """Returns whether or not a drag is in progress"""
        buttons_held_down = list(ctrl.mouse_buttons_down())
        return len(buttons_held_down) > 0

    def mouse_sleep():
        """Disables control mouse, zoom mouse, and re-enables cursor"""
        actions.tracking.control_zoom_toggle(False)
        actions.tracking.control_toggle(False)
        actions.tracking.control1_toggle(False)

        show_cursor_helper(True)
        stop_scroll()

        # todo: fixme temporary fix for drag command
        button_down = len(list(ctrl.mouse_buttons_down())) > 0
        if button_down:
            ctrl.mouse_click(button=0, up=True)

    def mouse_scroll_down(amount: float = 1):
        """Scrolls down"""
        mouse_scroll(amount * setting_mouse_wheel_down_amount.get())()

    def mouse_scroll_down_continuous():
        """Scrolls down continuously"""
        global continuous_scoll_mode
        continuous_scoll_mode = "scroll down continuous"
        mouse_scroll(setting_mouse_continuous_scroll_amount.get())()

        if scroll_job is None:
            start_scroll()

        if setting_mouse_hide_mouse_gui.get() == 0:
            gui_wheel.show()

    def mouse_scroll_up(amount: float = 1):
        """Scrolls up"""
        mouse_scroll(-amount * setting_mouse_wheel_down_amount.get())()

    def mouse_scroll_up_continuous():
        """Scrolls up continuously"""
        global continuous_scoll_mode
        continuous_scoll_mode = "scroll up continuous"
        mouse_scroll(-setting_mouse_continuous_scroll_amount.get())()

        if scroll_job is None:
            start_scroll()
        if setting_mouse_hide_mouse_gui.get() == 0:
            gui_wheel.show()

    def mouse_scroll_left(amount: float = 1):
        """Scrolls left"""
        actions.mouse_scroll(0, -amount * setting_mouse_wheel_horizontal_amount.get())

    def mouse_scroll_right(amount: float = 1):
        """Scrolls right"""
        actions.mouse_scroll(0, amount * setting_mouse_wheel_horizontal_amount.get())

    def mouse_scroll_stop():
        """Stops scrolling"""
        stop_scroll()

    def mouse_gaze_scroll():
        """Starts gaze scroll"""
        global continuous_scoll_mode
        continuous_scoll_mode = "gaze scroll"

        start_cursor_scrolling()
        if setting_mouse_hide_mouse_gui.get() == 0:
            gui_wheel.show()

        # enable 'control mouse' if eye tracker is present and not enabled already
        global control_mouse_forced
        if not actions.tracking.control_enabled():
            actions.tracking.control_toggle(True)
            control_mouse_forced = True

    def mouse_gaze_scroll_cursor():
        # Scroll the window if your eyes gaze up or down relative to the current curser position
        """Starts gaze scroll cursor"""
        global continuous_scoll_mode
        continuous_scoll_mode = "gaze scroll"

        start_cursor_scrolling()
        if setting_mouse_hide_mouse_gui.get() == 0:
            gui_wheel.show()

    def copy_mouse_position():
        """Copy the current mouse position coordinates"""
        position = ctrl.mouse_pos()
        clip.set_text(repr(position))

    def mouse_move_center_active_window():
        """move the mouse cursor to the center of the currently active window"""
        rect = ui.active_window().rect
        ctrl.mouse_move(rect.left + (rect.width / 2), rect.top + (rect.height / 2))


def show_cursor_helper(show):
    """Show/hide the cursor"""
    if app.platform == "windows":
        import ctypes
        import winreg

        import win32con

        try:
            Registrykey = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Control Panel\Cursors", 0, winreg.KEY_WRITE
            )

            for value_name, value in default_cursor.items():
                if show:
                    winreg.SetValueEx(
                        Registrykey, value_name, 0, winreg.REG_EXPAND_SZ, value
                    )
                else:
                    winreg.SetValueEx(
                        Registrykey, value_name, 0, winreg.REG_EXPAND_SZ, hidden_cursor
                    )

            winreg.CloseKey(Registrykey)

            ctypes.windll.user32.SystemParametersInfoA(
                win32con.SPI_SETCURSORS, 0, None, 0
            )

        except OSError:
            print(f"Unable to show_cursor({str(show)})")
    else:
        ctrl.cursor_visible(show)


def mouse_scroll(amount):
    def scroll():
        global scroll_amount
        if continuous_scoll_mode:
            if (scroll_amount >= 0) == (amount >= 0):
                scroll_amount += amount
            else:
                scroll_amount = amount
        actions.mouse_scroll(y=int(amount))

    return scroll


def scroll_continuous_helper():
    global scroll_amount
    # print("scroll_continuous_helper")
    if scroll_amount and (eye_zoom_mouse.zoom_mouse.state == eye_zoom_mouse.STATE_IDLE):
        actions.mouse_scroll(by_lines=False, y=int(scroll_amount / 10))


def start_scroll():
    global scroll_job
    scroll_job = cron.interval("60ms", scroll_continuous_helper)


def gaze_scroll():
    # print("gaze_scroll")
    if (
        eye_zoom_mouse.zoom_mouse.state == eye_zoom_mouse.STATE_IDLE
    ):  # or eye_zoom_mouse.zoom_mouse.state == eye_zoom_mouse.STATE_SLEEP:
        x, y = ctrl.mouse_pos()

        # the rect for the window containing the mouse
        rect = None

        # on windows, check the active_window first since ui.windows() is not z-ordered
        if app.platform == "windows" and ui.active_window().rect.contains(x, y):
            rect = ui.active_window().rect
        else:
            windows = ui.windows()
            for w in windows:
                if w.rect.contains(x, y):
                    rect = w.rect
                    break

        if rect is None:
            # print("no window found!")
            return

        midpoint = rect.y + rect.height / 2
        amount = int(((y - midpoint) / (rect.height / 10)) ** 3)
        actions.mouse_scroll(by_lines=False, y=amount)

    # print(f"gaze_scroll: {midpoint} {rect.height} {amount}")


def gaze_scroll_cursor():
    # Scroll the window if your eyes gaze up or down relative to the current window position

    gaze_y = 0
    hist = mouse.eye_hist[-eye_avg:]
    for l, r in hist:
        gaze_y += l.gaze.y + r.gaze.y
    gaze_y /= 2 * len(hist)

    cursor_x, cursor_y = ctrl.mouse_pos()
    cursor_y /= main_screen.height
    diff_y = gaze_y - cursor_y

    if abs(diff_y) > scroll_offset:
        amount = int(scroll_formula(diff_y))
        if diff_y < 0 and amount > 0:
            amount = -amount
        actions.mouse_scroll(by_lines=False, y=amount)


def stop_scroll():
    global scroll_amount, scroll_job, gaze_job, continuous_scoll_mode
    scroll_amount = 0
    if scroll_job:
        cron.cancel(scroll_job)

    if gaze_job:
        cron.cancel(gaze_job)

    global control_mouse_forced
    if control_mouse_forced:
        actions.tracking.control_toggle(False)
        control_mouse_forced = False

    scroll_job = None
    gaze_job = None
    gui_wheel.hide()

    continuous_scoll_mode = ""


def start_cursor_scrolling():
    global scroll_job, gaze_job
    stop_scroll()
    gaze_job = cron.interval("60ms", gaze_scroll)


def custom_zoom_enable(self):
    # print("custom zoom enable hit")
    if self.enabled:
        return
    eye_zoom_mouse.ctx.tags = ["talon_plugins.eye_zoom_mouse.zoom_mouse_enabled"]

    # intentionally don't register pop, handled in on_pop.
    # noise.register("pop", self.on_pop)
    # noise.register("hiss", self.on_hiss)

    tap.register(tap.MCLICK | tap.HOOK, self.on_key)

    # app.register('overlay', self.draw_gaze)
    self.enabled = True


# monkey patch for allowing continuous scrolling to be stopped via a pop
# and coexist well with the zoom mouse.
eye_zoom_mouse.ZoomMouse.enable = custom_zoom_enable

if eye_zoom_mouse.zoom_mouse.enabled:
    noise.unregister("pop", eye_zoom_mouse.zoom_mouse.on_pop)
    noise.unregister("hiss", eye_zoom_mouse.zoom_mouse.on_hiss)


@ctx.action_class("self")
class UserActions:
    def noise_trigger_pop():
        if setting_mouse_enable_pop_stops_scroll.get() >= 1 and (
            gaze_job or scroll_job
        ):
            stop_scroll()
        elif not actions.tracking.control_zoom_enabled():
            if setting_mouse_enable_pop_click.get() >= 1:
                ctrl.mouse_click(button=0, hold=16000)
        elif actions.tracking.control_zoom_enabled():
            if "talon_plugins.eye_zoom_mouse.zoom_mouse_noise" in registry.tags:
                eye_zoom_mouse.zoom_mouse.on_pop(eye_zoom_mouse.zoom_mouse.state)
            else:
                actions.user.move_cursor_to_gaze_point()

    def noise_trigger_hiss():
        if actions.tracking.control_zoom_enabled():
            if "talon_plugins.eye_zoom_mouse.zoom_mouse_noise" in registry.tags:
                eye_zoom_mouse.zoom_mouse.on_hiss(eye_zoom_mouse.zoom_mouse.state)
            else:
                actions.skip()
