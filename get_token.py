from google_auth_oauthlib.flow import InstalledAppFlow
import os

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def main():
    flow = InstalledAppFlow.from_client_secrets_file(
        'credentials/client_secret_channel_1.json',
        scopes=SCOPES,
        redirect_uri='http://localhost'
    )
    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
    print("\n" + "="*80)
    print("NEW AUTHORIZATION URL (COPIED BELOW)")
    print("="*80)
    print(auth_url)
    print("="*80 + "\n")

if __name__ == "__main__":
    main()
