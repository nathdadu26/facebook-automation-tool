import os
from flask import Flask, jsonify, request, render_template
import db
import monitor
import config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))

# Scheduler yahan module-level pe start hota hai taaki yeh gunicorn (Railway/production)
# aur seedha "python app.py" (local dev) dono ke sath kaam kare.
# NOTE: Agar production me multiple gunicorn workers use karoge to yeh job
# har worker me alag-alag chalega — isliye Procfile me workers=1 rakha gaya hai.
monitor.start_scheduler()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/stats")
def api_stats():
    return jsonify(db.get_stats())


@app.route("/api/pages", methods=["GET"])
def api_get_pages():
    pages = db.get_all_pages()
    for p in pages:
        p["_id"] = str(p["_id"])
    return jsonify(pages)


@app.route("/api/pages", methods=["POST"])
def api_add_page():
    data = request.get_json(force=True)
    facebook_url = data.get("facebook_url", "").strip()
    page_name = data.get("page_name", "").strip()

    if not facebook_url:
        return jsonify({"error": "facebook_url required hai"}), 400

    if not page_name:
        page_name = facebook_url

    db.add_page(facebook_url, page_name)

    # Turant recent 2 posts fetch karke logs me daal do aur response me bhi bhej do
    recent_posts = monitor.fetch_and_log_initial_posts(facebook_url, page_name, count=2)

    return jsonify({"success": True, "recent_posts": recent_posts})


@app.route("/api/pages/<path:facebook_url>", methods=["DELETE"])
def api_delete_page(facebook_url):
    db.delete_page(facebook_url)
    return jsonify({"success": True})


@app.route("/api/logs")
def api_get_logs():
    logs = db.get_recent_logs(limit=100)
    for log in logs:
        log["_id"] = str(log["_id"])
        log["notified_at"] = log["notified_at"].isoformat()
    return jsonify(logs)


@app.route("/api/check-now", methods=["POST"])
def api_check_now():
    """Manually turant check trigger karne ke liye."""
    monitor.check_all_pages()
    return jsonify({"success": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.FLASK_PORT, debug=False)
