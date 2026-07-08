import logging
import random
import re
import time
from urllib.parse import urlparse, parse_qs

from apscheduler.schedulers.background import BackgroundScheduler
from playwright.sync_api import sync_playwright

import db
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("monitor")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def extract_page_identifier(facebook_url: str) -> dict:
    """
    Facebook URL do format me aata hai:
      1. Page (username wala): https://www.facebook.com/nasa
      2. Profile (numeric ID wala): https://www.facebook.com/profile.php?id=123456&sk=reels_tab

    Return: {"url": <full www.facebook.com URL jo Playwright khol sakta hai>}
    """
    parsed = urlparse(facebook_url)
    path = parsed.path.strip("/")
    query = parse_qs(parsed.query)

    if path.lower() == "profile.php" and "id" in query:
        fb_id = query["id"][0]
        return {"url": f"https://www.facebook.com/profile.php?id={fb_id}"}

    slug = path.split("/")[0] if path else facebook_url
    return {"url": f"https://www.facebook.com/{slug}/"}


def _derive_post_id(post_url: str) -> str:
    """Post permalink se ek stable ID nikalta hai. Na mile to poora URL hi ID ban jata hai."""
    match = re.search(r"(?:story_fbid|fbid|/posts/|/videos/|/photos/)[/=](\d+)", post_url)
    if match:
        return match.group(1)
    return post_url


def fetch_recent_posts(facebook_url: str, count: int = 2):
    """
    Headless Chromium (Playwright) se page/profile khol ke uske recent posts
    ka permalink + text nikalta hai.

    NOTE: Yeh best-effort hai — Facebook apna DOM structure baar-baar badalta
    hai, kabhi checkpoint/login-wall bhi dikha sakta hai. 0 posts aana kabhi
    kabhi normal hai, khaaskar agar bahut jaldi-jaldi requests bheji jaayein.
    """
    identifier = extract_page_identifier(facebook_url)
    posts = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        try:
            page.goto(identifier["url"], wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)

            # Lazy-loaded posts render karne ke liye thoda scroll karo
            for _ in range(2):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(1500)

            articles = page.query_selector_all('div[role="article"]')

            for article in articles[:count]:
                link_el = article.query_selector(
                    'a[href*="/posts/"], a[href*="story_fbid"], '
                    'a[href*="/videos/"], a[href*="/photos/"]'
                )
                post_url = link_el.get_attribute("href") if link_el else ""
                if post_url and post_url.startswith("/"):
                    post_url = "https://www.facebook.com" + post_url

                text = article.inner_text()[:500] if article else ""

                if post_url:
                    posts.append({
                        "post_id": _derive_post_id(post_url),
                        "post_url": post_url,
                        "text": text,
                        "time": "",
                    })
        except Exception as e:
            logger.warning(f"Playwright fetch fail hua ({facebook_url}): {e}")
        finally:
            browser.close()

    return posts[:count]


def fetch_and_log_initial_posts(facebook_url: str, page_name: str, count: int = 2):
    """
    Naya page/profile add hote hi turant uske sabse recent 'count' posts fetch
    karke logs me daal deta hai, taaki dashboard pe turant post links dikhein.
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
            logger.warning(f"[{page_name}] Fetch fail hua: {e}")
            continue

        if not posts:
            db.update_last_checked(facebook_url)
            continue

        # Playwright se posts newest-first order me aate hain (page pe jaisa dikhta hai)
        new_posts = []
        for post in posts:
            post_id = post.get("post_id")
            if post_id == last_post_id:
                break
            new_posts.append(post)

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

        # Rate limiting: har page ke beech random delay
        time.sleep(random.uniform(config.MIN_DELAY_SECONDS, config.MAX_DELAY_SECONDS))


def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_all_pages, "interval", seconds=config.POLL_INTERVAL_SECONDS)
    scheduler.start()
    logger.info(f"Scheduler started, har {config.POLL_INTERVAL_SECONDS}s me check hoga.")
    return scheduler
