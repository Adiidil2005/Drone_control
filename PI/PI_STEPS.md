# PI

ONE TIME:
1. Copy the whole PI folder to the Pi.
2. On the Pi:
       cd PI
       source venv/bin/activate
       pip install -r requirements.txt

EVERY TIME (after the laptop steps 1 and 2):
- Test with no drone hardware:
       python3 pi_webrtc_client_video_only.py wss://xxxx.ngrok-free.dev/ws --dry-run
- Real (Pixhawk connected, PROPS OFF):
       python3 pi_webrtc_client_video_only.py wss://xxxx.ngrok-free.dev/ws

Use the same wss link as the laptop. Ctrl+C to stop.
