import os
import json
import gspread
from google.oauth2.service_account import Credentials


def escribir_en_google_sheets(data):
    print("📦 DATA RECIBIDA EN sheet_writer.py:")
    print(json.dumps(data, indent=2))  # ✅ ESTA LÍNEA ESTABA MAL INDENTADA

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_dict = json.loads(os.getenv("GOOGLE_CREDS"))
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)

    client = gspread.authorize(credentials)

    try:
        sheet = client.open_by_key("1uY7ifI73AoZ-aXF0EbJWa1sLIj0iihLo4oO6iUd34AE").sheet1
        print("✅ Hoja abierta correctamente.")

        codigos = data.get("codigos_detectados", [])
        factura = data.get("facturacion", {})

        for item in codigos:
            fila = [
                item.get("codigo", ""),
                item.get("valor", ""),
                factura.get("1A", ""),  # Nombre
                factura.get("2A", ""),  # Correo
                factura.get("3A", ""),  # Fecha Inicio
                factura.get("4A", "")   # Fecha Fin
            ]
            print(f"➡️ Escribiendo fila: {fila}")
            sheet.append_row(fila)

        print("✅ Todos los datos fueron escritos correctamente.")

    except Exception as e:
        print(f"❌ Error al escribir en Google Sheets: {e}")

        print(f"❌ Error al escribir en Google Sheets: {e}")
