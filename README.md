# Drone Control System over the Internet

[![CI](https://github.com/Adiidil2005/SE_Assingment2/actions/workflows/ci.yml/badge.svg)](https://github.com/Adiidil2005/SE_Assingment2/actions/workflows/ci.yml)

Fly a Pixhawk drone from a web browser, from anywhere, with a live camera feed.

## Abstract

This project controls an ArduCopter (Pixhawk) drone over the internet from a web browser. A Raspberry Pi on the drone streams live video from the Pi Camera and receives control commands. Both travel over a **WebRTC** peer-to-peer connection. A small **Rust signaling server** only helps the browser and the Pi find each other; after that, video and control go directly between them. On the Pi, `flight_bridge.py` converts the browser's stick commands into **MAVLink RC overrides** for the Pixhawk. It has safety features: a capped throttle, arming only at zero throttle, and an automatic **LAND failsafe** if commands stop arriving for 0.5 s.

## Team 12

| Name | Class | Role |
|---|---|---|
| Aditya Dileep | CT | Repository setup, unit tests, planning |
| Jonathan D'Cruz | CS1 | CI/CD pipeline, test documentation, deployment |

## Architecture

```
 Browser (web-ui)                Signaling server (Rust)               Raspberry Pi (on drone)
 ----------------                -----------------------               -----------------------
 index.html  ── register / offer ──►  /ws on port 9090  ◄── register / answer ──  pi_webrtc_client
     │                               (exposed via ngrok)                              │
     │                                                                                │
     └────────────── WebRTC peer-to-peer: video ◄─, control ─►, telemetry ◄─ ─────────┘
                                                                                      │
                                                                         flight_bridge.py
                                                                                      │ MAVLink (serial)
                                                                                   Pixhawk
```

## Technology Used

| Part | Technology |
|---|---|
| Signaling server | Rust, axum, tokio, serde_json |
| Drone client | Python, aiortc (WebRTC), websockets, picamera2, PyAV, NumPy |
| Flight control | pymavlink, ArduCopter on Pixhawk |
| Controller UI | HTML, CSS, JavaScript (WebRTC data channels) |
| Tunnel | ngrok |
| Testing / CI | PyTest, GitHub Actions |

## Project Structure

```
├── LAPTOP/
│   ├── signaling-server/        # Rust WebSocket signaling server (port 9090)
│   │   ├── Cargo.toml
│   │   └── src/main.rs
│   ├── web-ui/index.html        # Browser controller: video, telemetry, keyboard control
│   └── LAPTOP_STEPS.md
├── PI/
│   ├── pi_webrtc_client_video_only.py   # WebRTC client: camera stream + control channel
│   ├── flight_bridge.py                 # Browser commands -> MAVLink, failsafe, telemetry
│   ├── requirements.txt
│   └── PI_STEPS.md
├── tests/test_flight_bridge.py  # PyTest unit tests
└── .github/workflows/ci.yml     # GitHub Actions CI pipeline
```

## How to Run

### Requirements
- **Laptop:** Rust (cargo), ngrok, a modern browser
- **Raspberry Pi:** Python 3, Pi Camera Module, and a Pixhawk connected on `/dev/ttyAMA0` at 57600 baud

### 1. Start the signaling server (laptop)
```bash
cd LAPTOP/signaling-server
cargo run
```

### 2. Expose it to the internet (laptop, second terminal)
```bash
ngrok http 9090
```
ngrok prints a link like `https://xxxx.ngrok-free.dev`. Change it to **`wss://xxxx.ngrok-free.dev/ws`**.

### 3. Start the drone client (Raspberry Pi)
One-time setup:
```bash
cd PI
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
Test without drone hardware (fake telemetry, nothing is sent to the Pixhawk):
```bash
python3 pi_webrtc_client_video_only.py wss://xxxx.ngrok-free.dev/ws --dry-run
```
Real flight (Pixhawk connected; **remove the propellers for the first tests**):
```bash
python3 pi_webrtc_client_video_only.py wss://xxxx.ngrok-free.dev/ws
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


## Deployment
The signaling server can be hosted on a PaaS such as Render or Railway, or on an IaaS VM such as AWS EC2, which would replace ngrok. It can be packaged as a Docker container exposing port 9090. The web UI is a static page and can be hosted on GitHub Pages. The Pi client runs on the drone itself.
