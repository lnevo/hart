HART Digicon (CATS) on this Pi
==============================

Installed:
  /home/pi/JMRI/cats.jar          CATS 3.2 + MQTT load-safety overlay
  /home/pi/JMRI/designer.jar
  /home/pi/JMRI/cats.csh
  /home/pi/hart/cats/panels/HART_Master_CTC_hold.xml   <-- CATS CTC (HOLD_ONLY; SML)
  /home/pi/hart/cats/panels/HART_Master_ABS.xml        <-- CATS ABS (Digicon reference; SML owns LE)
  /home/pi/hart/cats/panels/HART_Master_ABS_hold.xml   <-- optional ABS HOLD_ONLY spectator
  /home/pi/hart/cats/panels/HART_Master.xml            <-- CTC geometry source

PanelPro vs CATS (same profile TCS_MQTT — sequential, never both):
  PanelPro  — edit/store JMRI tables, MQTT, Start Up. Then quit.
  CATS      — loads preference:tables.xml from the profile, then the Digicon XML.
  Never Store tables while CATS has a layout open (Rodney Black / cats-users).
  Desktop CATS icons refuse to start if PanelPro is still running.

Launch CATS (after quitting PanelPro):
  /home/pi/hart/launch_cats.sh
  # default panel = HART_Master_CTC_hold.xml

Desktop icons:
  CATS CTC -> HART_Master_CTC_hold.xml  (/home/pi/hart/launch_hart_master_desktop.sh)
  CATS ABS -> HART_Master_ABS.xml  (Digicon reference; SML owns LE)

Or with an explicit panel:
  /home/pi/hart/launch_cats.sh /home/pi/hart/cats/panels/HART_Master_CTC_hold.xml
  /home/pi/hart/launch_cats.sh /home/pi/hart/cats/panels/HART_Master_ABS.xml

Profile used: TCS_MQTT.3f32a166 (same as current PanelPro)

JMRI tables (routes, internal turnouts, etc.):
  Startup loads preference:tables.xml
  On this Pi, preference: → /home/pi/JMRI_UserFiles/  (NOT the profile folder)
  Live file: /home/pi/JMRI_UserFiles/tables.xml
  Repo mirror: jmri/layouts/hart/output/tables.xml
  Yard-ladder buttons need IO:AUTO:0201–0210 + IT:HART:YL:* in that file.
  Do not patch only ~/.jmri/TCS_MQTT.jmri/tables.xml — CATS will ignore it.

JMRI web home (STS link):
  SoR: cats/resources/jmri-web/  (Home.html + sts.html)
  Live: /home/pi/JMRI_UserFiles/web/servlet/home/Home.html
  STS = Shipper-driven Traffic Simulator → http://10.0.0.53:8980/sts/
  Install/refresh: /home/pi/hart/cats/scripts/install_jmri_web_override.sh
  Full pack sync from Mac (SSH): ./cats/scripts/sync_hart_package.sh --pi
  Windows: ./cats/scripts/sync_hart_package.sh --win  (SSH :2222; do not use Dropbox)

JMRI Start Up scripts (profile PerformScript):
  /home/pi/hart/jmri/layouts/hart/scripts/apply_maintain_mqtt.py
  /home/pi/hart/jmri/layouts/hart/scripts/sync_yard_ladder_buttons.py
  /home/pi/hart/jmri/scripts/mqtt_signalhead_publisher.py
  (unhold_signal_masts.py retired: Held belongs to CATS CTC — hold at
   load, unhold when a route is lined; masts boot Unheld anyway)
  (refreshed by sync_hart_package.sh --pi)
  One-shot SML Discover (PanelPro, then Store): discover_sml.py

Do NOT run PanelPro and CATS at the same time on this profile.
PanelPro AutoIdentify desktop icon launches PanelPro by itself (not autostarted at login).

Blank Swing windows (tables, System Console, WiThrottle, analog clock) on labwc:
  Java needs _JAVA_AWT_WM_NONREPARENTING=1 (set in launchers + ~/.config/labwc/environment).
  Layout Editor can still paint without it because it redraws on a timer.
Use **CATS CTC** as the live CTC Digicon (HOLD_ONLY; JMRI SML owns aspects).
**CATS ABS** is Digicon reference (own lamps). Layout Editor is SML. No HOLD_ONLY.
Without CATS, Unhold + SML = ABS.

TrainStat (optional yard/trainmaster client)
============================================

Installed:
  /home/pi/hart/trainstat/              TrainStat package
  /home/pi/hart/trainstat/hart_trainstat.xml   connects to localhost:54321
  (light theme: black text on white/gray — stock demo was white-on-black and
   goes invisible under GTK LAF on modern Pi Java)

Launch (CATS must already be running):
  /home/pi/hart/launch_trainstat.sh
  # or desktop icon: TrainStat
  # launcher forces MetalLookAndFeel so colors stay readable

In CATS: Network menu should show Start TrainStat Server checked
(panel includes <TRAINSTATLABEL /> which enables it on load).

If text is washed out again: Bindings → Colors / Fonts, or reload
hart_trainstat.xml (File → Load). Backup of old dark config:
hart_trainstat.xml.bak_dark_*
