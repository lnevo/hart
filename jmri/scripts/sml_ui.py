# -*- coding: utf-8 -*-
# JMRI jython -- part of signal_coordinator.py: the Swing side: the SML Enabled / Disabled button on
# the PanelPro main-window strip, the stored-Enabled warning popup and the force-override confirm.
#
# signal_coordinator.py loads this from preference:jython after sml_quit and reloads it on every run
# (jython_siblings.py).

from java.lang import InterruptedException, Runnable, RuntimeException, Thread
from java.lang.reflect import InvocationTargetException
from javax.swing import JButton, JOptionPane, SwingUtilities

from sml_beans import _ascii, _log_once

# Retries of the main-window button: the strip appears some time after Start Up runs.
_BUTTON_ATTEMPTS = 12
_BUTTON_RETRY_MS = 500
# What a JMRI dialog can raise before the plain Swing one is shown instead: ImportError or AttributeError
# from a JMRI without JmriJOptionPane or the method, a Java RuntimeException (HeadlessException) from Swing.
_DIALOG_ERRORS = (ImportError, AttributeError, RuntimeException)


class _Call(Runnable):
    """A Runnable that calls fn(): the Swing thread's work and the retry thread's."""

    def __init__(self, fn):
        self._fn = fn

    def run(self):
        self._fn()


