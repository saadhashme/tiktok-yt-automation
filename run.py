import argparse
import sys
import os
from dotenv import load_dotenv

# Force UTF-8 encoding for Windows stdout/stderr
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.config import Config
from src.channel_runner import ChannelRunner

def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="TikTok to YouTube Shorts Automation Pipeline")
    parser.add_argument("--slot", type=int, required=True, help="Slot number (e.g. 1 or 2)")
    parser.add_argument("--channel", type=str, required=True, help="Channel ID (e.g. channel_1)")
    parser.add_argument("--dry-run", action="store_true", help="Perform a dry run without actual upload")

    args = parser.parse_args()

    config = Config("channels.yaml")
    channel_cfg = config.get_channel(args.channel)

    if not channel_cfg:
        print(f"Error: Channel '{args.channel}' not found in channels.yaml configuration.")
        sys.exit(1)

    runner = ChannelRunner(channel_cfg, dry_run=args.dry_run)
    runner.run_slot(args.slot)

if __name__ == "__main__":
    main()
