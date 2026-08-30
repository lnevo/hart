# Script REF_SCRIPT_7 — REF_SCRIPT_6 -> REF_SCRIPT_7
# Changes from REF_SCRIPT_6:
# 1) Adds standard deviation (rounded to 1 decimal) of the rolling readings and displays
#    it under the Rolling Median label in the right pane.
# 2) Left-aligns the text in the right pane so it lines up with the vertical split divider.
# No other behavior was changed.
# Using 99.4 instead of 99.0 to better align with Digitrax throttle settings

import time
import threading
import math
import jmri
from java.awt import Font, BorderLayout, FlowLayout, Dimension, Component
from java.awt.event import WindowAdapter, ComponentAdapter, MouseAdapter, ActionListener
from javax.swing import (JFrame, JPanel, JLabel, JButton, JTextField, SwingUtilities,
                         Box, BoxLayout, JSplitPane, JComboBox, BorderFactory, Timer)
from java.beans import PropertyChangeListener

# =========================
# Configuration
# =========================
sensor_names = ["LS1","LS2","LS3","LS4","LS5","LS6","LS7","LS8","LS9","LS10","LS11","LS12"]
pieces_total = 24
pieces_per_sensor = 2
radius_inch = 19.0

average_count = 7
RAW_MAX = 127
VSTEP_MAX = 28      
DEBOUNCE_SEC = 0.06
THROTTLE_HOLD_INTERVAL_MS = 100   # repeat when holding
HOLD_THRESHOLD_MS = 300           # delay before repeating starts

# =========================
# Runtime state
# =========================
paused = False
running = True

last_speeds = []
last_sensor_full_index = None
last_sensor_time = None
state_lock = threading.RLock()

sm = None
try:
    sm = jmri.InstanceManager.getDefault(jmri.SensorManager)
except Exception:
    sm = None

Sensors = [None] * len(sensor_names)
LowSpeedArray = []
MediumSpeedArray = []
HighSpeedArray = []
MaxSpeedArray = []

_throttle_obj = None
_throttle_prop_listener = None
_last_raw_speed = None
_last_raw_lock = threading.RLock()
_manual_raw = 0

_hold_timers = {'up': None, 'down': None}

# =========================
# Helper math & utils
# =========================

def raw_to_vstep(raw):
    try:
        return int(round(float(raw) * VSTEP_MAX / RAW_MAX))
    except Exception:
        return 0

def vstep_to_raw(vstep):
    try:
        v = int(vstep)
        v = max(0, min(VSTEP_MAX, v))
        return int(round(v * RAW_MAX / float(VSTEP_MAX)))
    except Exception:
        return 0

# --- Digitrax 0–99% mode conversion helpers (revised for smoother scaling) ---
def raw_to_percent_99(raw_val):
    ###
    #Convert raw throttle (0–127) to approximate 0–99% for Digitrax.
    #Uses linear mapping with rounding to nearest whole percent.
    ###
    try:
        pct = int(round(float(raw_val) * 99.4 / RAW_MAX))
        return max(0, min(99, pct))
    except Exception:
        return 0

def percent_99_to_raw(pct_val):
    ###
    #Convert Digitrax-style percent (0–99) back to raw throttle (0–127).
    #Uses same linear scaling as raw_to_percent_99() to ensure consistent stepping.
    ###
    try:
        raw = int(round(float(pct_val) * RAW_MAX / 99.4))
        return max(0, min(RAW_MAX, raw))
    except Exception:
        return 0


def calculate_speed_nscale_mph(distance_ft, elapsed_sec):
    if elapsed_sec <= 0:
        return 0.0
    real_mph = (distance_ft / elapsed_sec) * 0.681818
    return real_mph * 160.0

def calc_median(values):
    n = len(values)
    if n == 0:
        return 0.0
    s = sorted(values)
    mid = n // 2
    return s[mid] if n % 2 == 1 else (s[mid - 1] + s[mid]) / 2.0

# =========================
# Initialize sensors & arrays
# =========================

def init_sensors_and_arrays():
    global Sensors, LowSpeedArray, MediumSpeedArray, HighSpeedArray, MaxSpeedArray, sm
    if sm is None:
        try:
            sm = jmri.InstanceManager.getDefault(jmri.SensorManager)
        except Exception:
            sm = None
    if sm is None:
        print "SensorManager not found; sensors will be unavailable."
        return
    for i, name in enumerate(sensor_names):
        try:
            sk = sm.getSensor(name)
        except Exception:
            sk = None
        Sensors[i] = sk
        if sk is None:
            print "Sensor not found:", name
    MaxSpeedArray = [Sensors[0], Sensors[4], Sensors[8]]
    HighSpeedArray = [Sensors[0], Sensors[3], Sensors[6], Sensors[9]]
    MediumSpeedArray = [Sensors[i] for i in (0,2,4,6,8,10)]
    LowSpeedArray = list(Sensors)
    globals()['MaxSpeedArray'] = MaxSpeedArray
    globals()['HighSpeedArray'] = HighSpeedArray
    globals()['MediumSpeedArray'] = MediumSpeedArray
    globals()['LowSpeedArray'] = LowSpeedArray

