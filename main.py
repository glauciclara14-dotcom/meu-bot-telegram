import os
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def home():
    # Isso vai fazer a Railway parar de dar erro 404
    # E o seu bot vai parar de ter atualizações pendentes
    return jsonify({"status": "ok", "message": "Bot is running!"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)