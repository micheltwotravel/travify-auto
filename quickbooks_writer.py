import os
import requests
import json
from urllib.parse import quote
from codigo_mapper import codigo_a_servicio, obtener_item_id_desde_codigo



# Cargar tokens desde el archivo generado en /callback
def cargar_tokens():
    try:
        # Intentar leer primero desde /tmp (token refrescado)
        if os.path.exists("/tmp/quickbooks_token.json"):
            with open("/tmp/quickbooks_token.json", "r") as f:
                return json.load(f)
        # Si no existe, leer desde el Secret File de Render
        with open("/etc/secrets/quickbooks_token.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print("⚠️ No se encontró quickbooks_token.json")
        return None

def refrescar_token():
    try:
        # Cargar desde el secret original
        with open("/etc/secrets/quickbooks_token.json", "r") as f:
            tokens = json.load(f)
    except FileNotFoundError:
        print("❌ No hay archivo de tokens en /etc/secrets/")
        return None

    refresh_token = tokens.get("refresh_token")
    client_id = os.getenv("QUICKBOOKS_CLIENT_ID")
    client_secret = os.getenv("QUICKBOOKS_CLIENT_SECRET")

    token_url = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    auth = (client_id, client_secret)
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }

    r = requests.post(token_url, headers=headers, auth=auth, data=data)
    if r.status_code != 200:
        print("❌ Falló el refresh:", r.text)
        return None

    nuevos_tokens = r.json()
    tokens["access_token"] = nuevos_tokens.get("access_token")
    tokens["refresh_token"] = nuevos_tokens.get("refresh_token")

    # Guardar los nuevos tokens en un archivo temporal
    with open("/tmp/quickbooks_token.json", "w") as f:
        json.dump(tokens, f)

    print("🔁 Token actualizado exitosamente (guardado en /tmp)")
    return tokens

def buscar_cliente_por_email(email, base_url, headers):
    # ✅ Reemplazamos 'PrimaryEmailAddr.Address' por 'PrimaryEmailAddr'
    query = f"SELECT Id, DisplayName FROM Customer WHERE PrimaryEmailAddr = '{email}'"
    encoded_query = quote(query)
    url = f"{base_url}/query?query={encoded_query}"

    r = requests.get(url, headers=headers)

    if r.status_code == 200:
        customers = r.json().get("QueryResponse", {}).get("Customer", [])
        if customers:
            return customers[0].get("Id")

    if r.status_code == 401 or "AuthenticationFailed" in r.text:
        print("🔁 Token expirado. Refrescando...")
        tokens = refrescar_token()
        if not tokens:
            return None
        headers["Authorization"] = f"Bearer {tokens['access_token']}"
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            customers = r.json().get("QueryResponse", {}).get("Customer", [])
            if customers:
                return customers[0].get("Id")

    print("❌ Error buscando cliente por correo:", r.text)
    return None

def obtener_item_id(codigo):
    return codigo  # puedes hacer un mapeo real aquí

def crear_invoice_api_call(invoice_data, base_url, headers):
    r = requests.post(f"{base_url}/invoice", headers=headers, json=invoice_data)
    return r.json()

