# Alias for older Mac Start Up entries — runs the HART standard MQTT retain paint.
import os

_script = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "apply_maintain_mqtt.py",
)
_f = open(_script, "r")
try:
    _src = _f.read()
finally:
    _f.close()
exec(compile(_src, _script, "exec"))
