HART Digicon (CATS) on this Pi
==============================

Installed:
  /home/pi/JMRI/cats.jar          CATS 3.2 + MQTT load-safety overlay
  /home/pi/JMRI/designer.jar
  /home/pi/JMRI/cats.csh
  /home/pi/hart/cats/panels/HART_Master.xml            <-- primary CTC Digicon
  /home/pi/hart/cats/panels/HART_Master_ABS.xml        <-- ABS / open house
  /home/pi/hart/cats/panels/HART_Master_ABS_hold.xml   <-- ABS-RO (signals hold; turnouts on)

PanelPro vs CATS (same profile TCS_MQTT — sequential, never both):
  PanelPro  — edit/store JMRI tables, MQTT, Start Up. Then quit.
  CATS      — loads preference:tables.xml from the profile, then the Digicon XML.
  Never Store tables while CATS has a layout open (Rodney Black / cats-users).
  Desktop CATS icons refuse to start if PanelPro is still running.

Launch CATS (after quitting PanelPro):
  /home/pi/hart/launch_cats.sh
  # default panel = HART_Master.xml

Desktop icons:
  CATS CTC     -> HART_Master.xml            (/home/pi/hart/launch_hart_master_desktop.sh)
  CATS ABS     -> HART_Master_ABS.xml        (/home/pi/hart/launch_hart_master_abs_desktop.sh)
  CATS ABS-RO  -> HART_Master_ABS_hold.xml   (/home/pi/hart/launch_hart_master_abs_hold_desktop.sh)

Or with an explicit panel:
  /home/pi/hart/launch_cats.sh /home/pi/hart/cats/panels/HART_Master.xml
  /home/pi/hart/launch_cats.sh /home/pi/hart/cats/panels/HART_Master_ABS.xml
  /home/pi/hart/launch_cats.sh /home/pi/hart/cats/panels/HART_Master_ABS_hold.xml

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
  (refreshed by sync_hart_package.sh --pi)

Do NOT run PanelPro and CATS at the same time on this profile.
PanelPro AutoIdentify desktop icon launches PanelPro by itself (not autostarted at login).

Blank Swing windows (tables, System Console, WiThrottle, analog clock) on labwc:
  Java needs _JAVA_AWT_WM_NONREPARENTING=1 (set in launchers + ~/.config/labwc/environment).
  Layout Editor can still paint without it because it redraws on a timer.
Use one Digicon as signal authority (CATS or CATS ABS).
CATS ABS-RO still throws turnouts / shows occupancy; signals are HOLD_ONLY
(paints from MQTT — does not drive Clear/Approach/Stop).

TrainStat (optional yard/trainmaster client)
============================================

Installed:
  /home/pi/hart/trainstat/              TrainStat package
  /home/pi/hart/trainstat/hart_trainstat.xml   connects to localhost:54321

Launch (CATS must already be running):
  /home/pi/hart/launch_trainstat.sh
  # or desktop icon: TrainStat

In CATS: Network menu should show Start TrainStat Server checked
(panel includes <TRAINSTATLABEL /> which enables it on load).
