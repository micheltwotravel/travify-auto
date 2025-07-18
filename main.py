from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sheet_writer import escribir_en_google_sheets
from fastapi import Request

import fitz  # PyMuPDF
import re
import traceback
import requests
import os



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

        # Construir y enviar mensaje a Slack
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

        requests.post(SLACK_WEBHOOK_URL, json={"text": mensaje})


        
        return data

    except Exception as e:
        print("ERROR:", traceback.format_exc())
        return {"error": traceback.format_exc()}

@app.post("/slack/events")
async def slack_events(req: Request):
    body = await req.json()

    # ⚠️ Slack envía un "challenge" al verificar la URL
    if "challenge" in body:
        return {"challenge": body["challenge"]}

    print("Evento recibido de Slack:", body)
    return {"ok": True}
