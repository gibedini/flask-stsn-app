### app/auth.py

### app/auth.py

from flask import render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import app
from app.models import User, get_connection

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.find_by_username(username)
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("members"))
        else:
            flash("Invalid username or password", "danger")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully", "info")
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
@login_required
def register():
    if not current_user.is_admin:
        flash("You are not authorized to register new users.", "danger")
        return redirect(url_for("members"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        hashed = generate_password_hash(password, method="pbkdf2:sha256", salt_length=16)
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO users (username, password_hash, is_admin) VALUES (%s, %s, %s)",
                        (username, hashed, False))
            conn.commit()
            cur.close()
            conn.close()
            flash("User registered successfully", "success")
            return redirect(url_for("members"))
        except:
            flash("Username already exists or DB error", "warning")
    return render_template("register.html")
