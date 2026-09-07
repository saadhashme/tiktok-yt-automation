import os
import sys
import requests
from typing import Optional

# Reconfigure stdout for UTF-8 compatibility on Windows console
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

class DiscordNotifier:
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")

    def send_notification(self, title: str, description: str, color: int = 0x3498db, fields: list = None):
        if not self.webhook_url:
            try:
                print(f"[Notifier Log] {title}: {description}")
            except UnicodeEncodeError:
                safe_title = title.encode("ascii", "ignore").decode("ascii")
                safe_desc = description.encode("ascii", "ignore").decode("ascii")
                print(f"[Notifier Log] {safe_title}: {safe_desc}")
            return

        embed = {
            "title": title,
            "description": description,
            "color": color,
            "fields": fields or []
        }

        payload = {
            "embeds": [embed]
        }

        try:
            response = requests.post(self.webhook_url, json=payload, timeout=10)
            response.raise_for_status()
        except Exception as e:
            try:
                print(f"Failed to send Discord webhook alert: {e}")
            except UnicodeEncodeError:
                print("Failed to send Discord webhook alert.")
