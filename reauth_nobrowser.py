import sys
import os
import json
from google_auth_oauthlib.flow import Flow

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def main():
    channel_id = sys.argv[1] if len(sys.argv) > 1 else "channel_1"
    client_secret_file = f"credentials/client_secret_{channel_id}.json"

    flow = Flow.from_client_secrets_file(
        client_secret_file,
        scopes=SCOPES,
        redirect_uri='http://localhost',
        autogenerate_code_verifier=False
    )

    if len(sys.argv) > 2:
        redirected_url = sys.argv[2]
        flow.fetch_token(authorization_response=redirected_url)
        creds = flow.credentials
        os.makedirs('tokens', exist_ok=True)
        for i in range(1, 14):
            with open(f"tokens/channel_{i}_token.json", 'w', encoding='utf-8') as f:
                f.write(creds.to_json())
        print("Success! OAuth tokens minted and saved for all 13 channels.")
        return

    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')

    print("\n" + "="*80)
    print(f"OAUTH RE-AUTHENTICATION FOR CHANNEL: {channel_id}")
    print("="*80)
    print("1. Open the following URL in your browser:\n")
    print(auth_url)
    print("\n2. Grant permission and copy the full redirected URL from your browser address bar.")
    print("3. Run: py -3.11 reauth_nobrowser.py channel_1 \"<redirected_url>\"\n")

if __name__ == "__main__":
    main()
