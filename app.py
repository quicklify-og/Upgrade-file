
from flask import Flask, request, jsonify, send_file, render_template_string
from flask_cors import CORS
import yt_dlp
import os
import uuid
from urllib.parse import urlparse
import threading
import time
import json
import subprocess
import sys

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Install FFmpeg if not available
def install_ffmpeg():
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        print("FFmpeg is available")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Installing FFmpeg...")
        try:
            subprocess.run(['apt-get', 'update'], capture_output=True, check=True)
            subprocess.run(['apt-get', 'install', '-y', 'ffmpeg'], capture_output=True, check=True)
            print("FFmpeg installed successfully")
        except subprocess.CalledProcessError as e:
            print(f"Failed to install FFmpeg: {e}")

# Install FFmpeg on startup
install_ffmpeg()

# Create downloads directory
DOWNLOADS_DIR = 'downloads'
if not os.path.exists(DOWNLOADS_DIR):
    os.makedirs(DOWNLOADS_DIR)

# Clean up old files every hour
def cleanup_old_files():
    while True:
        try:
            current_time = time.time()
            for filename in os.listdir(DOWNLOADS_DIR):
                filepath = os.path.join(DOWNLOADS_DIR, filename)
                if os.path.isfile(filepath):
                    # Delete files older than 1 hour
                    if current_time - os.path.getmtime(filepath) > 3600:
                        os.remove(filepath)
        except Exception as e:
            print(f"Cleanup error: {e}")
        time.sleep(3600)  # Run every hour

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()

@app.route('/')
def index():
    return send_file('media-downloader.html')

@app.route('/analyze', methods=['POST'])
def analyze_media():
    """Fast analysis of media to show available formats"""
    try:
        data = request.get_json()
        url = data.get('url')
        
        if not url:
            return jsonify({'success': False, 'error': 'URL is required'})
        
        # Quick info extraction without downloading
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Get available formats
            formats = info.get('formats', [])
            video_formats = []
            audio_formats = []
            
            for f in formats:
                if f.get('vcodec') != 'none' and f.get('height'):
                    video_formats.append({
                        'quality': f.get('height'),
                        'ext': f.get('ext'),
                        'filesize': f.get('filesize'),
                        'format_id': f.get('format_id')
                    })
                elif f.get('acodec') != 'none':
                    audio_formats.append({
                        'ext': f.get('ext'),
                        'abr': f.get('abr'),
                        'format_id': f.get('format_id')
                    })
            
            # Remove duplicates and sort
            video_qualities = list(set([f['quality'] for f in video_formats if f['quality']]))
            video_qualities.sort(reverse=True)
            
            # Ensure we have standard quality options even if not detected
            standard_qualities = [2160, 1440, 1080, 720, 480, 360, 240, 144]
            available_qualities = []
            
            # Add detected qualities
            for q in video_qualities:
                if q not in available_qualities:
                    available_qualities.append(q)
            
            # Add standard qualities that might be available
            for q in standard_qualities:
                if q not in available_qualities:
                    available_qualities.append(q)
            
            # Sort in descending order
            available_qualities.sort(reverse=True)
            
            return jsonify({
                'success': True,
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration'),
                'thumbnail': info.get('thumbnail'),
                'video_qualities': available_qualities,
                'has_audio': len(audio_formats) > 0,
                'platform': info.get('extractor', 'Unknown')
            })
            
    except Exception as e:
        return jsonify({'success': False, 'error': f'Analysis failed: {str(e)}'})

@app.route('/download', methods=['POST'])
def download_media():
    try:
        data = request.get_json()
        url = data.get('url')
        media_type = data.get('type', 'video')
        quality = data.get('quality', 'best')
        
        if not url:
            return jsonify({'success': False, 'error': 'URL is required'})
        
        # Generate unique filename
        unique_id = str(uuid.uuid4())[:8]
        
        # Configure yt-dlp options for faster downloads
        ydl_opts = {
            'outtmpl': os.path.join(DOWNLOADS_DIR, f'{unique_id}_%(title)s.%(ext)s'),
            'restrictfilenames': True,
            'extract_flat': False,
            'writethumbnail': False,
            'writeinfojson': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'quiet': False,  # Enable output for debugging
            'no_warnings': False,
        }
        
        # Optimized format selection
        if media_type == 'audio':
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        elif media_type == 'video':
            if quality == 'best':
                ydl_opts['format'] = 'best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best'
            else:
                ydl_opts['format'] = f'best[height<={quality}][ext=mp4]/bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best'
        else:  # best quality
            ydl_opts['format'] = 'best[ext=mp4]/best'
        
        # Download the media
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Download directly without separate info extraction
            ydl.download([url])
            
            # Find the downloaded file
            downloaded_file = None
            for filename in os.listdir(DOWNLOADS_DIR):
                if filename.startswith(unique_id):
                    downloaded_file = filename
                    break
            
            if downloaded_file:
                download_url = f'/file/{downloaded_file}'
                return jsonify({
                    'success': True,
                    'filename': downloaded_file,
                    'download_url': download_url
                })
            else:
                return jsonify({'success': False, 'error': 'File not found after download'})
                
    except Exception as e:
        error_msg = str(e)
        if 'Unsupported URL' in error_msg or 'No video formats found' in error_msg:
            return jsonify({'success': False, 'error': 'This platform is not supported or the URL is invalid'})
        elif 'Video unavailable' in error_msg or 'Private video' in error_msg:
            return jsonify({'success': False, 'error': 'Video is unavailable, private, or restricted'})
        elif 'format' in error_msg.lower():
            return jsonify({'success': False, 'error': 'Requested quality not available. Try a different quality.'})
        else:
            return jsonify({'success': False, 'error': f'Download failed: {error_msg}'})

@app.route('/file/<filename>')
def download_file(filename):
    try:
        filepath = os.path.join(DOWNLOADS_DIR, filename)
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True)
        else:
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