init_sensors_and_arrays()

# =========================
# GUI
# =========================
frame = JFrame("Measure Speeds Manually — STRR_Speed_Measure_Script_v1.0")
frame.setDefaultCloseOperation(JFrame.DISPOSE_ON_CLOSE)

class MyWindowAdapter(WindowAdapter):
    def windowClosing(self, evt):
        global running
        running = False
        try:
            remove_throttle_listener_and_release()
        except Exception:
            pass
        try:
            remove_all_listeners()
        except Exception:
            pass

frame.addWindowListener(MyWindowAdapter())

main_panel = JPanel(BorderLayout())

# Right panel (readouts)
right_panel = JPanel()
right_panel.setLayout(BoxLayout(right_panel, BoxLayout.Y_AXIS))
right_panel.setBorder(BorderFactory.createEmptyBorder(12,12,12,12))

lbl_current_speed = JLabel("Current Speed: --- scale MPH", JLabel.LEFT)
lbl_avg_speed = JLabel("Rolling Average: --- scale MPH", JLabel.LEFT)
lbl_median_speed = JLabel("Rolling Median: --- scale MPH", JLabel.LEFT)
lbl_stddev = JLabel("Std Dev: ---    (lower is better)", JLabel.LEFT)  # NEW
lbl_current_speed.setFont(Font("SansSerif", Font.PLAIN, 18))
lbl_avg_speed.setFont(Font("SansSerif", Font.PLAIN, 16))
lbl_median_speed.setFont(Font("SansSerif", Font.PLAIN, 16))
lbl_stddev.setFont(Font("SansSerif", Font.PLAIN, 16))

# Left-align labels inside the BoxLayout column so they line up with the split divider
for lbl in (lbl_current_speed, lbl_avg_speed, lbl_median_speed, lbl_stddev):
    try:
        lbl.setHorizontalAlignment(JLabel.LEFT)
        lbl.setAlignmentX(Component.LEFT_ALIGNMENT)
    except Exception:
        pass

lbl_raw = JLabel("raw: 0", JLabel.LEFT)
lbl_step = JLabel("Step: 0", JLabel.LEFT)
lbl_percent = JLabel("Throttle: 0%", JLabel.LEFT)
info_font = Font("SansSerif", Font.PLAIN, 15)
lbl_raw.setFont(info_font)
lbl_step.setFont(info_font)
lbl_percent.setFont(info_font)

right_panel.add(lbl_current_speed)
right_panel.add(Box.createRigidArea(Dimension(0,18)))
right_panel.add(lbl_avg_speed)
right_panel.add(Box.createRigidArea(Dimension(0,18)))
right_panel.add(lbl_median_speed)
right_panel.add(Box.createRigidArea(Dimension(0,8)))
right_panel.add(lbl_stddev)  # NEW placement: under median and above raw/step
right_panel.add(Box.createRigidArea(Dimension(0,16)))

info_row = JPanel(FlowLayout(FlowLayout.LEFT))
# Make the info_row left-aligned and its labels left too
try:
    info_row.setAlignmentX(Component.LEFT_ALIGNMENT)
except Exception:
    pass

lbl_array = JLabel("Array: ---", JLabel.LEFT)
lbl_array.setFont(info_font)
try:
    lbl_raw.setHorizontalAlignment(JLabel.LEFT)
    lbl_raw.setAlignmentX(Component.LEFT_ALIGNMENT)
    lbl_step.setHorizontalAlignment(JLabel.LEFT)
    lbl_step.setAlignmentX(Component.LEFT_ALIGNMENT)
    lbl_percent.setHorizontalAlignment(JLabel.LEFT)
    lbl_percent.setAlignmentX(Component.LEFT_ALIGNMENT)
    lbl_array.setHorizontalAlignment(JLabel.LEFT)
    lbl_array.setAlignmentX(Component.LEFT_ALIGNMENT)
except Exception:
    pass

info_row.add(lbl_raw)
info_row.add(Box.createRigidArea(Dimension(6,0)))
info_row.add(lbl_step)
info_row.add(Box.createRigidArea(Dimension(6,0)))
info_row.add(lbl_percent)
info_row.add(Box.createRigidArea(Dimension(6,0)))
info_row.add(lbl_array)
info_row.add(Box.createRigidArea(Dimension(6,0)))

right_panel.add(info_row)
right_panel.add(Box.createVerticalGlue())

# Left panel (controls)
left_panel = JPanel()
left_panel.setLayout(BoxLayout(left_panel, BoxLayout.Y_AXIS))
left_panel.setBorder(BorderFactory.createEmptyBorder(12,12,12,12))

