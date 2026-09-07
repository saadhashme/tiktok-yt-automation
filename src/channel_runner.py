import os
from typing import Dict, Any
from src.db import DatabaseManager
from src.tiktok_downloader import TikTokDownloader
from src.youtube_uploader import YouTubeUploader
from src.notifier import DiscordNotifier

class ChannelRunner:
    def __init__(self, channel_config: Dict[str, Any], dry_run: bool = False):
        self.config = channel_config
        self.channel_id = channel_config["id"]
        self.dry_run = dry_run

        self.db_path = f"data/{self.channel_id}.db"
        self.db = DatabaseManager(self.db_path)
        self.downloader = TikTokDownloader()
        self.notifier = DiscordNotifier()

    def run_slot(self, slot: int):
        print(f"--- Starting run for Channel {self.channel_id} | Slot {slot} | Dry Run: {self.dry_run} ---")

        # 1. Per-day guard check
        if self.db.slot_already_ran_today(slot):
            msg = f"Slot {slot} has already succeeded today for channel {self.channel_id}. Skipping."
            print(msg)
            return

        # 2. List profile videos
        tiktok_handle = self.config["tiktok_username"]
        videos = self.downloader.list_user_videos(tiktok_handle, limit=150)
        if not videos:
            msg = f"No videos found or failed to fetch profile for TikTok @{tiktok_handle}."
            print(msg)
            self.db.record_run(slot, "no_content", msg)
            self.notifier.send_notification("Upload Warning", msg, color=0xe67e22)
            return

        # 3. Filter videos already posted
        unposted_videos = []
        for v in videos:
            v_id = str(v.get("id") or v.get("url", "").split("/")[-1])
            if v_id and not self.db.is_video_posted(v_id):
                unposted_videos.append((v_id, v))

        if not unposted_videos:
            msg = f"All fetched videos for @{tiktok_handle} have already been uploaded."
            print(msg)
            self.db.record_run(slot, "no_content", msg)
            self.notifier.send_notification("No Content", msg, color=0xf1c40f)
            return

        # 4. Pick candidate video based on upload mode (e.g. popular_split)
        selected_id, selected_video = unposted_videos[0]
        title = selected_video.get("title") or f"Short from {tiktok_handle}"
        target_url = selected_video.get("url") or selected_video.get("webpage_url")

        print(f"Selected candidate video TikTok ID: {selected_id} | Title: '{title}'")

        if self.dry_run:
            msg = f"[DRY RUN] Would download video {selected_id} ('{title}') and upload to YouTube channel {self.config.get('youtube_channel_name')}."
            print(msg)
            self.db.record_run(slot, "dry_run", msg)
            self.notifier.send_notification("Dry Run Succeeded", msg, color=0x2ecc71)
            return

        # 5. Download video
        try:
            downloaded_file = self.downloader.download_video(selected_id, video_url=target_url, username=tiktok_handle)
        except Exception as e:
            err_msg = f"Failed to download video {selected_id}: {e}"
            print(err_msg)
            self.db.record_run(slot, "failed", err_msg)
            self.notifier.send_notification("Download Failed", err_msg, color=0xe74c3c)
            return

        # 6. Upload to YouTube
        try:
            uploader = YouTubeUploader(self.channel_id)
            yt_id = uploader.upload_short(downloaded_file, title=title)

            # Record success in DB
            self.db.record_posted_video(selected_id, yt_id, status="uploaded", title=title)
            self.db.record_run(slot, "success", f"Uploaded video {selected_id} -> YouTube ID {yt_id}")

            # Notify Discord
            success_msg = f"Uploaded TikTok video `{selected_id}` to YouTube channel `{self.config.get('youtube_channel_name')}`!\nWatch: https://youtube.com/shorts/{yt_id}"
            self.notifier.send_notification("Upload Successful! 🚀", success_msg, color=0x2ecc71)

        except Exception as e:
            err_msg = f"Failed to upload video {selected_id} to YouTube: {e}"
            print(err_msg)
            self.db.record_run(slot, "failed", err_msg)
            self.notifier.send_notification("Upload Failed ❌", err_msg, color=0xe74c3c)

        finally:
            # Clean up local downloaded file
            if os.path.exists(downloaded_file):
                os.remove(downloaded_file)
