# TikTok to YouTube Shorts Automation Pipeline

Automated system to scrape TikTok videos without watermarks using `yt-dlp`, verify audio streams, upload them to YouTube Shorts via YouTube Data API v3, track states in SQLite, and notify via Discord.

## 🚀 Supported Channels Configured

The system is configured with 13 target TikTok handles in `channels.yaml`:

| Channel ID | TikTok Handle | Videos/Day | Mode |
|---|---|---|---|
| `channel_1` | `@truthdaddy` | 2 | `popular_split` |
| `channel_2` | `@voxcortexofficial` | 2 | `popular_split` |
| `channel_3` | `@ethancshow` | 2 | `popular_split` |
| `channel_4` | `@datingadvicex` | 2 | `popular_split` |
| `channel_5` | `@taylor_cruz_podcast` | 2 | `popular_split` |
| `channel_6` | `@gooodthings2` | 2 | `popular_split` |
| `channel_7` | `@mindfuldating0` | 2 | `popular_split` |
| `channel_8` | `@inspiring.moments8` | 2 | `popular_split` |
| `channel_9` | `@jax_motivation` | 2 | `popular_split` |
| `channel_10` | `@wiseminute4` | 2 | `popular_split` |
| `channel_11` | `@mindd_voice` | 2 | `popular_split` |
| `channel_12` | `@steve_ralph_official` | 2 | `popular_split` |
| `channel_13` | `@josh_hill_podcast` | 2 | `popular_split` |

---

## 🛠 Local Setup & Dry Run Testing

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Test Dry Run (No Upload):**
   ```bash
   python run.py --slot 1 --channel channel_1 --dry-run
   ```

---

## 🔑 Minting YouTube OAuth Tokens (Headless)

Run the no-browser re-authentication utility for any channel:
```bash
python reauth_nobrowser.py channel_1
```
Follow the URL on screen, authenticate with the channel's Gmail, paste the redirect URL back into the console, and it will generate `tokens/channel_1_token.json`.

---

## ☁️ GitHub Secrets Setup

Store the following secrets in your GitHub Repository (`Settings > Secrets and variables > Actions`):

- `DISCORD_WEBHOOK_URL`: Your Discord webhook endpoint.
- `TIKTOK_COOKIES`: Base64 string of Netscape `cookies.txt`.
- `CHANNEL_1_CLIENT_SECRET`: Base64 string of `credentials/client_secret_channel_1.json`
- `CHANNEL_1_TOKEN`: Base64 string of `tokens/channel_1_token.json`
- *(Repeat secret pairs for each channel ID)*

---

## ⏰ Cron-Job.org Trigger Configuration

Add 2 cron jobs per channel on [cron-job.org](https://cron-job.org):

- **Target URL:** `https://api.github.com/repos/YOUR_USER/YOUR_REPO/actions/workflows/upload-slot1.yml/dispatches`
- **Method:** `POST`
- **Headers:**
  - `Accept`: `application/vnd.github.v3+json`
  - `Authorization`: `Bearer YOUR_GITHUB_PAT`
  - `User-Agent`: `cron-job.org`
- **Body (JSON):**
  ```json
  {
    "ref": "main",
    "inputs": {
      "channel": "channel_1",
      "dry_run": false
    }
  }
  ```
