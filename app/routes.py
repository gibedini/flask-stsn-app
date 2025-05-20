### app/routes.py

from flask import render_template, request, redirect, url_for, flash, Response, session
from flask_login import login_required, current_user
from flask import render_template, render_template_string
from app import app
from app.models import get_connection, User
from collections import Counter
from psycopg2 import IntegrityError
import csv
import io
from datetime import date


def generate_missing_fees_data():
    current_year = datetime.now().year
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT member_id, surname, name, email, stato, sex FROM member_status")
    members = cur.fetchall()

    messages = []
    csv_rows = []

    for member in members:
        member_id, surname, name, email, stato, sex = member
        stato = stato.strip().lower()

        cur.execute("""
            SELECT MAX(year) FROM subscriptions
            WHERE member_id = %s AND fee_paid = 'yes'
        """, (member_id,))
        last_paid = cur.fetchone()[0] or 2022

        start_due = last_paid + 1
        amt_owed = 0 if stato == "regolare" else 35 * (current_year - last_paid)
        titolo = "Gentile Sig.ra" if sex == "f" else "Gentile Sig."

        if stato == "moroso":
            if current_year - last_paid > 1:
                template_name = "messages/moroso_plus.txt"
            else:
                template_name = "messages/moroso_one.txt"
        else:
            template_name = f"messages/{stato}.txt"

        context = {
            "titolo": titolo,
            "nome": name,
            "cognome": surname,
            "ultimo_anno": last_paid,
            "anno_da_saldare": start_due,
            "stato": stato,
            "a_debito": amt_owed
        }

        msg = render_template(template_name, **context)
        messages.append((email, msg))
        csv_rows.append([email, name, surname, titolo, last_paid, start_due, stato, amt_owed, msg])

    cur.close()
    conn.close()
    return messages, csv_rows

@app.route("/members")
@login_required
def members():
    search = request.args.get("search", "")
    conn = get_connection()
    cur = conn.cursor()

    if search:
        cur.execute("""
            SELECT member_id, surname, name, email, street_address, year_joined, stato
            FROM member_status
            WHERE surname ILIKE %s OR name ILIKE %s OR email ILIKE %s
            ORDER BY surname
        """, (f"%{search}%", f"%{search}%", f"%{search}%"))
    else:
        cur.execute("""
            SELECT member_id, surname, name, email, street_address, year_joined, stato
            FROM member_status
            ORDER BY surname
        """)

    members_data = cur.fetchall()
    statuses = {}
    for member in members_data:
        cur.execute("""
            SELECT COUNT(*) FROM subscriptions
            WHERE member_id = %s AND year >= 2023 AND fee_paid = 'no'
        """, (member[0],))
        unpaid = cur.fetchone()[0]
        statuses[member[0]] = (unpaid == 0)

    cur.close()
    conn.close()
    return render_template("members.html", members=members_data, search=search, statuses=statuses)

@app.route("/members/add", methods=["GET", "POST"])
@login_required
def add_member():
    if request.method == "POST":
        surname = request.form["surname"]
        name = request.form["name"]
        email = request.form["email"]
        street_address = request.form["street_address"]
        year_joined = request.form["year_joined"]

        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO members (surname, name, email, street_address, year_joined)
                VALUES (%s, %s, %s, %s, %s)
            """, (surname, name, email, street_address, year_joined))
            conn.commit()
            flash("Socio aggiunto con successo", "success")
        except IntegrityError:
            conn.rollback()
            flash("Questo socio esiste già.", "warning")
        finally:
            cur.close()
            conn.close()
        return redirect("/members")

    return render_template("add_member.html")

@app.route("/members/<int:member_id>")
@login_required
def member_detail(member_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT member_id, surname, name, email, street_address, year_joined, stato
        FROM member_status
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

        try:
            cur.execute("""
                UPDATE members
                SET surname = %s, name = %s, email = %s, street_address = %s, year_joined = %s
                WHERE member_id = %s
            """, (surname, name, email, street_address, year_joined, member_id))
            conn.commit()
            flash("Dati del socio aggiornati", "success")
        except IntegrityError:
            conn.rollback()
            flash("Esiste già un socio con questi dati.", "warning")
        finally:
            cur.close()
            conn.close()
        return redirect(url_for("members"))

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
    

@app.route("/members/<int:member_id>/subscriptions/add", methods=["GET", "POST"])
@login_required
def add_subscription(member_id):
    if request.method == "POST":
        year = request.form["year"]
        fee_paid = request.form["fee_paid"]

        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO subscriptions (member_id, year, fee_paid)
                VALUES (%s, %s, %s)
            """, (member_id, year, fee_paid))
            conn.commit()
            flash("Quota inserita", "success")
        except IntegrityError:
            conn.rollback()
            flash("Quota già esistente per questo socio e anno.", "warning")
        finally:
            cur.close()
            conn.close()        
        return redirect(f"/members/{member_id}")
    else:
        current_year = datetime.now().year            
        return render_template("add_subscription.html", member_id=member_id, default_year=current_year)

@app.route("/members/<int:member_id>/subscriptions/<int:year>/edit", methods=["GET", "POST"])
@login_required
def edit_subscription(member_id, year):
    conn = get_connection()
    cur = conn.cursor()

    if request.method == "POST":
        new_year = request.form["year"]
        fee_paid = request.form["fee_paid"]

        try:
            cur.execute("""
                UPDATE subscriptions
                SET year = %s, fee_paid = %s
                WHERE member_id = %s AND year = %s
            """, (new_year, fee_paid, member_id, year))
            conn.commit()
            flash("Quota aggiornata", "success")
        except IntegrityError:
            conn.rollback()
            flash("Esiste già una quota per questo socio in quell'anno.", "warning")
        finally:
            cur.close()
            conn.close()
        return redirect(url_for("member_detail", member_id=member_id))

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

@app.route("/members/<int:member_id>/subscriptions/<int:year>/delete", methods=["POST"])
@login_required
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

@app.route("/members/<int:member_id>/delete", methods=["POST"])
@login_required
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
    
    
from datetime import datetime


@app.route("/missing_fees")
@login_required
def missing_fees():
    messages, _ = generate_missing_fees_data()
    return render_template("missing_fees.html", messages=messages)

@app.route("/missing_fees/export")
@login_required
def export_missing_fees():
    _, csv_rows = generate_missing_fees_data()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Email", "Nome", "Cognome", "Titolo", "Ultimo anno pagato", "Anno da saldare", "Stato", "Importo", "Messaggio"])
    writer.writerows(csv_rows)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=missing_fees.csv"}
    )
    

@app.route("/")
def index():
    return render_template("index.html")
