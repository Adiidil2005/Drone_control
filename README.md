```

### 4. Fly from the browser (laptop)
1. Open `LAPTOP/web-ui/index.html`.
2. Paste the `wss://` link into the top box and click the refresh arrow.
3. Select `drone-1`, click **CONNECT**, then **ARM**.

| Key | Action |
|---|---|
| W / S | Pitch forward / back |
| A / D | Roll left / right |
| Q / E | Yaw left / right |
| Space / Shift | Throttle up / down |

## Safety Features
- **Throttle cap:** `THROTTLE_MAX_PWM = 1500` in `flight_bridge.py` limits power during testing.
- **Safe arming:** the drone arms only when throttle is near zero, and it never re-arms by itself.
- **Link-loss failsafe:** if no command arrives for 0.5 s, the drone switches to **LAND** mode.
- **Dry-run mode:** test the full pipeline without any hardware.

## Running the Tests
```bash
pip install pytest
python -m pytest -v
```
The tests run `flight_bridge.py` in dry-run mode, so no drone or Pixhawk is needed. The same tests run automatically on every push and pull request through GitHub Actions.

## Known Limitations
- The signaling server has **no authentication**. Anyone with the URL can register or connect, so don't share the ngrok link publicly.
- The free ngrok URL changes each time ngrok restarts.

## Deployment
The signaling server can be hosted on a PaaS such as Render or Railway, or on an IaaS VM such as AWS EC2, which would replace ngrok. It can be packaged as a Docker container exposing port 9090. The web UI is a static page and can be hosted on GitHub Pages. The Pi client runs on the drone itself.