class SmlUi(object):
    """DigiconMqttSml's main-window button, stored-Enabled popup and override confirm."""

    def _stored_enabled_source_names(self):
        """UserNames of Digicon sources that loaded with any dest Enabled."""
        names = []
        n = 0
        for mast in self._masts:
            c = self._enabled_dest_count(mast)
            if c <= 0:
                continue
            n += c
            try:
                name = mast.getUserName() or mast.getSystemName()
            except RuntimeException as exc:  # a Java bean getter that fails
                _log_once("mqtt_signalhead: cannot read the name of mast %s: %s" % (_ascii(mast), _ascii(exc)))
                name = "?"
            names.append(_ascii(name))
        return n, names

    def _warn_if_stored_sml_enabled(self):
        """Popup if tables.xml stored Digicon SML Enabled. Does not stop boot."""
        n, sources = self._stored_enabled_source_names()
        if n == 0:
            return False
        preview = ", ".join(sources[:8])
        if len(sources) > 8:
            preview += ", ..."
        print(
            "mqtt_signalhead: stored SML Enabled "
            "(%d dests on %d sources) -- warning popup"
            % (n, len(sources))
        )
        msg = (
            "Digicon SML was stored Enabled in tables.xml "
            "(%d destination(s) on %d source(s)).\n"
            "This warning returns at every start until you Store "
            "with SML Disabled.\n\n"
            "Sources: %s\n\n"
            "Startup continues."
            % (n, len(sources), preview)
        )

        class _Warn(Runnable):
            def run(_self):
                try:
                    from jmri.util.swing import JmriJOptionPane

                    JmriJOptionPane.showMessageDialog(
                        None,
                        msg,
                        "Digicon SML stored Enabled",
                        JmriJOptionPane.WARNING_MESSAGE,
                    )
                except _DIALOG_ERRORS as exc:
                    print("mqtt_signalhead: JMRI dialog failed (%s) -- plain Swing dialog" % _ascii(exc))
                    JOptionPane.showMessageDialog(
                        None,
                        msg,
                        "Digicon SML stored Enabled",
                        JOptionPane.WARNING_MESSAGE,
                    )

        SwingUtilities.invokeLater(_Warn())
        return True

    def _button_on_strip(self, space):
        """True if this run's button is already on the strip. A button left by an earlier run
        drives that run's controller, so it is taken off rather than reused."""
        for i in range(space.getComponentCount() - 1, -1, -1):
            c = space.getComponent(i)
            try:
                if c is self._button:
                    return True
                if not hasattr(c, "getText"):  # a panel or separator: not a button
                    continue
                if c.getText() in ("SML Enabled", "SML Disabled"):
                    space.remove(c)
                    print("mqtt_signalhead: removed SML button left by an earlier run")
            except RuntimeException as exc:  # a Swing component that cannot be read or removed
                _log_once("mqtt_signalhead: cannot read button-strip component %s: %s" % (_ascii(c), _ascii(exc)))
        return False

    def _add_toggle_button(self, attempt=0):
        """PanelPro main-window strip — kept in addition to the LE Signals lamp. The first
        attempt runs on the Swing thread; each retry waits _BUTTON_RETRY_MS on its own thread."""
        if attempt == 0:
            if self._button is None:
                self._button = self._new_toggle_button()
            SwingUtilities.invokeLater(_Call(lambda: self._attach_or_retry(attempt)))
        else:
            Thread(_Call(lambda: self._retry_attach(attempt)), "mqtt-sml-button").start()

    def _new_toggle_button(self):
        """The SML button, its click the toggle."""
        button = JButton("SML Disabled")
        button.addActionListener(lambda e: self._on_toggle())
        return button

    def _retry_attach(self, attempt):
        """On the retry thread: wait, then attach on the Swing thread unless detached meanwhile."""
        Thread.sleep(_BUTTON_RETRY_MS)
        if not self._shutting_down:
            SwingUtilities.invokeLater(_Call(lambda: self._attach_or_retry(attempt)))

    def _attach_or_retry(self, attempt):
        """On the Swing thread: put the button on the strip, else schedule the next attempt
        until _BUTTON_ATTEMPTS."""
        # Detached by a re-run (or quitting): leave the strip to the new one.
        if self._shutting_down:
            return
        if self._try_attach(attempt):
            self._set_button_label()
            return
        if attempt + 1 >= _BUTTON_ATTEMPTS:
            print(
                "mqtt_signalhead: giving up on main-window SML button "
                "(panel Signals lamp still works)"
            )
            return
        self._add_toggle_button(attempt + 1)

    def _try_attach(self, attempt):
        """Put this run's button on the PanelPro strip; True when it is there."""
        try:
            from apps import Apps

            space = Apps.buttonSpace()
            if space is None:
                self._attach_failed(attempt, "Apps.buttonSpace() is None")
                return False
            if self._button_on_strip(space):  # already there (a retry)
                space.revalidate()
                space.repaint()
                return True
            if self._button is None:
                self._button = self._new_toggle_button()
            space.add(self._button)
            space.revalidate()
            space.repaint()
            print("mqtt_signalhead: SML toggle on PanelPro button strip")
            return True
        except (ImportError, RuntimeException) as exc:  # not PanelPro (no apps), or a Swing failure
            self._attach_failed(attempt, _ascii(exc))
            return False

    def _attach_failed(self, attempt, why):
        print(
            "mqtt_signalhead: buttonSpace attempt %d failed: %s"
            % (attempt + 1, why)
        )

    def _set_button_busy(self):
        """Grey the button while a worker runs (on the Swing thread)."""
        button = self._button
        if button is None:
            return

        class _Grey(Runnable):
            def run(_self):
                button.setEnabled(False)

        SwingUtilities.invokeLater(_Grey())

    def _set_button_label(self):
        if self._button is None:
            return
        label = "SML Enabled" if self._global_enabled else "SML Disabled"

        class _Set(Runnable):
            def run(_self):
                self._button.setText(label)
                self._button.setEnabled(True)

        SwingUtilities.invokeLater(_Set())

    def _ask_force_override_edt(self):
        """Show override confirm on the EDT. Return True if Yes."""
        holder = [JOptionPane.NO_OPTION]
        msg = (
            "track/bridge/sml_mode is already enabled "
            "(another Digicon session or stale retain).\n"
            "Force override Digicon control?"
        )
        title = "SML Enabled"

        class _Ask(Runnable):
            def run(_self):
                try:
                    from jmri.util.swing import JmriJOptionPane

                    holder[0] = JmriJOptionPane.showConfirmDialog(
                        None,
                        msg,
                        title,
                        JmriJOptionPane.YES_NO_OPTION,
                        JmriJOptionPane.WARNING_MESSAGE,
                    )
                except _DIALOG_ERRORS as exc:
                    print("mqtt_signalhead: JMRI dialog failed (%s) -- plain Swing dialog" % _ascii(exc))
                    holder[0] = JOptionPane.showConfirmDialog(
                        None,
                        msg,
                        title,
                        JOptionPane.YES_NO_OPTION,
                        JOptionPane.WARNING_MESSAGE,
                    )

        try:
            if SwingUtilities.isEventDispatchThread():
                _Ask().run()
            else:
                SwingUtilities.invokeAndWait(_Ask())
        # invokeAndWait wraps what the dialog raised (InvocationTargetException) or is interrupted; on the
        # Swing thread the plain dialog's own RuntimeException arrives unwrapped. Each counts as No.
        except (InvocationTargetException, InterruptedException, RuntimeException) as exc:
            print("mqtt_signalhead: override dialog failed: " + _ascii(exc))
            return False
        return holder[0] == JOptionPane.YES_OPTION
