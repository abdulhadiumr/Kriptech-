# utils.py
import sqlite3
import os
import random
import string
from PIL import Image, ImageDraw, ImageFont
import requests

def init_db():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INTEGER PRIMARY KEY, balance REAL, email TEXT, verified INTEGER)''')
    conn.commit()
    conn.close()

def generate_captcha():
    captcha_text = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    image = Image.new('RGB', (200, 100), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()  # Use a default font; for better fonts, download and specify
    draw.text((10, 40), captcha_text, fill=(0, 0, 0), font=font)
    image_path = "captcha.png"
    image.save(image_path)
    return captcha_text, image_path

def send_ton_to_faucetpay(email, amount):
    payload = {
        "api_key": FAUCETPAY_API_KEY,
        "to": email,
        "amount": amount,
        "currency": "TON"
    }
    try:
        response = requests.post(FAUCETPAY_WITHDRAW_URL, data=payload)
        if response.status_code == 200 and response.json().get("status") == "success":
            return True, response.json().get("txid", "HASH")
        return False, response.text
    except Exception as e:
        return False, str(e)

from config import FAUCETPAY_API_KEY, FAUCETPAY_WITHDRAW_URL  # Import config values