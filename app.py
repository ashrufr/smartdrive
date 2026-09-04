from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from db import get_db, init_db, dict_from_row, dict_from_rows
from email_utils import send_email
from datetime import datetime, timedelta
from urllib.parse import urljoin
import secrets
import os

app = Flask(__name__)
app.secret_key = "carsales-secret-key-change-in-production"
app.config["GMAIL_SMTP_USER"] = os.environ.get("GMAIL_SMTP_USER", "Not configured")

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_user():
    if "user_id" in session:
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM SD_users WHERE id = %s", (session["user_id"],))
        user = dict_from_row(cur, cur.fetchone())
        db.close()
        return user
    return None


def send_verification_email(user_email, token):
    verify_path = url_for("verify_email", token=token)
    verify_url = request.host_url.rstrip("/") + verify_path
    subject = "Verify your email - SmartDrive"
    body = f"""
    <h2>Welcome to SmartDrive!</h2>
    <p>Please verify your email address by clicking the link below:</p>
    <p><a href="{verify_url}" style="background:#e94560;color:#fff;padding:12px 24px;text-decoration:none;border-radius:6px;display:inline-block;">Verify Email</a></p>
    <p>Or copy this link: {verify_url}</p>
    <p>This link expires in 24 hours.</p>
    <p>If you did not create an account, please ignore this email.</p>
    """
    send_email(user_email, subject, body)


@app.before_request
def require_verification():
    if "user_id" not in session:
        return
    allowed = {"login", "register", "logout", "static",
               "verify_email", "verify_email_sent",
               "verify_email_prompt", "resend_email"}
    if request.endpoint in allowed or request.endpoint is None:
        return
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT email_verified FROM SD_users WHERE id = %s", (session["user_id"],))
    user = dict_from_row(cur, cur.fetchone())
    db.close()
    if user and not user["email_verified"]:
        token = session.get("verify_email_token")
        if not token:
            token = secrets.token_urlsafe(32)
            expires = datetime.utcnow() + timedelta(hours=24)
            db2 = get_db()
            cur2 = db2.cursor()
            cur2.execute("UPDATE SD_email_verifications SET used = 1 WHERE user_id = %s", (session["user_id"],))
            cur2.execute(
                "INSERT INTO SD_email_verifications (user_id, token, expires_at) VALUES (%s, %s, %s)",
                (session["user_id"], token, expires.isoformat()),
            )
            db2.commit()
            db2.close()
            session["verify_email_token"] = token
            try:
                send_verification_email(user["email"], token)
            except Exception:
                pass
        return redirect(url_for("verify_email_sent"))


@app.route("/")
def index():
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT c.*, u.username as seller FROM SD_cars c JOIN SD_users u ON c.user_id = u.id WHERE c.is_sold = 0 ORDER BY c.created_at DESC"
    )
    cars = dict_from_rows(cur, cur.fetchall())
    db.close()
    return render_template("index.html", cars=cars, user=get_user())


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]
        phone = request.form.get("phone", "").strip()

        if not username or not email or not password:
            flash("All fields are required.", "error")
            return render_template("register.html", user=None)

        db = get_db()
        cur = db.cursor()
        cur.execute(
            "SELECT id FROM SD_users WHERE username = %s OR email = %s", (username, email)
        )
        existing = cur.fetchone()
        if existing:
            flash("Username or email already taken.", "error")
            db.close()
            return render_template("register.html", user=None)

        cur.execute(
            "INSERT INTO SD_users (username, email, password_hash, phone) VALUES (%s, %s, %s, %s)",
            (username, email, generate_password_hash(password), phone),
        )
        db.commit()

        cur.execute("SELECT * FROM SD_users WHERE username = %s", (username,))
        user = dict_from_row(cur, cur.fetchone())

        token = secrets.token_urlsafe(32)
        expires = datetime.utcnow() + timedelta(hours=24)
        cur.execute(
            "INSERT INTO SD_email_verifications (user_id, token, expires_at) VALUES (%s, %s, %s)",
            (user["id"], token, expires.isoformat()),
        )
        db.commit()
        db.close()

        session["user_id"] = user["id"]
        session["verify_email_token"] = token

        try:
            send_verification_email(email, token)
            flash("Account created! Please check your email to verify.", "success")
        except Exception as e:
            flash("Account created! Email could not be sent. Please contact support.", "error")

        return redirect(url_for("verify_email_sent"))
    return render_template("register.html", user=get_user())


@app.route("/verify/email/sent")
def verify_email_sent():
    if "user_id" not in session:
        return redirect(url_for("login"))
    user = get_user()
    token = session.get("verify_email_token")
    return render_template("verify_email_sent.html", user=user, token=token)


