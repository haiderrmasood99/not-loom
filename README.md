# Loom-Style Local Recorder

Local-first screen recorder with a Loom-like UI. The React/Vite frontend captures screen, mic, and webcam directly in the browser (MediaRecorder). The Flask/OpenCV/PyAudio backend is included as an optional native recorder that merges audio/video via ffmpeg. All recordings stay on your machine—no cloud.

## Features
- Screen + mic + webcam overlay (circular, positionable)
- Countdown start, status UI, and quick download (WebM) in-browser
- Optional backend capture with OpenCV + ffmpeg output to Desktop/LoomRecordings
- Adjustable FPS, webcam size, and corner position
- Local-only: no uploads, accounts, or trackers

## Project Layout
- `frontend/` — React + Vite app; MediaRecorder-based capture, Loom-style UI
- `backend/` — Flask API with OpenCV/mss screen grab, PyAudio capture, ffmpeg mux

## Requirements
- Node.js 16+ (frontend)
- Modern Chromium-based browser for system-audio capture (frontend)
- Python 3.9+ (backend)
- ffmpeg + PortAudio dev libs (backend merge/audio)

## Setup
```bash
# Frontend
cd frontend
npm install

# Backend (optional)
cd ../backend
pip install -r requirements.txt
```

## Running the Frontend (recommended)
```bash
cd frontend
npm run dev
# open the shown URL (e.g., http://localhost:5173)
```
1) Click Start Recording → choose screen/window/tab and allow mic/camera.  
2) Webcam overlays on a circular badge in your chosen corner.  
3) Stop to get a download button (WebM). Everything stays local.

## Running the Backend (optional native recorder)
```bash
cd backend
python backend.py
# API at http://localhost:5000
```
The backend saves `loom_<timestamp>.mp4` to `~/Desktop/LoomRecordings` (or `backend/Recordings`). Endpoints: `/api/start`, `/api/stop`, `/api/status`, `/api/settings`. The provided frontend previously called these; current UI records in-browser.

## Notes & Tips
- System audio: grant “share tab audio” or “share system audio” in the browser prompt; otherwise mic-only.
- FPS: higher FPS costs CPU; 20–30 is typical. Webcam size 150–250px.  
- If using the backend, ensure ffmpeg is in PATH and no other app holds the webcam/mic.
- Outputs: frontend saves a blob URL for download (WebM). Backend writes MP4 to the LoomRecordings folder.

## Troubleshooting
- Black preview: ensure browser permissions and that hidden videos can play (page must stay focused initially).
- Out-of-sync when using backend: the frontend’s MediaRecorder path is recommended; backend relies on OS/ffmpeg timing.

