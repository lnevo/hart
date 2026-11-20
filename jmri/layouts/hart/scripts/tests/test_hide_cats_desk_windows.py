"""hide_cats_desk_windows.py: which windows it hides under CATS, and that it is safe without them.

The script runs as it loads, so each test builds a fake desktop (windows, system properties,
the Apps button strip) and then loads it. Nothing is shown: the windows are plain objects, and
the GUI calls JMRI would queue (`runOnGUI`, `runOnGUIDelayed`) are run or kept by the test.

Java exceptions are modelled on Jython 2.7.4 (checked against JMRI's jython-standalone jar,
2026-11-19): the script's `except Exception` does not catch them, so `JavaException` derives
from BaseException.
"""
from __future__ import annotations

import contextlib
import io
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jmri_fake as jf  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "hide_cats_desk_windows.py"
PANELPRO = "apps.PanelPro.PanelPro"
CATS = "cats.apps.Crandic"


class JavaThrowable(BaseException):
    """java.lang.Throwable: not a Python Exception in Jython."""


class JavaException(JavaThrowable):
    """java.lang.Exception."""


# --- a fake desktop -------------------------------------------------------------------


class Component:
    def __init__(self, name=None):
        self.name, self.children, self.layout, self.refreshed = name, [], None, 0

    def getName(self):
        return self.name

    def setName(self, name):
        self.name = name

    def add(self, child, where=None):
        self.children.append(child)
        if where is not None and self.layout is not None:
            self.layout.places[where] = child

    def getComponentCount(self):
        return len(self.children)

    def getComponent(self, i):
        return self.children[i]

    def getLayout(self):
        return self.layout

    def revalidate(self):
        self.refreshed += 1

    def repaint(self):
        pass


class BorderLayout:
    NORTH, CENTER = "North", "Center"

    def __init__(self):
        self.places = {}

    def getLayoutComponent(self, where):
        return self.places.get(where)


class FlowLayout:
    RIGHT = 2

    def __init__(self, *args):
        pass


class JPanel(Component):
    def __init__(self, layout=None):
        super().__init__()
        self.layout = layout


class JButton(Component):
    def __init__(self, text):
        super().__init__()
        self.text, self.tip, self.listeners = text, None, []

    def getText(self):
        return self.text

    def setToolTipText(self, tip):
        self.tip = tip

    def addActionListener(self, listener):
        self.listeners.append(listener)

    def click(self):
        for listener in self.listeners:
            listener.actionPerformed(None)


class Item:
    def __init__(self, text, name=None):
        self.text, self.name = text, name

    def getText(self):
        return self.text

    def getName(self):
        return self.name


class Menu:
    def __init__(self, text, *items):
        self.text, self.items = text, list(items)

    def getText(self):
        return self.text

    def getItemCount(self):
        return len(self.items)

    def getItem(self, i):
        return self.items[i]

    def remove(self, item):
        self.items.remove(item)

    def labels(self):
        return [item.text if item is not None else None for item in self.items]


class MenuBar(Component):
    def __init__(self, *menus):
        super().__init__()
        self.menus = list(menus)

    def getMenuCount(self):
        return len(self.menus)

    def getMenu(self, i):
        return self.menus[i]


class Window:
    """java.awt.Window: a dialog or other window that is not a Frame."""

    def __init__(self, title, cls="javax.swing.JDialog"):
        self.title, self.cls, self.visible = title, cls, True

    def getClass(self):
        return types.SimpleNamespace(getName=lambda: self.cls)

    def getTitle(self):
        return self.title

    def setVisible(self, value):
        self.visible = value


class Frame(Window):
    def __init__(self, title, cls="javax.swing.JFrame", menu_bar=None):
        super().__init__(title, cls)
        self.content, self.menu_bar, self.refreshed = JPanel(), menu_bar, 0

    def getContentPane(self):
        return self.content

    def setContentPane(self, pane):
        self.content = pane

    def getJMenuBar(self):
        return self.menu_bar

    def revalidate(self):
        self.refreshed += 1

    def repaint(self):
        pass