@app.route("/verify/email/<token>")
def verify_email(token):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT * FROM SD_email_verifications WHERE token = %s", (token,)
    )
    row = dict_from_row(cur, cur.fetchone())

    if not row:
        db.close()
        flash("Invalid or expired verification link.", "error")
        return redirect(url_for("index"))

    if row["used"]:
        db.close()
        flash("This verification link has already been used.", "error")
        return redirect(url_for("index"))

    expires = row["expires_at"]
    if isinstance(expires, str):
        expires = datetime.fromisoformat(expires)
    if datetime.utcnow() > expires:
        db.close()
        flash("Verification link has expired. Please request a new one.", "error")
        return redirect(url_for("resend_email"))

    cur.execute("UPDATE SD_users SET email_verified = 1, verified = 'Yes' WHERE id = %s", (row["user_id"],))
    cur.execute("UPDATE SD_email_verifications SET used = 1 WHERE id = %s", (row["id"],))
    db.commit()
    db.close()

    session.pop("verify_email_token", None)
    flash("Email verified successfully!", "success")
    return redirect(url_for("index"))


@app.route("/verify/email/prompt")
def verify_email_prompt():
    if "user_id" not in session:
        return redirect(url_for("login"))
    user = get_user()
    if user and user["email_verified"]:
        return redirect(url_for("index"))
    return render_template("verify_email_prompt.html", user=user)


@app.route("/resend/email", methods=["POST"])
def resend_email():
    if "user_id" not in session:
        return redirect(url_for("login"))
    user = get_user()
    db = get_db()
    cur = db.cursor()

    cur.execute("UPDATE SD_email_verifications SET used = 1 WHERE user_id = %s", (user["id"],))
    token = secrets.token_urlsafe(32)
    expires = datetime.utcnow() + timedelta(hours=24)
    cur.execute(
        "INSERT INTO SD_email_verifications (user_id, token, expires_at) VALUES (%s, %s, %s)",
        (user["id"], token, expires.isoformat()),
    )
    db.commit()
    db.close()

    session["verify_email_token"] = token

    try:
        send_verification_email(user["email"], token)
        flash("Verification email resent. Please check your inbox.", "success")
    except Exception:
        flash("Email could not be sent. Please try again later.", "error")

    return redirect(url_for("verify_email_sent"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]

        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM SD_users WHERE username = %s", (username,))
        user = dict_from_row(cur, cur.fetchone())
        db.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            if not user["email_verified"]:
                token = secrets.token_urlsafe(32)
                expires = datetime.utcnow() + timedelta(hours=24)
                db2 = get_db()
                cur2 = db2.cursor()
                cur2.execute("UPDATE SD_email_verifications SET used = 1 WHERE user_id = %s", (user["id"],))
                cur2.execute(
                    "INSERT INTO SD_email_verifications (user_id, token, expires_at) VALUES (%s, %s, %s)",
                    (user["id"], token, expires.isoformat()),
                )
                db2.commit()
                db2.close()
                session["verify_email_token"] = token
                try:
                    send_verification_email(user["email"], token)
                except Exception:
                    pass
                return redirect(url_for("verify_email_sent"))
            flash("Welcome back!", "success")
            return redirect(url_for("index"))
        flash("Invalid username or password.", "error")
    return render_template("login.html", user=get_user())


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("index"))


