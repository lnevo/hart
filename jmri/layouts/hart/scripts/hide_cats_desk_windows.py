# JMRI Jython: under CATS, hide HART Railroad and add Help/Quit on CTC Panel.
#
# LogixNG IQ:AUTO:0001 runs this at init as IQC:AUTO:0004. IQC:0001-0003 already
# hide WiThrottle, USS CTC, and Dispatcher System on every host. PanelPro leaves
# HART Railroad up; CATS is a separate JVM (cats.apps.Crandic) and should not
# keep that geographic panel.
#
# MUST stay ASCII. Jython 2.7 LogixNG ActionScript crashes the whole file on a
# UnicodeDecodeError (em-dash in a print previously aborted before chrome).
#
# Mac puts JMenuBar items in the screen menu bar and drops JButtons on a
# JMenuBar, so Help/Quit are a toolbar inside the window. Restart RPi /
# Shutdown RPi stay on Apps.buttonSpace(); do not put Help/Quit there too.

from __future__ import print_function

from java.awt import BorderLayout, FlowLayout, Frame, Window
from java.awt.event import ActionListener
from java.io import File
from java.lang import System

from javax.swing import JButton, JMenuItem, JPanel

from jmri.util import JmriJFrame, ThreadingUtil

HART_RAILROAD = "HART Railroad"
CTC_PANEL = "CTC Panel"
DISPATCHER_PANEL = "Dispatcher Panel"
WRAP_NAME = "HART:CATS:Wrapped"
TOOLBAR_NAME = "HART:CATS:Toolbar"
HELP_NAME = "HART:CATS:Help"
QUIT_NAME = "HART:CATS:Quit"
GUIDE_NAME = "HART:CATS:Guide"
QUIT_ITEM_NAME = "HART:CATS:QuitItem"
GUIDE_SPECS = (
    "home:hart/cats/docs/DISPATCHER_GUIDE_CTC.md",
)

_state = {"tries": 0, "hid": False, "chrome": False}
_MAX_TRIES = 40


def under_cats():
    cmd = System.getProperty("sun.java.command") or ""
    cfg = System.getProperty("org.jmri.Apps.configFilename") or ""
    if "cats.apps" in cmd or cfg.lower() == "catsconfig.xml":
        return True
    for window in Window.getWindows():
        try:
            if window.getClass().getName().startswith("cats."):
                return True
        except Exception:
            pass
    return False


def hide_title(title):
    frame = JmriJFrame.getFrame(title)
    if frame is not None:
        frame.setVisible(False)
        return True
    for window in Window.getWindows():
        try:
            if isinstance(window, Frame) and window.getTitle() == title:
                window.setVisible(False)
                return True
        except Exception:
            pass
    return False


class _Call(ActionListener):
    def __init__(self, fn):
        self.fn = fn

    def actionPerformed(self, event):
        self.fn()


def _quit_cats():
    from apps import Apps
    Apps.handleQuit()


def _show_jmri_help():
    from jmri.util import HelpUtil
    try:
        HelpUtil.displayHelpRef("index")
    except Exception:
        HelpUtil.displayHelpRef("package.apps.PanelPro.PanelPro")


def _open_dispatcher_guide():
    from jmri.util import FileUtil
    from java.awt import Desktop
    for spec in GUIDE_SPECS:
        try:
            path = FileUtil.getExternalFilename(spec)
        except Exception:
            path = None
        if path and File(path).isFile():
            try:
                if Desktop.isDesktopSupported():
                    Desktop.getDesktop().open(File(path))
                    return
            except Exception:
                pass
    _show_jmri_help()


def _has_named(container, name):
    if container is None:
        return False
    try:
        count = container.getComponentCount()
    except Exception:
        return False
    for i in range(count):
        try:
            if container.getComponent(i).getName() == name:
                return True
        except Exception:
            pass
    return False


def _menu_has_named(menu, name):
    if menu is None:
        return False
    for i in range(menu.getItemCount()):
        item = menu.getItem(i)
        if item is not None and item.getName() == name:
            return True
    return False


def _find_menu(bar, title):
    if bar is None:
        return None
    for i in range(bar.getMenuCount()):
        menu = bar.getMenu(i)
        if menu is not None and menu.getText() == title:
            return menu
    return None


def _new_button(title, name, fn):
    btn = JButton(title)
    btn.setName(name)
    btn.setToolTipText(title)
    btn.addActionListener(_Call(fn))
    return btn


def frame_named(title):
    frame = JmriJFrame.getFrame(title)
    if frame is not None:
        return frame
    for window in Window.getWindows():
        try:
            if isinstance(window, Frame) and window.getTitle() == title:
                return window
        except Exception:
            pass
    return None


def _refresh(frame):
    try:
        frame.revalidate()
    except Exception:
        frame.validate()
    try:
        frame.repaint()
    except Exception:
        pass


