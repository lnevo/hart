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
# CTC Panel: Help/Quit go on Apps.buttonSpace() (bottom, with Restart RPi).
# Do not wrap a second toolbar at the top. Dispatcher Panel has no button
# strip, so it keeps the in-window toolbar. File already has Exit; do not
# add a second Quit.

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


def _remove_named_menu_item(menu, name):
    if menu is None:
        return
    doomed = []
    for i in range(menu.getItemCount()):
        item = menu.getItem(i)
        if item is not None and item.getName() == name:
            doomed.append(item)
    for item in doomed:
        try:
            menu.remove(item)
        except Exception:
            pass


def _item_label(item):
    if item is None:
        return ""
    try:
        return (item.getText() or "").strip().lower()
    except Exception:
        return ""


def _clean_file_quit(menu):
    """Drop the extra File -> Quit we used to add. Keep File -> Exit."""
    if menu is None:
        return
    _remove_named_menu_item(menu, QUIT_ITEM_NAME)
    has_exit = False
    quits = []
    for i in range(menu.getItemCount()):
        item = menu.getItem(i)
        if item is None:
            continue
        label = _item_label(item)
        if label in ("exit", "exit..."):
            has_exit = True
        elif label == "quit":
            quits.append(item)
    doomed = quits if has_exit else quits[1:]
    for item in doomed:
        try:
            menu.remove(item)
        except Exception:
            pass


def _has_button_text(container, title):
    if container is None:
        return False
    want = (title or "").strip().lower()
    try:
        count = container.getComponentCount()
    except Exception:
        return False
    for i in range(count):
        try:
            label = container.getComponent(i).getText()
        except Exception:
            continue
        if label is not None and label.strip().lower() == want:
            return True
    return False


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


def remove_window_toolbar(frame):
    """Undo a prior wrap so CTC Panel is not stuck with a top Help/Quit row."""
    if frame is None:
        return False
    cp = frame.getContentPane()
    if cp is None or cp.getName() != WRAP_NAME:
        return False
    inner = None
    layout = cp.getLayout()
    if isinstance(layout, BorderLayout):
        inner = layout.getLayoutComponent(BorderLayout.CENTER)
    if inner is None:
        for i in range(cp.getComponentCount()):
            child = cp.getComponent(i)
            if child.getName() != TOOLBAR_NAME:
                inner = child
                break
    if inner is None:
        return False
    frame.setContentPane(inner)
    _refresh(frame)
    return True


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


def add_script_style_buttons():
    """Help/Quit on the Apps button strip (bottom of CTC Panel)."""
    try:
        from apps import Apps
        space = Apps.buttonSpace()
    except Exception:
        return False
    if space is None:
        return False
    added = False
    if not _has_named(space, HELP_NAME) and not _has_button_text(space, "Help"):
        space.add(_new_button("Help", HELP_NAME, _show_jmri_help))
        added = True
    if not _has_named(space, QUIT_NAME) and not _has_button_text(space, "Quit"):
        space.add(_new_button("Quit", QUIT_NAME, _quit_cats))
        added = True
    if added:
        try:
            space.revalidate()
            space.repaint()
        except Exception:
            pass
        print("HART: CATS Help/Quit on CTC Panel button strip")
    return True


def decorate_menus(frame):
    """Help menu extras only. File already has Exit; do not add Quit."""
    if frame is None:
        return False
    bar = frame.getJMenuBar()
    if bar is None:
        return True
    file_menu = _find_menu(bar, "File")
    _clean_file_quit(file_menu)
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
    remove_window_toolbar(frame)
    if not add_script_style_buttons():
        return False
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
