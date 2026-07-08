from pymongo import MongoClient, DESCENDING
from datetime import datetime, timezone
import config

client = MongoClient(config.MONGO_URI)
db = client[config.MONGO_DB_NAME]

pages_col = db["pages"]
logs_col = db["logs"]

# Indexes: ek facebook_url sirf ek baar add ho, aur post_id duplicate na ho
pages_col.create_index("facebook_url", unique=True)
logs_col.create_index([("facebook_url", 1), ("post_id", 1)], unique=True)


def add_page(facebook_url: str, page_name: str):
    """
    Naya page monitoring list me add karta hai.
    NOTE: Ab access_token ki zaroorat nahi — n8n workflow Apify actor ke
    zariye is facebook_url ko directly scrape karega (Graph API use nahi hota).
    """
    doc = {
        "facebook_url": facebook_url,
        "page_name": page_name,
        "added_at": datetime.now(timezone.utc),
        "last_checked": None,
        "last_post_id": None,
    }
    pages_col.update_one(
        {"facebook_url": facebook_url},
        {"$setOnInsert": doc},
        upsert=True,
    )


def get_all_pages():
    return list(pages_col.find({}))


def delete_page(facebook_url: str):
    pages_col.delete_one({"facebook_url": facebook_url})


def update_last_checked(facebook_url: str, last_post_id: str = None):
    update = {"last_checked": datetime.now(timezone.utc)}
    if last_post_id:
        update["last_post_id"] = last_post_id
    pages_col.update_one({"facebook_url": facebook_url}, {"$set": update})


def add_log(facebook_url: str, page_name: str, post_id: str, post_link: str, message: str, created_time: str):
    """Naya post mila to log entry banata hai. Duplicate ho to silently ignore.
    NOTE: Yeh function ab sirf reference ke liye hai — asli insert n8n workflow
    MongoDB node se seedha karega (README dekho)."""
    try:
        logs_col.insert_one({
            "facebook_url": facebook_url,
            "page_name": page_name,
            "post_id": post_id,
            "post_link": post_link,
            "message": message or "",
            "created_time": created_time,
            "notified_at": datetime.now(timezone.utc),
        })
        return True
    except Exception:
        # duplicate key -> already logged
        return False


def get_recent_logs(limit: int = 50):
    return list(logs_col.find({}).sort("notified_at", DESCENDING).limit(limit))


def get_stats():
    return {
        "total_pages": pages_col.count_documents({}),
        "total_new_posts": logs_col.count_documents({}),
    }