def crear_invoice_en_quickbooks(data):
    tokens = cargar_tokens()
    if not tokens:
        print("🚫 No se pudo cargar el token. Conecta QuickBooks primero.")
        return None

    access_token = tokens["access_token"]
    realm_id = tokens["realm_id"]
    base_url = f"https://quickbooks.api.intuit.com/v3/company/{realm_id}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    # Validar si el token ya está expirado antes de cualquier acción
    prueba_url = f"{base_url}/companyinfo/{realm_id}"
    r = requests.get(prueba_url, headers=headers)
    if r.status_code == 401 or "AuthenticationFailed" in r.text:
        print("🔁 Token expirado antes de empezar. Refrescando...")
        tokens = refrescar_token()
        if not tokens:
            return None
        access_token = tokens["access_token"]
        headers["Authorization"] = f"Bearer {access_token}"

    codigos = data.get("codigos_detectados", [])
    facturacion = data.get("facturacion", {})

    correo = facturacion.get("2A", "correo@ejemplo.com")
    cliente_id = buscar_cliente_por_email(correo, base_url, headers)

    if not cliente_id:
        cliente_id = crear_cliente_si_no_existe(facturacion, base_url, headers)
        if not cliente_id:
            print("❌ No se pudo crear ni encontrar cliente.")
            return None

    line_items = []
    for item in codigos:
        codigo = item["codigo"]
        valor = item["valor"]

        nombre_servicio = codigo_a_servicio.get(codigo)
        if not nombre_servicio:
            print(f"❌ Código no reconocido: {codigo}")
            continue

        item_id = obtener_item_id_desde_codigo(codigo)
        if not item_id:
            print(f"⚠️ No se encontró ID en QuickBooks para {nombre_servicio}")
            continue

        line_items.append({
            "DetailType": "SalesItemLineDetail",
            "Amount": valor,
            "SalesItemLineDetail": {
                "ItemRef": {
                    "value": item_id,
                    "name": nombre_servicio
                }
            }
        })

    if not line_items:
        print("⚠️ No se generó ningún ítem válido para la factura.")
        return None

    invoice_data = {
        "CustomerRef": {"value": cliente_id},
        "Line": line_items
    }

    resultado = crear_invoice_api_call(invoice_data, base_url, headers)

    if resultado.get("Fault", {}).get("Error", [{}])[0].get("Message") == "Token expired":
        print("🔁 Token expirado al facturar. Refrescando...")
        tokens = refrescar_token()
        if not tokens:
            return None
        headers["Authorization"] = f"Bearer {tokens['access_token']}"
        resultado = crear_invoice_api_call(invoice_data, base_url, headers)

    if "Invoice" not in resultado:
        print("❌ Error creando factura:", resultado)
        return None

    invoice_id = resultado["Invoice"].get("Id")
    doc_number = resultado["Invoice"].get("DocNumber")
    invoice_url = f"https://app.qbo.intuit.com/app/invoice?txnId={invoice_id}" if invoice_id else "No disponible"

    return {
        "success": True,
        "invoice_id": invoice_id,
        "doc_number": doc_number,
        "invoice_url": invoice_url,
        "detalle": resultado
    }

    
def obtener_cliente_por_nombre(nombre, base_url, headers):
    query = f"SELECT Id, DisplayName, SyncToken FROM Customer WHERE DisplayName = '{nombre}'"
    url = f"{base_url}/query?query={quote(query)}"
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        customers = r.json().get("QueryResponse", {}).get("Customer", [])
        if customers:
            return customers[0]  # retorna todo el objeto con Id y SyncToken
    print("❌ Error buscando cliente por nombre:", r.text)
    return None

def crear_cliente_si_no_existe(facturacion, base_url, headers):
    nombre = facturacion.get("1A", "Cliente Desconocido")
    correo = facturacion.get("2A", "correo@ejemplo.com")

    # Buscar por correo
    cliente_id = buscar_cliente_por_email(correo, base_url, headers)
    if cliente_id:
        return cliente_id

    # Intentar crear cliente nuevo
    payload = {
        "DisplayName": nombre,
        "PrimaryEmailAddr": {"Address": correo}
    }

    r = requests.post(f"{base_url}/customer", headers=headers, json=payload)

    if r.status_code == 200:
        print("✅ Cliente creado con éxito.")
        return r.json().get("Customer", {}).get("Id")

    elif r.status_code == 400 and "Duplicate Name Exists" in r.text:
        print("⚠️ Nombre ya existe. Buscando cliente por nombre para agregar correo...")

        cliente = obtener_cliente_por_nombre(nombre, base_url, headers)
        if not cliente:
            print("❌ No se pudo encontrar el cliente por nombre.")
            return None

        update_payload = {
            "Id": cliente["Id"],
            "SyncToken": cliente["SyncToken"],
            "sparse": True,
            "PrimaryEmailAddr": {"Address": correo}
        }

        update_url = f"{base_url}/customer"
        update_r = requests.post(update_url, headers=headers, json=update_payload)

        if update_r.status_code == 200:
            print("✅ Cliente actualizado con correo.")
            return cliente["Id"]
        else:
            print("❌ Falló al actualizar cliente existente:", update_r.text)
            return None

    print("❌ Error creando cliente:", r.text)
    return None

item_id = obtener_item_id_desde_codigo(codigo)
if not item_id:
    print(f"❌ Código no encontrado o sin ID: {codigo}")
    continue

