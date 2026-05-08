import os
import time
import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_CHANNEL_ID = "C094NE421NV"
API_UPLOAD_ENDPOINT = "https://travify-api.onrender.com/upload/"

client = WebClient(token=SLACK_BOT_TOKEN)
last_ts = None

def get_file_url(file):
    url = file.get("url_private_download") or file.get("url_private")
    if not url:
        file_id = file.get("id")
        if file_id:
            try:
                info = client.files_info(file=file_id)
                full = info["file"]
                url = full.get("url_private_download") or full.get("url_private")
            except SlackApiError as e:
                print(f"files.info error: {e.response['error']}")
    return url

def get_latest_file():
    global last_ts
    try:
        response = client.conversations_history(channel=SLACK_CHANNEL_ID, limit=10)
        for msg in response["messages"]:
            if "files" not in msg:
                continue
            for file in msg["files"]:
                if file.get("filetype") != "pdf":
                    continue
                if last_ts is not None and msg["ts"] <= last_ts:
                    continue
                last_ts = msg["ts"]
                url = get_file_url(file)
                if url:
                    return url, file.get("name", "itinerary.pdf")
                else:
                    print(f"Archivo sin URL: {file.get('id')}")
    except SlackApiError as e:
        print(f"Error conversations_history: {e.response['error']}")
    return None, None

def download_and_upload_pdf(url, filename):
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    pdf = requests.get(url, headers=headers)
    if pdf.status_code == 200:
        print(f"✅ PDF descargado: {filename} ({len(pdf.content)} bytes)")
        files = {"file": (filename, pdf.content, "application/pdf")}
        r = requests.post(API_UPLOAD_ENDPOINT, files=files)
        print("Respuesta servidor:", r.json())
    else:
        print(f"❌ Fallo descarga ({pdf.status_code}): {url}")

if __name__ == "__main__":
    print("🎧 Escuchando canal de Slack...")
    while True:
        url, filename = get_latest_file()
        if url:
            print(f"📄 Nuevo PDF: {filename}")
            download_and_upload_pdf(url, filename)
        time.sleep(10)
