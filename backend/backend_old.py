#!/usr/bin/env python3
"""
Improved Loom Clone Backend - Fixed timing and aspect ratio
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
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import base64

app = Flask(__name__)
CORS(app)

class ImprovedRecorder:
    def __init__(self):
        self.recording = False
        self.frames = []
        self.audio_frames = []
        self.frame_timestamps = []  # Track actual frame times
        
        # Audio settings
        self.audio_format = pyaudio.paInt16
        self.channels = 2
        self.rate = 44100
        self.chunk = 1024
        
        # Video settings
        self.target_fps = 30
        self.webcam_size = 250
        self.webcam_position = "bottom-right"
        
        self.p = pyaudio.PyAudio()
        self.output_dir = self.get_output_dir()
        
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
        """Create circular mask"""
        mask = np.zeros((size, size), dtype=np.uint8)
        center = (size // 2, size // 2)
        cv2.circle(mask, center, size // 2, 255, -1)
        return mask
    
    def crop_to_square(self, frame):
        """Crop frame to square (center crop) to maintain aspect ratio"""
        h, w = frame.shape[:2]
        
        if h > w:
            # Crop height
            start = (h - w) // 2
            return frame[start:start+w, :]
        elif w > h:
            # Crop width
            start = (w - h) // 2
            return frame[:, start:start+h]
        else:
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
        """Record screen and webcam with proper timing"""
        # Try multiple camera indices with DirectShow backend (Windows compatible)
        cap = None
        for camera_idx in [0, 1, 2]:
            # Use DirectShow on Windows (cv2.CAP_DSHOW) - more compatible
            cap = cv2.VideoCapture(camera_idx, cv2.CAP_DSHOW)
            if cap.isOpened():
                print(f"✅ Webcam opened on camera index {camera_idx} with DirectShow")
                break
            cap.release()
            
        if not cap or not cap.isOpened():
            print("❌ Could not open webcam! Trying without DirectShow...")
            # Fallback to default backend
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                print("❌ Webcam completely unavailable. Recording without webcam overlay.")
                self.recording = False
                return
        
        # Set webcam properties for better quality
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)  # Lower resolution for better compatibility
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduce buffer
        
        # Give webcam time to initialize
        time.sleep(0.5)
        
        # Test webcam capture multiple times
        test_success = False
        for i in range(5):
            ret, test_frame = cap.read()
            if ret and test_frame is not None:
                test_success = True
                print(f"✅ Webcam test successful! Frame shape: {test_frame.shape}")
                break
            time.sleep(0.2)
        
        if not test_success:
            print("❌ Webcam not capturing frames after 5 attempts!")
            print("💡 TIP: Close your browser tab to release the webcam, then restart recording")
            cap.release()
            self.recording = False
            return
        
        sct = mss()
        monitor = sct.monitors[1]
        
        screen_width = monitor['width']
        screen_height = monitor['height']
        
        mask = self.create_circular_mask(self.webcam_size)
        webcam_x, webcam_y = self.get_webcam_position(screen_width, screen_height)
        
        print(f"🎥 Recording at {screen_width}x{screen_height}, webcam at ({webcam_x}, {webcam_y})")
        
        # Track start time for proper frame timing
        start_time = time.time()
        frame_count = 0
        target_frame_duration = 1.0 / self.target_fps
        webcam_overlay_count = 0
        webcam_fail_count = 0
        
        while self.recording:
            frame_start = time.time()
            
            # Calculate what frame number we should be on
            elapsed = frame_start - start_time
            expected_frame = int(elapsed * self.target_fps)
            
            # Skip frames if we're behind
            if frame_count < expected_frame:
                # Capture screen
                screenshot = sct.grab(monitor)
                screen_frame = np.array(screenshot)
                screen_frame = cv2.cvtColor(screen_frame, cv2.COLOR_BGRA2BGR)
                
                # Capture webcam - try multiple times if it fails
                webcam_captured = False
                for attempt in range(3):
                    ret, webcam_frame = cap.read()
                    if ret and webcam_frame is not None and webcam_frame.size > 0:
                        webcam_captured = True
                        webcam_overlay_count += 1
                        
                        # Crop to square FIRST (maintains aspect ratio)
                        webcam_square = self.crop_to_square(webcam_frame)
                        
                        # Then resize (no distortion since it's already square)
                        webcam_resized = cv2.resize(webcam_square, (self.webcam_size, self.webcam_size))
                        
                        # Create circular webcam
                        circle_webcam = np.zeros((self.webcam_size, self.webcam_size, 3), dtype=np.uint8)
                        circle_webcam[mask == 255] = webcam_resized[mask == 255]
                        
                        # Add border with shadow effect
                        border_thickness = 6
                        # Shadow (offset)
                        cv2.circle(circle_webcam, (self.webcam_size // 2 + 3, self.webcam_size // 2 + 3), 
                                 self.webcam_size // 2 - border_thickness // 2, (40, 40, 40), border_thickness)
                        # White border
                        cv2.circle(circle_webcam, (self.webcam_size // 2, self.webcam_size // 2), 
                                 self.webcam_size // 2 - border_thickness // 2, (255, 255, 255), border_thickness)
                        
                        # Overlay webcam on screen
                        y1, y2 = webcam_y, webcam_y + self.webcam_size
                        x1, x2 = webcam_x, webcam_x + self.webcam_size
                        
                        # Ensure bounds are valid
                        if y2 <= screen_height and x2 <= screen_width and y1 >= 0 and x1 >= 0:
                            roi = screen_frame[y1:y2, x1:x2].copy()
                            roi[mask == 255] = circle_webcam[mask == 255]
                            screen_frame[y1:y2, x1:x2] = roi
                        
                        break  # Success, exit retry loop
                    else:
                        time.sleep(0.01)  # Small delay before retry
                
                if not webcam_captured:
                    webcam_fail_count += 1
                    if webcam_fail_count % 30 == 0:  # Log every second
                        print(f"⚠️ Webcam frame capture failing (attempt {webcam_fail_count})")
                
                self.frames.append(screen_frame)
                self.frame_timestamps.append(elapsed)
                frame_count += 1
            
            # Smart sleep - only sleep if we're ahead
            frame_elapsed = time.time() - frame_start
            if frame_elapsed < target_frame_duration:
                time.sleep(target_frame_duration - frame_elapsed)
        
        cap.release()
        print(f"✅ Recording complete!")
        print(f"   Total frames: {frame_count}")
        print(f"   Duration: {time.time() - start_time:.2f}s")
        print(f"   Actual FPS: {frame_count / (time.time() - start_time):.2f}")
        print(f"   Webcam overlays applied: {webcam_overlay_count}")
        print(f"   Webcam failures: {webcam_fail_count}")
        if webcam_overlay_count == 0:
            print(f"   ⚠️ WARNING: No webcam frames were captured!")
            print(f"   💡 Close browser tab and try again, or check webcam permissions")
    
    def save_recording(self, output_name=None):
        """Save with proper frame timing"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if output_name:
            base_name = output_name
        else:
            base_name = f"recording_{timestamp}"
        
        video_file = os.path.join(self.output_dir, f"{base_name}_temp.mp4")
        audio_file = os.path.join(self.output_dir, f"{base_name}_audio.wav")
        final_file = os.path.join(self.output_dir, f"loom_{base_name}.mp4")
        
        # Calculate actual FPS from timestamps
        if len(self.frame_timestamps) > 1:
            duration = self.frame_timestamps[-1] - self.frame_timestamps[0]
            actual_fps = len(self.frames) / duration if duration > 0 else self.target_fps
            # Use actual FPS for accurate playback
            output_fps = actual_fps
        else:
            output_fps = self.target_fps
        
        print(f"Saving with FPS: {output_fps:.2f}")
        
        # Save video
        if self.frames:
            height, width = self.frames[0].shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(video_file, fourcc, output_fps, (width, height))
            
            for frame in self.frames:
                out.write(frame)
            out.release()
        
        # Save audio
        if self.audio_frames:
            wf = wave.open(audio_file, 'wb')
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.p.get_sample_size(self.audio_format))
            wf.setframerate(self.rate)
            wf.writeframes(b''.join(self.audio_frames))
            wf.close()
        
        # Merge with ffmpeg
        try:
            import subprocess
            subprocess.run([
                'ffmpeg', '-y',
                '-i', video_file,
                '-i', audio_file,
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '23',
                '-c:a', 'aac',
                '-b:a', '192k',
                '-shortest',
                final_file
            ], check=True, capture_output=True)
            
            # Cleanup
            if os.path.exists(video_file):
                os.remove(video_file)
            if os.path.exists(audio_file):
                os.remove(audio_file)
            
            return final_file
        except Exception as e:
            print(f"Error merging: {e}")
            return video_file