def set_big_font(component, size=15):
    try:
        component.setFont(Font("SansSerif", Font.PLAIN, size))
    except Exception:
        pass

# Group 1: DCC + Start/Stop
group1 = JPanel(FlowLayout(FlowLayout.LEFT))
group1.add(JLabel("DCC Address:"))
txt_dccaddress = JTextField("", 4)
set_big_font(txt_dccaddress, 15)
group1.add(txt_dccaddress)
btn_start = JButton("Start / Acquire")
btn_stop = JButton("Stop / Release")
set_big_font(btn_start, 15)
set_big_font(btn_stop, 15)
group1.add(btn_start)
group1.add(btn_stop)
left_panel.add(group1)
left_panel.add(Box.createRigidArea(Dimension(0,10)))

# Group 2: Throttle mode + Up/Down + throttle box
group2 = JPanel(FlowLayout(FlowLayout.LEFT))
group2.add(JLabel("Throttle mode:"))
cmb_throttle_mode = JComboBox()
cmb_throttle_mode.addItem("128-step (default) ")
cmb_throttle_mode.addItem("28-step")
cmb_throttle_mode.addItem("Percent 0-99%")

set_big_font(cmb_throttle_mode, 15)
group2.add(cmb_throttle_mode)

btn_throttle_down = JButton("Throttle -")
btn_throttle_up = JButton("Throttle +")
set_big_font(btn_throttle_down, 15)
set_big_font(btn_throttle_up, 15)
group2.add(btn_throttle_down)
group2.add(btn_throttle_up)

# Throttle textbox — show 3 digits only
txt_throttle_box = JTextField(str(_manual_raw), 3)
txt_throttle_box.setMaximumSize(Dimension(48, 26))  # small width so only ~3 digits fit
set_big_font(txt_throttle_box, 15)
lbl_throttle_box = JLabel("Throttle:")
set_big_font(lbl_throttle_box, 15)

group2.add(Box.createRigidArea(Dimension(8,0)))
group2.add(lbl_throttle_box)
group2.add(txt_throttle_box)

left_panel.add(group2)
left_panel.add(Box.createRigidArea(Dimension(0,10)))

# Group 3: Tools
group3 = JPanel(FlowLayout(FlowLayout.LEFT))
lbl_tools = JLabel("Tools:")
set_big_font(lbl_tools, 15)
group3.add(lbl_tools)
btn_pause = JButton("Pause Readings")
btn_reset = JButton("Reset All Blocks")
set_big_font(btn_pause, 15)
set_big_font(btn_reset, 15)
group3.add(btn_pause)
group3.add(btn_reset)
group3.add(JLabel(" # entries:"))
txt_average = JTextField(str(average_count), 3)
set_big_font(txt_average, 15)
group3.add(txt_average)
left_panel.add(group3)
left_panel.add(Box.createRigidArea(Dimension(0,10)))

# Group 4: Status
group4 = JPanel(FlowLayout(FlowLayout.LEFT))
status_label = JLabel("Status: Idle")
set_big_font(status_label, 15)
group4.add(status_label)
left_panel.add(group4)
left_panel.add(Box.createVerticalGlue())

split = JSplitPane(JSplitPane.HORIZONTAL_SPLIT, left_panel, right_panel)
split.setResizeWeight(0.38)
main_panel.add(split, BorderLayout.CENTER)
frame.getContentPane().add(main_panel)

# =========================
# Throttle property listener classes
# =========================
class ThrottlePropertyListener(PropertyChangeListener):
    def propertyChange(self, evt):
        global _last_raw_speed
        try:
            new = evt.getNewValue()
        except Exception:
            new = None
        if new is None:
            return
        try:
            # integer raw
            if isinstance(new, (int, long)):
                with _last_raw_lock:
                    _last_raw_speed = int(max(0, min(RAW_MAX, int(new))))
                return
        except Exception:
            pass
        try:
            v = float(new)
            if 0.0 <= v <= 1.0:
                r = int(round(v * RAW_MAX))
            elif 0.0 <= v <= 99.4:
                r = int(round(v * RAW_MAX / 99.4))
            else:
                r = int(round(v))
            with _last_raw_lock:
                _last_raw_speed = max(0, min(RAW_MAX, r))
        except Exception:
            pass

class MyThrottleListener(jmri.ThrottleListener):
    def __init__(self):
        pass
    def notifyThrottleFound(self, throttle):
        global _throttle_obj, _throttle_prop_listener
        _throttle_obj = throttle
        try:
            listener = ThrottlePropertyListener()
            throttle.addPropertyChangeListener(listener)
            _throttle_prop_listener = listener
            seed_raw_from_throttle(throttle)
            print "notifyThrottleFound: throttle attached."
        except Exception as e:
            print "notifyThrottleFound: could not attach property listener:", e
            _throttle_prop_listener = None
    def notifyFailedThrottleRequest(self, addr, reason):
        print "notifyFailedThrottleRequest: address", addr, "reason:", reason
    def notifyDecisionRequired(self, address, question):
        print "notifyDecisionRequired: address", address, "question:", question
    def notifyThrottleDisposed(self):
        global _throttle_obj
        _throttle_obj = None
        print "notifyThrottleDisposed"

