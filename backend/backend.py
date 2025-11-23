#!/usr/bin/env python3
"""
Optimized Loom Clone Backend - Fast & Efficient
"""

import cv2
import numpy as np
import pyaudio
import wave
import threading
import time
from datetime import datetime
from mss import mss
import os
from flask import Flask, jsonify, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

class OptimizedRecorder:
    def __init__(self):
        self.recording = False
        self.frames = []
        self.audio_frames = []
        self.frame_timestamps = []
        
        # Audio settings
        self.audio_format = pyaudio.paInt16
        self.channels = 2
        self.rate = 44100
        self.chunk = 1024
        
        # Video settings - Optimized!
        self.target_fps = 20  # Lower FPS for better performance
        self.webcam_size = 200  # Smaller webcam for faster processing
        self.webcam_position = "bottom-right"
        self.scale_factor = 1.0  # Can reduce for lower resolution
        
        self.p = pyaudio.PyAudio()
        self.output_dir = self.get_output_dir()
        self.start_event = threading.Event()
        self.record_start_time = None
        
    def get_output_dir(self):
        """Get output directory"""
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", "LoomRecordings")
        if os.path.exists(os.path.join(os.path.expanduser("~"), "Desktop")):
            os.makedirs(desktop_path, exist_ok=True)
            return desktop_path
        
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(script_dir, "Recordings")
        os.makedirs(output_dir, exist_ok=True)
        return output_dir
    
    def create_circular_mask(self, size):
        """Create circular mask - cached for speed"""
        mask = np.zeros((size, size), dtype=np.uint8)
        cv2.circle(mask, (size // 2, size // 2), size // 2, 255, -1)
        return mask
    
    def crop_to_square(self, frame):
        """Crop frame to square (center crop)"""
        h, w = frame.shape[:2]
        if h > w:
            start = (h - w) // 2
            return frame[start:start+w, :]
        elif w > h:
            start = (w - h) // 2
            return frame[:, start:start+h]
        return frame
    
    def get_webcam_position(self, screen_width, screen_height):
        """Calculate webcam position"""
        margin = 30
        size = self.webcam_size
        
        positions = {
            "bottom-right": (screen_width - size - margin, screen_height - size - margin),
            "bottom-left": (margin, screen_height - size - margin),
            "top-right": (screen_width - size - margin, margin),
            "top-left": (margin, margin)
        }
        
        return positions.get(self.webcam_position, positions["bottom-right"])
    
    def record_audio(self):
        """Record audio"""
        try:
            # Wait until video is ready to start to keep A/V in sync
            self.start_event.wait(timeout=2)
            stream = self.p.open(
                format=self.audio_format,
                channels=self.channels,
                rate=self.rate,
                input=True,
                frames_per_buffer=self.chunk
            )
            
            while self.recording:
                data = stream.read(self.chunk, exception_on_overflow=False)
                self.audio_frames.append(data)
            
            stream.stop_stream()
            stream.close()
        except Exception as e:
            print(f"Audio recording error: {e}")
    
    def record_video(self):
        """Optimized video recording"""
        self.start_event.clear()
        self.record_start_time = None
        self.frame_timestamps = []

        # Try multiple camera indices and fall back to screen-only if none work.
        cap = None
        webcam_available = False
        camera_indices = [0, 1, 2, 3]
        backends = [cv2.CAP_DSHOW] if os.name == "nt" else [cv2.CAP_ANY]

        for idx in camera_indices:
            for backend in backends:
                cap = cv2.VideoCapture(idx, backend)
                if cap.isOpened():
                    webcam_available = True
                    print(f"✅ Webcam opened on index {idx} (backend {backend})")
                    break
                cap.release()
                cap = None
            if webcam_available:
                break

        if webcam_available:
            # Lower webcam resolution for speed
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            # CRITICAL: Flush initial frames (they're often black/garbage)
            print("🔄 Flushing initial webcam frames...")
            for _ in range(10):
                cap.read()
                time.sleep(0.05)

            # Test webcam
            ret, test_frame = cap.read()
            if not ret:
                print("❌ Webcam not working! Continuing without webcam overlay.")
                cap.release()
                cap = None
                webcam_available = False
            else:
                print(f"✅ Webcam initialized! Shape: {test_frame.shape}")
        else:
            print("⚠️ No webcam available. Continuing with screen-only recording.")

        # Align audio start with when we are ready to capture video frames
        # Align audio start with when we are ready to capture video frames
        self.record_start_time = time.perf_counter()
        self.start_event.set()
        
        # Setup screen capture
        sct = mss()
        monitor = sct.monitors[1]
        
        screen_width = monitor['width']
        screen_height = monitor['height']
        
        # Pre-create circular mask (don't recreate every frame!)
        mask = self.create_circular_mask(self.webcam_size)
        webcam_x, webcam_y = self.get_webcam_position(screen_width, screen_height)
        
        print(f"🎥 Recording at {screen_width}x{screen_height}")
        print(f"📍 Webcam at ({webcam_x}, {webcam_y}), size: {self.webcam_size}px")
        print(f"🎬 Target FPS: {self.target_fps}")
        
        start_time = time.time()
        frame_count = 0
        webcam_success = 0
        webcam_failures = 0
        
        # Pre-allocate for webcam circle (performance optimization)
        circle_webcam = np.zeros((self.webcam_size, self.webcam_size, 3), dtype=np.uint8)
        
        while self.recording:
            loop_start = time.time()
            
            # Capture screen
            screenshot = sct.grab(monitor)
            screen_frame = np.array(screenshot)
            screen_frame = cv2.cvtColor(screen_frame, cv2.COLOR_BGRA2BGR)
            
            # Capture webcam
            webcam_frame = None
            ret = False
            if webcam_available and cap is not None:
                ret, webcam_frame = cap.read()

            if ret and webcam_frame is not None and webcam_frame.size > 0:
                webcam_success += 1
                
                # Crop to square
                webcam_square = self.crop_to_square(webcam_frame)
                
                # Resize
                webcam_resized = cv2.resize(webcam_square, (self.webcam_size, self.webcam_size))
                
                # Apply circular mask (faster: reuse circle_webcam array)
                circle_webcam.fill(0)  # Clear previous
                circle_webcam[mask == 255] = webcam_resized[mask == 255]
                
                # Add border
                cv2.circle(circle_webcam, 
                          (self.webcam_size // 2, self.webcam_size // 2), 
                          self.webcam_size // 2 - 3, 
                          (255, 255, 255), 
                          5)
                
                # Overlay on screen (bounds already checked)
                y1, y2 = webcam_y, webcam_y + self.webcam_size
                x1, x2 = webcam_x, webcam_x + self.webcam_size
                
                if y2 <= screen_height and x2 <= screen_width:
                    screen_frame[y1:y2, x1:x2][mask == 255] = circle_webcam[mask == 255]
            elif webcam_available:
                webcam_failures += 1
                if webcam_failures % 60 == 0:
                    print("⚠️ Webcam capture failing; keeping recording without overlay.")
            
            # Track timestamp relative to start for accurate FPS
            if self.record_start_time is not None:
                self.frame_timestamps.append(time.perf_counter() - self.record_start_time)
            self.frames.append(screen_frame)
            frame_count += 1
            
            # Frame rate control - simple sleep
            elapsed = time.time() - loop_start
            target_time = 1.0 / self.target_fps
            if elapsed < target_time:
                time.sleep(target_time - elapsed)
            
            # Log progress every 2 seconds
            if frame_count % (self.target_fps * 2) == 0:
                print(f"📊 Captured {frame_count} frames ({webcam_success} with webcam)")
        
        if cap is not None:
            cap.release()
        
        duration = time.time() - start_time
        actual_fps = frame_count / duration if duration > 0 else 0
        
        print(f"\n✅ Recording complete!")
        print(f"   Frames: {frame_count}")
        print(f"   Duration: {duration:.2f}s")
        print(f"   Actual FPS: {actual_fps:.2f}")
        print(f"   Webcam overlays: {webcam_success}")
    
    def save_recording(self, output_name=None):
        """Save recording"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if output_name:
            base_name = output_name
        else:
            base_name = f"recording_{timestamp}"
        
        video_file = os.path.join(self.output_dir, f"{base_name}_temp.mp4")
        audio_file = os.path.join(self.output_dir, f"{base_name}_audio.wav")
        final_file = os.path.join(self.output_dir, f"loom_{base_name}.mp4")
        
        print("💾 Saving video...")
        
        # Calculate actual FPS from timestamps to keep A/V in sync
        if len(self.frame_timestamps) > 1:
            duration = self.frame_timestamps[-1]
            output_fps = len(self.frame_timestamps) / duration if duration > 0 else self.target_fps
        else:
            output_fps = self.target_fps
        
        # Save video at actual recorded FPS
        if self.frames:
            height, width = self.frames[0].shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            # Use target FPS for consistent playback
            out = cv2.VideoWriter(video_file, fourcc, output_fps, (width, height))
            
            for frame in self.frames:
                out.write(frame)
            out.release()
            print(f"✅ Video saved: {len(self.frames)} frames at {output_fps:.2f} FPS")
        
        # Save audio
        if self.audio_frames:
            wf = wave.open(audio_file, 'wb')
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.p.get_sample_size(self.audio_format))
            wf.setframerate(self.rate)
            wf.writeframes(b''.join(self.audio_frames))
            wf.close()
            print("✅ Audio saved")
        
        # Merge with ffmpeg
        print("🔄 Merging audio and video...")
        try:
            import subprocess
            audio_offset = self.frame_timestamps[0] if self.frame_timestamps else 0
            ffmpeg_cmd = [
                'ffmpeg', '-y',
                '-i', video_file,
                '-itsoffset', f'{audio_offset:.3f}',
                '-i', audio_file,
                '-c:v', 'libx264',
                '-preset', 'ultrafast',  # Faster encoding
                '-crf', '23',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-shortest',
                final_file
            ]
            subprocess.run(ffmpeg_cmd, check=True, capture_output=True, timeout=60)
            
            # Cleanup
            if os.path.exists(video_file):
                os.remove(video_file)
            if os.path.exists(audio_file):
                os.remove(audio_file)
            
            print(f"✅ Final video saved: {final_file}")
            return final_file
        except Exception as e:
            print(f"⚠️ Error merging: {e}")
            return video_file

# Global recorder
recorder = OptimizedRecorder()

@app.route('/api/start', methods=['POST'])
def start_recording():
    """Start recording with countdown"""
    global recorder
    
    if recorder.recording:
        return jsonify({"error": "Already recording"}), 400
    
    data = request.json
    recorder.webcam_size = min(data.get('webcam_size', 200), 250)  # Limit max size
    recorder.webcam_position = data.get('webcam_position', 'bottom-right')
    recorder.target_fps = min(data.get('fps', 20), 20)  # Cap at 20 FPS for performance
    # Frontend already handles countdown, so start immediately here
    countdown = 0
    
    recorder.recording = True
    recorder.frames = []
    recorder.audio_frames = []
    recorder.frame_timestamps = []
    
    def delayed_start():
        time.sleep(countdown)
        audio_thread = threading.Thread(target=recorder.record_audio, daemon=True)
        video_thread = threading.Thread(target=recorder.record_video, daemon=True)
        audio_thread.start()
        video_thread.start()
    
    threading.Thread(target=delayed_start, daemon=True).start()
    
    return jsonify({"status": "recording", "countdown": countdown})

@app.route('/api/stop', methods=['POST'])
def stop_recording():
    """Stop recording"""
    global recorder
    
    if not recorder.recording:
        return jsonify({"error": "Not recording"}), 400
    
    recorder.recording = False
    time.sleep(1)
    
    output_file = recorder.save_recording()
    
    return jsonify({
        "status": "stopped",
        "file": output_file,
        "frames": len(recorder.frames)
    })

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get status"""
    return jsonify({
        "recording": recorder.recording,
        "frames": len(recorder.frames),
        "output_dir": recorder.output_dir
    })

@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Get settings"""
    return jsonify({
        "webcam_size": recorder.webcam_size,
        "webcam_position": recorder.webcam_position,
        "fps": recorder.target_fps
    })

if __name__ == '__main__':
    print("🎥 Optimized Loom Clone Starting...")
    print(f"📁 Recordings: {recorder.output_dir}")
    print("🚀 Server: http://localhost:5000")
    print("\n⚡ Performance Tips:")
    print("   - FPS capped at 20 for smooth recording")
    print("   - Webcam size capped at 250px")
    print("   - Lower settings = better performance!\n")
    app.run(host='0.0.0.0', port=5000, debug=False)
