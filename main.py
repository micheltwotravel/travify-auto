from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sheet_writer import escribir_en_google_sheets

import fitz  # PyMuPDF
import re
import traceback

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

        return data

    except Exception as e:
        print("ERROR:", traceback.format_exc())
        return {"error": traceback.format_exc()}
