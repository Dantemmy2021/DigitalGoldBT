import requests
from django.conf import settings

def send_whatsapp_message(to_number, message):
    """
    to_number: must be 2348012345678 format. No + or spaces
    """
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": message}
    }
    
    try:
        response = requests.post(settings.WHATSAPP_API_URL, json=payload, headers=headers, timeout=10)
        print("WHATSAPP RESPONSE:", response.json()) # for debugging
        return response.status_code == 200, response.json()
    except Exception as e:
        print("WHATSAPP ERROR:", e)
        return False, str(e)

def format_phone(number):
    """Convert 0803... or +234... to 234803..."""
    if not number:
        return None
    number = str(number).strip().replace(" ", "").replace("-", "").replace("+", "")
    if number.startswith("0"):
        number = "234" + number[1:]
    if number.startswith("234"):
        return number
    return None