def install_window_toolbar(frame):
    """Help/Quit strip inside the frame (visible on Mac; JMenuBar buttons are not)."""
    if frame is None:
        return False
    cp = frame.getContentPane()
    if cp is None:
        return False
    if cp.getName() == WRAP_NAME or _has_named(cp, TOOLBAR_NAME):
        return True
    tools = JPanel(FlowLayout(FlowLayout.RIGHT, 8, 2))
    tools.setName(TOOLBAR_NAME)
    tools.add(_new_button("Help", HELP_NAME, _show_jmri_help))
    tools.add(_new_button("Quit", QUIT_NAME, _quit_cats))
    wrap = JPanel(BorderLayout())
    wrap.setName(WRAP_NAME)
    wrap.add(tools, BorderLayout.NORTH)
    wrap.add(cp, BorderLayout.CENTER)
    frame.setContentPane(wrap)
    _refresh(frame)
    return True


def decorate_menus(frame):
    """File/Help items (Mac screen menu bar). Safe if bar is missing."""
    if frame is None:
        return False
    bar = frame.getJMenuBar()
    if bar is None:
        return True
    file_menu = _find_menu(bar, "File")
    if file_menu is not None and not _menu_has_named(file_menu, QUIT_ITEM_NAME):
        item = JMenuItem("Quit")
        item.setName(QUIT_ITEM_NAME)
        item.addActionListener(_Call(_quit_cats))
        file_menu.addSeparator()
        file_menu.add(item)
    help_menu = _find_menu(bar, "Help")
    if help_menu is not None and not _menu_has_named(help_menu, GUIDE_NAME):
        jmri_item = JMenuItem("Window Help...")
        jmri_item.setName("HART:CATS:HelpItem")
        jmri_item.addActionListener(_Call(_show_jmri_help))
        guide_item = JMenuItem("HART Dispatcher Guide")
        guide_item.setName(GUIDE_NAME)
        guide_item.addActionListener(_Call(_open_dispatcher_guide))
        help_menu.insert(guide_item, 0)
        help_menu.insert(jmri_item, 0)
        help_menu.insertSeparator(2)
    try:
        bar.revalidate()
        bar.repaint()
    except Exception:
        pass
    return True


def decorate_ctc_panel():
    frame = frame_named(CTC_PANEL)
    if frame is None:
        return False
    decorate_menus(frame)
    cp = frame.getContentPane()
    already = cp is not None and (
        cp.getName() == WRAP_NAME or _has_named(cp, TOOLBAR_NAME)
    )
    if not install_window_toolbar(frame):
        return False
    if not already:
        print("HART: CATS Help/Quit on CTC Panel")
    return True


def decorate_dispatcher_panel():
    frame = frame_named(DISPATCHER_PANEL)
    if frame is None:
        return False
    decorate_menus(frame)
    cp = frame.getContentPane()
    already = cp is not None and (
        cp.getName() == WRAP_NAME or _has_named(cp, TOOLBAR_NAME)
    )
    if not install_window_toolbar(frame):
        return False
    if not already:
        print("HART: CATS Help/Quit on Dispatcher Panel")
    return True


def hide_cats_desk_windows():
    if not under_cats():
        return
    hidden = []

    def _hide():
        if hide_title(HART_RAILROAD):
            hidden.append(HART_RAILROAD)

    ThreadingUtil.runOnGUI(_hide)
    if hidden:
        print("HART: CATS control hid " + ", ".join(hidden))
        _state["hid"] = True


def _pass():
    if not under_cats():
        return
    if not _state["hid"]:
        if hide_title(HART_RAILROAD):
            _state["hid"] = True
            print("HART: CATS control hid " + HART_RAILROAD)
    ctc_ok = False
    desk_ok = False
    try:
        ctc_ok = decorate_ctc_panel()
    except Exception as e:
        print("HART: CATS Help/Quit CTC Panel failed: %s" % e)
    try:
        desk_ok = decorate_dispatcher_panel()
    except Exception as e:
        print("HART: CATS Help/Quit Dispatcher Panel failed: %s" % e)
    if ctc_ok:
        _state["chrome"] = True
        if desk_ok:
            return
    _state["tries"] += 1
    if _state["tries"] >= _MAX_TRIES:
        if not _state["chrome"]:
            print("HART: CATS Help/Quit incomplete (ctc=%s desk=%s)" % (ctc_ok, desk_ok))
        return
    ThreadingUtil.runOnGUIDelayed(_pass, 500)


try:
    if under_cats():
        hide_cats_desk_windows()
        ThreadingUtil.runOnGUI(_pass)
    else:
        hide_cats_desk_windows()
except Exception as e:
    print("HART: hide_cats_desk_windows failed: %s" % e)
