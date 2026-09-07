import sys
import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow

# Allow http for local token exchange
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

def main():
    if len(sys.argv) < 2:
        print("Error: Please provide the redirected URL.")
        sys.exit(1)

    redirected_url = sys.argv[1]

    flow = InstalledAppFlow.from_client_secrets_file(
        'credentials/client_secret_channel_1.json',
        scopes=SCOPES,
        redirect_uri='http://localhost',
        state='KC2t5SeqYSJkGnYVoBgwHHur1aark3'
    )

    flow.fetch_token(authorization_response=redirected_url)
    creds = flow.credentials

    os.makedirs('tokens', exist_ok=True)

    # Save token for channel_1
    token_path_1 = 'tokens/channel_1_token.json'
    with open(token_path_1, 'w', encoding='utf-8') as f:
        f.write(creds.to_json())
    print(f"Successfully generated OAuth token: {token_path_1}")

    # Copy token to all 13 channels
    for i in range(2, 14):
        t_path = f"tokens/channel_{i}_token.json"
        with open(t_path, 'w', encoding='utf-8') as f:
            f.write(creds.to_json())

    print("Tokens saved for all 13 channels successfully!")

if __name__ == "__main__":
    main()