@app.route("/sell", methods=["GET", "POST"])
def sell():
    if "user_id" not in session:
        flash("Please login to sell a car.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        image_url = ""
        if "image" in request.files:
            file = request.files["image"]
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                filename = f"{secrets.token_hex(8)}_{filename}"
                file.save(os.path.join(UPLOAD_FOLDER, filename))
                image_url = f"uploads/{filename}"

        db = get_db()
        cur = db.cursor()
        cur.execute(
            """INSERT INTO SD_cars (user_id, title, make, model, year, mileage, price, color,
               fuel_type, transmission, description, image_url)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                session["user_id"],
                request.form["title"].strip(),
                request.form["make"].strip(),
                request.form["model"].strip(),
                int(request.form["year"]),
                int(request.form.get("mileage", 0)),
                float(request.form["price"]),
                request.form.get("color", "").strip(),
                request.form.get("fuel_type", "Gasoline"),
                request.form.get("transmission", "Automatic"),
                request.form.get("description", "").strip(),
                image_url,
            ),
        )
        db.commit()
        db.close()
        flash("Car listed successfully!", "success")
        return redirect(url_for("index"))
    return render_template("sell.html", user=get_user())


@app.route("/car/<int:car_id>")
def car_detail(car_id):
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT c.*, u.username as seller, u.phone as seller_phone, u.email as seller_email FROM SD_cars c JOIN SD_users u ON c.user_id = u.id WHERE c.id = %s",
        (car_id,),
    )
    car = dict_from_row(cur, cur.fetchone())
    db.close()
    if not car:
        flash("Car not found.", "error")
        return redirect(url_for("index"))
    return render_template("car_detail.html", car=car, user=get_user())


@app.route("/car/<int:car_id>/sold", methods=["POST"])
def mark_sold(car_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM SD_cars WHERE id = %s AND user_id = %s", (car_id, session["user_id"]))
    car = dict_from_row(cur, cur.fetchone())
    if car:
        cur.execute("UPDATE SD_cars SET is_sold = 1 WHERE id = %s", (car_id,))
        db.commit()
        flash("Marked as sold.", "success")
    db.close()
    return redirect(url_for("index"))


@app.route("/my-listings")
def my_listings():
    if "user_id" not in session:
        return redirect(url_for("login"))
    db = get_db()
    cur = db.cursor()
    cur.execute(
        "SELECT * FROM SD_cars WHERE user_id = %s ORDER BY created_at DESC", (session["user_id"],)
    )
    cars = dict_from_rows(cur, cur.fetchall())
    db.close()
    return render_template("my_listings.html", cars=cars, user=get_user())


@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    db = get_db()
    cur = db.cursor()
    cur.execute(
        """SELECT c.*, u.username as seller FROM SD_cars c
           JOIN SD_users u ON c.user_id = u.id
           WHERE c.is_sold = 0 AND (
               c.make LIKE %s OR c.model LIKE %s OR c.title LIKE %s OR c.description LIKE %s
           ) ORDER BY c.created_at DESC""",
        (f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%"),
    )
    cars = dict_from_rows(cur, cur.fetchall())
    db.close()
    return render_template("index.html", cars=cars, user=get_user(), query=query)


@app.route("/test-email", methods=["GET", "POST"])
def test_email():
    gmail_user = os.environ.get("GMAIL_SMTP_USER", "Not configured")
    if request.method == "POST":
        to_email = request.form.get("to_email", "").strip()
        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "").strip()

        if not to_email or not subject or not body:
            flash("All fields are required.", "error")
            return render_template("test_email.html", user=get_user(), gmail_user=gmail_user)

        try:
            send_email(to_email, subject, body)
            flash(f"Email sent successfully to {to_email}!", "success")
        except Exception as e:
            flash(f"Failed to send email: {str(e)}", "error")

        return redirect(url_for("test_email"))
    return render_template("test_email.html", user=get_user(), gmail_user=gmail_user)


@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "user_id" not in session:
        flash("Please login to access your dashboard.", "error")
        return redirect(url_for("login"))

    user = get_user()
    db = get_db()
    cur = db.cursor()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "update_profile":
            username = request.form["username"].strip()
            email = request.form["email"].strip()
            phone = request.form.get("phone", "").strip()

            if not username or not email:
                flash("Username and email are required.", "error")
                db.close()
                return redirect(url_for("dashboard"))

            cur.execute(
                "SELECT id FROM SD_users WHERE (username = %s OR email = %s) AND id != %s",
                (username, email, user["id"]),
            )
            existing = cur.fetchone()
            if existing:
                flash("Username or email already taken.", "error")
                db.close()
                return redirect(url_for("dashboard"))

            cur.execute(
                "UPDATE SD_users SET username = %s, email = %s, phone = %s WHERE id = %s",
                (username, email, phone, user["id"]),
            )
            db.commit()
            flash("Profile updated successfully!", "success")

        elif action == "change_password":
            current_password = request.form["current_password"]
            new_password = request.form["new_password"]
            confirm_password = request.form["confirm_password"]

            cur.execute("SELECT password_hash FROM SD_users WHERE id = %s", (user["id"],))
            row = cur.fetchone()
            if not row or not check_password_hash(row[0], current_password):
                flash("Current password is incorrect.", "error")
                db.close()
                return redirect(url_for("dashboard"))

            if new_password != confirm_password:
                flash("New passwords do not match.", "error")
                db.close()
                return redirect(url_for("dashboard"))

            if len(new_password) < 6:
                flash("Password must be at least 6 characters.", "error")
                db.close()
                return redirect(url_for("dashboard"))

            cur.execute(
                "UPDATE SD_users SET password_hash = %s WHERE id = %s",
                (generate_password_hash(new_password), user["id"]),
            )
            db.commit()
            flash("Password changed successfully!", "success")

        elif action == "delete_account":
            password = request.form["password"]
            cur.execute("SELECT password_hash FROM SD_users WHERE id = %s", (user["id"],))
            row = cur.fetchone()
            if not row or not check_password_hash(row[0], password):
                flash("Incorrect password. Account not deleted.", "error")
                db.close()
                return redirect(url_for("dashboard"))

            cur.execute("DELETE FROM SD_cars WHERE user_id = %s", (user["id"],))
            cur.execute("DELETE FROM SD_email_verifications WHERE user_id = %s", (user["id"],))
            cur.execute("DELETE FROM SD_phone_verifications WHERE user_id = %s", (user["id"],))
            cur.execute("DELETE FROM SD_users WHERE id = %s", (user["id"],))
            db.commit()
            db.close()
            session.clear()
            flash("Your account has been deleted.", "success")
            return redirect(url_for("index"))

        db.close()
        return redirect(url_for("dashboard"))

    cur.execute("SELECT COUNT(*) FROM SD_cars WHERE user_id = %s", (user["id"],))
    car_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM SD_cars WHERE user_id = %s AND is_sold = 1", (user["id"],))
    sold_count = cur.fetchone()[0]
    db.close()

    return render_template("dashboard.html", user=user, car_count=car_count, sold_count=sold_count)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
