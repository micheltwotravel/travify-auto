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


from sheet_writer import escribir_raw_travify, escribir_logistica_min

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
    """
    Soporta:
      <texto libre> [CODE][VALOR][DESCRIPCION]
      <texto libre> [CODE][VALOR]
      [CODE][VALOR]                   (usa la línea previa como descripción)
    Prioridad: si viene [DESCRIPCION], se usa; si no, usa el texto a la izquierda (head);
    si tampoco hay, usa la línea previa no vacía.
    """
    codigos = []
    facturacion = {}

    lines = [l.strip() for l in texto.splitlines()]
    prev_nonempty = ""

    for line in lines:
        if line:
            prev_nonempty = line

        # Caso con 2 o 3 corchetes en la MISMA línea
        m = re.search(
            r'^(?P<head>.*?)?\s*\[(?P<code>[A-Z]{2}\d{3})\]\s*\[(?P<val>\d+)\](?:\s*\[(?P<desc>[^\]]+)\])?',
            line
        )
        if m:
            code = m.group('code')
            val  = m.group('val')
            desc = m.group('desc')
            if not desc:
                head = (m.group('head') or '').strip(' -—:·')
                desc = head if head else prev_nonempty.strip(' -—:·')
            codigos.append({
                "codigo": code,
                "valor": int(val) if val else None,
                "descripcion": (desc or "").strip()
            })
            continue

        # Fallback: si aparecen [CODE][VAL] sin head en la línea
        for mm in re.finditer(r'\[(?P<code>[A-Z]{2}\d{3})\]\s*\[(?P<val>\d+)\]', line):
            codigos.append({
                "codigo": mm.group('code'),
                "valor": int(mm.group('val')),
                "descripcion": prev_nonempty.strip(' -—:·') or ""
            })

    # Campos [1A]..[4A]
    for campo, defecto in [("1A","Cliente desconocido"),
                           ("2A","correo@ejemplo.com"),
                           ("3A","Fecha inicio"),
                           ("4A","Fecha fin")]:
        patron = re.search(rf"\[{campo}\]\s*\[([^\]]+)\]", texto)
        facturacion[campo] = patron.group(1) if patron else defecto

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
    
import asyncio
import aiohttp

# --- REEMPLAZA TODO TU /slack/events POR ESTO ---

@app.post("/slack/events")
async def slack_events(req: Request):
    body = await req.json()

    # 1) verificación inicial de Slack
    if "challenge" in body:
        return {"challenge": body["challenge"]}

    # 2) responde INMEDIATO para evitar timeout de Slack (<3s)
    asyncio.create_task(_procesar_evento_slack(body))
    return {"ok": True}


async def _procesar_evento_slack(body: dict):
    try:
        event = body.get("event", {}) or {}
        event_id = body.get("event_id")
        if not event_id:
            return

        # de-dup
        if event_id in eventos_procesados:
            print(f"⚠️ Evento duplicado ignorado: {event_id}")
            return
        guardar_evento(event_id)

        etype   = event.get("type")
        subtype = event.get("subtype")

        # =========================
        # Caso A) message.file_share
        # =========================
        if etype == "message" and subtype == "file_share":
            files = event.get("files") or []
            if not files:
                print("⚠️ No se encontraron archivos en el evento Slack (message.file_share).")
                return
            file_url   = files[0].get("url_private_download")
            channel_id = event.get("channel") or event.get("channel_id")
            if not file_url:
                print("⚠️ file_url vacío.")
                return
            await _procesar_pdf(file_url, channel_id)
            return

        # =========================
        # Caso B) file_shared (evento raíz)
        # =========================
        if etype == "file_shared":
            file_id   = event.get("file_id")
            channel_id = event.get("channel_id") or event.get("channel")
            if not file_id:
                print("⚠️ file_id vacío en file_shared.")
                return

            async with aiohttp.ClientSession(headers={
                "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                "Accept": "application/json; charset=utf-8"
            }) as session:
                # files.info para obtener la URL privada de descarga
                async with session.post("https://slack.com/api/files.info", data={"file": file_id}) as r:
                    info = await r.json()
                    if not info.get("ok"):
                        print("❌ files.info falló:", info)
                        return
                    file_url = info["file"].get("url_private_download")
                    if not file_url:
                        print("⚠️ No vino url_private_download en files.info.")
                        return
            await _procesar_pdf(file_url, channel_id)
            return

        print(f"ℹ️ Evento ignorado: type={etype} subtype={subtype}")

    except Exception as e:
        print("❌ Error en _procesar_evento_slack:", e)


async def _procesar_pdf(file_url: str, channel_id: str | None):
    """Descarga el PDF, extrae datos, escribe Sheets, crea factura y postea resultado."""
    try:
        async with aiohttp.ClientSession(headers={
            "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
            "Accept": "application/json; charset=utf-8"
        }) as session:
            async with session.get(file_url) as resp:
                if resp.status != 200:
                    print("❌ No se pudo descargar el archivo:", resp.status)
                    return

                pdf_data = await resp.read()

                if not pdf_data.startswith(b'%PDF'):
                    print("❌ El archivo descargado NO es un PDF válido.")
                    if channel_id:
                        await session.post("https://slack.com/api/chat.postMessage", json={
                            "channel": channel_id,
                            "text": "❌ El archivo subido no es un PDF válido. Por favor intenta nuevamente con otro archivo."
                        })
                    return

                # Extrae, escribe y factura
                texto = extraer_texto_pdf_bytes(pdf_data)
                codigos, facturacion = extraer_codigos_y_factura(texto)
                data = {"codigos_detectados": codigos, "facturacion": facturacion}

                # Sheets
                escribir_raw_travify(data)     # Detalle completo
                escribir_logistica_min(data)   # Cliente / Descripción / Fecha

                # QuickBooks
                resultado = crear_invoice_en_quickbooks(data)
                if not resultado:
                    if channel_id:
                        await session.post("https://slack.com/api/chat.postMessage", json={
                            "channel": channel_id,
                            "text": "⚠️ No se pudo generar la factura. Verifica QuickBooks OAuth."
                        })
                    return

                # Mensaje de confirmación a Slack
                nombre       = facturacion.get("1A", "Cliente desconocido")
                fecha_inicio = facturacion.get("3A", "Fecha inicio")
                fecha_fin    = facturacion.get("4A", "Fecha fin")
                servicios = "\n".join([
                    f'{s["codigo"]} – {s.get("descripcion","")} : ${s["valor"]}'
                    if s.get("valor") is not None
                    else f'{s["codigo"]} – {s.get("descripcion","")} : (sin valor)'
                    for s in codigos
                ])
                factura_url = resultado.get("invoice_url", "No disponible")

                if channel_id:
                    await session.post("https://slack.com/api/chat.postMessage", json={
                        "channel": channel_id,
                        "text": (
                            "🧾 Factura generada en QuickBooks\n"
                            f"👤 Cliente: {nombre}\n"
                            f"📅 Desde: {fecha_inicio} hasta {fecha_fin}\n"
                            f"💼 Servicios:\n{servicios}\n\n"
                            f"🔗 Ver factura: {factura_url}\n\n"
                            "✅ Enviado al equipo de finanzas."
                        )
                    })

    except Exception as e:
        print("❌ Error en _procesar_pdf:", e)


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




@app.post("/facturar")
async def facturar(request: Request):
    try:
        data = await request.json()
        resultado = crear_invoice_en_quickbooks(data)
        return {"ok": True, "resultado": resultado}
    except Exception as e:
        print("❌ Error en /facturar:", e)
        return {"ok": False, "error": str(e)}
        




