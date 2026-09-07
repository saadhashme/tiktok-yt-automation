import os
import json
import subprocess
import shutil
from typing import List, Dict, Any, Optional

class TikTokDownloader:
    def __init__(self, cookies_file: Optional[str] = "cookies.txt", downloads_dir: str = "./downloads"):
        self.cookies_file = cookies_file
        self.downloads_dir = downloads_dir
        os.makedirs(self.downloads_dir, exist_ok=True)

    def list_user_videos(self, username: str, limit: int = 150) -> List[Dict[str, Any]]:
        clean_handle = username.lstrip("@")
        url = f"https://www.tiktok.com/@{clean_handle}"
        
        headers = [
            "--add-header", "Referer:https://www.tiktok.com/",
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ]

        cmd = [
            "yt-dlp",
            "--flat-playlist",
            "--dump-json",
            "--playlist-end", str(limit)
        ] + headers + [url]

        if self.cookies_file and os.path.exists(self.cookies_file):
            cmd.extend(["--cookies", self.cookies_file])

        print(f"Fetching profile listing for TikTok @{clean_handle}...")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            videos = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    try:
                        v = json.loads(line)
                        videos.append(v)
                    except json.JSONDecodeError:
                        continue
            print(f"Found {len(videos)} videos on profile @{clean_handle}.")
            return videos
        except subprocess.CalledProcessError as e:
            print(f"Error fetching TikTok profile via yt-dlp: {e.stderr}")
            return []

    def download_video(self, video_id: str, video_url: Optional[str] = None, username: Optional[str] = None) -> str:
        if not video_url:
            if username:
                clean_handle = username.lstrip("@")
                video_url = f"https://www.tiktok.com/@{clean_handle}/video/{video_id}"
            else:
                video_url = f"https://www.tiktok.com/video/{video_id}"

        output_path = os.path.join(self.downloads_dir, f"{video_id}.mp4")
        headers = [
            "--add-header", "Referer:https://www.tiktok.com/",
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ]

        cmd = [
            "yt-dlp",
            "-o", output_path,
            "--format", "b/best"
        ] + headers + [video_url]

        if self.cookies_file and os.path.exists(self.cookies_file):
            cmd.extend(["--cookies", self.cookies_file])

        print(f"Downloading video from {video_url} to {output_path}...")
        subprocess.run(cmd, check=True)

        if not self.has_audio_stream(output_path):
            print(f"Warning: Downloaded video {output_path} has no audio stream! Attempting audio fallback download...")
            cmd_fallback = [
                "yt-dlp",
                "-o", output_path,
                "-f", "bestvideo+bestaudio/best"
            ] + headers + [video_url]
            if self.cookies_file and os.path.exists(self.cookies_file):
                cmd_fallback.extend(["--cookies", self.cookies_file])
            try:
                subprocess.run(cmd_fallback, check=True)
            except Exception as e:
                print(f"Audio fallback download attempt skipped: {e}")

        return output_path

    def has_audio_stream(self, file_path: str) -> bool:
        if not shutil.which("ffprobe"):
            print("ffprobe not available on path; skipping audio verification.")
            return True

        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "a",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            file_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            return "audio" in result.stdout.lower()
        except Exception as e:
            print(f"ffprobe check failed: {e}")
            return True
