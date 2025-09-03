import json
import gspread
from google.oauth2.service_account import Credentials

# IDs que me diste
SHEET_ID_TRAVIFY   = "1uY7ifI73AoZ-aXF0EbJWa1sLIj0iihLo4oO6iUd34AE"
SHEET_ID_LOGISTICA = "1km7hs-0r1ktkXh8csaiD20ZiU3k-nVg9zDiUmAAUQBI"

def _client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    with open("/etc/secrets/credentials.json") as f:
        creds_dict = json.load(f)
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)

def _ws(sheet_id):
    sh = _client().open_by_key(sheet_id)
    return sh.get_worksheet(0)  # primera pestaña

def escribir_raw_travify(data):
    ws = _ws(SHEET_ID_TRAVIFY)
    codigos = data.get("codigos_detectados", []) or []
    factura = data.get("facturacion", {}) or {}
    rows = []
    for it in codigos:
        rows.append([
            it.get("codigo",""),
            it.get("valor",""),
            factura.get("1A",""),
            factura.get("2A",""),
            factura.get("3A",""),
            factura.get("4A",""),
            it.get("descripcion",""),
        ])
    if rows:
        ws.append_rows(rows, value_input_option="USER_ENTERED")

def escribir_logistica_min(data):
    ws = _ws(SHEET_ID_LOGISTICA)
    codigos = data.get("codigos_detectados", []) or []
    factura = data.get("facturacion", {}) or {}
    cliente = factura.get("1A","")
    fecha   = factura.get("3A","")  # usa 4A si prefieres fin
    rows = []
    for it in codigos:
        rows.append([cliente, it.get("descripcion") or "", fecha])
    if rows:
        ws.append_rows(rows, value_input_option="USER_ENTERED")
