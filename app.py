import os
import subprocess
import traceback
from pathlib import Path
from flask import Flask, render_template, request, send_file, url_for, redirect, flash, after_this_request,jsonify
from urllib.parse import urlparse, parse_qs

app = Flask(__name__)
app.secret_key = "your_secret_key"  # Needed for flash messages

# Configure directories
OUTPUT_DIR = "static/audio"
THUMBNAIL_DIR = "static/thumbnails"

# Create directories if they don't exist
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(THUMBNAIL_DIR, exist_ok=True)

def get_video_id(youtube_url):
    """Extract the video ID from a YouTube URL."""
    parsed_url = urlparse(youtube_url)
    
    if parsed_url.netloc == 'youtu.be':
        return parsed_url.path[1:]
    
    if parsed_url.netloc in ('www.youtube.com', 'youtube.com'):
        if parsed_url.path == '/watch':
            query = parse_qs(parsed_url.query)
            return query['v'][0]
        elif parsed_url.path.startswith('/embed/'):
            return parsed_url.path.split('/')[2]
        elif parsed_url.path.startswith('/v/'):
            return parsed_url.path.split('/')[2]
    
    # If no match, return None
    return None


@app.route("/", methods=["GET"])
def index():
    """Render the main page with the form."""
    return render_template("index.html")


@app.route("/get_thumbnail", methods=["POST"])
def get_thumbnail():
    """Get video thumbnail and basic info from YouTube URL."""
    youtube_url = request.form.get("youtube_url")
    
    if not youtube_url:
        return jsonify({"error": "Please enter a valid YouTube URL"}), 400
    
    try:
        from yt_dlp import YoutubeDL
        
        # Extract video info without downloading
        ydl_opts = {
            'format': 'bestaudio/best',
            'skip_download': True,
            'quiet': True,
        }
        
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            
        # Get video details
        video_title = info.get('title', 'Unknown Title')
        video_duration = info.get('duration', 0)
        minutes, seconds = divmod(video_duration, 60)
        duration_formatted = f"{minutes}:{seconds:02d}"
        
        # Get thumbnail URL (use the highest quality available)
        thumbnail_url = None
        thumbnails = info.get('thumbnails', [])
        if thumbnails:
            # Sort by resolution (width * height) and get the highest resolution
            best_thumbnail = max(thumbnails, key=lambda x: x.get('width', 0) * x.get('height', 0))
            thumbnail_url = best_thumbnail.get('url')
        
        return jsonify({
            "title": video_title,
            "duration": duration_formatted,
            "thumbnail_url": thumbnail_url
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/convert", methods=["POST"])
def convert():
    """Process the YouTube URL and convert to audio."""
    youtube_url = request.form.get("youtube_url")
    
    if not youtube_url:
        flash("Please enter a valid YouTube URL", "error")
        return redirect(url_for("index"))
    
    try:
        from yt_dlp import YoutubeDL
        
        # Check for FFmpeg
        try:
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
            if result.returncode != 0:
                flash("FFmpeg is not properly installed. Please install FFmpeg.", "error")
                return redirect(url_for("index"))
        except FileNotFoundError:
            flash("FFmpeg is not installed or not in PATH. Please install FFmpeg.", "error")
            return redirect(url_for("index"))
        
        # Make sure OUTPUT_DIR exists and is writable
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # ** Delete existing audio files (.mp3) and thumbnails (.jpg) before converting new video **
        files = sorted(Path(OUTPUT_DIR).glob("*.mp3"), key=os.path.getmtime, reverse=True)
        thumbnail_files = sorted(Path(OUTPUT_DIR).glob("*.wepg"), key=os.path.getmtime, reverse=True)
        
        # Remove old audio files
        for file in files:
            os.remove(file)
        
        # Remove old thumbnail files
        for file in thumbnail_files:
            os.remove(file)
        
        # Get video info first
        ydl_info_opts = {
            'format': 'bestaudio/best',
            'skip_download': True,
            'quiet': True,
        }
        
        with YoutubeDL(ydl_info_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            video_title = info.get('title', 'Unknown Title')
            
        # Download video and convert to audio
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': f'{OUTPUT_DIR}/%(title)s.%(ext)s',
            'quiet': False,
            'no_warnings': False,
            'geo-bypass': True,
            'no-check-certificate': True,
            # Download thumbnail
            'writethumbnail': True,
            'outtmpl_na_placeholder': 'NA',
        }
        
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])
            
        # Get the filename of the most recently downloaded file
        files = sorted(Path(OUTPUT_DIR).glob("*.mp3"), key=os.path.getmtime, reverse=True)
        if not files:
            flash("No files were downloaded. Check if FFmpeg is installed correctly.", "error")
            return redirect(url_for("index"))
            
        latest_file = files[0]
        filename = latest_file.name
        
        # Find thumbnail
        thumbnail_files = sorted(Path(OUTPUT_DIR).glob("*.jpg"), key=os.path.getmtime, reverse=True)
        thumbnail_filename = None
        if thumbnail_files:
            thumbnail_file = thumbnail_files[0]
            thumbnail_filename = thumbnail_file.name
            
        flash(f"Successfully converted: {filename}", "success")
        return render_template("result.html", filename=filename, thumbnail=thumbnail_filename)
        
    except ImportError:
        flash("yt-dlp is not installed. Please install it with 'pip install yt-dlp'", "error")
        return redirect(url_for("index"))
    except Exception as e:
        error_details = traceback.format_exc()
        app.logger.error(f"Error in conversion: {error_details}")
        flash(f"An error occurred: {str(e)}", "error")
        return redirect(url_for("index"))


# Define UPLOAD_FOLDER before using it
UPLOAD_FOLDER = os.path.join('static', 'audio')  # Ensure proper path
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/download/<filename>')
def download_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    thumbnail_path = os.path.join(app.config['UPLOAD_FOLDER'], filename.replace('.mp3', '.jpg'))  # Adjust extension if needed

    if not os.path.exists(file_path):
        flash("File not found!", "error")
        return redirect(url_for('index'))

    @after_this_request
    def remove_file(response):
        try:
            os.remove(file_path)
            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)  # Delete the thumbnail if it exists
        except Exception as e:
            app.logger.error(f"Error deleting file: {e}")
        return response

    return send_file(file_path, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)