# =========================
# seed raw / remove / release
# =========================

def seed_raw_from_throttle(throttle):
    global _last_raw_speed
    try:
        v = None
        try:
            v = throttle.getSpeed()
        except Exception:
            v = None
        if v is None:
            try:
                v = throttle.getSpeedSetting()
            except Exception:
                v = None
        if v is None:
            try:
                pct = throttle.getPercent()
                if pct is not None:
                    v = int(round(float(pct) * RAW_MAX / 99.4))
            except Exception:
                v = None
        if v is not None:
            with _last_raw_lock:
                _last_raw_speed = int(round(float(v)))
    except Exception:
        pass

def remove_throttle_listener_and_release():
    global _throttle_obj, _throttle_prop_listener, _manual_raw
    try:
        if _throttle_obj is not None:
            # bring loco to stop first
            try:
                _throttle_obj.setSpeedSetting(0.0)
            except Exception:
                try:
                    _throttle_obj.setSpeed(0)
                except Exception:
                    pass
            # remove property listener
            try:
                if _throttle_prop_listener is not None:
                    _throttle_obj.removePropertyChangeListener(_throttle_prop_listener)
            except Exception:
                pass
            # release throttle
            try:
                _throttle_obj.release(None)
            except Exception:
                pass
    except Exception:
        pass
    _throttle_prop_listener = None
    _throttle_obj = None
    with _last_raw_lock:
        _manual_raw = 0
    try:
        # update textbox according to mode
        sel = cmb_throttle_mode.getSelectedIndex()
        if sel == 1:
            txt_throttle_box.setText(str(raw_to_vstep(_manual_raw)))
        elif sel == 2:
            txt_throttle_box.setText(str(raw_to_percent_99(_manual_raw)))
        else:
            txt_throttle_box.setText(str(_manual_raw))
    except Exception:
        pass
    print "Throttle released (if supported)."

# =========================
# Throttle acquisition (blocking + async fallback)
# =========================

def acquire_throttle_blocking(addr, timeout=10.0):
    global _throttle_obj, _throttle_prop_listener
    tm = None
    try:
        tm = jmri.InstanceManager.getDefault(jmri.ThrottleManager)
    except Exception:
        tm = None
    if tm is None:
        print "No ThrottleManager available."
        return False

    # Try blocking getThrottle(addr, isLong, wait)
    try:
        t = tm.getThrottle(int(addr), True, True)
        if t is not None:
            _throttle_obj = t
            try:
                listener = ThrottlePropertyListener()
                t.addPropertyChangeListener(listener)
                _throttle_prop_listener = listener
                seed_raw_from_throttle(t)
            except Exception:
                pass
            print "Blocking getThrottle succeeded (3-arg)."
            return True
    except Exception:
        pass

    # Try getThrottle(addr, isLong)
    try:
        t = tm.getThrottle(int(addr), True)
        if t is not None:
            _throttle_obj = t
            try:
                listener = ThrottlePropertyListener()
                t.addPropertyChangeListener(listener)
                _throttle_prop_listener = listener
                seed_raw_from_throttle(t)
            except Exception:
                pass
            print "Blocking getThrottle succeeded (2-arg)."
            return True
    except Exception:
        pass

    # Fallback to async requestThrottle
    try:
        listener = MyThrottleListener()
        ok = tm.requestThrottle(int(addr), True, listener, True)
        print "requestThrottle called; returned:", ok
    except Exception:
        try:
            listener = MyThrottleListener()
            ok = tm.requestThrottle(int(addr), listener)
            print "requestThrottle (fallback) called; returned:", ok
        except Exception as e:
            print "requestThrottle failed:", e
            return False

    start = time.time()
    while time.time() - start < timeout:
        with _last_raw_lock:
            if _throttle_obj is not None:
                return True
        time.sleep(0.1)
    print "Timeout waiting for throttle for addr", addr
    return False

def acquire_throttle_from_gui():
    addr_text = txt_dccaddress.getText().strip()
    if not addr_text:
        print "No address entered."
        return False
    try:
        addr = int(addr_text)
    except Exception:
        print "Invalid DCC address:", addr_text
        return False
    return acquire_throttle_blocking(addr, timeout=10.0)

# =========================
# Sensor listeners management
# =========================
sensor_listener_pairs = []

class SensorListener(PropertyChangeListener):
    def __init__(self, idx):
        self.idx = idx
    def propertyChange(self, evt):
        try:
            sensor_changed(evt, self.idx)
        except Exception:
            pass

