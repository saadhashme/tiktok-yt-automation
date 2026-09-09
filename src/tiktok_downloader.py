import os
import json
import re
import subprocess
import shutil
from typing import List, Dict, Any, Optional

from src.audio_processor import AudioProcessor

class TikTokDownloader:
    def __init__(self, cookies_file: Optional[str] = "cookies.txt", downloads_dir: str = "./downloads"):
        self.cookies_file = cookies_file
        self.downloads_dir = downloads_dir
        os.makedirs(self.downloads_dir, exist_ok=True)
        self.audio_processor = AudioProcessor()

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

    def download_video(self, video_id: str, video_url: Optional[str] = None, username: Optional[str] = None) -> "tuple[str, bool]":
        """Returns (video_path, audio_is_copyright_safe). See
        AudioProcessor.replace_background_music for what "safe" means --
        it's an objective check, not just "the pipeline didn't crash"."""
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

        output_path = self.normalize_for_shorts(output_path)
        output_path, audio_clean = self.audio_processor.replace_background_music(output_path)

        return output_path, audio_clean

    def _probe_dimensions(self, file_path: str) -> Optional[tuple]:
        cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "json",
            file_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            streams = json.loads(result.stdout).get("streams") or []
            if not streams:
                return None
            return streams[0].get("width"), streams[0].get("height")
        except Exception as e:
            print(f"ffprobe dimension check failed: {e}")
            return None

    def _detect_crop(self, file_path: str) -> Optional[tuple]:
        cmd = ["ffmpeg", "-i", file_path, "-vf", "cropdetect=24:2:0", "-t", "1.5", "-f", "null", "-"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            matches = re.findall(r"crop=(\d+):(\d+):(\d+):(\d+)", result.stderr)
            if not matches:
                return None
            return tuple(int(v) for v in matches[-1])
        except Exception as e:
            print(f"ffmpeg cropdetect failed: {e}")
            return None

    def normalize_for_shorts(self, file_path: str) -> str:
        """Ensure the downloaded video is genuinely vertical/square so YouTube
        classifies the upload as a Short. TikTok videos are normally already
        vertical, but some download paths can return a landscape-dimensioned
        file (either real landscape footage, or vertical content pillarboxed
        inside a landscape frame). YouTube's Shorts classifier looks at the
        actual encoded pixel dimensions, not just how the video looks, so we
        detect and fix that here rather than relying on #Shorts tags alone.
        """
        if not shutil.which("ffprobe") or not shutil.which("ffmpeg"):
            print("ffprobe/ffmpeg not available; skipping Shorts orientation check.")
            return file_path

        dims = self._probe_dimensions(file_path)
        if not dims or not dims[0] or not dims[1]:
            return file_path
        width, height = dims

        if height >= width:
            return file_path

        print(f"Warning: downloaded video is landscape ({width}x{height}); adjusting for Shorts eligibility.")
        working_path = file_path

        crop = self._detect_crop(file_path)
        if crop:
            cw, ch, cx, cy = crop
            if ch > cw and (cw, ch) != (width, height):
                cropped_path = file_path.replace(".mp4", "_cropped.mp4")
                cmd = ["ffmpeg", "-y", "-i", file_path, "-vf", f"crop={cw}:{ch}:{cx}:{cy}",
                       "-c:a", "copy", cropped_path]
                try:
                    subprocess.run(cmd, check=True, capture_output=True, text=True)
                    width, height = self._probe_dimensions(cropped_path) or (cw, ch)
                    working_path = cropped_path
                except subprocess.CalledProcessError as e:
                    print(f"Crop attempt failed: {e.stderr}; falling back to pad.")

        if height >= width:
            if working_path != file_path:
                os.remove(file_path)
            return working_path

        # Genuine landscape footage after crop attempt - fill the vertical
        # canvas with a blurred, zoomed copy of the same video behind the
        # full, uncropped original (Reels/Shorts-style blur-fill) instead of
        # plain black bars, so the whole original frame stays visible.
        padded_path = file_path.replace(".mp4", "_padded.mp4")
        filter_complex = (
            "[0:v]split=2[bgsrc][fgsrc];"
            "[bgsrc]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,gblur=sigma=20[bg];"
            "[fgsrc]scale=1080:-2[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2[outv]"
        )
        cmd = ["ffmpeg", "-y", "-i", working_path, "-filter_complex", filter_complex,
               "-map", "[outv]", "-map", "0:a?", "-c:a", "copy", padded_path]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            os.remove(working_path)
            return padded_path
        except subprocess.CalledProcessError as e:
            print(f"Blur-fill to vertical canvas failed: {e.stderr}; falling back to letterbox pad.")
            vf = "scale=1080:-2,pad=1080:1920:(1080-iw)/2:(1920-ih)/2:black"
            fallback_cmd = ["ffmpeg", "-y", "-i", working_path, "-vf", vf, "-c:a", "copy", padded_path]
            try:
                subprocess.run(fallback_cmd, check=True, capture_output=True, text=True)
                os.remove(working_path)
                return padded_path
            except subprocess.CalledProcessError as e2:
                print(f"Fallback letterbox padding also failed: {e2.stderr}; uploading original file as-is.")
                return working_path

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
