from fastapi import FastAPI, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from sheet_writer import escribir_en_google_sheets
import fitz  # PyMuPDF
import re
import traceback
import os
import aiohttp
import json

# Carga token desde Render Secrets
with open("/etc/secrets/slack_token", "r") as f:
    SLACK_BOT_TOKEN = f.read().strip()

# Archivo donde se almacenan eventos procesados
EVENTOS_FILE = "eventos_procesados.json"

# Cargar eventos previos si existen
if os.path.exists(EVENTOS_FILE):
    with open(EVENTOS_FILE, "r") as f:
        eventos_procesados = set(json.load(f))
else:
    eventos_procesados = set()

def guardar_evento(event_id):
    eventos_procesados.add(event_id)
    with open(EVENTOS_FILE, "w") as f:
        json.dump(list(eventos_procesados), f)

app = FastAPI(
    title="PDF to Google Sheets API",
    description="Sube un PDF y guarda los datos extraídos en Sheets",
    version="1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def extraer_codigos_y_factura(texto):
    codigos = []
    facturacion = {}
    matches = re.findall(r"\[([A-Z]{2}\d{3})\](?:\[(\d+)\])?", texto)
    for codigo, valor in matches:
        if valor:
            codigos.append({"codigo": codigo, "valor": int(valor)})
    patron_factura = re.findall(r"\[(\dA)\]\[(.*?)\]", texto)
    for campo, valor in patron_factura:
        facturacion[campo] = valor
    return codigos, facturacion

def extraer_texto_pdf_bytes(pdf_bytes):
    texto_total = ""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for i, page in enumerate(doc):
            texto = page.get_text()
            print(f"📄 Texto página {i+1}:", texto[:500])
            texto_total += texto + "\n"
    return texto_total

@app.post("/upload/")
async def upload_pdf(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        texto = extraer_texto_pdf_bytes(contents)
        codigos, facturacion = extraer_codigos_y_factura(texto)

        data = {
            "codigos_detectados": codigos,
            "facturacion": facturacion
        }

        escribir_en_google_sheets(data)
        return {"ok": True, "data": data}

    except Exception as e:
        print("ERROR:", traceback.format_exc())
        return {"error": traceback.format_exc()}

@app.post("/slack/events")
async def slack_events(req: Request):
    body = await req.json()

    if "challenge" in body:
        return {"challenge": body["challenge"]}

    event_id = body.get("event_id")
    if event_id in eventos_procesados:
        print(f"⚠️ Evento duplicado ignorado: {event_id}")
        return {"ok": True}
    guardar_evento(event_id)

    event = body.get("event", {})
    subtype = event.get("subtype")

    if event.get("type") == "message" and subtype == "file_share":
        if "files" not in event or not event["files"]:
            print("⚠️ No se encontraron archivos en el evento Slack.")
            return {"error": "No hay archivos"}

        file_info = event["files"][0]
        file_url = file_info["url_private_download"]
        channel_id = event.get("channel") or event.get("channel_id")

        async with aiohttp.ClientSession(headers={
            "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
            "Accept": "application/json; charset=utf-8"
        }) as session:
            async with session.get(file_url) as resp:
                if resp.status != 200:
                    return {"error": "No se pudo descargar el archivo"}

                pdf_data = await resp.read()

                if not pdf_data.startswith(b'%PDF'):
                    print("❌ El archivo descargado NO es un PDF válido.")
                    await session.post("https://slack.com/api/chat.postMessage", headers={
                        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                        "Accept": "application/json; charset=utf-8"
                    }, json={
                        "channel": channel_id,
                        "text": "❌ El archivo subido no es un PDF válido. Por favor intenta nuevamente con otro archivo."
                    })
                    return {"error": "Archivo no es PDF"}

                texto = extraer_texto_pdf_bytes(pdf_data)
                codigos, facturacion = extraer_codigos_y_factura(texto)

                data = {
                    "codigos_detectados": codigos,
                    "facturacion": facturacion
                }

                escribir_en_google_sheets(data)

                nombre = facturacion.get("1A", "Cliente desconocido")
                fecha_inicio = facturacion.get("3A", "Fecha inicio")
                fecha_fin = facturacion.get("4A", "Fecha fin")
                servicios = "\n".join([f'{s["codigo"]}: ${s["valor"]}' for s in codigos])

                mensaje = (
                    f"Servicios detectados correctamente para {nombre}\n"
                    f"Fecha de inicio: {fecha_inicio}\n"
                    f"Fecha de fin: {fecha_fin}\n\n"
                    f"{servicios}\n\n"
                    f"Gracias. Enviando la información al equipo de finanzas."
                )

                await session.post("https://slack.com/api/chat.postMessage", headers={
                    "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                    "Accept": "application/json; charset=utf-8"
                }, json={
                    "channel": channel_id,
                    "text": mensaje
                })

    return {"ok": True}
