from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, request, redirect, Response,url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
import os
from collections import Counter
from datetime import date
import csv
import io

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY")
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, id, username, password_hash, is_admin):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.is_admin = is_admin

    @staticmethod
    def get(user_id):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, username, password_hash, is_admin FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return User(*row)
        return None

    @staticmethod
    def find_by_username(username):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, username, password_hash, is_admin FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return User(*row)
        return None

# Load user from session
@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)



# Update with your real PostgreSQL credentials
def get_connection():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT")
    )

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
            cur.execute("INSERT INTO users (username, password_hash,is_admin) VALUES (%s, %s,%s)", (username, hashed, FALSE))
            conn.commit()
            cur.close()
            conn.close()
            flash("User registered successfully", "success")
            return redirect(url_for("members"))
        except:
            flash("Username already exists", "warning")

    return render_template("register.html")


# Protect all admin routes with @login_required

@app.route("/members")
@login_required
def members():
    search = request.args.get("search", "")
    conn = get_connection()
    cur = conn.cursor()

    if search:
        cur.execute("""
            SELECT member_id, surname, name, email, street_address, year_joined
            FROM members
            WHERE surname ILIKE %s OR name ILIKE %s OR email ILIKE %s
            ORDER BY surname
        """, (f"%{search}%", f"%{search}%", f"%{search}%"))
    else:
        cur.execute("""
            SELECT member_id, surname, name, email, street_address, year_joined
            FROM members
            ORDER BY surname
        """)

    members_data = cur.fetchall()
    # After getting members_data
    statuses = {}
    for member in members_data:
        cur.execute("""
        SELECT COUNT(*) FROM subscriptions
        WHERE member_id = %s AND year >= 2023 AND fee_paid = 'no'
        """, (member[0],))
        unpaid = cur.fetchone()[0]
        statuses[member[0]] = (unpaid == 0)  # True = all paid, False = still owing

    cur.close()
    conn.close()
    return render_template("members.html", members=members_data, search=search, statuses=statuses)

@app.route("/members/<int:member_id>")
def member_detail(member_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT member_id, surname, name, email, street_address, year_joined
        FROM members
        WHERE member_id = %s
    """, (member_id,))
    member = cur.fetchone()

    cur.execute("""
        SELECT year, fee_paid
        FROM subscriptions
        WHERE member_id = %s
        ORDER BY year DESC
    """, (member_id,))
    subscriptions = cur.fetchall()

    summary = Counter(year for year, paid in subscriptions if paid.lower() == 'yes')

    cur.close()
    conn.close()

    return render_template("member_detail.html", member=member, subscriptions=subscriptions, summary=summary)

@app.route("/members/add", methods=["GET", "POST"])
@login_required
def add_member():
    if request.method == "POST":
        surname = request.form["surname"]
        name = request.form["name"]
        email = request.form["email"]
        street_address = request.form["street_address"]
        year_joined = request.form["year_joined"]

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO members (surname, name, email, street_address, year_joined)
            VALUES (%s, %s, %s, %s, %s)
        """, (surname, name, email, street_address, year_joined))
        conn.commit()
        cur.close()
        conn.close()
        return redirect("/members")

    return render_template("add_member.html")

@app.route("/members/<int:member_id>/edit", methods=["GET", "POST"])
@login_required
def edit_member(member_id):
    conn = get_connection()
    cur = conn.cursor()

    if request.method == "POST":
        surname = request.form["surname"]
        name = request.form["name"]
        email = request.form["email"]
        street_address = request.form["street_address"]
        year_joined = request.form["year_joined"]

        cur.execute("""
            UPDATE members
            SET surname = %s, name = %s, email = %s, street_address = %s, year_joined = %s
            WHERE member_id = %s
        """, (surname, name, email, street_address, year_joined, member_id))
        conn.commit()
        cur.close()
        conn.close()
        return redirect("/members")

    cur.execute("""
        SELECT surname, name, email, street_address, year_joined
        FROM members WHERE member_id = %s
    """, (member_id,))
    member = cur.fetchone()
    cur.close()
    conn.close()

    if not member:
        return "Member not found", 404

    return render_template("edit_member.html", member_id=member_id, member=member)

