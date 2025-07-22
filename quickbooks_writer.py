import os
import requests
import json

# Cargar tokens desde el archivo generado en /callback
def cargar_tokens():
    try:
        with open("quickbooks_token.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print("⚠️ No se encontró quickbooks_token.json")
        return None

def obtener_cliente_id_por_correo(correo, base_url, headers):
    query = f"select * from Customer where PrimaryEmailAddr = '{correo}'"
    url = f"{base_url}/query?query={requests.utils.quote(query)}"
    r = requests.get(url, headers=headers)
    clientes = r.json().get("QueryResponse", {}).get("Customer", [])
    return clientes[0]["Id"] if clientes else None

def crear_cliente_si_no_existe(facturacion, base_url, headers):
    nombre = facturacion.get("1A", "Cliente Desconocido")
    correo = facturacion.get("2A", "correo@ejemplo.com")

    payload = {
        "DisplayName": nombre,
        "PrimaryEmailAddr": {"Address": correo}
    }

    r = requests.post(f"{base_url}/customer", headers=headers, json=payload)
    return r.json().get("Customer", {}).get("Id")

def obtener_item_id(codigo):
    return codigo  # Reemplazar por mapeo real si lo tienes

def crear_invoice_api_call(invoice_data, base_url, headers):
    r = requests.post(f"{base_url}/invoice", headers=headers, json=invoice_data)
    return r.json()

def crear_invoice_en_quickbooks(data):
    tokens = cargar_tokens()
    if not tokens:
        print("🚫 No se pudo cargar el token. Conecta QuickBooks primero.")
        return

    access_token = tokens["access_token"]
    realm_id = tokens["realm_id"]

    base_url = f"https://quickbooks.api.intuit.com/v3/company/{realm_id}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    codigos = data["codigos_detectados"]
    facturacion = data["facturacion"]

    correo = facturacion.get("2A", "correo@ejemplo.com")
    cliente_id = obtener_cliente_id_por_correo(correo, base_url, headers)

    if not cliente_id:
        cliente_id = crear_cliente_si_no_existe(facturacion, base_url, headers)

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

    resultado = crear_invoice_api_call(invoice_data, base_url, headers)

    invoice_id = resultado.get("Invoice", {}).get("Id")
    doc_number = resultado.get("Invoice", {}).get("DocNumber")
    invoice_url = f"https://app.qbo.intuit.com/app/invoice?txnId={invoice_id}" if invoice_id else "No disponible"

    return {
        "success": True,
        "invoice_id": invoice_id,
        "doc_number": doc_number,
        "invoice_url": invoice_url,
        "detalle": resultado
    }