def attach_listeners_to_all_sensors():
    global sensor_listener_pairs
    if sm is None:
        return
    remove_all_listeners()
    for i, sk in enumerate(Sensors):
        if sk is None:
            continue
        try:
            listener = SensorListener(i)
            sk.addPropertyChangeListener(listener)
            sensor_listener_pairs.append((sk, listener))
        except Exception as e:
            print "Could not attach listener to sensor", sensor_names[i], ":", e

def remove_all_listeners():
    global sensor_listener_pairs
    for sk, listener in tuple(sensor_listener_pairs):
        try:
            sk.removePropertyChangeListener(listener)
        except Exception:
            pass
    sensor_listener_pairs[:] = []

attach_listeners_to_all_sensors()

# =========================
# Sensor helpers & handler
# =========================
def sensor_obj_to_full_index(sensor_obj):
    if sensor_obj is None:
        return None
    for i, sk in enumerate(Sensors):
        try:
            if sk is sensor_obj:
                return i
            if sk is not None and sensor_obj is not None and sk.getSystemName() == sensor_obj.getSystemName():
                return i
        except Exception:
            pass
    return None

def full_index_distance_ft(prev_full_idx, curr_full_idx):
    if prev_full_idx is None:
        return 0.0
    n = len(sensor_names)
    if n <= 0:
        return 0.0
    delta = (curr_full_idx - prev_full_idx) % n
    if delta == 0:
        return 0.0
    total_pieces = delta * pieces_per_sensor
    angle_per_piece = 360.0 / float(pieces_total)
    arc_length_inch = 2 * 3.141592653589793 * radius_inch * (angle_per_piece * total_pieces / 360.0)
    return arc_length_inch / 12.0

def choose_array_for_vstep(step28):
    if 0 <= step28 <= 12:
        return LowSpeedArray, "Low"
    if 13 <= step28 <= 21:
        return MediumSpeedArray, "Medium"
    if 22 <= step28 <= 25:
        return HighSpeedArray, "High"
    return MaxSpeedArray, "Max"

def get_throttle_raw_and_vstep():
    global _last_raw_speed
    raw = None
    with _last_raw_lock:
        if _last_raw_speed is not None:
            raw = int(_last_raw_speed)
    if raw is None and _throttle_obj is not None:
        try:
            v = None
            try:
                v = _throttle_obj.getSpeed()
            except Exception:
                v = None
            if v is None:
                try:
                    v = _throttle_obj.getSpeedSetting()
                except Exception:
                    v = None
            if v is None:
                try:
                    pct = _throttle_obj.getPercent()
                    if pct is not None:
                        v = int(round(float(pct) * RAW_MAX / 99.4))
                except Exception:
                    v = None
            if v is not None:
                raw = int(round(float(v)))
        except Exception:
            raw = None
    if raw is None:
        raw = _manual_raw
    raw = max(0, min(RAW_MAX, int(raw)))
    vstep = raw_to_vstep(raw)
    return raw, vstep

def sensor_in_array(idx, arr):
    if arr is None or len(arr) == 0:
        return False
    target = Sensors[idx]
    for s in arr:
        try:
            if s is target:
                return True
            if s is not None and target is not None and s.getSystemName() == target.getSystemName():
                return True
        except Exception:
            pass
    return False

