# slack_listener.py
import os
import time
import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_CHANNEL = "invoices-concierge"  # cambia si es otro canal
API_UPLOAD_ENDPOINT = "https://travify-api.onrender.com/upload/"


client = WebClient(token=SLACK_BOT_TOKEN)

# Guarda el timestamp del último archivo procesado
last_ts = None

def get_latest_file():
    global last_ts
    try:
        response = client.conversations_history(channel=SLACK_CHANNEL, limit=10)
        messages = response['messages']

        for msg in messages:
            if 'files' in msg:
                for file in msg['files']:
                    if file['filetype'] == 'pdf' and (last_ts is None or msg['ts'] > last_ts):
                        last_ts = msg['ts']
                        return file['url_private_download'], file['name']

    except SlackApiError as e:
        print(f"Error al obtener mensajes: {e.response['error']}")
    return None, None

def download_and_upload_pdf(url, filename):
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    pdf = requests.get(url, headers=headers)

    if pdf.status_code == 200:
        print(f"PDF descargado: {filename}")
        files = {'file': (filename, pdf.content, 'application/pdf')}
        r = requests.post(API_UPLOAD_ENDPOINT, files=files)
        print("Respuesta del servidor:", r.json())
    else:
        print("Fallo al descargar el archivo")

if __name__ == "__main__":
    while True:
        url, filename = get_latest_file()
        if url:
            print("Nuevo PDF detectado, procesando...")
            download_and_upload_pdf(url, filename)
        time.sleep(10)  # Espera antes de revisar de nuevo
