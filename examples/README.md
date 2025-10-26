# Examples

These scripts demonstrate logging in, listing devices, and controlling your FanSync fan/light via the cloud.

## Prerequisites

- Create `credentials.py` in the project root from the template:

```
cp examples/credentials.example.py credentials.py
# Edit credentials.py and set EMAIL and PASSWORD
```

- Use the project virtualenv (recommended):

```
source venv/bin/activate
```

## Running examples

From the project root, add the project root to PYTHONPATH so Python can import the top-level `fansync` package and your local `credentials.py`:

```
PYTHONPATH=$(pwd) venv/bin/python examples/test_connection.py
```

Turn off the fan:

```
PYTHONPATH=$(pwd) venv/bin/python examples/turn_off_fan.py
```

Other examples:
- `examples/turn_on_fan.py`
- `examples/set_fan_speed.py`
- `examples/set_fan_direction.py`
- `examples/set_fan_mode.py`
- `examples/set_fan_state.py`

## Notes

- Avoid committing real credentials; `credentials.py` is git-ignored.
- The examples use blocking I/O and are intended for manual use and experimentation.