def sensor_changed(event, sensor_full_index):
    global paused, last_sensor_full_index, last_sensor_time, last_speeds
    if paused or not running:
        return
    with _last_raw_lock:
        have_raw = (_last_raw_speed is not None) or (_manual_raw is not None)
    if _throttle_obj is None and not have_raw:
        return
    try:
        sensor = event.getSource()
    except Exception:
        return
    try:
        state = sensor.getKnownState()
    except Exception:
        try:
            state = sensor.getState()
        except Exception:
            state = None
    if state != jmri.Sensor.ACTIVE:
        return
    current_time = time.time()
    raw, vstep = get_throttle_raw_and_vstep()
    chosen_array, arr_name = choose_array_for_vstep(vstep)
    curr_idx = sensor_full_index
    prev_idx = last_sensor_full_index
    if prev_idx is None:
        last_sensor_full_index = curr_idx
        last_sensor_time = current_time
        def init_update():
            try:
                pct = raw_to_percent_99(raw)
                lbl_raw.setText("raw: %d" % raw)
                lbl_step.setText("Step: %d" % vstep)
                lbl_percent.setText("Throttle: %d%%" % pct)
            except Exception:
                pass
        SwingUtilities.invokeLater(init_update)
        return
    if not sensor_in_array(curr_idx, chosen_array):
        last_sensor_full_index = curr_idx
        last_sensor_time = current_time
        return
    distance_ft = full_index_distance_ft(prev_idx, curr_idx)
    elapsed = current_time - last_sensor_time if last_sensor_time is not None else 0.0
    if elapsed <= 0.0001 or distance_ft <= 0.0:
        last_sensor_full_index = curr_idx
        last_sensor_time = current_time
        return
    speed_mph = calculate_speed_nscale_mph(distance_ft, elapsed)
    with state_lock:
        last_speeds.append(speed_mph)
        if len(last_speeds) > average_count:
            last_speeds.pop(0)
        avg_speed = sum(last_speeds) / len(last_speeds) if last_speeds else 0.0
        median_speed = calc_median(last_speeds)
        # compute standard deviation (population) of the readings used for rolling average/median
        stddev = 0.0
        try:
            if len(last_speeds) > 0:
                mean = avg_speed
                var = sum((x - mean) ** 2 for x in last_speeds) / float(len(last_speeds))
                stddev = math.sqrt(var)
        except Exception:
            stddev = 0.0
        last_sensor_full_index = curr_idx
        last_sensor_time = current_time
    def do_update():
        try:
            pct = raw_to_percent_99(raw)
            lbl_current_speed.setText("Current Speed: %.1f scale MPH" % (speed_mph,))
            lbl_avg_speed.setText("Rolling Average (last %d): %.1f scale MPH" % (average_count, avg_speed))
            lbl_median_speed.setText("Rolling Median (last %d): %.1f scale MPH" % (average_count, median_speed))
            # show std dev rounded to 1 decimal
            lbl_stddev.setText("Std Dev: %.1f" % (round(stddev, 1),))
            lbl_raw.setText("raw: %d" % raw)
            lbl_step.setText("Step: %d" % vstep)
            lbl_percent.setText("Throttle: %d%%" % pct)
            lbl_array.setText("Array: %s" % arr_name)
        except Exception:
            pass
    SwingUtilities.invokeLater(do_update)
    print "Raw %d, Step %d, Throttle %d%% | Array %s | Current: %.1f | Avg: %.1f | Median: %.1f (%d readings)" % (raw, vstep, raw_to_percent_99(raw), arr_name, speed_mph, avg_speed, median_speed, len(last_speeds))" % (raw, vstep, arr_name, speed_mph, avg_speed, median_speed, len(last_speeds))

# =========================
# Manual throttle controls (apply to GUI + throttle if present)
# =========================

def apply_manual_raw(raw):
    global _manual_raw
    raw = max(0, min(RAW_MAX, int(raw)))
    _manual_raw = raw
    vstep = raw_to_vstep(raw)
    try:
        lbl_raw.setText("raw: %d" % raw)
        lbl_step.setText("Step: %d" % vstep)
        # update textbox according to selected mode
        sel = cmb_throttle_mode.getSelectedIndex()
        if sel == 1:
            txt_throttle_box.setText(str(vstep))
        elif sel == 2:
            txt_throttle_box.setText(str(raw_to_percent_99(_manual_raw)))
        else:
            txt_throttle_box.setText(str(raw))
    except Exception:
        pass
    if _throttle_obj is not None:
        try:
            _throttle_obj.setSpeedSetting(float(raw) / RAW_MAX)
        except Exception:
            try:
                _throttle_obj.setSpeed(int(raw))
            except Exception:
                pass

def on_throttle_box_enter(evt=None):
    try:
        text = txt_throttle_box.getText().strip()
        sel = cmb_throttle_mode.getSelectedIndex()
        if sel == 1:
            # 28-step mode: expect 0..VSTEP_MAX
            v = int(text)
            if v < 0 or v > VSTEP_MAX:
                status_label.setText("Invalid step (0-%d)" % VSTEP_MAX)
                return
            raw = vstep_to_raw(v)
            apply_manual_raw(raw)
        elif sel == 2:
            # Digitrax Percent mode: expect 0..99
            v = int(text)
            if v < 0 or v > 99:
                status_label.setText("Invalid percent (0-99)")
                return
            raw = percent_99_to_raw(v)
            apply_manual_raw(raw)
        else:
            # 128-step mode: expect 0..RAW_MAX
            v = int(text)
            if v < 0 or v > RAW_MAX:
                status_label.setText("Invalid raw (0-%d)" % RAW_MAX)
                return
            apply_manual_raw(v)
        # clear any status message
        try:
            status_label.setText("Status: Idle")
        except Exception:
            pass
    except Exception:
        try:
            status_label.setText("Invalid input")
        except Exception:
            pass

# =========================
# Click-and-hold throttle behavior (mode-aware: 128-step raw, 28-step vstep, 0-99 percent)
# =========================
class PyActionListener(ActionListener):
    def __init__(self, fn):
        self.fn = fn
    def actionPerformed(self, evt):
        try:
            self.fn()
        except Exception:
            pass

