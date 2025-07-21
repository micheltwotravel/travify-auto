import os
import requests

# Reemplaza este ID con el tuyo real de QuickBooks
QUICKBOOKS_BASE_URL = "https://quickbooks.api.intuit.com/v3/company/1234567890"
ACCESS_TOKEN = os.getenv("QUICKBOOKS_ACCESS_TOKEN")  # Usa Render Secret o .env

HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

def obtener_cliente_id_por_correo(correo):
    url = f"{QUICKBOOKS_BASE_URL}/query?query=select * from Customer where PrimaryEmailAddr = '{correo}'"
    r = requests.get(url, headers=HEADERS)
    clientes = r.json().get("QueryResponse", {}).get("Customer", [])
    return clientes[0]["Id"] if clientes else None

def crear_cliente_si_no_existe(facturacion):
    nombre = facturacion.get("1A", "Cliente Desconocido")
    correo = facturacion.get("2A", "correo@ejemplo.com")

    payload = {
        "DisplayName": nombre,
        "PrimaryEmailAddr": {"Address": correo}
    }

    r = requests.post(f"{QUICKBOOKS_BASE_URL}/customer", headers=HEADERS, json=payload)
    return r.json().get("Customer", {}).get("Id")

def obtener_item_id(codigo):
    # Debes mapear estos códigos con los reales en QuickBooks si es necesario
    return codigo

def crear_invoice_api_call(invoice_data):
    r = requests.post(f"{QUICKBOOKS_BASE_URL}/invoice", headers=HEADERS, json=invoice_data)
    return r.json()

def crear_invoice_en_quickbooks(data):
    codigos = data["codigos_detectados"]
    facturacion = data["facturacion"]

    correo = facturacion.get("2A", "correo@ejemplo.com")
    cliente_id = obtener_cliente_id_por_correo(correo)

    if not cliente_id:
        cliente_id = crear_cliente_si_no_existe(facturacion)

    line_items = []
    for servicio in codigos:
        line_items.append({
            "DetailType": "SalesItemLineDetail",
            "Amount": servicio["valor"],
            "SalesItemLineDetail": {
                "ItemRef": {
                    "value": obtener_item_id(servicio["codigo"]),
                    "name": servicio["codigo"]
                }
            }
        })

    invoice_data = {
        "CustomerRef": {"value": cliente_id},
        "Line": line_items
    }

    crear_invoice_api_call(invoice_data)

