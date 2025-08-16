from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3, glob, os
from werkzeug.utils import secure_filename
import requests

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a secure key
app.config['UPLOAD_FOLDER'] = 'static/uploads/'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# Create upload folders if they don't exist
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'avatars'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'backgrounds'), exist_ok=True)

OWNERS = ["zni", "waiser"]  # Replace with actual owner usernames

# ----------------------
# Helper Functions
# ----------------------

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_user(username):
    with sqlite3.connect("users.db") as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

def load_badges():
    badge_folder = os.path.join(app.static_folder, "badges")
    return [
        {
            "name": os.path.splitext(filename)[0],
            "url": url_for("static", filename=f"badges/{filename}")
        }
        for filename in os.listdir(badge_folder)
        if filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))
    ]

# ----------------------
# Routes
# ----------------------

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/signup', methods=['GET','POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        with sqlite3.connect("users.db") as conn:
            try:
                conn.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
                return redirect('/login')
            except sqlite3.IntegrityError:
                return "Username already taken"
    return render_template('signup.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        user = get_user(username)
        if user and user['password'] == password:
            session['username'] = username
            return redirect('/dashboard')
        else:
            return "Invalid login"
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect('/login')

@app.route('/edit_profile', methods=['GET','POST'])
def edit_profile():
    if 'username' not in session:
        return redirect('/login')
    username = session['username']
    user = get_user(username)

    if request.method == 'POST':
        bio = request.form.get("bio", "")
        avatar_file = request.files.get("avatar")
        avatar_url = request.form.get("avatar_url", "").strip()
        bg_file = request.files.get("background")
        bg_url = request.form.get("background_url", "").strip()
        music_url = request.form.get("music_url", "").strip()
        github = request.form.get("github", "")
        discord = request.form.get("discord", "")
        discord_server = request.form.get("discord_server", "")
        show_discord = 1 if request.form.get("show_discord") == "on" else 0
        show_github = 1 if request.form.get("show_github") == "on" else 0
        text_glow = 1 if request.form.get("text_glow") == "on" else 0
        text_color = request.form.get("text_color", "#ffffff").strip()
        custom_font = request.form.get("custom_font", "").strip()

        avatar_path = user['avatar']
        bg_path = user['background']

        if avatar_url:
            avatar_path = avatar_url
        elif avatar_file and allowed_file(avatar_file.filename):
            filename = secure_filename(avatar_file.filename)
            avatar_path = f"uploads/avatars/{username}_{filename}"
            avatar_file.save(os.path.join("static", avatar_path))

        if bg_url:
            bg_path = bg_url
        elif bg_file and allowed_file(bg_file.filename):
            filename = secure_filename(bg_file.filename)
            bg_path = f"uploads/backgrounds/{username}_{filename}"
            bg_file.save(os.path.join("static", bg_path))

        with sqlite3.connect("users.db") as conn:
            conn.execute("""
                UPDATE users SET
                    bio = ?, avatar = ?, background = ?, github = ?, discord = ?, 
                    show_discord = ?, show_github = ?, discord_server = ?, 
                    text_glow = ?, text_color = ?, custom_font = ?, music_url = ?
                WHERE username = ?
            """, (bio, avatar_path, bg_path, github, discord, show_discord, show_github, discord_server, text_glow, text_color, custom_font, music_url, username))
        return redirect('/dashboard')

    return render_template('edit_profile.html', **user)

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect('/login')
    username = session['username']
    user = get_user(username)

    with sqlite3.connect("users.db") as conn:
        total_accounts = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        total_views = conn.execute("SELECT SUM(profile_views) FROM users").fetchone()[0] or 0
        recent_users = conn.execute("SELECT username, created_at FROM users ORDER BY id DESC LIMIT 5").fetchall()

    badges = user['badges'].split(",") if user['badges'] else []

    return render_template(
        'dashboard.html',
        user=user,
        username=user['username'],
        bio=user['bio'],
        avatar=user['avatar'],
        discord=user['discord'],
        github=user['github'],
        badges=badges,
        profile_views=user['profile_views'],
        total_accounts=total_accounts,
        total_views=total_views,
        recent_users=recent_users
    )

@app.route('/<username>')
def user_profile(username):
    user = get_user(username)
    if not user:
        return "User not found", 404

    if f"viewed_{username}" not in session:
        with sqlite3.connect("users.db") as conn:
            conn.execute("UPDATE users SET profile_views = profile_views + 1 WHERE username = ?", (username,))
        session[f"viewed_{username}"] = True

    badges = user['badges'].split(",") if user['badges'] else []
    badge_urls = {}
    for badge in badges:
        matches = glob.glob(os.path.join(app.static_folder, "badges", f"{badge.lower()}.*"))
        if matches:
            badge_urls[badge.lower()] = url_for("static", filename=f"badges/{os.path.basename(matches[0])}")

    discord_invite = None
    discord_server_code = user['discord_server'] or ""
    if discord_server_code:
        invite_code = discord_server_code.strip().split("/")[-1]
        try:
            response = requests.get(f"https://discord.com/api/v10/invites/{invite_code}?with_counts=true")
            if response.status_code == 200:
                discord_invite = response.json()
        except Exception as e:
            print("Error fetching Discord invite:", e)

    return render_template(
        'user_profile.html',
        username=user['username'],
        bio=user['bio'],
        avatar=user['avatar'],
        background=user['background'],
        badges=badges,
        badge_urls=badge_urls,
        github=user['github'],
        discord=user['discord'],
        profile_views=user['profile_views'],
        music_url=user['music_url'],
        discord_invite=discord_invite,
        text_glow=user['text_glow'],
        text_color=user['text_color'],
        custom_font=user['custom_font']
    )

@app.route("/admin", methods=["GET","POST"])
def admin_dashboard():
    if 'username' not in session or session['username'] not in OWNERS:
        return "Access denied", 403

    message = None
    available_badges = load_badges()

    if request.method == "POST":
        target_username = request.form.get("target_username").strip()
        selected_badges = ",".join(request.form.getlist("badges"))
        make_admin = 1 if "make_admin" in request.form else 0

        with sqlite3.connect("users.db") as conn:
            conn.execute("UPDATE users SET badges = ?, is_admin = ? WHERE username = ?", (selected_badges, make_admin, target_username))
        message = f"Updated {target_username}"
        return redirect(url_for("admin_dashboard"))

    with sqlite3.connect("users.db") as conn:
        users_list = conn.execute("SELECT username, badges, is_admin FROM users").fetchall()

    return render_template(
        "admin_dashboard.html",
        available_badges=available_badges,
        users=users_list,
        message=message
    )

# ----------------------
# Database Initialization
# ----------------------

def init_db():
    with sqlite3.connect("users.db") as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT,
                bio TEXT,
                avatar TEXT,
                background TEXT,
                badges TEXT,
                is_admin INTEGER DEFAULT 0,
                github TEXT,
                discord TEXT,
                profile_views INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                show_discord INTEGER DEFAULT 1,
                show_github INTEGER DEFAULT 1,
                music_url TEXT,
                discord_server TEXT,
                text_glow INTEGER DEFAULT 0,
                text_color TEXT DEFAULT '#ffffff',
                custom_font TEXT DEFAULT ''
            )
        """)
        conn.commit()

# ----------------------
# Run App
# ----------------------

if __name__ == '__main__':
    init_db()
    app.run(debug=True)

