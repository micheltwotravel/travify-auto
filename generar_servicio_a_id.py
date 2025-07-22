## generar_servicio_a_id.py

from codigo_mapper import codigo_a_servicio
import os, json, requests
from urllib.parse import quote
from dotenv import load_dotenv
load_dotenv()

def cargar_tokens():
    with open("/etc/secrets/quickbooks_token.json", "r") as f:
        return json.load(f)

def obtener_item_ids(servicios):
    tokens = cargar_tokens()
    access_token = tokens["access_token"]
    realm_id = tokens["realm_id"]
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }
    base_url = f"https://quickbooks.api.intuit.com/v3/company/{realm_id}"
    nombre_a_id = {}

    for nombre in servicios:
        query = f"SELECT Id FROM Item WHERE Name = '{nombre}'"
        url = f"{base_url}/query?query={quote(query)}"
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            items = r.json().get("QueryResponse", {}).get("Item", [])
            if items:
                nombre_a_id[nombre] = items[0]["Id"]
                print(f"✅ {nombre} → {items[0]['Id']}")
            else:
                print(f"⚠️ No encontrado: {nombre}")
        else:
            print(f"❌ Error con {nombre}:", r.text)
    return nombre_a_id

if __name__ == "__main__":
    servicios = list(set(codigo_a_servicio.values()))
    resultado = obtener_item_ids(servicios)
    with open("servicio_a_id.py", "w") as f:
        f.write("servicio_a_id = " + json.dumps(resultado, indent=4))