@app.route("/members/<int:member_id>/delete", methods=["POST"])
def delete_member(member_id):
    today = date.today()

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO archived_members (member_id, surname, name, email, street_address, year_joined, deletion_date)
        SELECT member_id, surname, name, email, street_address, year_joined, %s
        FROM members WHERE member_id = %s
    """, (today, member_id))

    cur.execute("""
        INSERT INTO archived_subscriptions (member_id, year, fee_paid, deletion_date)
        SELECT member_id, year, fee_paid, %s
        FROM subscriptions WHERE member_id = %s
    """, (today, member_id))

    cur.execute("DELETE FROM subscriptions WHERE member_id = %s", (member_id,))
    cur.execute("DELETE FROM members WHERE member_id = %s", (member_id,))

    conn.commit()
    cur.close()
    conn.close()
    return redirect("/members")

@app.route("/members/<int:member_id>/subscriptions/add", methods=["GET", "POST"])
def add_subscription(member_id):
    if request.method == "POST":
        year = request.form["year"]
        fee_paid = request.form["fee_paid"]

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO subscriptions (member_id, year, fee_paid)
            VALUES (%s, %s, %s)
        """, (member_id, year, fee_paid))
        conn.commit()
        cur.close()
        conn.close()
        return redirect(f"/members/{member_id}")

    return render_template("add_subscription.html", member_id=member_id)

@app.route("/members/<int:member_id>/subscriptions/<int:year>/delete", methods=["POST"])
def delete_subscription(member_id, year):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM subscriptions
        WHERE member_id = %s AND year = %s
    """, (member_id, year))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(f"/members/{member_id}")

@app.route("/members/<int:member_id>/export")
def export_csv(member_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT year, fee_paid
        FROM subscriptions
        WHERE member_id = %s
        ORDER BY year DESC
    """, (member_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Year', 'Fee Paid'])
    writer.writerows(rows)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=subscriptions_{member_id}.csv"}
    )

@app.route("/archived")
def archived_members():
    search = request.args.get("search", "")
    conn = get_connection()
    cur = conn.cursor()

    if search:
        cur.execute("""
            SELECT member_id, surname, name, email, street_address, year_joined, deletion_date
            FROM archived_members
            WHERE surname ILIKE %s OR name ILIKE %s OR email ILIKE %s
            ORDER BY deletion_date DESC
        """, (f"%{search}%", f"%{search}%", f"%{search}%"))
    else:
        cur.execute("""
            SELECT member_id, surname, name, email, street_address, year_joined, deletion_date
            FROM archived_members
            ORDER BY deletion_date DESC
        """)

    archived_data = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("archived.html", members=archived_data, search=search)
    
    
@app.route("/members/<int:member_id>/subscriptions/<int:year>/edit", methods=["GET", "POST"])
def edit_subscription(member_id, year):
    conn = get_connection()
    cur = conn.cursor()

    if request.method == "POST":
        new_year = request.form["year"]
        fee_paid = request.form["fee_paid"]

        # Update subscription row
        cur.execute("""
            UPDATE subscriptions
            SET year = %s, fee_paid = %s
            WHERE member_id = %s AND year = %s
        """, (new_year, fee_paid, member_id, year))

        conn.commit()
        cur.close()
        conn.close()
        return redirect(f"/members/{member_id}")

    # GET request: fetch existing subscription
    cur.execute("""
        SELECT year, fee_paid
        FROM subscriptions
        WHERE member_id = %s AND year = %s
    """, (member_id, year))
    sub = cur.fetchone()

    cur.close()
    conn.close()

    if not sub:
        return "Subscription not found", 404

    return render_template("edit_subscription.html", member_id=member_id, subscription=sub)
    

if __name__ == "__main__":
    app.run(debug=True)