def click_increment(which):
    """Single-click increment/decrement respecting selected throttle mode."""
    global _manual_raw
    sel = cmb_throttle_mode.getSelectedIndex()
    if sel == 1:
        # 28-step mode
        curr_vstep = raw_to_vstep(_manual_raw)
        new_vstep = curr_vstep + (1 if which == 'up' else -1)
        new_vstep = max(0, min(VSTEP_MAX, new_vstep))
        apply_manual_raw(vstep_to_raw(new_vstep))
    elif sel == 2:
        # Digitrax percent 0..99
        curr_pct = raw_to_percent_99(_manual_raw)
        new_pct = curr_pct + (1 if which == 'up' else -1)
        new_pct = max(0, min(99, new_pct))
        apply_manual_raw(percent_99_to_raw(new_pct))
    else:
        # 128-step raw
        apply_manual_raw(min(RAW_MAX, _manual_raw + 1) if which == 'up' else max(0, _manual_raw - 1))

def hold_step_function(which):
    """Return a function suitable for repeated Timer calls during hold, respecting mode."""
    def fn():
        sel = cmb_throttle_mode.getSelectedIndex()
        if sel == 1:
            # 28-step: increment vstep by 1 each tick
            curr_vstep = raw_to_vstep(_manual_raw)
            new_vstep = curr_vstep + (1 if which == 'up' else -1)
            new_vstep = max(0, min(VSTEP_MAX, new_vstep))
            apply_manual_raw(vstep_to_raw(new_vstep))
        elif sel == 2:
            # Digitrax percent: increment percent by 1 each tick
            curr_pct = raw_to_percent_99(_manual_raw)
            new_pct = curr_pct + (1 if which == 'up' else -1)
            new_pct = max(0, min(99, new_pct))
            apply_manual_raw(percent_99_to_raw(new_pct))
        else:
            # 128-step raw
            new_raw = _manual_raw + (1 if which == 'up' else -1)
            new_raw = max(0, min(RAW_MAX, new_raw))
            apply_manual_raw(new_raw)
    return fn

def start_hold(which):
    stop_hold(which)
    fn = hold_step_function(which)
    t = Timer(THROTTLE_HOLD_INTERVAL_MS, PyActionListener(fn))
    t.setRepeats(True)
    t.start()
    _hold_timers[which] = t

def stop_hold(which):
    t = _hold_timers.get(which)
    if t is not None:
        try:
            t.stop()
        except Exception:
            pass
        _hold_timers[which] = None

class HoldMouseAdapter(MouseAdapter):
    def __init__(self, which):
        self.which = which
        self.hold_timer = None
        self.is_holding = False

    def mousePressed(self, evt):
        self.is_holding = False
        # Immediate single click behavior (mode-aware)
        try:
            click_increment(self.which)
        except Exception:
            pass

        # Start repeating hold after threshold
        def start_repeating():
            self.is_holding = True
            start_hold(self.which)

        try:
            self.hold_timer = Timer(HOLD_THRESHOLD_MS, PyActionListener(start_repeating))
            self.hold_timer.setRepeats(False)
            self.hold_timer.start()
        except Exception:
            self.hold_timer = None

    def mouseReleased(self, evt):
        try:
            if self.hold_timer is not None:
                self.hold_timer.stop()
                self.hold_timer = None
        except Exception:
            pass
        if self.is_holding:
            stop_hold(self.which)

# Attach MouseAdapters
btn_throttle_up.addMouseListener(HoldMouseAdapter('up'))
btn_throttle_down.addMouseListener(HoldMouseAdapter('down'))

# Throttle textbox action wiring
try:
    txt_throttle_box.addActionListener(PyActionListener(on_throttle_box_enter))
except Exception:
    pass

# =========================
# Mode change handling: update textbox display & tooltip
# =========================
def on_throttle_mode_changed(evt=None):
    try:
        sel = cmb_throttle_mode.getSelectedIndex()
        if sel == 1:
            # 28-step: show step value
            txt_throttle_box.setText(str(raw_to_vstep(_manual_raw)))
            txt_throttle_box.setToolTipText("Enter step 0-%d" % VSTEP_MAX)
        elif sel == 2:
            # Digitrax percent 0..99
            txt_throttle_box.setText(str(raw_to_percent_99(_manual_raw)))
            txt_throttle_box.setToolTipText("Enter percent 0-99")
        else:
            # 128-step raw
            txt_throttle_box.setText(str(_manual_raw))
            txt_throttle_box.setToolTipText("Enter raw 0-%d" % RAW_MAX)
    except Exception:
        pass

try:
    cmb_throttle_mode.addActionListener(PyActionListener(on_throttle_mode_changed))
except Exception:
    pass

# initialize textbox to current mode
on_throttle_mode_changed()

