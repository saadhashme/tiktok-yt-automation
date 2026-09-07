import os
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

class YouTubeUploader:
    SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

    def __init__(self, channel_id: str, credentials_dir: str = "credentials", tokens_dir: str = "tokens"):
        self.channel_id = channel_id
        self.credentials_file = os.path.join(credentials_dir, f"client_secret_{channel_id}.json")
        self.token_file = os.path.join(tokens_dir, f"{channel_id}_token.json")
        self.youtube = None

    def authenticate(self):
        creds = None
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, self.SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(self.token_file, "w", encoding="utf-8") as token_out:
                    token_out.write(creds.to_json())
            else:
                if not os.path.exists(self.credentials_file):
                    raise FileNotFoundError(f"Credentials file {self.credentials_file} missing for channel {self.channel_id}")
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, self.SCOPES)
                creds = flow.run_local_server(port=0)
                os.makedirs(os.path.dirname(self.token_file), exist_ok=True)
                with open(self.token_file, "w", encoding="utf-8") as token_out:
                    token_out.write(creds.to_json())

        self.youtube = build('youtube', 'v3', credentials=creds)

    def upload_short(self, video_file_path: str, title: str, description: str = "", tags: list = None) -> str:
        if not self.youtube:
            self.authenticate()

        full_title = f"{title} #Shorts" if "#shorts" not in title.lower() else title
        if len(full_title) > 100:
            full_title = full_title[:95] + "..."

        body = {
            'snippet': {
                'title': full_title,
                'description': f"{description}\n\n#Shorts #Viral #Trending",
                'tags': (tags or []) + ['Shorts', 'TikTok', 'Viral'],
                'categoryId': '24'
            },
            'status': {
                'privacyStatus': 'public',
                'selfDeclaredMadeForKids': False,
            }
        }

        media = MediaFileUpload(video_file_path, chunksize=-1, resumable=True, mimetype='video/mp4')
        request = self.youtube.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media
        )

        print(f"Uploading {video_file_path} to YouTube as '{full_title}'...")
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"Upload progress: {int(status.progress() * 100)}%")

        youtube_id = response.get('id')
        print(f"Upload completed successfully! YouTube Video ID: {youtube_id}")
        return youtube_id
