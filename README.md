# Facebook Page Monitor (self-hosted, free edition)

Apne managed/kisi bhi **public** Facebook Pages ko monitor karta hai aur naya
post aane par dashboard me turant log dikhata hai. Yeh koi paid service
(Graph API ya Apify) use NAHI karta — sab kuch free, self-hosted Python se
chalta hai using `kevinzg/facebook-scraper` library.

## ⚠️ Zaroori disclaimer (please poora padho)

Yeh library Facebook ke public HTML structure ko parse karke data nikalti
hai — koi official API nahi. Iska matlab:

- **Break ho sakta hai**: Jab bhi Facebook apna page layout/HTML badalta hai,
  scraping tootne ka risk hai. Isko fix karne ke liye
  `pip install --upgrade facebook-scraper` chalao — community isse
  regularly patch karti hai, lekin turant fix ki guarantee nahi hai.
- **IP ban ka risk**: Bahut zyada ya bahut jaldi-jaldi requests bhejne se
  Facebook temporarily tumhari server IP block kar sakta hai. Isliye:
  - Har page check ke beech **random delay** (5-15 sec) already built-in hai
  - Poll interval kam se kam **1 hour** rakho (default already 1 hour hai)
  - Bahut saare pages (50+) monitor karne ho to residential proxy lena
    consider karo
- **Legal/ethical**: Sirf public data hi nikalta hai (koi login/private data
  nahi), lekin phir bhi Facebook ke Terms of Service ke against maana ja
  sakta hai. Apni risk tolerance ke hisab se decide karo.

Agar reliability zyada important hai aur budget available hai, **Apify**
jaisi managed service (jisme proxies/anti-bot unke side handle hota hai)
zyada stable option hai — is project ka purana Apify+n8n version chat history
me upar available hai.

## Architecture

```
Flask app (app.py)
   → APScheduler background job har 1 hour (adjustable) me chalta hai
   → MongoDB se monitored pages ki list uthata hai
   → har page ke liye facebook_scraper.get_posts() call karta hai
   → naye posts detect karta hai (last_post_id se compare)
   → MongoDB "logs" collection me insert karta hai
   → Dashboard (index.html) har 15 sec me auto-refresh hoke naye logs dikhata hai
```

Sab kuch ek hi Python process me chalta hai — koi external workflow tool
(n8n) ki zaroorat nahi.

## Setup

```bash
cd fb_monitor
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

MongoDB local chalane ke liye:
```bash
mongod --dbpath /path/to/data
```
Ya MongoDB Atlas ka free tier (512MB) use kar sakte ho — bas `.env` me
`MONGO_URI` update kar do.

## Run

```bash
python app.py
```

Browser me kholo: http://localhost:5000

## Page kaise add karo

Dashboard ke "Add Page" form me sirf public Facebook Page ka URL daalo:
```
https://www.facebook.com/nasa
```
Koi login, token, ya cookie ki zaroorat nahi.

## Kaise kaam karta hai

- Background scheduler (APScheduler) har `POLL_INTERVAL_SECONDS` (default
  3600 = 1 hour) me har page ke naye posts check karta hai
- Har page check ke beech `MIN_DELAY_SECONDS`–`MAX_DELAY_SECONDS` (default
  5-15 sec) ka random delay hai — IP ban risk kam karne ke liye
- Naya post milte hi MongoDB me log save hota hai
- Dashboard har 15 second me auto-refresh hoke naye logs dikhata hai
- "Refresh Now" button se turant manual check bhi kar sakte ho

## Agar scraping fail hone lage

1. Pehle library update karo: `pip install --upgrade facebook-scraper`
2. Terminal logs check karo — `[Page Name] Fetch fail hua: ...` jaisa
   warning dikhega jisme exact error hoga
3. Agar IP-ban lagta hai (bahut saare requests fail ho rahe ho ek saath),
   `POLL_INTERVAL_SECONDS` aur `MIN/MAX_DELAY_SECONDS` badha do
4. Agar phir bhi na chale, Apify wala reliable-but-paid approach consider karo

## Costs

- Poori tarah **free** — koi per-post ya per-request charge nahi
- Sirf apna server/VPS chalane ka cost (agar cloud pe host kar rahe ho)
- MongoDB: local free, ya MongoDB Atlas free tier (512MB)
- Agar proxies use karni pade (bahut saare pages ke liye), unka alag cost hoga

## Railway par Deploy karna

1. Is project ko GitHub repo me push karo (ya Railway CLI se directly deploy karo)
2. https://railway.app par jao → **New Project** → **Deploy from GitHub repo**
3. Railway apne aap `Procfile` aur `requirements.txt` detect kar lega
4. **Environment Variables** set karo (Railway dashboard → Variables):
   - `MONGO_URI` — apna MongoDB Atlas connection string (Railway khud MongoDB
     host nahi karta easily, isliye **MongoDB Atlas free tier** use karo:
     https://www.mongodb.com/cloud/atlas — 512MB free)
   - `MONGO_DB_NAME` — `fb_monitor`
   - `POLL_INTERVAL_SECONDS` — `3600` (ya jitna chahiye)
   - `PORT` ki chinta mat karo — Railway yeh khud set karta hai
5. Deploy hote hi Railway ek public URL de dega (e.g. `xxx.up.railway.app`)

⚠️ **Zaroori baat**: Railway (aur zyadatar PaaS platforms) **shared IP ranges**
use karte hain — matlab ho sakta hai us IP range se pehle hi kisi aur user
ki activity ki wajah se Facebook ne use flag kar rakha ho. Agar deploy karne
ke baad scraping consistently fail ho, yeh ek common reason hota hai.
Is case me options: (a) Railway ka static/dedicated IP add-on try karo,
(b) residential proxy add karo, ya (c) apna khud ka VPS (DigitalOcean,
Hetzner) use karo jahan tumhari IP dedicated hogi.

**Local dev ke liye** ab bhi `python app.py` use karo. **Production
(Railway)** ke liye `Procfile` `gunicorn` se app start karta hai
(`workers=1` rakha hai jaanbujh ke, taaki background scheduler duplicate
na chale).

## Project Structure

```
fb_monitor/
├── app.py              # Flask routes + scheduler startup
├── monitor.py          # facebook-scraper polling logic
├── db.py               # MongoDB helpers
├── config.py           # env config (Mongo URI, poll interval, PORT)
├── Procfile            # Railway/gunicorn start command
├── requirements.txt
├── .env.example
└── templates/
    └── index.html      # Dashboard — HTML+CSS+JS sab ek hi file me
```