# =========================
# GUI handlers: start/stop/reset/pause/average/manual
# =========================
def on_start(evt=None):
    def acquire_thread():
        def set_status(text):
            try:
                status_label.setText(text)
            except Exception:
                pass
        set_status("Status: Getting throttle")
        ok = acquire_throttle_from_gui()
        if ok:
            def after_ok():
                status_label.setText("Status: Throttle acquired")
                with _last_raw_lock:
                    if _last_raw_speed is not None:
                        apply_manual_raw(int(_last_raw_speed))
                    else:
                        apply_manual_raw(_manual_raw)
            SwingUtilities.invokeLater(after_ok)
        else:
            def after_fail():
                status_label.setText("Status: Could not acquire throttle")
            SwingUtilities.invokeLater(after_fail)
    threading.Thread(target=acquire_thread).start()

def on_stop(evt=None):
    try:
        if _throttle_obj is not None:
            try:
                _throttle_obj.setSpeedSetting(0.0)
            except Exception:
                try:
                    _throttle_obj.setSpeed(0)
                except Exception:
                    pass
    except Exception:
        pass
    remove_throttle_listener_and_release()
    try:
        status_label.setText("Status: Throttle released")
    except Exception:
        pass

def on_reset(evt=None):
    global last_speeds, last_sensor_full_index, last_sensor_time
    with state_lock:
        last_speeds = []
        last_sensor_full_index = None
        last_sensor_time = None
    try:
        lbl_current_speed.setText("Current Speed: --- scale MPH")
        lbl_avg_speed.setText("Rolling Average: --- scale MPH")
        lbl_median_speed.setText("Rolling Median: --- scale MPH")
        lbl_stddev.setText("Std Deviation: ---")
    except Exception:
        pass
    print "Reset pressed"

def on_pause(evt=None):
    global paused
    paused = not paused
    try:
        btn_pause.setText("Resume Readings" if paused else "Pause Readings")
    except Exception:
        pass
    print "Pause toggled ->", paused

def on_average_changed(evt=None):
    global average_count
    try:
        v = int(txt_average.getText())
        if v > 0:
            average_count = v
    except Exception:
        pass

# Wire GUI handlers
try:
    txt_average.addActionListener(PyActionListener(on_average_changed))
except Exception:
    pass
try:
    btn_start.addActionListener(PyActionListener(on_start))
except Exception:
    pass
try:
    btn_stop.addActionListener(PyActionListener(on_stop))
except Exception:
    pass
try:
    btn_reset.addActionListener(PyActionListener(on_reset))
except Exception:
    pass
try:
    btn_pause.addActionListener(PyActionListener(on_pause))
except Exception:
    pass

# =========================
# Autoscale & show
# =========================
def compute_text_width_px(text, font, comp):
    try:
        fm = comp.getFontMetrics(font)
        return fm.stringWidth(text)
    except Exception:
        return int(len(text) * font.getSize() * 0.6)

def auto_position_divider():
    try:
        frame.pack()
        frame.setSize(950, 230)
        texts = [lbl_current_speed.getText(), lbl_avg_speed.getText(), lbl_median_speed.getText(), lbl_raw.getText()]
        fonts = [lbl_current_speed.getFont(), lbl_avg_speed.getFont(), lbl_median_speed.getFont(), lbl_raw.getFont()]
        comp_for_metrics = frame
        req_widths = []
        for t, f in zip(texts, fonts):
            try:
                w = compute_text_width_px(t, f, comp_for_metrics)
            except Exception:
                w = len(t) * f.getSize() * 6 / 10
            req_widths.append(w)
        req_width = max(req_widths) + 60
        min_left_w = 220
        total_w = frame.getWidth()
        if total_w - min_left_w < req_width:
            new_total_w = req_width + min_left_w
            frame.setSize(new_total_w, frame.getHeight())
            total_w = new_total_w
        desired_left_w = total_w - req_width
        if desired_left_w < min_left_w:
            desired_left_w = min_left_w
        try:
            split.setDividerLocation(desired_left_w)
        except Exception:
            pass
    except Exception:
        pass

def autoscale_right_labels_once():
    try:
        avail_w = right_panel.getWidth()
    except Exception:
        avail_w = 400
    for size in range(20, 11, -1):
        f = Font("SansSerif", Font.PLAIN, size)
        fits = True
        for lbl in (lbl_current_speed, lbl_avg_speed, lbl_median_speed):
            try:
                fm = frame.getFontMetrics(f)
                w = fm.stringWidth(lbl.getText())
            except Exception:
                w = int(len(lbl.getText()) * size * 0.6)
            if w > avail_w - 40:
                fits = False
                break
        if fits:
            for lbl in (lbl_current_speed, lbl_avg_speed, lbl_median_speed):
                lbl.setFont(Font("SansSerif", Font.PLAIN, size))
            break

class ResizeListener(ComponentAdapter):
    def componentResized(self, evt):
        try:
            autoscale_right_labels_once()
        except Exception:
            pass

frame.addComponentListener(ResizeListener())

# Final show
auto_position_divider()
autoscale_right_labels_once()
frame.setVisible(True)