# Global recorder instance
recorder = ImprovedRecorder()

@app.route('/api/start', methods=['POST'])
def start_recording():
    """Start recording with countdown"""
    global recorder
    
    if recorder.recording:
        return jsonify({"error": "Already recording"}), 400
    
    data = request.json
    recorder.webcam_size = data.get('webcam_size', 250)
    recorder.webcam_position = data.get('webcam_position', 'bottom-right')
    recorder.target_fps = data.get('fps', 30)
    countdown = data.get('countdown', 3)  # Default 3 second countdown
    
    recorder.recording = True
    recorder.frames = []
    recorder.audio_frames = []
    recorder.frame_timestamps = []
    
    # Start threads with countdown delay
    def delayed_start():
        time.sleep(countdown)  # Wait for countdown
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
    time.sleep(1)  # Wait for threads to finish
    
    # Save recording
    output_file = recorder.save_recording()
    
    return jsonify({
        "status": "stopped",
        "file": output_file,
        "frames": len(recorder.frames)
    })

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get recording status"""
    return jsonify({
        "recording": recorder.recording,
        "frames": len(recorder.frames),
        "output_dir": recorder.output_dir
    })

@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Get current settings"""
    return jsonify({
        "webcam_size": recorder.webcam_size,
        "webcam_position": recorder.webcam_position,
        "fps": recorder.target_fps
    })

if __name__ == '__main__':
    print("🎥 Loom Clone Backend Starting...")
    print(f"📁 Recordings will be saved to: {recorder.output_dir}")
    print("🚀 Server running on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
