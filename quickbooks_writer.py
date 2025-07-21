import os
import requests
import json

# Cargar tokens desde el archivo generado en /callback
with open("quickbooks_token.json", "r") as f:
    tokens = json.load(f)

ACCESS_TOKEN = tokens["access_token"]
REALM_ID = tokens["realm_id"]

QUICKBOOKS_BASE_URL = f"https://quickbooks.api.intuit.com/v3/company/{REALM_ID}"

HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

def obtener_cliente_id_por_correo(correo):
    query = f"select * from Customer where PrimaryEmailAddr = '{correo}'"
    url = f"{QUICKBOOKS_BASE_URL}/query?query={requests.utils.quote(query)}"
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
    # Esto es manual. Podrías mapear códigos con Item IDs reales si quieres.
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

    return crear_invoice_api_call(invoice_data)


