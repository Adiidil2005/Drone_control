# LAPTOP (do this first)

1. VS Code terminal 1:
       cd LAPTOP/signaling-server
       cargo run

2. VS Code terminal 2:
       ngrok http 9090
   Copy the link, change it to:  wss://xxxx.ngrok-free.dev/ws

3. Go do the PI steps, then come back.

4. Open LAPTOP/web-ui/index.html in the browser.
   Paste the wss link in the top box -> click the refresh arrow -> CONNECT -> ARM.
   Fly with W A S D, Q E, SPACE.
