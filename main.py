from fastapi import FastAPI, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

import os
import re
import json
import fitz  # PyMuPDF
import requests
import traceback
import urllib.parse
import aiohttp

NOMBRES_SERVICIOS = {
    "TR046": "Transporte aeropuerto",
    "CT009": "City tour",
    "SE042": "Servicio especial",
    "OS037": "Taller cigarros",
    "MA031": "Masaje 1 hora",
    "IV027": "Terapia IV",
    "CD011": "Cena chef Niku",
    "BE004": "Beach Club",
    "BA003": "Bartender personal",
    "CB010": "Chef BBQ villa",
    "ND034": "Nightclub VIP",
    "GR023": "Compras y abastecimiento",
    "LD030": "Licores premium",
    "DJ018": "DJ profesional",
    "BO006": "Seguridad privada",
    "SP044": "Spa y tratamientos",
}


from sheet_writer import escribir_en_google_sheets
from quickbooks_writer import crear_invoice_en_quickbooks


with open("/etc/secrets/slack_token", "r") as f:
    SLACK_BOT_TOKEN = f.read().strip()


EVENTOS_FILE = "eventos_procesados.json"


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

    matches = re.findall(r"\[([A-Z]{2}\d{3})\]\s*\[?(\d+)?\]?", texto)
    for codigo, valor in matches:
        codigos.append({
            "codigo": codigo,
            "valor": int(valor) if valor else None  # ← permite que sea None
        })

    for campo in ["1A", "2A", "3A", "4A"]:
        patron = re.search(rf"\[{campo}\]\s*\[([^\]]+)\]", texto)
        facturacion[campo] = patron.group(1) if patron else {
            "1A": "Cliente desconocido",
            "2A": "correo@ejemplo.com",
            "3A": "Fecha inicio",
            "4A": "Fecha fin"
        }[campo]

    return codigos, facturacion



def extraer_texto_pdf_bytes(pdf_bytes):
    texto_total = ""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    for i, page in enumerate(doc):
        texto = page.get_text()
        print(f"📄 Texto página {i+1}:", texto[:500])
        texto_total += texto + "\n"
    return texto_total

@app.api_route("/callback", methods=["GET", "POST"])
async def quickbooks_callback(request: Request):
    if request.method == "GET":
        params = request.query_params
    else:
        params = await request.form()

    code = params.get("code")
    realm_id = params.get("realmId")

    token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
    client_id = os.getenv("QUICKBOOKS_CLIENT_ID")
    client_secret = os.getenv("QUICKBOOKS_CLIENT_SECRET")
    redirect_uri = "https://travify-api.onrender.com/callback"

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    auth = (client_id, client_secret)

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri
    }

    response = requests.post(token_url, headers=headers, auth=auth, data=data)

    if response.status_code != 200:
        return {"error": "Failed to exchange token", "details": response.text}

    tokens = response.json()

    token_data = {
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "realm_id": realm_id
    }

    print("📦 TOKENS:", token_data)

    with open("quickbooks_token.json", "w") as f:
        json.dump(token_data, f)

    return {"ok": True, "msg": "Tokens guardados exitosamente"}

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
                resultado = crear_invoice_en_quickbooks(data)

                if not resultado:
                    await session.post("https://slack.com/api/chat.postMessage", headers={
                        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                        "Accept": "application/json; charset=utf-8"
                    }, json={
                        "channel": channel_id,
                        "text": "⚠️ No se pudo generar la factura. Verifica si QuickBooks está conectado correctamente."
                    })
                    return {"error": "Factura no generada"}

                nombre = facturacion.get("1A", "Cliente desconocido")
                fecha_inicio = facturacion.get("3A", "Fecha inicio")
                fecha_fin = facturacion.get("4A", "Fecha fin")
                servicios = "\n".join([
                    f'{s["codigo"]} – {NOMBRES_SERVICIOS.get(s["codigo"], "Servicio desconocido")}: ${s["valor"]}'
                    if "valor" in s and s["valor"] is not None
                    else f'{s["codigo"]} – {NOMBRES_SERVICIOS.get(s["codigo"], "Servicio desconocido")}: (sin valor)'
                    for s in codigos
                ])
                    
                    
                # Obtener link real de la factura si está disponible
                invoice_id = resultado.get("invoice_id")
                if invoice_id:
                    factura_url = f"https://app.qbo.intuit.com/app/invoice?txnId={invoice_id}"
                else:
                    factura_url = "No disponible"

                mensaje = (
                    f"🧾 Factura generada en QuickBooks\n"
                    f"👤 Cliente: {nombre}\n"
                    f"📅 Desde: {fecha_inicio} hasta {fecha_fin}\n"
                    f"💼 Servicios:\n{servicios}\n\n"
                    f"🔗 Ver factura: {factura_url}\n\n"
                    f"✅ Enviado al equipo de finanzas."
                )

                await session.post("https://slack.com/api/chat.postMessage", headers={
                    "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                    "Accept": "application/json; charset=utf-8"
                }, json={
                    "channel": channel_id,
                    "text": mensaje
                })
                return {"ok": True}


@app.get("/")
def root():
    return {"msg": "Hello from FastAPI on Render!"}

@app.get("/connect")
def connect_to_quickbooks():
    client_id = os.getenv("QUICKBOOKS_CLIENT_ID")
    redirect_uri = "https://travify-api.onrender.com/callback"
    scope = "com.intuit.quickbooks.accounting"
    state = "secure_random_string"  # Puedes mejorar esto con un generador aleatorio real

    auth_url = (
        "https://appcenter.intuit.com/connect/oauth2?"
        f"client_id={client_id}&response_type=code&scope={urllib.parse.quote(scope)}"
        f"&redirect_uri={urllib.parse.quote(redirect_uri)}&state={state}"
    )
    return RedirectResponse(auth_url)

@app.get("/callback")
async def quickbooks_callback(request: Request):
    code = request.query_params.get("code")
    realm_id = request.query_params.get("realmId")

    token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
    client_id = os.getenv("QUICKBOOKS_CLIENT_ID")
    client_secret = os.getenv("QUICKBOOKS_CLIENT_SECRET")
    redirect_uri = "https://travify-api.onrender.com/callback"

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    auth = (client_id, client_secret)

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri
    }

    response = requests.post(token_url, headers=headers, auth=auth, data=data)

    if response.status_code != 200:
        return {"error": "Failed to exchange token", "details": response.text}

    tokens = response.json()

    token_data = {
        "access_token": tokens.get("access_token"),
        "refresh_token": tokens.get("refresh_token"),
        "realm_id": realm_id
    }

    
    print("📦 TOKENS:", token_data)

  
    with open("quickbooks_token.json", "w") as f:
        json.dump(token_data, f)

    return {"ok": True, "msg": "Tokens guardados exitosamente"}


@app.post("/facturar")
async def facturar(request: Request):
    try:
        data = await request.json()
        resultado = crear_invoice_en_quickbooks(data)
        return {"ok": True, "resultado": resultado}
    except Exception as e:
        print("❌ Error en /facturar:", e)
        return {"ok": False, "error": str(e)}
        
