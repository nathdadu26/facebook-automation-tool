import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "fb_monitor")
# Railway apne aap PORT env var set karta hai deploy ke time - usko priority do
FLASK_PORT = int(os.getenv("PORT", os.getenv("FLASK_PORT", "5000")))

# Har kitne seconds me saare pages check karne hain (default 3600 = 1 hour)
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "3600"))

# Har page check ke beech random delay (IP ban risk kam karne ke liye)
MIN_DELAY_SECONDS = float(os.getenv("MIN_DELAY_SECONDS", "5"))
MAX_DELAY_SECONDS = float(os.getenv("MAX_DELAY_SECONDS", "15"))
