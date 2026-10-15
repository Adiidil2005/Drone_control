"""
pi_webrtc_client_video_only.py — PRESENTATION VERSION, runs on the Raspberry Pi.

Stripped-down version of pi_webrtc_client.py for demoing just the camera feed:
browser connects, registers, and receives live video from the Pi Camera Module.
NOW WITH FLIGHT CONTROL: control messages from the browser are passed to
flight_bridge.py, which flies the Pixhawk over MAVLink. Run with --dry-run to
test without a Pixhawk (fake telemetry, nothing sent).

Everything else (signaling, WebRTC negotiation, video track) is identical to
the full script - this is not a different pipeline, just the full one with
the Arduino piece disconnected for now.
"""

import asyncio
import json
import sys

import websockets
from flight_bridge import FlightBridge          # <-- NEW: real flight control
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from av import VideoFrame

# =============================================================================
# CONFIG — edit these two for your deployment
# =============================================================================
DRONE_ID = "drone-1"                       # must match what the browser UI selects
SIGNALING_URL = "wss://skinning-paramount-singular.ngrok-free.dev/ws"   # overridden by the command-line argument
# =============================================================================


class PiCameraTrack(VideoStreamTrack):
    """Real video from the Raspberry Pi Camera Module (CSI ribbon cable),
    using picamera2 - the standard camera library on current Raspberry Pi OS
    (Bookworm and newer).

    Known gotcha (documented picamera2 behavior, not a bug here): the
    "RGB888" format actually delivers bytes in BGR order, which is why the
    VideoFrame below is built with format="bgr24" - using "rgb24" would give
    a blue-tinted picture.

    capture_array() is a blocking call, so it runs in a background thread
    (via run_in_executor) so it doesn't freeze WebRTC negotiation while
    waiting on the camera.
    """
    def __init__(self, width=640, height=480):
        super().__init__()
        from picamera2 import Picamera2
        self._picam2 = Picamera2()
        config = self._picam2.create_video_configuration(
            main={"size": (width, height), "format": "RGB888"}
        )
        self._picam2.configure(config)
        self._picam2.start()

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        loop = asyncio.get_event_loop()
        frame_arr = await loop.run_in_executor(None, self._picam2.capture_array)
        frame = VideoFrame.from_ndarray(frame_arr, format="bgr24")
        frame.pts = pts
        frame.time_base = time_base
        return frame

    def stop(self):
        super().stop()
        self._picam2.stop()


class DroneNode:
    def __init__(self, bridge):
        self.bridge = bridge       # NEW: the Pixhawk flight bridge
        self.pc = None
        self.control_channel = None
        self.telemetry_channel = None
        self.ws = None
        self.camera_track = None   # created once, reused across reconnects -
                                    # the camera can only be held open by one
                                    # thing at a time, so we must NOT create a
                                    # new Picamera2() on every offer

    def on_control_message(self, msg):
        # Browser control -> Pixhawk (via flight_bridge), real telemetry -> browser.
        try:
            data = json.loads(msg)
        except (json.JSONDecodeError, TypeError) as e:
            print(f"bad control message ignored: {e}")
            return

        self.bridge.handle(data)

        if self.telemetry_channel and self.telemetry_channel.readyState == "open":
            self.telemetry_channel.send(json.dumps(self.bridge.telemetry()))

    async def run(self):
        async with websockets.connect(SIGNALING_URL) as ws:
            self.ws = ws
            await ws.send(json.dumps({"type": "register", "id": DRONE_ID, "role": "drone"}))
            print(f"registered as {DRONE_ID}, waiting for a controller to connect...")

            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("type") == "offer":
                    try:
                        await self.handle_offer(msg)
                    except Exception as e:
                        # Don't let one failed connection attempt kill the
                        # whole script - print the error and keep waiting
                        # for the next offer instead.
                        print(f"failed to handle offer: {e!r}")

    async def handle_offer(self, msg):
        controller_id = msg["from"]
        print(f"offer received from {controller_id}")

        # If a previous connection is still open (e.g. the browser reconnected,
        # or double-clicked CONNECT), close it first. Without this, a second
        # offer would try to grab the camera while the first connection still
        # holds it, and fail with "Device or resource busy".
        if self.pc is not None:
            print("closing previous connection before starting a new one")
            await self.pc.close()
            self.pc = None

        self.pc = RTCPeerConnection()

        # Create the camera exactly once, the first time it's needed, then
        # reuse the same track for every subsequent connection.
        if self.camera_track is None:
            self.camera_track = PiCameraTrack()
        self.pc.addTrack(self.camera_track)

        @self.pc.on("datachannel")
        def on_datachannel(channel):
            print(f"data channel opened: {channel.label}")
            if channel.label == "control":
                self.control_channel = channel

                @channel.on("message")
                def on_message(m):
                    self.on_control_message(m)
            elif channel.label == "telemetry":
                self.telemetry_channel = channel

        await self.pc.setRemoteDescription(RTCSessionDescription(sdp=msg["sdp"], type="offer"))
        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)

        await self.ws.send(json.dumps({
            "type": "answer", "target": controller_id,
            "sdp": self.pc.localDescription.sdp,
        }))


if __name__ == "__main__":
    # usage:  python3 pi_webrtc_client_video_only.py wss://xxxx.ngrok-free.dev/ws [--dry-run]
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv
    if args:
        SIGNALING_URL = args[0]
    bridge = FlightBridge(dry_run=dry_run)
    bridge.start()                      # connects to the Pixhawk (skipped in --dry-run)
    node = DroneNode(bridge)
    try:
        asyncio.run(node.run())
    finally:
        bridge.stop()
