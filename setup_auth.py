"""
YouTube OAuth2 Kurulumu
Ilk calistirmada tarayicida Google hesabi ile yetkilendirme yapar.
"""

import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRETS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "client_secrets.json")
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.json")


def main():
    if not os.path.exists(CLIENT_SECRETS_FILE):
        print("HATA: client_secrets.json bulunamadi!")
        print()
        print("1. https://console.cloud.google.com adresine git")
        print("2. Yeni proje olustur veya mevcut projeyi sec")
        print("3. YouTube Data API v3'u etkinlestir")
        print("4. Credentials -> OAuth consent screen -> User type: External")
        print("5. Credentials -> Create Credentials -> OAuth client ID")
        print("6. Application type: Desktop app")
        print("7. client_secrets.json indir ve proje dizinine koy")
        print()
        print("Onden YouTube kanal ID'ni de bul:")
        print("  https://www.youtube.com/channel/KANAL_IDN")
        sys.exit(1)

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Token yenileniyor...")
            creds.refresh(Request())
        else:
            print("Tarayicida yetkilendirme baslatiliyor...")
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRETS_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        print("Token kaydedildi: token.json")
    else:
        print("Token zaten gecerli.")

    print()
    print("YouTube OAuth2 kurulumu tamamlandi!")
    print("Artik youtube-automator'u kullanabilirsin.")


if __name__ == "__main__":
    main()
