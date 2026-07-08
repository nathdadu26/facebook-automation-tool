import logging
import random
import time
from urllib.parse import urlparse

from apscheduler.schedulers.background import BackgroundScheduler
from facebook_scraper import get_posts

import db
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("monitor")


def extract_page_slug(facebook_url: str) -> str:
    """
    Facebook page URL se uska slug/username nikalta hai, jo facebook_scraper
    library ko chahiye (poora URL nahi, sirf 'nasa' jaisa naam).
    e.g. https://www.facebook.com/nasa/  ->  nasa
    """
    path = urlparse(facebook_url).path.strip("/")
    return path.split("/")[0] if path else facebook_url


def check_all_pages():
    """Har monitored page ko check karta hai aur naye posts ke liye log banata hai."""
    pages = db.get_all_pages()

    for page in pages:
        facebook_url = page["facebook_url"]
        page_name = page["page_name"]
        last_post_id = page.get("last_post_id")
        slug = extract_page_slug(facebook_url)

        try:
            posts = list(get_posts(slug, pages=1))
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
