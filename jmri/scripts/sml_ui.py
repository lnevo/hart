# -*- coding: utf-8 -*-
# JMRI jython -- part of signal_coordinator.py: the Swing side: the SML Enabled / Disabled button on
# the PanelPro main-window strip, the stored-Enabled warning popup and the force-override confirm.
#
# signal_coordinator.py loads this from preference:jython after sml_quit and reloads it on every run
# (jython_siblings.py).

from java.lang import Runnable, Thread
from javax.swing import JButton, JOptionPane, SwingUtilities

from sml_beans import _ascii, _log_once


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
            except Exception as exc:
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
                except Exception as exc:
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
            except Exception as exc:
                _log_once("mqtt_signalhead: cannot read button-strip component %s: %s" % (_ascii(c), _ascii(exc)))
        return False

    def _add_toggle_button(self, attempt=0):
        """PanelPro main-window strip — kept in addition to the LE Signals lamp."""
        max_attempts = 12
        delay_ms = 500

        def _try_attach():
            try:
                from apps import Apps

                space = Apps.buttonSpace()
                if space is None:
                    raise RuntimeError("Apps.buttonSpace() is None")
                if self._button_on_strip(space):  # already there (a retry)
                    space.revalidate()
                    space.repaint()
                    return True
                if self._button is None:
                    self._button = JButton("SML Disabled")
                    self._button.addActionListener(lambda e: self._on_toggle())
                space.add(self._button)
                space.revalidate()
                space.repaint()
                print("mqtt_signalhead: SML toggle on PanelPro button strip")
                return True
            except Exception as exc:
                print(
                    "mqtt_signalhead: buttonSpace attempt %d failed: %s"
                    % (attempt + 1, _ascii(exc))
                )
                return False

        class _Attach(Runnable):
            def run(_self):
                # Detached by a re-run (or quitting): leave the strip to the new one.
                if self._shutting_down:
                    return
                if _try_attach():
                    self._set_button_label()
                    return
                if attempt + 1 >= max_attempts:
                    print(
                        "mqtt_signalhead: giving up on main-window SML button "
                        "(panel Signals lamp still works)"
                    )
                    return
                self._add_toggle_button(attempt + 1)

        if attempt == 0 and self._button is None:
            self._button = JButton("SML Disabled")
            self._button.addActionListener(lambda e: self._on_toggle())

        if attempt == 0:
            SwingUtilities.invokeLater(_Attach())
        else:

            class _Retry(Runnable):
                def run(_self):
                    Thread.sleep(delay_ms)
                    if not self._shutting_down:
                        SwingUtilities.invokeLater(_Attach())

            Thread(_Retry(), "mqtt-sml-button").start()

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
                except Exception as exc:
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
        except Exception as exc:
            print("mqtt_signalhead: override dialog failed: " + _ascii(exc))
            return False
        return holder[0] == JOptionPane.YES_OPTION
