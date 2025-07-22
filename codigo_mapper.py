codigo_a_servicio = {
    "AT001": "ATV",
    "BA002": "Baby Sitters",
    "BA003": "Bartender",
    "BE004": "Beach Club",
    "BO005": "Boat Lunch Box",
    "BO006": "Bodyguard",
    "CA007": "Cake",
    "CR008": "Car Rental",
    "CT009": "Cartagena Tours",
    "CB010": "Chef BBQ",
    "CD011": "Chef Dinner",
    "CL012": "Chef Lunch at the villa",
    "CC013": "Chef catering",
    "CO014": "Chef on board",
    "CL015": "Cleaning",
    "CO016": "Concierge",
    "CO017": "Cook",
    "DJ018": "DJ",
    "DC019": "Dance Class",
    "DR020": "Driver",
    "FL021": "FlyBoard",
    "GO022": "Golf",
    "GR023": "Groceries",
    "GY024": "Gym",
    "HM025": "Hair & Makeup",
    "HE026": "Helicopter",
    "IV027": "IV Therapy",
    "IH028": "Island Hopping",
    "LA029": "Laundry",
    "LD030": "Liquor and Drinks",
    "MA031": "Massage",
    "MT032": "Medellin Tours",
    "MT033": "Mexican Tours",
    "ND034": "NightClub (Deposit)",
    "NF035": "Non - Food Purchases",
    "OC036": "O - Chef",
    "OS037": "Other services",
    "PH038": "Photographer",
    "PF039": "Private Flight",
    "RE040": "Rentals",
    "SD041": "Scuba Diving",
    "SE042": "Services",
    "SN043": "Snorkel",
    "SP044": "Spa",
    "TI045": "Tickets",
    "TR046": "Transport",
    "WR047": "Wrestling",
    "YO048": "Yoga"
}

from servicio_a_id import servicio_a_id

def obtener_item_id_desde_codigo(codigo):
    nombre_servicio = codigo_a_servicio.get(codigo)
    return servicio_a_id.get(nombre_servicio)


def obtener_item_id_desde_codigo(codigo):
    nombre_servicio = codigo_a_servicio.get(codigo)
    return servicio_a_id.get(nombre_servicio, "1")  # "1" como fallback para pruebas
