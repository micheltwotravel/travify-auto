# generar_servicio_a_id.py

import os
import json
import requests
from urllib.parse import quote
from codigo_mapper import codigo_a_servicio
from dotenv import load_dotenv

load_dotenv()

def cargar_tokens():
    with open("/etc/secrets/quickbooks_token.json", "r") as f:
        return json.load(f)

def obtener_item_ids(servicios):
    tokens = cargar_tokens()
    access_token = tokens["access_token"]
    realm_id = tokens["realm_id"]
    base_url = f"https://quickbooks.api.intuit.com/v3/company/{realm_id}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }

    nombre_a_id = {}

    for nombre in servicios:
        query = f"SELECT Id FROM Item WHERE Name = '{nombre}'"
        url = f"{base_url}/query?query={quote(query)}"
        r = requests.get(url, headers=headers)

        if r.status_code == 200:
            items = r.json().get("QueryResponse", {}).get("Item", [])
            if items:
                item_id = items[0]["Id"]
                nombre_a_id[nombre] = item_id
                print(f"✅ {nombre} → {item_id}")
            else:
                print(f"⚠️ No se encontró: {nombre}")
        else:
            print(f"❌ Error con {nombre}: {r.text}")

    return nombre_a_id

if __name__ == "__main__":
    servicios = list(set(codigo_a_servicio.values()))
    resultado = obtener_item_ids(servicios)

    with open("servicio_a_id.py", "w") as f:
        f.write("servicio_a_id = " + json.dumps(resultado, indent=4))
        print("📁 Diccionario guardado en servicio_a_id.py")
