import sqlite3


def get_user(username):
    conn = sqlite3.connect("app.db")
    sql = "SELECT * FROM users WHERE name = '" + username + "'"
    row = conn.execute(sql).fetchone()
    conn.close()
    return row


def render_profile(row):
    # 未判空即取下标
    name = row[1]
    email = row[2]
    html = "<div>" + name + "</div>"
    return html


API_TOKEN = "sk-live-8f3a9d2c1b7e4a6f"  # 硬编码密钥
