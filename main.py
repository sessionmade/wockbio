from flask import Flask, render_template, request, redirect, session, url_for
import os, glob, asyncio, requests
from werkzeug.utils import secure_filename
import asyncpg

app = Flask(__name__)
app.secret_key = 'your_secret_key'

app.config['UPLOAD_FOLDER'] = 'static/uploads/'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'avatars'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'backgrounds'), exist_ok=True)

OWNERS = ["zni", "waiser"]
SUPABASE_DB_URL = os.getenv("postgresql://postgres:wockboss11$@db.jsakzjalxuedioelwtcz.supabase.co:5432/postgres")  # Supabase connection string


# ----------------------
# Helper Functions
# ----------------------

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


async def get_conn():
    return await asyncpg.connect(SUPABASE_DB_URL)


async def get_user(username):
    conn = await get_conn()
    user = await conn.fetchrow("SELECT * FROM users WHERE username=$1", username)
    await conn.close()
    return user


async def update_user_profile(username, **kwargs):
    conn = await get_conn()
    await conn.execute("""
        UPDATE users SET
            bio=$1, avatar=$2, background=$3, github=$4, discord=$5,
            show_discord=$6, show_github=$7, discord_server=$8,
            text_glow=$9, text_color=$10, custom_font=$11, music_url=$12
        WHERE username=$13
    """, kwargs['bio'], kwargs['avatar'], kwargs['background'], kwargs['github'],
       kwargs['discord'], kwargs['show_discord'], kwargs['show_github'],
       kwargs['discord_server'], kwargs['text_glow'], kwargs['text_color'],
       kwargs['custom_font'], kwargs['music_url'], username)
    await conn.close()


async def create_user(username, password):
    conn = await get_conn()
    try:
        await conn.execute("INSERT INTO users (username, password) VALUES ($1, $2)", username, password)
    except asyncpg.UniqueViolationError:
        await conn.close()
        return False
    await conn.close()
    return True


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
        success = asyncio.run(create_user(username, password))
        if success:
            return redirect('/login')
        else:
            return "Username already taken"
    return render_template('signup.html')


@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        user = asyncio.run(get_user(username))
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
    user = asyncio.run(get_user(username))

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

        asyncio.run(update_user_profile(username,
                                        bio=bio, avatar=avatar_path, background=bg_path,
                                        github=github, discord=discord, show_discord=show_discord,
                                        show_github=show_github, discord_server=discord_server,
                                        text_glow=text_glow, text_color=text_color,
                                        custom_font=custom_font, music_url=music_url))

        return redirect('/dashboard')

    return render_template('edit_profile.html', **user)


@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect('/login')

    username = session['username']
    user = asyncio.run(get_user(username))

    conn = asyncio.run(get_conn())
    total_accounts = asyncio.run(conn.fetchval("SELECT COUNT(*) FROM users"))
    total_views = asyncio.run(conn.fetchval("SELECT SUM(profile_views) FROM users")) or 0
    recent_users = asyncio.run(conn.fetch("SELECT username, created_at FROM users ORDER BY id DESC LIMIT 5"))
    asyncio.run(conn.close())

    badges = user['badges'].split(",") if user['badges'] else []

    return render_template('dashboard.html', user=user, username=user['username'],
                           bio=user['bio'], avatar=user['avatar'], discord=user['discord'],
                           github=user['github'], badges=badges, profile_views=user['profile_views'],
                           total_accounts=total_accounts, total_views=total_views, recent_users=recent_users)


# ----------------------
# Initialize DB (run once in Supabase)
# ----------------------

async def init_db():
    conn = await get_conn()
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        show_discord INTEGER DEFAULT 1,
        show_github INTEGER DEFAULT 1,
        music_url TEXT,
        discord_server TEXT,
        text_glow INTEGER DEFAULT 0,
        text_color TEXT DEFAULT '#ffffff',
        custom_font TEXT DEFAULT ''
    )
    """)
    await conn.close()


if __name__ == '__main__':
    asyncio.run(init_db())
    app.run(debug=True)
