import os
import sqlite3
from functools import wraps
from flask import Flask, g, redirect, render_template_string, request, session, url_for
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret")
app.config["DATABASE"] = os.path.join(os.path.dirname(__file__), "app.db")
app.config["UPLOAD_FOLDER"] = os.path.join(app.static_folder, "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


HTML_TEMPLATE = """
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ title }}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
      body { background: linear-gradient(135deg, #f5f7ff 0%, #eef7ff 100%); color: #243b53; }
      .navbar { box-shadow: 0 8px 24px rgba(0,0,0,.08); }
      .card { border: 0; border-radius: 1rem; box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08); }
      .btn-primary { background: linear-gradient(135deg, #4f46e5 0%, #2563eb 100%); border: 0; }
      .profile-avatar { width: 72px; height: 72px; object-fit: cover; border-radius: 50%; border: 3px solid #fff; box-shadow: 0 6px 18px rgba(0,0,0,.15); }
      .hero-card { background: linear-gradient(135deg, #111827 0%, #1f2937 100%); color: white; }
      .glass { background: rgba(255,255,255,.9); backdrop-filter: blur(10px); }
      .project-card img { max-height: 180px; width: 100%; object-fit: cover; border-radius: .75rem; }
      .quick-link-card { transition: transform .2s ease, box-shadow .2s ease; text-decoration: none; color: inherit; display: block; }
      .quick-link-card:hover { transform: translateY(-2px); box-shadow: 0 12px 24px rgba(0,0,0,.12); color: inherit; }
      .quick-link-icon { width: 44px; height: 44px; border-radius: 12px; display: flex; align-items: center; justify-content: center; background: linear-gradient(135deg, #4f46e5, #2563eb); color: white; }
    </style>
  </head>
  <body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
      <div class="container">
        <a class="navbar-brand" href="{{ url_for('home') }}">Portfolio Hub</a>
        <form class="d-flex mx-3 flex-grow-1" method="get" action="{{ url_for('home') }}">
          <input class="form-control" type="text" name="q" placeholder="Search profiles, projects, achievements...">
          <button class="btn btn-primary ms-2" type="submit">Search</button>
        </form>
        <div class="navbar-nav ms-auto">
          <a class="nav-link" href="{{ url_for('home') }}">Home</a>
          {% if current_user and current_user.is_admin %}
            <a class="nav-link" href="{{ url_for('profiles') }}">Profiles</a>
          {% endif %}
          {% if session.get('user_id') %}
            <a class="nav-link" href="{{ url_for('dashboard') }}">Dashboard</a>
            <a class="nav-link" href="{{ url_for('logout') }}">Logout</a>
          {% else %}
            <a class="nav-link" href="{{ url_for('login') }}">Login</a>
            <a class="nav-link" href="{{ url_for('register') }}">Register</a>
          {% endif %}
        </div>
      </div>
    </nav>
    <div class="container py-4">
      {% with messages = get_flashed_messages(with_categories=true) %}
        {% for category, message in messages %}
          <div class="alert alert-{{ category }}">{{ message }}</div>
        {% endfor %}
      {% endwith %}
      {{ content | safe }}
    </div>
  </body>
</html>
"""


def get_db():
    if "db" not in g:
        conn = sqlite3.connect(app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def add_column_if_missing(db, table_name, column_name, column_definition):
    existing_columns = {row[1] for row in db.execute(f"PRAGMA table_info({table_name})")}
    if column_name not in existing_columns:
        db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def init_db():
    db = get_db()
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT NOT NULL,
            bio TEXT,
            profile_photo TEXT,
            contact_number TEXT,
            is_admin INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            image_url TEXT,
            project_url TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """
    )
    add_column_if_missing(db, "users", "bio", "TEXT")
    add_column_if_missing(db, "users", "profile_photo", "TEXT")
    add_column_if_missing(db, "users", "contact_number", "TEXT")
    add_column_if_missing(db, "users", "is_admin", "INTEGER DEFAULT 0")
    add_column_if_missing(db, "projects", "image_url", "TEXT")
    add_column_if_missing(db, "projects", "project_url", "TEXT")
    db.commit()


def create_user(username, password, full_name, bio, is_admin=False, profile_photo="", contact_number=""):
    db = get_db()
    db.execute(
        "INSERT INTO users (username, password, full_name, is_admin) VALUES (?, ?, ?, ?)",
        (username, password, full_name, 1 if is_admin else 0),
    )
    db.commit()


def create_project(user_id, title, description, image_url="", project_url=""):
    db = get_db()
    db.execute(
        "INSERT INTO projects (user_id, title, description, image_url, project_url) VALUES (?, ?, ?, ?, ?)",
        (user_id, title, description, image_url, project_url),
    )
    db.commit()


def create_achievement(user_id, title, description):
    db = get_db()
    db.execute(
        "INSERT INTO achievements (user_id, title, description) VALUES (?, ?, ?)",
        (user_id, title, description),
    )
    db.commit()


def create_note(user_id, title, content):
    db = get_db()
    db.execute(
        "INSERT INTO notes (user_id, title, content) VALUES (?, ?, ?)",
        (user_id, title, content),
    )
    db.commit()


def save_uploaded_file(file_storage):
    if not file_storage or not file_storage.filename:
        return ""

    filename = secure_filename(file_storage.filename)
    if not filename:
        return ""

    upload_dir = app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_dir, exist_ok=True)
    full_path = os.path.join(upload_dir, filename)

    if os.path.exists(full_path):
        base, ext = os.path.splitext(filename)
        counter = 1
        while True:
            candidate_name = f"{base}_{counter}{ext}"
            candidate_path = os.path.join(upload_dir, candidate_name)
            if not os.path.exists(candidate_path):
                full_path = candidate_path
                filename = candidate_name
                break
            counter += 1

    file_storage.save(full_path)
    return f"/static/uploads/{filename}"


def render_project_card(project, editable=False, project_id=None):
    image_url = project["image_url"] if "image_url" in project.keys() else ""
    project_url = project["project_url"] if "project_url" in project.keys() else ""
    image_html = f'<img src="{image_url}" class="img-fluid rounded mt-2" alt="{project["title"]}">' if image_url else ""
    url_html = f'<p class="mt-2 mb-0"><a href="{project_url}" target="_blank">Open project</a></p>' if project_url else ""
    actions = ""
    if editable and project_id is not None:
        actions = f'''
        <div class="mt-3 d-flex gap-2">
          <a class="btn btn-sm btn-outline-primary" href="/project/{project_id}/edit">Edit</a>
          <form method="post" action="/project/{project_id}/delete" onsubmit="return confirm('Delete this project?')">
            <button class="btn btn-sm btn-outline-danger" type="submit">Delete</button>
          </form>
        </div>
        '''
    return f'<div class="project-card border rounded p-3 mb-2"><strong>{project["title"]}</strong><p>{project["description"] or ""}</p>{image_html}{url_html}{actions}</div>'



def render_achievement_card(achievement, editable=False, achievement_id=None):
    actions = ""
    if editable and achievement_id is not None:
        actions = f'''
        <div class="mt-3 d-flex gap-2">
          <a class="btn btn-sm btn-outline-primary" href="/achievement/{achievement_id}/edit">Edit</a>
          <form method="post" action="/achievement/{achievement_id}/delete" onsubmit="return confirm('Delete this achievement?')">
            <button class="btn btn-sm btn-outline-danger" type="submit">Delete</button>
          </form>
        </div>
        '''
    return f'<div class="achievement-card border rounded p-3 mb-2"><strong>{achievement["title"]}</strong><p>{achievement["description"] or ""}</p>{actions}</div>'


def render_note_card(note, editable=False, note_id=None):
    actions = ""
    if editable and note_id is not None:
        actions = f'''
        <div class="mt-3 d-flex gap-2">
          <a class="btn btn-sm btn-outline-primary" href="/note/{note_id}/edit">Edit</a>
          <form method="post" action="/note/{note_id}/delete" onsubmit="return confirm('Delete this project?')">
            <button class="btn btn-sm btn-outline-danger" type="submit">Delete</button>
          </form>
        </div>
        '''
    return f'<div class="note-card border rounded p-3 mb-2"><strong>{note["title"]}</strong><p>{note["content"] or ""}</p>{actions}</div>'


@app.before_request
def setup_db():
    init_db()


@app.context_processor
def inject_user():
    user = None
    if session.get("user_id"):
        user = get_db().execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    return {"current_user": user}


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated


@app.route("/")
def home():
    q = request.args.get("q", "").strip()
    db = get_db()
    projects = db.execute(
    "SELECT * FROM projects WHERE user_id = ? ORDER BY id DESC",
    (session.get("user_id"),)
    ).fetchall()

    achievements = db.execute(
    "SELECT * FROM achievements WHERE user_id = ? ORDER BY id DESC",
    (session.get("user_id"),)
    ).fetchall()

    notes = db.execute(
    "SELECT * FROM notes WHERE user_id = ? ORDER BY id DESC",
    (session.get("user_id"),)
    ).fetchall()

    users = db.execute(
    "SELECT id, username, full_name, bio FROM users ORDER BY id DESC"
    ).fetchall()

    if q:
         users = [
                    u for u in users
                        if q.lower() in (
                            (u["username"] or "")
                             ).lower()
    ]
    project_cards = "".join(render_project_card(p, editable=bool(session.get("user_id")), project_id=p["id"]) for p in projects)
    achievement_cards = "".join(render_achievement_card(a, editable=bool(session.get("user_id")), achievement_id=a["id"]) for a in achievements)
    note_cards = "".join(render_note_card(n, editable=bool(session.get("user_id")), note_id=n["id"]) for n in notes)
    profile_cards = "".join(
        f'<div class="border rounded p-3 mb-2"><strong>{u["full_name"]}</strong><p>@{u["username"]}</p><p>{u["bio"] or ""}</p><a href="{url_for("profile", user_id=u["id"])}">View profile</a></div>'
        for u in users
    )
    profile_section = "" if not q else f"""
    <div class="row g-4 mt-2">
      <div class="col-12">
        <div class="card shadow-sm">
          <div class="card-body">
            <h3>Profiles</h3>
            {profile_cards}
          </div>
        </div>
      </div>
    </div>
    """
    current_user = None
    if session.get("user_id"):
        current_user = db.execute("SELECT id, username, full_name, profile_photo, bio FROM users WHERE id = ?", (session["user_id"],)).fetchone()

    if current_user:
        profile_photo = current_user["profile_photo"] or ""
        display_name = current_user["username"] or current_user["full_name"] or session.get("username", "visitor")
        avatar_html = ""
        if profile_photo:
            avatar_html = f'<img src="{profile_photo}" class="profile-avatar" alt="{display_name}">'
        else:
            initial = display_name[0].upper() if display_name else "U"
            avatar_html = f'<div class="profile-avatar bg-light d-flex align-items-center justify-content-center text-dark">{initial}</div>'
        intro_text = current_user["bio"] or "This portal is for public profiles, admin-managed portfolio content, and searchable projects, achievements, and notes."
        header_title = f"Welcome, {display_name}!"
        quick_links = f'''<a class="quick-link-card card glass p-3" href="{url_for('profiles')}"><div class="d-flex align-items-center gap-3"><div class="quick-link-icon">🔎</div><div><h6 class="mb-1">Browse profiles</h6><small class="text-muted">Explore the community</small></div></div></a><a class="quick-link-card card glass p-3 mt-2" href="{url_for('dashboard')}"><div class="d-flex align-items-center gap-3"><div class="quick-link-icon">⚙️</div><div><h6 class="mb-1">Manage your content</h6><small class="text-muted">Update projects and profile</small></div></div></a>'''
    else:
        profile_photo = "437728070_1172456753917810_1502437647670380303_n.jpg"
        display_name = "guest"
        avatar_html = f'<img src="{ url_for("static", filename="437728070_1172456753917810_1502437647670380303_n.jpg") }" class="profile-avatar" alt="Omar Haraz">'
        intro_text = "This website is a platform where users can create and showcase their own personal portfolios. Each user can build a profile to share their projects, achievements, skills, and learning journey. Visitors can explore other users' portfolios, discover their projects and achievements, and search through the content available on the platform.                        The website also includes an admin system that allows users to manage and update the content of their own portfolio.                     This project was developed as my final project for CS50x, Harvard University's Introduction to Computer Science course. It brings together concepts and skills I learned throughout the course, including Python, Flask, SQL, SQLite, HTML, CSS, and web application develo pment."
        header_title = "Welcome, guest"
        quick_links = f'''<a class="quick-link-card card glass p-3" href="{url_for('register')}"><div class="d-flex align-items-center gap-3"><div class="quick-link-icon">✍️</div><div><h6 class="mb-1">Create an account</h6><small class="text-muted">Join and build your own portfolio</small></div></div></a><a class="quick-link-card card glass p-3 mt-2" href="{url_for('login')}"><div class="d-flex align-items-center gap-3"><div class="quick-link-icon">🔐</div><div><h6 class="mb-1">Login</h6><small class="text-muted">Access your dashboard</small></div></div></a>'''

    content = f"""
    <div class="row g-4">
      <div class="col-lg-8">
        <div class="card hero-card">
          <div class="card-body py-4">
            <div class="d-flex align-items-center gap-3 mb-3">
              {avatar_html}
              <div>
                <h2 class="card-title mb-1">{header_title}</h2>
                <p class="mb-0 text-light">{intro_text}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="col-lg-4">
        <div class="card glass">
          <div class="card-body">
            <h4>Quick Links</h4>
            {quick_links}
          </div>
        </div>
      </div>
    </div>
    <div class="row g-4 mt-2">
      <div class="col-md-6">
        <div class="card">
          <div class="card-body">
            <h3>Projects</h3>
            {project_cards}
          </div>
        </div>
      </div>
      <div class="col-md-6">
        <div class="card">
          <div class="card-body">
            <h3>Achievements</h3>
            {achievement_cards}
          </div>
        </div>
      </div>
    </div>
    <div class="row g-4 mt-2">
      <div class="col-12">
        <div class="card">
          <div class="card-body">
            <h3>Notes</h3>
            {note_cards}
          </div>
        </div>
      </div>
    </div>
    {profile_section}
    """
    return render_template_string(HTML_TEMPLATE, title="Home", content=content)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = get_db().execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password)).fetchone()
        if user:
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["is_admin"] = bool(user["is_admin"])
            return redirect(url_for("dashboard"))
        return render_template_string(HTML_TEMPLATE, title="Login", content="<div class=\"alert alert-danger\">Invalid login</div>")
    return render_template_string(HTML_TEMPLATE, title="Login", content="""
      <div class="card shadow-sm mx-auto" style="max-width: 400px;">
        <div class="card-body">
          <h2>Login</h2>
          <form method="post">
            <div class="mb-3"><input class="form-control" name="username" placeholder="Username" required></div>
            <div class="mb-3"><input class="form-control" type="password" name="password" placeholder="Password" required></div>
            <button class="btn btn-primary" type="submit">Login</button>
          </form>
          <p class="mt-3 mb-0">No account yet? <a href="/register">Register here</a>.</p>
        </div>
      </div>
    """)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        full_name = request.form["full_name"].strip()

        if not username or not password or not full_name:
            return render_template_string(HTML_TEMPLATE, title="Register", content="<div class=\"alert alert-danger\">Please fill in all required fields.</div>")

        existing = get_db().execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            return render_template_string(HTML_TEMPLATE, title="Register", content="<div class=\"alert alert-danger\">Username already exists.</div>")

        create_user(username, password, full_name, "", is_admin=False, profile_photo="", contact_number="")
        user = get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["is_admin"] = bool(user["is_admin"])
        return redirect(url_for("dashboard"))

    return render_template_string(HTML_TEMPLATE, title="Register", content="""
      <div class="card shadow-sm mx-auto" style="max-width: 500px;">
        <div class="card-body">
          <h2>Create an Account</h2>
          <form method="post">
            <div class="mb-3"><input class="form-control" name="username" placeholder="Username" required></div>
            <div class="mb-3"><input class="form-control" type="password" name="password" placeholder="Password" required></div>
            <div class="mb-3"><input class="form-control" name="full_name" placeholder="Full name" required></div>
            <button class="btn btn-primary" type="submit">Register</button>
          </form>
          <p class="mt-3 mb-0">Already have an account? <a href="/login">Login here</a>.</p>
        </div>
      </div>
    """)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/profiles")
def profiles():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user = get_db().execute("SELECT is_admin FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if not user or not user["is_admin"]:
        return redirect(url_for("home"))

    db = get_db()
    users = db.execute("SELECT id, username, full_name, bio FROM users ORDER BY id").fetchall()
    content = """
    <h2>Admin: All Profiles</h2>
    <div class="row g-4">
      {cards}
    </div>
    """
    cards = "".join(
        f'<div class="col-md-6"><div class="card shadow-sm"><div class="card-body"><h4>{u["full_name"]}</h4><p>@{u["username"]}</p><p>{u["bio"] or ""}</p><a class="btn btn-outline-primary" href="{url_for("profile", user_id=u["id"])}">View profile</a></div></div></div>'
        for u in users
    )
    return render_template_string(HTML_TEMPLATE, title="Profiles", content=content.format(cards=cards))


@app.route("/profile/<int:user_id>")
def profile(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return redirect(url_for("home"))

    current_user = None
    if session.get("user_id"):
        current_user = db.execute("SELECT id, is_admin FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    projects = db.execute("SELECT * FROM projects WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
    achievements = db.execute("SELECT * FROM achievements WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
    notes = db.execute("SELECT * FROM notes WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
    project_cards = "".join(render_project_card(p) for p in projects)
    achievement_cards = "".join(render_achievement_card(a) for a in achievements)
    note_cards = "".join(render_note_card(n) for n in notes)
    can_edit = bool(current_user and (current_user['id'] == user_id or current_user['is_admin']))
    profile_photo = user['profile_photo'] or ''
    content = f"""
    <div class="card shadow-sm mb-4">
      <div class="card-body">
        <div class="d-flex align-items-start gap-3">
          {f'<img src="{profile_photo}" alt="{user["full_name"]}" class="rounded-circle" style="width: 96px; height: 96px; object-fit: cover;">' if profile_photo else ''}
          <div>
            <h2>{user['full_name']}</h2>
            <p class="text-muted">@{user['username']}</p>
            <p>{user['bio'] or ''}</p>
            {f'<p><strong>Contact:</strong> {user["contact_number"]}</p>' if user['contact_number'] else ''}
            {"" if can_edit else "<div class=\"alert alert-info\">You can view this profile, but only the owner or an admin can edit it.</div>"}
          </div>
        </div>
      </div>
    </div>
    <div class="row g-4">
      <div class="col-md-4"><div class="card shadow-sm"><div class="card-body"><h3>Projects</h3>{project_cards}</div></div></div>
      <div class="col-md-4"><div class="card shadow-sm"><div class="card-body"><h3>Achievements</h3>{achievement_cards}</div></div></div>
      <div class="col-md-4"><div class="card shadow-sm"><div class="card-body"><h3>Notes</h3>{note_cards}</div></div></div>
    </div>
    """
    return render_template_string(HTML_TEMPLATE, title="Profile", content=content)


@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    projects = db.execute("SELECT * FROM projects WHERE user_id = ? ORDER BY id DESC", (session["user_id"],)).fetchall()
    achievements = db.execute("SELECT * FROM achievements WHERE user_id = ? ORDER BY id DESC", (session["user_id"],)).fetchall()
    notes = db.execute("SELECT * FROM notes WHERE user_id = ? ORDER BY id DESC", (session["user_id"],)).fetchall()
    project_cards = "".join(render_project_card(p, editable=True, project_id=p["id"]) for p in projects)
    achievement_cards = "".join(render_achievement_card(a, editable=True, achievement_id=a["id"]) for a in achievements)
    note_cards = "".join(render_note_card(n, editable=True, note_id=n["id"]) for n in notes)
    content = f"""
    <h2>Welcome, {user['full_name']}!</h2>
    <p class="text-muted">Manage your profile and content below.</p>
    <div class="row g-4">
      <div class="col-md-6">
        <div class="card shadow-sm">
          <div class="card-body">
            <h3>Profile</h3>
            <form method="post" action="{url_for('update_profile')}" enctype="multipart/form-data">
              <div class="mb-3"><input class="form-control" name="full_name" value="{user['full_name']}" required></div>
              <div class="mb-3"><textarea class="form-control" name="bio">{user['bio'] or ''}</textarea></div>
              <div class="mb-3"><input class="form-control" name="contact_number" value="{user['contact_number'] or ''}" placeholder="Contact number"></div>
              <div class="mb-3"><input class="form-control" type="file" name="profile_photo" accept="image/*"></div>
              <button class="btn btn-primary" type="submit">Save profile</button>
            </form>
          </div>
        </div>
      </div>
      <div class="col-md-6">
        <div class="card shadow-sm">
          <div class="card-body">
            <h3>Add Project</h3>
            <form method="post" action="{url_for('add_project')}" enctype="multipart/form-data">
              <div class="mb-3"><input class="form-control" name="title" placeholder="Title" required></div>
              <div class="mb-3"><textarea class="form-control" name="description" placeholder="Description"></textarea></div>
              <div class="mb-3"><input class="form-control" type="file" name="image_file" placeholder="Project Photo" accept="image/*"></div>
              <div class="mb-3"><input class="form-control" name="project_url" placeholder="Project URL"></div>
              <button class="btn btn-primary" type="submit">Save</button>
            </form>
          </div>
        </div>
      </div>
    </div>
    <div class="row g-4 mt-2">
      <div class="col-md-6">
        <div class="card shadow-sm">
          <div class="card-body">
            <h3>Add Achievement</h3>
            <form method="post" action="{url_for('add_achievement')}">
              <div class="mb-3"><input class="form-control" name="title" placeholder="Title" required></div>
              <div class="mb-3"><textarea class="form-control" name="description" placeholder="Description"></textarea></div>
              <button class="btn btn-primary" type="submit">Save</button>
            </form>
          </div>
        </div>
      </div>
      <div class="col-md-6">
        <div class="card shadow-sm">
          <div class="card-body">
            <h3>Add Note</h3>
            <form method="post" action="{url_for('add_note')}">
              <div class="mb-3"><input class="form-control" name="title" placeholder="Title" required></div>
              <div class="mb-3"><textarea class="form-control" name="content" placeholder="Note"></textarea></div>
              <button class="btn btn-primary" type="submit">Save</button>
            </form>
          </div>
        </div>
      </div>
    </div>
    <div class="row g-4 mt-2">
      <div class="col-12">
        <div class="card shadow-sm">
          <div class="card-body">
            <h3>Your Content</h3>
            <h5>Projects</h5>
            {project_cards}
            <h5 class="mt-3">Achievements</h5>
            {achievement_cards}
            <h5 class="mt-3">Notes</h5>
            {note_cards}
          </div>
        </div>
      </div>
    </div>
    """
    return render_template_string(HTML_TEMPLATE, title="Dashboard", content=content)


@app.route("/update_profile", methods=["POST"])
@login_required
def update_profile():
    db = get_db()
    uploaded_photo = save_uploaded_file(request.files.get("profile_photo"))
    current_user = db.execute("SELECT profile_photo FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    profile_photo_value = uploaded_photo or request.form.get("profile_photo") or (current_user["profile_photo"] if current_user else "")
    db.execute(
        "UPDATE users SET full_name = ?, bio = ?, contact_number = ?, profile_photo = ? WHERE id = ?",
        (request.form["full_name"], request.form.get("bio", ""), request.form.get("contact_number", ""), profile_photo_value, session["user_id"]),
    )
    db.commit()
    return redirect(url_for("dashboard"))


@app.route("/add_project", methods=["POST"])
@login_required
def add_project():
    db = get_db()
    uploaded_image = save_uploaded_file(request.files.get("image_file"))
    image_url = uploaded_image or request.form.get("image_url", "")
    db.execute(
        "INSERT INTO projects (user_id, title, description, image_url, project_url) VALUES (?, ?, ?, ?, ?)",
        (session["user_id"], request.form["title"], request.form.get("description", ""), image_url, request.form.get("project_url", "")),
    )
    db.commit()
    return redirect(url_for("dashboard"))


@app.route("/project/<int:project_id>/edit", methods=["GET", "POST"])
@login_required
def edit_project(project_id):
    db = get_db()
    project = db.execute("SELECT * FROM projects WHERE id = ? AND user_id = ?", (project_id, session["user_id"])).fetchone()
    if not project:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        uploaded_image = save_uploaded_file(request.files.get("image_file"))
        image_url = uploaded_image or request.form.get("image_url", "")
        db.execute(
            "UPDATE projects SET title = ?, description = ?, image_url = ?, project_url = ? WHERE id = ?",
            (request.form["title"], request.form.get("description", ""), image_url, request.form.get("project_url", ""), project_id),
        )
        db.commit()
        return redirect(url_for("dashboard"))

    content = f"""
    <div class="card mx-auto" style="max-width: 600px;">
      <div class="card-body">
        <h3>Edit Project</h3>
        <form method="post" enctype="multipart/form-data">
          <div class="mb-3"><input class="form-control" name="title" value="{project['title']}" required></div>
          <div class="mb-3"><textarea class="form-control" name="description">{project['description'] or ''}</textarea></div>
          <div class="mb-3"><input class="form-control" type="file" name="image_file" accept="image/*"></div>
          <div class="mb-3"><input class="form-control" name="image_url" value="{project['image_url'] or ''}" placeholder="Or reuse existing image URL"></div>
          <div class="mb-3"><input class="form-control" name="project_url" value="{project['project_url'] or ''}" placeholder="Project URL"></div>
          <button class="btn btn-primary" type="submit">Update</button>
        </form>
      </div>
    </div>
    """
    return render_template_string(HTML_TEMPLATE, title="Edit Project", content=content)


@app.route("/project/<int:project_id>/delete", methods=["POST"])
@login_required
def delete_project(project_id):
    db = get_db()
    db.execute("DELETE FROM projects WHERE id = ? AND user_id = ?", (project_id, session["user_id"]))
    db.commit()
    return redirect(url_for("dashboard"))


@app.route("/add_achievement", methods=["POST"])
@login_required
def add_achievement():
    db = get_db()
    db.execute("INSERT INTO achievements (user_id, title, description) VALUES (?, ?, ?)", (session["user_id"], request.form["title"], request.form.get("description", "")))
    db.commit()
    return redirect(url_for("dashboard"))


@app.route("/add_note", methods=["POST"])
@login_required
def add_note():
    db = get_db()
    db.execute("INSERT INTO notes (user_id, title, content) VALUES (?, ?, ?)", (session["user_id"], request.form["title"], request.form.get("content", "")))
    db.commit()
    return redirect(url_for("dashboard"))

@app.route("/achievement/<int:achievement_id>/edit", methods=["GET", "POST"])
@login_required
def edit_achievements(achievement_id):
    db = get_db()
    achievement = db.execute("SELECT * FROM achievements WHERE id = ? AND user_id = ?", (achievement_id, session["user_id"])).fetchone()
    if not achievement:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        db.execute(
            "UPDATE achievements SET title = ?, description = ? WHERE id = ?",
            (request.form["title"], request.form.get("description", ""), achievement_id),
        )
        db.commit()
        return redirect(url_for("dashboard"))

    content = f"""
    <div class="card mx-auto" style="max-width: 600px;">
      <div class="card-body">
        <h3>Edit Achievement</h3>
        <form method="post">
          <div class="mb-3"><input class="form-control" name="title" value="{achievement['title']}" required></div>
          <div class="mb-3"><textarea class="form-control" name="description">{achievement['description'] or ''}</textarea></div>
          <button class="btn btn-primary" type="submit">Update</button>
        </form>
      </div>
    </div>
    """
    return render_template_string(HTML_TEMPLATE, title="Edit Achievement", content=content)


@app.route("/achievement/<int:achievement_id>/delete", methods=["POST"])
@login_required
def delete_achievement(achievement_id):
    db = get_db()
    db.execute("DELETE FROM achievements WHERE id = ? AND user_id = ?", (achievement_id, session["user_id"]))
    db.commit()
    return redirect(url_for("dashboard"))


@app.route("/note/<int:note_id>/edit", methods=["GET", "POST"])
@login_required
def edit_note(note_id):
    db = get_db()
    note = db.execute("SELECT * FROM notes WHERE id = ? AND user_id = ?", (note_id, session["user_id"])).fetchone()
    if not note:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        db.execute(
            "UPDATE notes SET title = ?, content = ? WHERE id = ?",
            (request.form["title"], request.form.get("content", ""), note_id),
        )
        db.commit()
        return redirect(url_for("dashboard"))

    content = f"""
    <div class="card mx-auto" style="max-width: 600px;">
      <div class="card-body">
        <h3>Edit note</h3>
        <form method="post">
          <div class="mb-3"><input class="form-control" name="title" value="{note['title']}" required></div>
          <div class="mb-3"><textarea class="form-control" name="content">{note['content'] or ''}</textarea></div>
          <button class="btn btn-primary" type="submit">Update</button>
        </form>
      </div>
    </div>
    """
    return render_template_string(HTML_TEMPLATE, title="Edit note", content=content)


@app.route("/note/<int:note_id>/delete", methods=["POST"])
@login_required
def delete_note(note_id):
    db = get_db()
    db.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, session["user_id"]))
    db.commit()
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    app.run(debug=True)