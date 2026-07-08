import logging
import random
import time
from urllib.parse import urlparse, parse_qs

from apscheduler.schedulers.background import BackgroundScheduler
from facebook_scraper import get_posts

import db
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("monitor")

FB_MOBILE_BASE = "https://m.facebook.com/"


def extract_page_identifier(facebook_url: str) -> dict:
    """
    Facebook URL do format me aata hai:
      1. Page (username wala): https://www.facebook.com/nasa           -> slug 'nasa'
      2. Profile (numeric ID wala): https://www.facebook.com/profile.php?id=123456&sk=reels_tab
         -> ID query-string me hoti hai, path me nahi, isliye alag handling chahiye

    Return: {"account": <slug ya id>, "start_url": <explicit URL agar profile.php ho, warna None>}
    """
    parsed = urlparse(facebook_url)
    path = parsed.path.strip("/")
    query = parse_qs(parsed.query)

    if path.lower() == "profile.php" and "id" in query:
        fb_id = query["id"][0]
        return {
            "account": fb_id,
            "start_url": f"{FB_MOBILE_BASE}profile.php?id={fb_id}",
        }

    slug = path.split("/")[0] if path else facebook_url
    return {"account": slug, "start_url": None}


def fetch_recent_posts(facebook_url: str, count: int = 2):
    """Kisi bhi page/profile ke sabse recent 'count' posts fetch karta hai (raw list)."""
    identifier = extract_page_identifier(facebook_url)
    kwargs = {"pages": 1}
    if identifier["start_url"]:
        kwargs["start_url"] = identifier["start_url"]

    posts = list(get_posts(identifier["account"], **kwargs))
    return posts[:count]


def fetch_and_log_initial_posts(facebook_url: str, page_name: str, count: int = 2):
    """
    Naya page/profile add hote hi turant uske sabse recent 'count' posts fetch
    karke logs me daal deta hai, taaki dashboard pe turant post links dikhein
    (background scheduler ka wait nahi karna padta).
    """
    try:
        posts = fetch_recent_posts(facebook_url, count=count)
    except Exception as e:
        logger.warning(f"[{page_name}] Initial fetch fail hua: {e}")
        return []

    if not posts:
        return []

    inserted = []
    for post in reversed(posts):  # oldest-first insert karo
        post_id = post.get("post_id")
        post_link = post.get("post_url", "")
        db.add_log(
            facebook_url=facebook_url,
            page_name=page_name,
            post_id=post_id,
            post_link=post_link,
            message=(post.get("text") or "")[:500],
            created_time=str(post.get("time", "")),
        )
        inserted.append({"post_id": post_id, "post_link": post_link})

    newest_id = posts[0].get("post_id")
    db.update_last_checked(facebook_url, last_post_id=newest_id)
    return list(reversed(inserted))  # newest-first return karo response ke liye


def check_all_pages():
    """Har monitored page ko check karta hai aur naye posts ke liye log banata hai."""
    pages = db.get_all_pages()

    for page in pages:
        facebook_url = page["facebook_url"]
        page_name = page["page_name"]
        last_post_id = page.get("last_post_id")

        try:
            posts = fetch_recent_posts(facebook_url, count=10)
        except Exception as e:
            # Facebook ne HTML change kar diya ho, ya rate-limit/IP flag ho jaaye
            # to yahi exception aayega — page skip karke aage badho, crash mat karo
            logger.warning(f"[{page_name}] Fetch fail hua: {e}")
            continue

        if not posts:
            db.update_last_checked(facebook_url)
            continue

        # facebook_scraper posts newest-first return karta hai
        new_posts = []
        for post in posts:
            post_id = post.get("post_id")
            if post_id == last_post_id:
                break
            new_posts.append(post)

        # Pehli baar check ho raha hai to sirf latest post record karo
        if last_post_id is None and new_posts:
            new_posts = new_posts[:1]

        for post in reversed(new_posts):  # oldest-first insert karo
            db.add_log(
                facebook_url=facebook_url,
                page_name=page_name,
                post_id=post.get("post_id"),
                post_link=post.get("post_url", ""),
                message=(post.get("text") or "")[:500],
                created_time=str(post.get("time", "")),
            )
            logger.info(f"[{page_name}] Naya post mila: {post.get('post_url')}")

        newest_id = posts[0].get("post_id") or last_post_id
        db.update_last_checked(facebook_url, last_post_id=newest_id)

        # Rate limiting: har page ke beech random delay, taaki IP ban ka
        # risk kam ho (Facebook rapid-fire requests ko bot samajhta hai)
        time.sleep(random.uniform(config.MIN_DELAY_SECONDS, config.MAX_DELAY_SECONDS))


def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_all_pages, "interval", seconds=config.POLL_INTERVAL_SECONDS)
    scheduler.start()
    logger.info(f"Scheduler started, har {config.POLL_INTERVAL_SECONDS}s me check hoga.")
    return scheduler
