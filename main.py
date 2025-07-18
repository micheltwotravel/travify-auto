from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sheet_writer import escribir_en_google_sheets
from fastapi import Request


import fitz  # PyMuPDF
import re
import traceback
import requests
import os
import aiohttp


app = FastAPI(
    title="PDF to Google Sheets API",
    description="Sube un PDF y guarda los datos extraídos en Sheets",
    version="1.0"
)

# Habilita CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from dotenv import load_dotenv
load_dotenv()
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")


@app.post("/upload/")
async def upload_pdf(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        with open("temp.pdf", "wb") as f:
            f.write(contents)
        print("PDF guardado")

        doc = fitz.open("temp.pdf")
        texto = ""
        for page in doc:
            texto += page.get_text()
        doc.close()
        print("Texto extraído")

        codigos = re.findall(r"\[(\w{2}\d{3})\]\[(\d+)\]", texto)
        facturacion = re.findall(r"\[(\w{2})\]\[([^\]]+)\]", texto)
        print("Códigos y facturación extraídos")

        data = {
            "codigos_detectados": [{"codigo": c, "valor": int(v)} for c, v in codigos],
            "facturacion": {clave: valor for clave, valor in facturacion if clave in ["1A", "2A", "3A", "4A"]}
        }

        print("Data construida:", data)
        escribir_en_google_sheets(data)
        print("Datos escritos en Sheets")

        # ✅ ESTE BLOQUE DEBE IR DENTRO DEL TRY
        nombre = data["facturacion"].get("1A", "Cliente desconocido")
        fecha_inicio = data["facturacion"].get("3A", "Fecha inicio")
        fecha_fin = data["facturacion"].get("4A", "Fecha fin")
        servicios = "\n".join([f'{s["codigo"]}: ${s["valor"]}' for s in data["codigos_detectados"]])
        mensaje = (
            f"Servicios detectados correctamente para {nombre}\n"
            f"Fecha de inicio: {fecha_inicio}\n"
            f"Fecha de fin: {fecha_fin}\n\n"
            f"{servicios}\n\n"
            f"Gracias. Enviando la información al equipo de finanzas."
        )

        # Enviar mensaje a Slack
        channel_id = "C094NE421NV"
        headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
        async with aiohttp.ClientSession() as session:
            await session.post("https://slack.com/api/chat.postMessage", headers=headers, json={
                "channel": channel_id,
                "text": mensaje
            })

        return data

    except Exception as e:
        print("ERROR:", traceback.format_exc())
        return {"error": traceback.format_exc()}


@app.post("/slack/events")
async def slack_events(req: Request):
    body = await req.json()

    # Verificación inicial de Slack (cuando activas la URL)
    if "challenge" in body:
        return {"challenge": body["challenge"]}

    event = body.get("event", {})
    subtype = event.get("subtype")

    # Detectar si el evento es un archivo compartido
    if event.get("type") == "message" and subtype == "file_share":
        file_info = event["files"][0]
        file_url = file_info["url_private_download"]
        filename = file_info["name"]
        user_id = event.get("user")
        channel_id = event.get("channel")

        # Descargar el PDF usando el token del bot
        headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url, headers=headers) as resp:
                if resp.status == 200:
                    pdf_data = await resp.read()
                    with open("temp.pdf", "wb") as f:
                        f.write(pdf_data)

        # Procesar como en tu endpoint de /upload
        import fitz
        doc = fitz.open("temp.pdf")
        texto = ""
        for page in doc:
            texto += page.get_text()
            print("🧾 TEXTO EXTRAÍDO:\n", texto[:1000])  # Ver los primeros 1000 caracteres

        doc.close()

                codigos = re.findall(r"\[(\w{2}\d{3})\]\[(\d+)\]", texto)
        facturacion = re.findall(r"\[(\w{2})\]\[(.*?)\]", texto)

        data = {
            "codigos_detectados": [{"codigo": c, "valor": int(v)} for c, v in codigos],
            "facturacion": {clave: valor for clave, valor in facturacion if clave in ["1A", "2A", "3A", "4A"]}
        }

        escribir_en_google_sheets(data)

        nombre = data["facturacion"].get("1A", "Cliente desconocido")
        fecha_inicio = data["facturacion"].get("3A", "Fecha inicio")
        fecha_fin = data["facturacion"].get("4A", "Fecha fin")
        servicios = "\n".join([f'{s["codigo"]}: ${s["valor"]}' for s in data["codigos_detectados"]])

        mensaje = (
            f"Servicios detectados correctamente para {nombre}\n"
            f"Fecha de inicio: {fecha_inicio}\n"
            f"Fecha de fin: {fecha_fin}\n\n"
            f"{servicios}\n\n"
            f"Gracias. Enviando la información al equipo de finanzas."
        )

        # Enviar respuesta al canal
        async with aiohttp.ClientSession() as session:
            await session.post("https://slack.com/api/chat.postMessage", headers=headers, json={
                "channel": channel_id,
                "text": mensaje
            })


    return {"ok": True}
