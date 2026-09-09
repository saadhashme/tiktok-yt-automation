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

        # 4. Try candidates in order until one has a *verified* copyright-safe
        # audio track. Demucs completing without an error is not enough on
        # its own to trust -- real uploads showed the original music still
        # audible even when the pipeline reported success. Rather than
        # publish a video that still carries copyright risk, this tries a
        # few candidates and skips any whose isolated audio fails the
        # objective Audio QC check in AudioProcessor.
        MAX_CANDIDATE_ATTEMPTS = 3
        downloaded_file = None
        selected_id = None
        title = None

        for attempt_id, attempt_video in unposted_videos[:MAX_CANDIDATE_ATTEMPTS]:
            attempt_title = attempt_video.get("title") or f"Short from {tiktok_handle}"
            attempt_url = attempt_video.get("url") or attempt_video.get("webpage_url")

            print(f"Selected candidate video TikTok ID: {attempt_id} | Title: '{attempt_title}'")

            if self.dry_run:
                msg = f"[DRY RUN] Would download video {attempt_id} ('{attempt_title}') and upload to YouTube channel {self.config.get('youtube_channel_name')}."
                print(msg)
                self.db.record_run(slot, "dry_run", msg)
                self.notifier.send_notification("Dry Run Succeeded", msg, color=0x2ecc71)
                return

            try:
                candidate_file, audio_clean = self.downloader.download_video(
                    attempt_id, video_url=attempt_url, username=tiktok_handle
                )
            except Exception as e:
                print(f"Failed to download video {attempt_id}: {e}; trying next candidate.")
                continue

            if audio_clean:
                downloaded_file, selected_id, title = candidate_file, attempt_id, attempt_title
                break

            print(f"Candidate {attempt_id} failed the copyright-safety audio check "
                  f"(original background music likely still audible); discarding and trying next candidate.")
            if os.path.exists(candidate_file):
                os.remove(candidate_file)

        if downloaded_file is None:
            checked = min(len(unposted_videos), MAX_CANDIDATE_ATTEMPTS)
            msg = (f"Checked {checked} candidate video(s) for channel {self.channel_id} but none "
                   f"passed the copyright-safety audio check (original background music could not "
                   f"be verifiably removed). Skipping this slot rather than uploading a video that "
                   f"still carries copyright risk.")
            print(msg)
            self.db.record_run(slot, "skipped_unclean_audio", msg)
            self.notifier.send_notification("Upload Skipped — Audio Not Clean", msg, color=0xe67e22)
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
