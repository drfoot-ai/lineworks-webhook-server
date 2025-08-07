from flask import Flask, request
import time
import jwt
import requests
import sqlite3
from datetime import datetime
import os
from openai import OpenAI

app = Flask(__name__)

# === LINE WORKS BOT設定 ===
CLIENT_ID = "D8vdojtove_ySt0oV38k"
SERVICE_ACCOUNT = "3yvvr.serviceaccount@drfoot"
CLIENT_SECRET = "kYN7FIdQq0"
BOT_ID = "10519782"
PRIVATE_KEY_PATH = "private_20250804154856.key"
TOKEN_URL = "https://auth.worksmobile.com/oauth2/v2.0/token"
PORT = int(os.environ.get("PORT", 10000))


# === OpenAI設定 ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY2")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# === formatted_reflex_text.txt読み込み ===
reflex_data = {}
try:
    with open("formatted_reflex_text.txt", "r", encoding="utf-8") as f:
        for line in f:
            # 「\n」を本来の改行に変換
            line = line.strip().replace("\\n", "\n")
            parts = line.split(" ", 1)
            if len(parts) == 2:
                keyword, description = parts
                reflex_data[keyword] = description
    print("✅ formatted_reflex_text.txt を読み込みました", flush=True)
except Exception as e:
    print("⚠️ 反射区データ読み込みエラー:", e, flush=True)





# === DB初期化 ===
def init_db():
    try:
        conn = sqlite3.connect("messages.db")
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            message TEXT,
            timestamp TEXT
        )
        ''')
        conn.commit()
        conn.close()
        print("✅ messagesテーブルを確認/作成完了", flush=True)
    except Exception as e:
        print("❌ DB初期化エラー:", e, flush=True)

# === メッセージ保存 ===
def save_message(user_id, message_text):
    try:
        conn = sqlite3.connect("messages.db")
        cursor = conn.cursor()
        timestamp = datetime.now().isoformat()
        cursor.execute("INSERT INTO messages (user_id, message, timestamp) VALUES (?, ?, ?)",
                       (user_id, message_text, timestamp))
        conn.commit()
        conn.close()
        print("💾 メッセージ保存完了", flush=True)
    except Exception as e:
        print("❌ メッセージ保存エラー:", e, flush=True)

# === アクセストークン取得 ===
def get_access_token():
    try:
        iat = int(time.time())
        exp = iat + 3600
        payload = {
            "iss": CLIENT_ID,
            "sub": SERVICE_ACCOUNT,
            "iat": iat,
            "exp": exp,
            "aud": TOKEN_URL
        }
        with open(PRIVATE_KEY_PATH, "rb") as f:
            private_key = f.read()
        jwt_token = jwt.encode(payload, private_key, algorithm='RS256')
        if isinstance(jwt_token, bytes):
            jwt_token = jwt_token.decode('utf-8')

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwt_token,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope": "bot"
        }
        response = requests.post(TOKEN_URL, headers=headers, data=data)
        if response.status_code == 200:
            print("🔑 AccessToken取得成功", flush=True)
            return response.json()["access_token"]
        else:
            print("❌ アクセストークン取得失敗:", response.text, flush=True)
            return None
    except Exception as e:
        print("⚠️ アクセストークン処理エラー:", e, flush=True)
        return None

# === AI応答処理 ===
def ask_ai(question):
    # 1️⃣ ローカル辞書を優先
    for key in reflex_data:
        if key in question:
            print(f"📌 ローカルデータから回答: {key}", flush=True)
            return reflex_data[key]

    # 2️⃣ OpenAIを利用
    if not OPENAI_API_KEY:
        return "現在AIサービスは利用できません。"

    try:
        SYSTEM_PROMPT = """
        あなたは足つぼ反射区の専門Botです。ユーザーから部位名や症状名を入力された場合、
        その反射区の位置と、刺激による効果・効能を簡潔に説明してください。

        【ルール】
        - 回答は反射区の解説に限定してください。
        - 反射区と関係のない話題には
        「申し訳ありませんが、反射区に関すること以外にはお答えできません。」
        - 医療行為や診断はせず、健康維持・リラクゼーション目的で説明してください。
        """

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question}
            ],
            temperature=0.3
        )

        if not hasattr(response, "choices") or len(response.choices) == 0:
            return "現在AIサーバーが利用制限中です。しばらく待ってからお試しください。"

        return response.choices[0].message.content.strip()

    except Exception as e:
        print("⚠️ AIエラー:", e, flush=True)
        return "現在AIサーバーが利用制限中です。しばらく待ってからお試しください。"

# === LINE WORKS返信処理 ===
def reply_message(account_id, message_text):
    access_token = get_access_token()
    if not access_token:
        print("⚠️ アクセストークンなし、返信不可", flush=True)
        return

    ai_reply = ask_ai(message_text)

    url = f"https://www.worksapis.com/v1.0/bots/{BOT_ID}/users/{account_id}/messages"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    data = {
        "content": {
            "type": "text",
            "text": ai_reply
        }
    }

    response = requests.post(url, headers=headers, json=data)
    print("📩 返信ステータス:", response.status_code, flush=True)
    print("📨 返信レスポンス:", response.text, flush=True)

# === Webhookエンドポイント ===
@app.route('/callback', methods=['POST'])
def webhook():
    try:
        data = request.get_json(force=True)
        print("🔔 Webhook受信データ:", data, flush=True)

        account_id = data["source"]["userId"]
        user_message = data["content"]["text"]
        print("📨 受信メッセージ:", user_message, flush=True)

        save_message(account_id, user_message)
        reply_message(account_id, user_message)

    except Exception as e:
        print("⚠️ 受信エラー:", e, flush=True)
    return "OK", 200

@app.route('/', methods=['GET'])
def health_check():
    return "LINE WORKS Webhook Server is running."

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=PORT)
