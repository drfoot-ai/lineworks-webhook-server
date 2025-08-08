from flask import Flask, request
import time
import jwt
import requests
import sqlite3
from datetime import datetime
import os
from openai import OpenAI
import tempfile

# ✅ ここに SYSTEM_PROMPT を定義する
SYSTEM_PROMPT = """
あなたは足つぼ反射区の専門Botです。ユーザーから入力される内容は、体の部位名だけでなく、「症状名」（例：便秘、肩こり、頭痛、不眠、冷え性、むくみなど）の場合もあります。

【あなたの役割】
- 入力されたキーワード（部位名または症状名）に関連する反射区を回答してください。
- 反射区の位置や、刺激による期待される効果を簡潔に説明してください。

【ルール】
- 回答は足裏または手のひらの反射区の解説に限定してください。
- 症状名が入力された場合は、対応する関連反射区を1つ以上示し、それらの刺激による効果を伝えてください。
- 医療行為・診断・病名確定は行わず、「健康維持・リラクゼーション目的」であることを前提にしてください。
- 反射区と無関係な話題には以下の定型文で応答してください：
「申し訳ありませんが、反射区に関すること以外にはお答えできません。」

【例】
ユーザー：「肩こり」  
→ 回答例：「肩こりには肩や首の反射区が効果的です。足の小指の下あたりを刺激すると、肩の緊張が緩和されやすくなります。」

ユーザー：「便秘」  
→ 回答例：「便秘には大腸・小腸の反射区がおすすめです。足裏中央の土踏まずの部分を刺激することで、腸の動きが活性化されやすくなります。」
"""


# 環境変数から秘密鍵の文字列を取得
private_key_content = os.getenv("Private_Key")




# 一時ファイルとして保存（jwt.encodeがファイルではなく文字列を受け取れるならそのままでもOK）
with tempfile.NamedTemporaryFile(delete=False, suffix=".key", mode="w", encoding="utf-8") as tmp_key_file:
    tmp_key_file.write(private_key_content)
    PRIVATE_KEY_PATH = tmp_key_file.name

# これ以降の jwt.encode に渡す部分はそのままでOK







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

        # ✅ 改行処理を追加
        private_key_content = os.getenv("Private_Key").replace("\\n", "\n")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".key", mode="w", encoding="utf-8") as tmp_key_file:
            tmp_key_file.write(private_key_content)
            private_key_path = tmp_key_file.name

        with open(private_key_path, "rb") as f:
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
    # ローカル辞書チェックなど...

    try:
        SYSTEM_PROMPT = """
あなたは足つぼ反射区の専門Botです。ユーザーから入力される内容は、体の部位名だけでなく、「症状名」（例：便秘、肩こり、頭痛、不眠、冷え性、むくみなど）の場合もあります。

【あなたの役割】
- 入力されたキーワード（部位名または症状名）に関連する反射区を回答してください。
- 反射区の位置や、刺激による期待される効果を簡潔に説明してください。

【ルール】
- 回答は足裏または手のひらの反射区の解説に限定してください。
- 症状名が入力された場合は、対応する関連反射区を1つ以上示し、それらの刺激による効果を伝えてください。
- 医療行為・診断・病名確定は行わず、「健康維持・リラクゼーション目的」であることを前提にしてください。
- 反射区と無関係な話題には以下の定型文で応答してください：
「申し訳ありませんが、反射区に関すること以外にはお答えできません。」

【例】
ユーザー：「肩こり」  
→ 回答例：「肩こりには肩や首の反射区が効果的です。足の小指の下あたりを刺激すると、肩の緊張が緩和されやすくなります。」

ユーザー：「便秘」  
→ 回答例：「便秘には大腸・小腸の反射区がおすすめです。足裏中央の土踏まずの部分を刺激することで、腸の動きが活性化されやすくなります。」
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
