from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sheet_writer import escribir_en_google_sheets
from fastapi import Request
from pdf2image import convert_from_path
import pytesseract


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

        texto = extraer_texto_ocr("temp.pdf")

        print("Texto extraído")

            
        codigos, facturacion = extraer_codigos_y_factura(texto)

        data = {
            "codigos_detectados": codigos,
            "facturacion": facturacion
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

        async with aiohttp.ClientSession() as session:
            await session.post("https://slack.com/api/chat.postMessage", headers=headers, json={
                "channel": "C094NE421NV",
                "text": mensaje
            })

        return data

    except Exception as e:
        print("ERROR:", traceback.format_exc())
        return {"error": traceback.format_exc()}

@app.post("/slack/events")
async def slack_events(req: Request):
    body = await req.json()

    if "challenge" in body:
        return {"challenge": body["challenge"]}

    event = body.get("event", {})
    subtype = event.get("subtype")

    if event.get("type") == "message" and subtype == "file_share":
        file_info = event["files"][0]
        file_url = file_info["url_private_download"]
        filename = file_info["name"]
        user_id = event.get("user")
        channel_id = event.get("channel")

        headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url, headers=headers) as resp:
                if resp.status == 200:
                    pdf_data = await resp.read()

                    print("Cabecera del archivo descargado:", pdf_data[:10])
                    if not pdf_data.startswith(b'%PDF'):
                        print("❌ El archivo descargado NO es un PDF válido.")
                        return {"error": "Archivo no es PDF"}

                    with open("temp.pdf", "wb") as f:
                        f.write(pdf_data)

        # Procesar como en el endpoint /upload
        texto = extraer_texto_ocr("temp.pdf")
        print("📄 TEXTO COMPLETO EXTRAÍDO:\n", texto)
        
        codigos, facturacion = extraer_codigos_y_factura(texto)

        data = {
            "codigos_detectados": codigos,
            "facturacion": facturacion
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

        async with aiohttp.ClientSession() as session:
            await session.post("https://slack.com/api/chat.postMessage", headers=headers, json={
                "channel": channel_id,
                "text": mensaje
            })

    return {"ok": True}

def extraer_codigos_y_factura(texto):
    codigos = []
    facturacion = {}

    # Extrae códigos de servicio con valor
    matches = re.findall(r"\[([A-Z]{2}\d{3})\](?:\[(\d+)\])?", texto)
    for codigo, valor in matches:
        if valor:
            codigos.append({
                "codigo": codigo,
                "valor": int(valor)
            })

    # Extrae info de facturación
    patron_factura = re.findall(r"\[(\dA)\]\[(.*?)\]", texto)
    for campo, valor in patron_factura:
        facturacion[campo] = valor

    return codigos, facturacion

def extraer_texto_ocr(pdf_path):
    from pdf2image import convert_from_path
    import pytesseract

    pages = convert_from_path(pdf_path)
    texto_total = ""
    for i, page in enumerate(pages):
        texto = pytesseract.image_to_string(page, lang="eng")
        print(f"📄 Texto OCR página {i+1}:\n{texto[:500]}")
        texto_total += texto + "\n"
    return texto_total