class Desk:
    """What one test's JVM holds."""

    def __init__(self, command=PANELPRO, config="PanelProConfig2.xml"):
        self.props = {"sun.java.command": command, "org.jmri.Apps.configFilename": config}
        self.windows = []          # java.awt.Window.getWindows()
        self.jmri_frames = {}      # JmriJFrame.getFrame(title)
        self.space = None          # Apps.buttonSpace()
        self.space_error = None
        self.gui_calls = 0         # ThreadingUtil.runOnGUI
        self.delayed = []          # (function, ms) from ThreadingUtil.runOnGUIDelayed
        self.quits = 0
        self.help = []
        self.help_error = None
        self.out = io.StringIO()
        self.script = None

    def jmri_frame(self, title, **kw):
        frame = Frame(title, cls="jmri.util.JmriJFrame", **kw)
        self.jmri_frames[title] = frame
        self.windows.append(frame)
        return frame

    def window(self, window):
        self.windows.append(window)
        return window

    # --- what the script imports ---

    def _run_on_gui(self, function):
        self.gui_calls += 1
        function()

    def _button_space(self):
        if self.space_error is not None:
            raise self.space_error
        return self.space

    def _quit(self):
        self.quits += 1

    def _help(self, ref):
        self.help.append(ref)
        if self.help_error is not None and ref == "index":
            raise self.help_error

    def modules(self):
        def mod(name, **attrs):
            m = types.ModuleType(name)
            m.__dict__.update(attrs)
            return m

        window_cls = type("Window", (Window,), {"getWindows": staticmethod(lambda: list(self.windows))})
        event = mod("java.awt.event", ActionListener=type("ActionListener", (object,), {}))
        awt = mod("java.awt", BorderLayout=BorderLayout, FlowLayout=FlowLayout, Frame=Frame,
                  Window=window_cls, event=event)
        lang = mod("java.lang", System=types.SimpleNamespace(getProperty=self.props.get),
                   Throwable=JavaThrowable, Exception=JavaException)
        swing = mod("javax.swing", JButton=JButton, JPanel=JPanel)
        util = mod("jmri.util", JmriJFrame=types.SimpleNamespace(getFrame=self.jmri_frames.get),
                   ThreadingUtil=types.SimpleNamespace(
                       runOnGUI=self._run_on_gui,
                       runOnGUIDelayed=lambda function, ms: self.delayed.append((function, ms))),
                   HelpUtil=types.SimpleNamespace(displayHelpRef=self._help))
        apps = mod("apps", Apps=types.SimpleNamespace(buttonSpace=self._button_space, handleQuit=self._quit))
        return {"java": mod("java", awt=awt, lang=lang), "java.awt": awt, "java.awt.event": event,
                "java.lang": lang, "javax": mod("javax", swing=swing), "javax.swing": swing,
                "jmri": mod("jmri", util=util), "jmri.util": util, "apps": apps}

    def load(self, case):
        """Run the script as JMRI does. The fake modules stay in place until the test ends."""
        stack = contextlib.ExitStack()
        case.addCleanup(stack.close)
        stack.enter_context(jf.fake_modules(self.modules()))
        stack.enter_context(jf.no_network())
        stack.enter_context(contextlib.redirect_stdout(self.out))
        self.script = {"__name__": "hart_script_under_test"}
        exec(compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec"), self.script)
        return self.script

    def tick(self, limit=100):
        """Run the delayed passes in order, as the Swing timer would; returns how many ran."""
        n = 0
        while self.delayed and n < limit:
            function, _ = self.delayed.pop(0)
            function()
            n += 1
        return n

    def printed(self):
        return self.out.getvalue().splitlines()


def cats_desk(**kw):
    """A CATS JVM with the windows PanelPro's tables open there."""
    desk = Desk(command=CATS, config="CATSConfig.xml", **kw)
    desk.railroad = desk.jmri_frame("HART Railroad")
    desk.ctc = desk.jmri_frame("CTC Panel")
    desk.dispatcher = desk.window(Frame("Dispatcher Panel", cls="cats.gui.DispPanel"))
    desk.space = JPanel()
    return desk


def wrapped(inner):
    """A content pane as the old top Help/Quit wrap left it."""
    wrap = JPanel(BorderLayout())
    wrap.setName("HART:CATS:Wrapped")
    tools = JPanel()
    tools.setName("HART:CATS:Toolbar")
    wrap.add(tools, BorderLayout.NORTH)
    wrap.add(inner, BorderLayout.CENTER)
    return wrap


# --- tests ----------------------------------------------------------------------------


class NotUnderCats(unittest.TestCase):
    """PanelPro: the script must leave every window alone."""

    def test_panelpro_keeps_every_window_and_schedules_nothing(self):
        desk = Desk()
        railroad = desk.jmri_frame("HART Railroad")
        ctc = desk.jmri_frame("CTC Panel")
        desk.space = JPanel()
        desk.load(self)
        self.assertTrue(railroad.visible)
        self.assertTrue(ctc.visible)
        self.assertEqual((desk.gui_calls, desk.delayed, desk.space.children), (0, [], []))
        self.assertEqual(desk.printed(), [])
        self.assertEqual(desk.script["_state"], {"tries": 0, "hid": False, "chrome": False})

    def test_no_windows_at_all_is_safe(self):
        desk = Desk()
        desk.load(self)
        self.assertEqual((desk.gui_calls, desk.delayed, desk.printed()), (0, [], []))

    def test_missing_system_properties_are_safe(self):
        desk = Desk(command=None, config=None)
        railroad = desk.jmri_frame("HART Railroad")
        desk.load(self)
        self.assertTrue(railroad.visible)

    def test_a_pass_run_by_hand_does_nothing_outside_cats(self):
        desk = Desk()
        railroad = desk.jmri_frame("HART Railroad")
        script = desk.load(self)
        script["_pass"]()
        script["hide_cats_desk_windows"]()
        self.assertTrue(railroad.visible)
        self.assertEqual((desk.gui_calls, desk.delayed), (0, []))


class UnderCats(unittest.TestCase):
    """How the script decides it runs inside CATS."""

    def under(self, desk):
        return desk.load(self)["under_cats"]()

    def test_cats_main_class_on_the_command_line(self):
        self.assertTrue(self.under(Desk(command=CATS + " -Xmx512m")))

    def test_cats_config_file_in_any_case(self):
        self.assertTrue(self.under(Desk(config="CATSConfig.xml")))
        self.assertTrue(self.under(Desk(config="catsconfig.XML")))
        self.assertFalse(self.under(Desk(config="/profile/CATSConfig.xml")))   # the whole name must match

    def test_a_window_of_a_cats_class(self):
        desk = Desk()
        desk.window(Frame("Dispatcher Panel", cls="cats.gui.DispPanel"))
        self.assertTrue(self.under(desk))

    def test_other_windows_do_not_count_and_a_window_that_fails_is_skipped(self):
        class Broken(Window):
            def getClass(self):
                raise RuntimeError("disposed")
        desk = Desk()
        desk.window(Broken("x"))
        desk.window(Frame("CATS notes", cls="jmri.util.JmriJFrame"))
        desk.window(Frame("Dispatcher Panel", cls="org.cats.Other"))
        self.assertFalse(self.under(desk))


class Hiding(unittest.TestCase):
    def test_hides_hart_railroad_and_leaves_every_other_window(self):
        desk = cats_desk()
        others = [desk.ctc, desk.dispatcher, desk.jmri_frame("WiThrottle"), desk.jmri_frame("HART Railroad Staging"),
                  desk.jmri_frame("hart railroad"), desk.jmri_frame("HART Railroad "), desk.jmri_frame("PanelPro"),
                  desk.window(Frame("Train Sheet", cls="cats.gui.Sheet"))]
        desk.load(self)
        self.assertFalse(desk.railroad.visible)
        self.assertEqual([w.title for w in others if not w.visible], [])
        self.assertTrue(desk.script["_state"]["hid"])
        self.assertEqual(desk.printed()[0], "HART: CATS control hid HART Railroad")
        self.assertEqual(desk.printed().count("HART: CATS control hid HART Railroad"), 1)

    def test_the_hide_goes_through_the_gui_thread_call(self):
        desk = cats_desk()
        desk.load(self)
        self.assertEqual(desk.gui_calls, 2)          # the hide, then the first pass

    def test_a_plain_frame_with_the_title_is_hidden_when_jmri_does_not_know_it(self):
        desk = Desk(command=CATS)
        plain = desk.window(Frame("HART Railroad"))
        other = desk.window(Frame("Other"))
        desk.load(self)
        self.assertFalse(plain.visible)
        self.assertTrue(other.visible)

    def test_a_window_that_is_not_a_frame_keeps_showing_even_with_the_title(self):
        desk = Desk(command=CATS)
        dialog = desk.window(Window("HART Railroad"))
        desk.load(self)
        self.assertTrue(dialog.visible)
        self.assertFalse(desk.script["_state"]["hid"])

    def test_only_the_first_match_is_hidden(self):
        desk = cats_desk()
        second = desk.window(Frame("HART Railroad"))
        desk.load(self)
        self.assertFalse(desk.railroad.visible)
        self.assertTrue(second.visible)              # JMRI's frame was found first; the scan stops there

    def test_a_frame_that_fails_on_its_title_is_skipped(self):
        class Broken(Frame):
            def getTitle(self):
                raise RuntimeError("disposed")
        desk = Desk(command=CATS)
        desk.window(Broken("x"))
        plain = desk.window(Frame("HART Railroad"))
        desk.load(self)
        self.assertFalse(plain.visible)

    def test_an_already_hidden_window_is_hidden_again_without_harm(self):
        desk = cats_desk()
        desk.railroad.visible = False
        desk.load(self)
        self.assertFalse(desk.railroad.visible)
        self.assertTrue(desk.script["_state"]["hid"])

    def test_the_window_is_not_hidden_twice_once_hidden(self):
        desk = cats_desk()
        desk.dispatcher.title = "not yet"            # keeps the passes going
        desk.load(self)
        desk.railroad.visible = True                 # the operator shows it again
        desk.tick(limit=3)
        self.assertTrue(desk.railroad.visible)


class NoCatsWindows(unittest.TestCase):
    """CATS is starting: none of its windows exist yet, or never will."""

    def test_no_window_exists_nothing_fails_and_it_retries_every_half_second(self):
        desk = Desk(command=CATS)
        desk.load(self)
        self.assertEqual(desk.printed(), [])
        self.assertEqual(desk.script["_state"], {"tries": 1, "hid": False, "chrome": False})
        self.assertEqual([ms for _, ms in desk.delayed], [500])

    def test_it_gives_up_after_forty_passes_and_says_so_once(self):
        desk = Desk(command=CATS)
        desk.load(self)
        self.assertEqual(desk.tick(), 39)            # the first pass ran at load
        self.assertEqual(desk.delayed, [])
        self.assertEqual(desk.script["_state"], {"tries": 40, "hid": False, "chrome": False})
        self.assertEqual(desk.printed(), ["HART: CATS Help/Quit incomplete (ctc=False desk=False)"])

    def test_a_window_that_opens_later_is_hidden_on_a_later_pass(self):
        desk = Desk(command=CATS)
        desk.load(self)
        desk.tick(limit=2)
        railroad = desk.jmri_frame("HART Railroad")
        desk.tick(limit=1)
        self.assertFalse(railroad.visible)
        self.assertTrue(desk.script["_state"]["hid"])
        self.assertIn("HART: CATS control hid HART Railroad", desk.printed())

    def test_a_window_that_opens_after_the_last_pass_stays(self):
        desk = Desk(command=CATS)
        desk.load(self)
        desk.tick()
        railroad = desk.jmri_frame("HART Railroad")
        self.assertEqual(desk.tick(), 0)
        self.assertTrue(railroad.visible)

    def test_no_button_strip_keeps_retrying_and_adds_nothing(self):
        for space_error in (None, RuntimeError("no Apps")):
            desk = cats_desk()
            desk.space, desk.space_error = None, space_error
            desk.load(self)
            desk.tick()
            self.assertEqual(desk.script["_state"], {"tries": 40, "hid": True, "chrome": False})
            self.assertEqual(desk.printed()[-1], "HART: CATS Help/Quit incomplete (ctc=False desk=True)")

    def test_a_python_error_at_load_is_printed_not_raised(self):
        desk = Desk(command=CATS)
        desk.props = types.SimpleNamespace(get=mock.Mock(side_effect=RuntimeError("no properties")))
        desk.load(self)
        self.assertEqual(desk.printed(), ["HART: hide_cats_desk_windows failed: no properties"])

    def test_a_python_error_in_one_panel_is_printed_and_the_pass_goes_on(self):
        desk = cats_desk()
        desk.ctc.getJMenuBar = mock.Mock(side_effect=RuntimeError("menu gone"))
        desk.load(self)
        self.assertEqual(desk.printed()[1], "HART: CATS Help/Quit CTC Panel failed: menu gone")
        self.assertEqual([ms for _, ms in desk.delayed], [500])
        self.assertEqual(desk.script["_state"]["tries"], 1)

    def test_a_java_exception_in_a_panel_escapes_and_stops_the_retries(self):
        """Fault, not fixed here: `except Exception` in _pass does not catch a Java exception in
        Jython, so it leaves _pass on the GUI thread before the next pass is scheduled."""
        desk = cats_desk()
        desk.dispatcher.title = "not yet"
        desk.load(self)
        desk.ctc.getJMenuBar = mock.Mock(side_effect=JavaException("IllegalStateException"))
        with self.assertRaises(JavaException):
            desk.tick()
        self.assertEqual(desk.delayed, [])

    def test_a_java_exception_at_load_escapes_the_script(self):
        """Fault, not fixed here: the script's last `except Exception` does not catch it either."""
        desk = Desk(command=CATS)
        desk.props = types.SimpleNamespace(get=mock.Mock(side_effect=JavaException("SecurityException")))
        with self.assertRaises(JavaException):
            desk.load(self)


class Chrome(unittest.TestCase):
    """Help and Quit on the CTC Panel button strip; nothing on the Dispatcher Panel."""

    def test_help_and_quit_go_on_the_button_strip_once_and_the_passes_stop(self):
        desk = cats_desk()
        script = desk.load(self)
        self.assertEqual([(b.text, b.name, b.tip) for b in desk.space.children],
                         [("Help", "HART:CATS:Help", "Help"), ("Quit", "HART:CATS:Quit", "Quit")])
        self.assertEqual(desk.delayed, [])
        self.assertEqual(script["_state"], {"tries": 0, "hid": True, "chrome": True})
        self.assertEqual(desk.printed(), ["HART: CATS control hid HART Railroad",
                                          "HART: CATS Help/Quit on CTC Panel button strip"])
        script["_pass"]()
        self.assertEqual(len(desk.space.children), 2)
        self.assertTrue(desk.ctc.visible and desk.dispatcher.visible)

    def test_buttons_already_there_by_name_or_text_are_not_added_again(self):
        desk = cats_desk()
        desk.space.add(JButton(" quit "))
        desk.load(self)
        self.assertEqual([b.text for b in desk.space.children], [" quit ", "Help"])

    def test_quit_asks_jmri_to_quit_and_help_opens_the_index(self):
        desk = cats_desk()
        desk.load(self)
        help_button, quit_button = desk.space.children
        quit_button.click()
        self.assertEqual(desk.quits, 1)
        help_button.click()
        self.assertEqual(desk.help, ["index"])

    def test_help_falls_back_to_the_panelpro_page_on_a_python_error(self):
        desk = cats_desk()
        desk.help_error = RuntimeError("no index")
        desk.load(self)
        desk.space.children[0].click()
        self.assertEqual(desk.help, ["index", "package.apps.PanelPro.PanelPro"])

    def test_ctc_panel_alone_gets_its_buttons_and_waits_quietly_for_the_dispatcher_panel(self):
        desk = cats_desk()
        desk.dispatcher.title = "not yet"
        desk.load(self)
        self.assertEqual(len(desk.space.children), 2)
        desk.tick()
        self.assertEqual(desk.script["_state"], {"tries": 40, "hid": True, "chrome": True})
        self.assertEqual(len(desk.space.children), 2)
        self.assertNotIn("incomplete", desk.out.getvalue())

    def test_the_dispatcher_panel_found_by_title_stops_the_passes(self):
        desk = cats_desk()
        desk.dispatcher.title = "not yet"
        desk.load(self)
        desk.tick(limit=2)
        desk.dispatcher.title = "Dispatcher Panel"
        desk.tick()
        self.assertEqual(desk.script["_state"]["tries"], 3)
        self.assertEqual(desk.delayed, [])

    def test_an_old_top_toolbar_wrap_is_removed_from_both_panels(self):
        desk = cats_desk()
        inner_ctc, inner_desk = desk.ctc.content, desk.dispatcher.content
        desk.ctc.content, desk.dispatcher.content = wrapped(inner_ctc), wrapped(inner_desk)
        desk.load(self)
        self.assertIs(desk.ctc.content, inner_ctc)
        self.assertIs(desk.dispatcher.content, inner_desk)
        self.assertEqual((desk.ctc.refreshed, desk.dispatcher.refreshed), (1, 1))

    def test_panels_without_the_wrap_keep_their_content_and_get_no_buttons_inside(self):
        desk = cats_desk()
        inner_ctc, inner_desk = desk.ctc.content, desk.dispatcher.content
        desk.load(self)
        self.assertIs(desk.ctc.content, inner_ctc)
        self.assertIs(desk.dispatcher.content, inner_desk)
        self.assertEqual((inner_ctc.children, inner_desk.children), ([], []))
        self.assertEqual((desk.ctc.refreshed, desk.dispatcher.refreshed), (0, 0))

    def test_file_menu_loses_quit_when_it_has_exit(self):
        desk = cats_desk()
        file_menu = Menu("File", Item("Open..."), Item("Quit", "HART:CATS:QuitItem"), None, Item(" QUIT "),
                         Item("Exit"))
        edit_menu = Menu("Edit", Item("Quit"))
        desk.ctc.menu_bar = MenuBar(file_menu, None, edit_menu)
        desk.load(self)
        self.assertEqual(file_menu.labels(), ["Open...", None, "Exit"])
        self.assertEqual(edit_menu.labels(), ["Quit"])
        self.assertEqual(desk.ctc.menu_bar.refreshed, 1)

    def test_file_menu_without_exit_keeps_its_first_quit(self):
        desk = cats_desk()
        file_menu = Menu("File", Item("Quit"), Item("Quit"), Item("Quit", "HART:CATS:QuitItem"))
        desk.dispatcher.menu_bar = MenuBar(file_menu)
        desk.load(self)
        self.assertEqual(len(file_menu.items), 1)
        self.assertIsNone(file_menu.items[0].name)

    def test_install_window_toolbar_is_kept_but_not_used_at_load(self):
        desk = cats_desk()
        script = desk.load(self)
        frame = Frame("Spare")
        inner = frame.content
        self.assertTrue(script["install_window_toolbar"](frame))
        self.assertEqual(frame.content.name, "HART:CATS:Wrapped")
        self.assertTrue(script["install_window_toolbar"](frame))       # a second call wraps nothing more
        self.assertIs(frame.content.layout.getLayoutComponent(BorderLayout.CENTER), inner)
        self.assertTrue(script["remove_window_toolbar"](frame))
        self.assertIs(frame.content, inner)
        self.assertFalse(script["remove_window_toolbar"](frame))
        self.assertFalse(script["remove_window_toolbar"](None))
        self.assertFalse(script["install_window_toolbar"](None))


class Source(unittest.TestCase):
    def test_script_stays_ascii_and_commands_nothing_on_the_layout(self):
        raw = SCRIPT.read_bytes()
        raw.decode("ascii")                           # Jython 2.7 fails the whole file on a non-ASCII byte
        text = raw.decode("ascii")
        for word in ("setCommandedState", "mqtt", "publish", "setKnownState", "dispose("):
            self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main()
