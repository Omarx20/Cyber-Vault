import os
import sqlite3
import tempfile
import unittest
from io import BytesIO

from app import app, init_db


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test.db")
        app.config.update(TESTING=True, SECRET_KEY="test-secret", DATABASE=self.db_path)
        with app.app_context():
            init_db()
            from app import create_user
            create_user("admin", "admin123", "Administrator", "Default admin account", is_admin=True)
        self.client = app.test_client()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_dashboard_handles_legacy_users_without_profile_columns(self):
        legacy_db_path = os.path.join(self.tmp_dir.name, "legacy.db")
        app.config["DATABASE"] = legacy_db_path

        with app.app_context():
            conn = sqlite3.connect(legacy_db_path)
            conn.execute(
                "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, full_name TEXT NOT NULL, is_admin INTEGER DEFAULT 0)"
            )
            conn.execute(
                "INSERT INTO users (username, password, full_name, is_admin) VALUES (?, ?, ?, ?)",
                ("legacy", "secret", "Legacy User", 0),
            )
            conn.commit()
            conn.close()

            init_db()

        response = self.client.post(
            "/login",
            data={"username": "legacy", "password": "secret"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Legacy User", response.data)

    def test_admin_can_login_and_view_profile(self):
        response = self.client.post(
            "/login",
            data={"username": "admin", "password": "admin123"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Welcome, Administrator", response.data)

    def test_search_filters_content(self):
        with app.app_context():
            from app import create_user, create_project, create_achievement
            create_user("alice", "secret", "Alice", "Hello", is_admin=False)
            create_project(1, "AI Dashboard", "A smart dashboard")
            create_achievement(1, "Award", "Won for design")

        self.client.post(
            "/login",
            data={"username": "alice", "password": "secret"},
            follow_redirects=True,
        )
        response = self.client.get("/?q=dashboard")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"AI Dashboard", response.data)

    def test_user_can_register(self):
        response = self.client.post(
            "/register",
            data={"username": "newuser", "password": "newpass", "full_name": "New User", "bio": "Hello there"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Manage your profile", response.data)

    def test_user_can_edit_and_delete_their_project(self):
        with app.app_context():
            from app import create_user, create_project
            create_user("owner", "secret", "Project Owner", "Hello", is_admin=False)
            create_project(2, "Draft Project", "Old description")

        self.client.post(
            "/login",
            data={"username": "owner", "password": "secret"},
            follow_redirects=True,
        )
        response = self.client.post(
            "/project/1/edit",
            data={"title": "Updated Project", "description": "New description", "project_url": "https://example.com/updated"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Updated Project", response.data)

        delete_response = self.client.post(
            "/project/1/delete",
            follow_redirects=True,
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertNotIn(b"Updated Project", delete_response.data)

    def test_home_page_shows_profile_photo_and_user_details(self):
        with app.app_context():
            from app import create_user, get_db
            create_user("homeuser", "secret", "Home User", "Hello", is_admin=False)
            db = get_db()
            db.execute("UPDATE users SET profile_photo = ? WHERE username = ?", ("/static/uploads/demo.png", "homeuser"))
            db.commit()

        self.client.post(
            "/login",
            data={"username": "homeuser", "password": "secret"},
            follow_redirects=True,
        )
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Welcome, homeuser", response.data)
        self.assertIn(b"/static/uploads/demo.png", response.data)

    def test_user_can_store_profile_media_and_project_links(self):
        with app.app_context():
            from app import create_user
            create_user("mediauser", "secret", "Media User", "Hello", is_admin=False)

        self.client.post(
            "/login",
            data={"username": "mediauser", "password": "secret"},
            follow_redirects=True,
        )
        self.client.post(
            "/update_profile",
            data={
                "full_name": "Media User",
                "bio": "Hello",
                "contact_number": "123456789",
                "profile_photo": (BytesIO(b"fake-image-data"), "profile.png"),
            },
            follow_redirects=True,
        )
        self.client.post(
            "/add_project",
            data={
                "title": "Media Project",
                "description": "Showcase",
                "image_file": (BytesIO(b"fake-project-data"), "project.png"),
                "project_url": "https://example.com/project",
            },
            follow_redirects=True,
        )

        with app.app_context():
            from app import get_db
            db = get_db()
            user = db.execute("SELECT profile_photo, contact_number FROM users WHERE username = ?", ("mediauser",)).fetchone()
            project = db.execute("SELECT image_url, project_url FROM projects WHERE title = ?", ("Media Project",)).fetchone()

        self.assertTrue(user["profile_photo"].startswith("/static/uploads/"))
        self.assertEqual(user["contact_number"], "123456789")
        self.assertTrue(project["image_url"].startswith("/static/uploads/"))
        self.assertEqual(project["project_url"], "https://example.com/project")

    def test_non_admin_cannot_view_profiles_page(self):
        with app.app_context():
            from app import create_user
            create_user("alice", "secret", "Alice", "Hello", is_admin=False)

        self.client.post(
            "/login",
            data={"username": "alice", "password": "secret"},
            follow_redirects=True,
        )
        response = self.client.get("/profiles", follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.request.path, "/")

    def test_search_can_find_profiles(self):
        with app.app_context():
            from app import create_user
            create_user("alice", "secret", "Alice Example", "Hello", is_admin=False)

        self.client.post(
            "/login",
            data={"username": "alice", "password": "secret"},
            follow_redirects=True,
        )
        response = self.client.get("/?q=alice")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Alice Example", response.data)
        self.assertIn(b"/profile/", response.data)

    def test_guest_sees_public_home_with_explanation_and_admin_profile(self):
        response = self.client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Welcome, guest", response.data)
        self.assertIn(b"Omar Haraz", response.data)
        self.assertIn(b"Computer Engineering student", response.data)

    def test_home_page_handles_stale_session_without_crashing(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = 999999
            sess["username"] = "ghost"

        response = self.client.get("/", follow_redirects=False)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Welcome, guest", response.data)


if __name__ == "__main__":
    unittest.main()
