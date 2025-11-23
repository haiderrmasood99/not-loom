import React, { useState, useRef } from 'react';
import './App.css';

function App() {
  const [recording, setRecording] = useState(false);
  const [frames, setFrames] = useState(0);
  const [countdown, setCountdown] = useState(0);
  const [statusError, setStatusError] = useState('');
  const [settings, setSettings] = useState({
    webcam_size: 200,
    webcam_position: 'bottom-right',
    fps: 20,
    countdown: 3,
  });
  const [lastRecording, setLastRecording] = useState(null);
  const [saving, setSaving] = useState(false);

  const canvasRef = useRef(null);
  const screenVideoRef = useRef(null);
  const webcamVideoRef = useRef(null);
  const drawLoopRef = useRef(null);
  const recorderRef = useRef(null);
  const streamRef = useRef({ display: null, webcam: null, mic: null, canvas: null });
  const chunksRef = useRef([]);

  const cleanupStreams = () => {
    Object.values(streamRef.current).forEach(stream => {
      if (stream && stream.getTracks) {
        stream.getTracks().forEach(t => t.stop());
      }
    });
    streamRef.current = { display: null, webcam: null, mic: null, canvas: null };
    if (drawLoopRef.current) {
      cancelAnimationFrame(drawLoopRef.current);
      drawLoopRef.current = null;
    }
  };

  const setupCapture = async () => {
    const display = await navigator.mediaDevices.getDisplayMedia({
      video: { frameRate: settings.fps },
      audio: true,
    });
    const webcam = await navigator.mediaDevices.getUserMedia({
      video: { width: settings.webcam_size, height: settings.webcam_size },
      audio: false,
    });
    const mic = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });

    streamRef.current.display = display;
    streamRef.current.webcam = webcam;
    streamRef.current.mic = mic;

    const screenVideo = screenVideoRef.current;
    const webcamVideo = webcamVideoRef.current;
    screenVideo.srcObject = display;
    webcamVideo.srcObject = webcam;

    await Promise.all([
      new Promise(res => (screenVideo.onloadedmetadata = res)),
      new Promise(res => (webcamVideo.onloadedmetadata = res)),
    ]);

    // Ensure playback starts so frames are available for the canvas
    await Promise.all([screenVideo.play().catch(() => {}), webcamVideo.play().catch(() => {})]);

    const canvas = canvasRef.current;
    canvas.width = screenVideo.videoWidth || 1280;
    canvas.height = screenVideo.videoHeight || 720;
    const ctx = canvas.getContext('2d');

    const draw = () => {
      drawLoopRef.current = requestAnimationFrame(draw);
      if (screenVideo.readyState >= 2) {
        ctx.drawImage(screenVideo, 0, 0, canvas.width, canvas.height);
      }

      const size = settings.webcam_size;
      const margin = 30;
      const positions = {
        'bottom-right': [canvas.width - size - margin, canvas.height - size - margin],
        'bottom-left': [margin, canvas.height - size - margin],
        'top-right': [canvas.width - size - margin, margin],
        'top-left': [margin, margin],
      };
      const [x, y] = positions[settings.webcam_position] || positions['bottom-right'];

      ctx.save();
      ctx.beginPath();
      ctx.arc(x + size / 2, y + size / 2, size / 2, 0, Math.PI * 2);
      ctx.closePath();
      ctx.clip();
      ctx.drawImage(webcamVideo, x, y, size, size);
      ctx.restore();

      ctx.strokeStyle = 'white';
      ctx.lineWidth = 5;
      ctx.beginPath();
      ctx.arc(x + size / 2, y + size / 2, size / 2 - 3, 0, Math.PI * 2);
      ctx.stroke();

      setFrames(prev => prev + 1);
    };
    draw();

    const canvasStream = canvas.captureStream(settings.fps || 20);
    streamRef.current.canvas = canvasStream;

    const audioCtx = new AudioContext();
    const dest = audioCtx.createMediaStreamDestination();
    [display, mic].forEach(srcStream => {
      if (!srcStream) return;
      srcStream.getAudioTracks().forEach(track => {
        const src = audioCtx.createMediaStreamSource(new MediaStream([track]));
        src.connect(dest);
      });
    });

    const combinedStream = new MediaStream([
      ...canvasStream.getVideoTracks(),
      ...dest.stream.getAudioTracks(),
    ]);

    return combinedStream;
  };

  const startRecording = async () => {
    setStatusError('');
    setFrames(0);
    try {
      const countdownTime = settings.countdown;
      setCountdown(countdownTime);
      for (let i = countdownTime; i > 0; i--) {
        setCountdown(i);
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
      setCountdown(0);

      const stream = await setupCapture();
      const mimeType = MediaRecorder.isTypeSupported('video/webm;codecs=vp9,opus')
        ? 'video/webm;codecs=vp9,opus'
        : 'video/webm;codecs=vp8,opus';
      const recorder = new MediaRecorder(stream, { mimeType, videoBitsPerSecond: 5_000_000 });

      chunksRef.current = [];
      recorder.ondataavailable = e => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        setSaving(true);
        const blob = new Blob(chunksRef.current, { type: mimeType });
        const url = URL.createObjectURL(blob);
        setLastRecording(url);
        setSaving(false);
        cleanupStreams();
      };

      recorder.start(200); // small timeslice to reduce data loss risk
      recorderRef.current = recorder;
      setRecording(true);
    } catch (err) {
      console.error('Error starting recording', err);
      setStatusError('Failed to start recording. Please allow screen and mic access.');
      setCountdown(0);
      cleanupStreams();
    }
  };

  const stopRecording = () => {
    try {
      if (recorderRef.current && recorderRef.current.state !== 'inactive') {
        recorderRef.current.stop();
      }
      setRecording(false);
    } catch (err) {
      console.error('Error stopping recording', err);
      setStatusError('Failed to stop recording.');
      cleanupStreams();
    }
  };

  const downloadRecording = () => {
    if (!lastRecording) return;
    const a = document.createElement('a');
    a.href = lastRecording;
    a.download = 'loom-recording.webm';
    a.click();
  };

  return (
    <div className="app">
      <div className="container">
        <header className="header">
          <div className="logo">
            <span className="icon">🎥</span>
            <h1>Loom Clone</h1>
          </div>
          <div className="tagline">Local-only, in-browser recording with webcam overlay</div>
        </header>

        <div className="content">
          <div className="preview-section">
            <div className="preview-card">
              <div className="preview-header">
                <h3>Recording Status</h3>
                <span className={`status-badge ${recording ? 'recording' : 'ready'}`}>
                  {recording ? '🔴 Recording' : '✅ Ready'}
                </span>
              </div>
              <div className="status-display">
                <canvas ref={canvasRef} className="live-canvas" />
                {countdown > 0 ? (
                  <div className="countdown-display">
                    <div className="countdown-number">{countdown}</div>
                    <div className="countdown-text">Recording starts in...</div>
                    <div className="countdown-hint">Select the screen or window you want to capture.</div>
                  </div>
                ) : recording ? (
                  <div className="recording-display">
                    <div className="recording-icon">
                      <div className="pulse-ring"></div>
                      <div className="pulse-dot">🎥</div>
                    </div>
                    <div className="recording-info">
                      <h2>{frames} frames captured</h2>
                      <p>Recording in progress...</p>
                      <p className="recording-hint">Everything stays on your machine.</p>
                    </div>
                  </div>
                ) : (
                  <div className="ready-display">
                    <div className="ready-icon">🎬</div>
                    <h2>Ready to Record</h2>
                    <p>Pick your settings and start recording locally.</p>
                    <div className="features-list">
                      <div className="feature-item">✅ Screen capture</div>
                      <div className="feature-item">✅ Webcam circle overlay</div>
                      <div className="feature-item">✅ Mic + system audio (if allowed)</div>
                      <div className="feature-item">✅ Countdown starter</div>
                    </div>
                  </div>
                )}
                {statusError && (
                  <div className="status-error">
                    <strong>⚠️ {statusError}</strong>
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="settings-section">
            <div className="settings-card">
              <h3>Settings</h3>

              <div className="setting-group">
                <label>Webcam Position</label>
                <div className="button-group">
                  {['top-left', 'top-right', 'bottom-left', 'bottom-right'].map(pos => (
                    <button
                      key={pos}
                      className={`position-btn ${settings.webcam_position === pos ? 'active' : ''}`}
                      onClick={() => setSettings({ ...settings, webcam_position: pos })}
                      disabled={recording}
                    >
                      {pos.split('-').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')}
                    </button>
                  ))}
                </div>
              </div>

              <div className="setting-group">
                <label>Webcam Size: {settings.webcam_size}px</label>
                <input
                  type="range"
                  min="150"
                  max="250"
                  value={settings.webcam_size}
                  onChange={e => setSettings({ ...settings, webcam_size: parseInt(e.target.value) })}
                  disabled={recording}
                  className="slider"
                />
                <div className="range-labels">
                  <span>Small (Fast)</span>
                  <span>Large (Slow)</span>
                </div>
              </div>

              <div className="setting-group">
                <label>Frame Rate: {settings.fps} FPS</label>
                <input
                  type="range"
                  min="15"
                  max="30"
                  value={settings.fps}
                  onChange={e => setSettings({ ...settings, fps: parseInt(e.target.value) })}
                  disabled={recording}
                  className="slider"
                />
                <div className="range-labels">
                  <span>Smooth (15)</span>
                  <span>Best (30)</span>
                </div>
                <p className="setting-hint">Lower FPS = lighter CPU usage</p>
              </div>

              <div className="setting-group">
                <label>Countdown Timer: {settings.countdown}s</label>
                <input
                  type="range"
                  min="0"
                  max="10"
                  value={settings.countdown}
                  onChange={e => setSettings({ ...settings, countdown: parseInt(e.target.value) })}
                  disabled={recording}
                  className="slider"
                />
                <div className="range-labels">
                  <span>None</span>
                  <span>10 sec</span>
                </div>
                <p className="setting-hint">Time to switch tabs before recording starts</p>
              </div>

              <div className="controls">
                {!recording && countdown === 0 ? (
                  <button className="btn btn-primary" onClick={startRecording}>
                    <span className="btn-icon">⏺</span>
                    Start Recording
                  </button>
                ) : countdown > 0 ? (
                  <button className="btn btn-primary" disabled>
                    <span className="btn-icon">⏳</span>
                    Starting in {countdown}...
                  </button>
                ) : (
                  <button className="btn btn-danger" onClick={stopRecording}>
                    <span className="btn-icon">⏹</span>
                    Stop Recording
                  </button>
                )}
              </div>

              {lastRecording && (
                <div className="last-recording">
                  <div className="success-message">
                    ✅ Recording saved locally
                  </div>
                  <div className="file-path">Ready to download</div>
                  <button className="btn btn-secondary" onClick={downloadRecording} disabled={saving}>
                    {saving ? 'Preparing...' : 'Download video'}
                  </button>
                </div>
              )}
            </div>

            <div className="info-cards">
              <div className="info-card">
                <div className="info-icon">💾</div>
                <div className="info-text">
                  <strong>Local Only</strong>
                  <span>Everything stays on your machine</span>
                </div>
              </div>
              <div className="info-card">
                <div className="info-icon">⚡</div>
                <div className="info-text">
                  <strong>Synced A/V</strong>
                  <span>Browser MediaRecorder handles sync</span>
                </div>
              </div>
              <div className="info-card">
                <div className="info-icon">🎯</div>
                <div className="info-text">
                  <strong>Loom-like UI</strong>
                  <span>Countdown, overlay, quick download</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <footer className="footer">
          <p>Built for local recording — no cloud required.</p>
        </footer>
      </div>

      {/* Hidden video elements used for drawing to canvas */}
      <video ref={screenVideoRef} style={{ display: 'none' }} playsInline muted autoPlay />
      <video ref={webcamVideoRef} style={{ display: 'none' }} playsInline muted autoPlay />
    </div>
  );
}

export default App;
