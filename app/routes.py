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
from datetime import date, datetime
from werkzeug.security import generate_password_hash
from app.decorators import edit_permission_required
from app.decorators import admin_required
# from app.database_models import TableName
# from app.database_session import db
# import smtp  # email

def get_template_by_name(name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT content FROM message_templates WHERE name = %s", (name,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None
# Esempio d'uso:
# template = get_template_by_name("moroso_one")
# msg = render_template_string(template, **context)


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
                template_name = get_template_by_name("moroso_plus")  # os.path.join(dir, filename)
            else:
                template_name = get_template_by_name("moroso_one")
        else:
            template_name = get_template_by_name(stato) 

        context = {
            "titolo": titolo,
            "nome": name,
            "cognome": surname,
            "ultimo_anno": last_paid,
            "anno_da_saldare": start_due,
            "stato": stato,
            "a_debito": amt_owed
        }

        msg = render_template_string(template_name, **context)
        messages.append((email, msg))
        csv_rows.append([email, name, surname, titolo, last_paid, start_due, stato, amt_owed, msg])

    cur.close()
    conn.close()
    return messages, csv_rows


@app.route("/db-test")
def db_test():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        result = cur.fetchone()
        cur.close()
        conn.close()
        return f"✅ Connessione al database riuscita. Risultato test: {result[0]}"
    except Exception as e:
        return f"❌ Errore nella connessione al database:<br><pre>{str(e)}</pre>"


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
@edit_permission_required
# class AddMember(qualcosa):
#    def post(path:MemberPath, body:MemberBody, query:MemberQuery):
#        pass
# from pydantic import BaseModel
# MemberPath(BaseModel):
#    member_id: int = Field(default=1, description='', pattern='', ge=0)

# class MemberBody(BaseModel):
#    surname: str
#    name: str
#    email: str
#    street_address: str
#    year_joined: int

# body.surname
# try:
#     db.session.add(body)
#     db.session.commit()
# except:
#    pass

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
@edit_permission_required
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
@edit_permission_required
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
@edit_permission_required
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
@edit_permission_required
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
@edit_permission_required
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
    
@app.route("/users")
@login_required
def list_users():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, is_admin, role FROM users ORDER BY id")
    users = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("users.html", users=users)



@app.route("/users/add", methods=["GET", "POST"])
@login_required
@admin_required
def add_user():
    if not current_user.is_admin:
        flash("Solo gli amministratori possono aggiungere utenti", "danger")
        return redirect(url_for("list_users"))

    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        is_admin = "is_admin" in request.form

        password_hash = generate_password_hash(password, method="pbkdf2:sha256")
        role = request.form["role"]
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO users (username, password_hash, is_admin, role) VALUES (%s, %s, %s, %s)",
                    (username, password_hash, is_admin, role))
        conn.commit()
        cur.close()
        conn.close()
        flash("Utente aggiunto con successo", "success")
        return redirect(url_for("list_users"))

    return render_template("add_user.html")


@app.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
def edit_user(user_id):
    if not current_user.role == "admin":
        flash("Solo gli amministratori possono modificare utenti.", "danger")
        return redirect(url_for("list_users"))

    conn = get_connection()
    cur = conn.cursor()

    if request.method == "POST":
        username = request.form["username"]
        role = request.form["role"]
        is_admin = "is_admin" in request.form

        cur.execute("""
            UPDATE users
            SET username = %s, role = %s, is_admin = %s
            WHERE id = %s
        """, (username, role, is_admin, user_id))

        conn.commit()
        cur.close()
        conn.close()
        flash("Utente aggiornato.", "success")
        return redirect(url_for("list_users"))

    cur.execute("SELECT id, username, role, is_admin FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    if not user:
        return "Utente non trovato", 404

    return render_template("edit_user.html", user=user)


@app.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
def delete_user(user_id):
    if not current_user.role == "admin":
        flash("Solo gli amministratori possono eliminare utenti.", "danger")
        return redirect(url_for("list_users"))
        
    if current_user.id == user_id:
        flash("Non puoi eliminare te stesso.", "warning")
        return redirect(url_for("list_users"))   

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    flash("Utente eliminato.", "info")
    return redirect(url_for("list_users"))




@app.route("/missing_fees")
@login_required
@edit_permission_required
def missing_fees():
    messages, _ = generate_missing_fees_data()
    return render_template("missing_fees.html", messages=messages)

@app.route("/missing_fees/export")
@login_required
@edit_permission_required
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

# Route per visualizzare, modificare e creare i template
@app.route("/templates")
@login_required
def list_templates():
    if current_user.role != "admin" and current_user.role != 'editor':
        flash("Solo gli amministratori possono modificare i template.", "danger")
        return redirect(url_for("members"))
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, name, description FROM message_templates ORDER BY name")
    templates = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("list_templates.html", templates=templates)

@app.route("/templates/<int:template_id>/edit", methods=["GET", "POST"])
@login_required
def edit_template(template_id):
    if current_user.role != "admin" and current_user.role != 'editor':
        flash("Solo gli amministratori possono modificare i template.", "danger")
        return redirect(url_for("members"))
    conn = get_connection()
    cur = conn.cursor()
    if request.method == "POST":
        description = request.form["description"]
        content = request.form["content"]
        cur.execute("UPDATE message_templates SET description = %s, content = %s WHERE id = %s", (description, content, template_id))
        conn.commit()
        flash("Template aggiornato.", "success")
        return redirect(url_for("list_templates"))
    cur.execute("SELECT id, name, description, content FROM message_templates WHERE id = %s", (template_id,))
    template = cur.fetchone()
    cur.close()
    conn.close()
    return render_template("edit_template.html", template=template)

@app.route("/templates/new", methods=["GET", "POST"])
@login_required
def create_template():
    if current_user.role != "admin" and current_user.role != 'editor':
        flash("Solo gli amministratori possono creare template.", "danger")
        return redirect(url_for("members"))
    if request.method == "POST":
        name = request.form["name"]
        description = request.form["description"]
        content = request.form["content"]

        conn = get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO message_templates (name, description, content) VALUES (%s, %s, %s)",
                    (name, description, content))
        conn.commit()
        cur.close()
        conn.close()
        flash("Template creato.", "success")
        return redirect(url_for("list_templates"))
    return render_template("create_template.html")


    

@app.route("/templates/help")
@login_required
def help_template():
    return render_template("help_template.html")
    
  
# Route for styled preview of a message template (HTML rendering)
@app.route("/templates/<int:template_id>/preview")
@login_required
def preview_template(template_id):
    if current_user.role != "admin" and current_user.role != 'editor':
        flash("Solo gli amministratori possono visualizzare l'anteprima.", "danger")
        return redirect(url_for("members"))

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name, description, content FROM message_templates WHERE id = %s", (template_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return "Template non trovato", 404

    name, description, template = row
    context = {
        "titolo": "Gentile Sig.",
        "nome": "Giuseppe",
        "cognome": "Verdi",
        "stato": "moroso",
        "a_debito": 70,
        "anno_da_saldare": 2023,
        "ultimo_anno": 2021
    }
    rendered_html = render_template_string(template, **context)
    return render_template("preview.html", rendered_html=rendered_html, name=name, description=description)
    

@app.route("/lettere/anteprima", methods=["GET", "POST"])
@login_required
def anteprima_lettera():
    if current_user.role != "admin" and current_user.role != 'editor':
        flash("Accesso riservato agli amministratori.", "danger")
        return redirect(url_for("members"))

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT name, description FROM message_templates ORDER BY name")
    templates = cur.fetchall()

    anteprima = None
    selected = None

    if request.method == "POST":
        selected = request.form.get("template")
        cur.execute("SELECT content FROM message_templates WHERE name = %s", (selected,))
        row = cur.fetchone()
        if row:
            template = row[0]
            context = {
                "titolo": "Gentile Sig.",
                "nome": "Giuseppe",
                "cognome": "Verdi",
                "stato": "regolare",
                "a_debito": 0,
                "anno_da_saldare": 2023,
                "ultimo_anno": 2022
            }
            anteprima = render_template_string(template, **context)

    cur.close()
    conn.close()
    return render_template("letter_preview.html", templates=templates, anteprima=anteprima, selected=selected, categoria=request.form.get("categoria", "tutti"))

@app.route("/lettere/export", methods=["POST"])
@login_required
def export_lettere():
    if current_user.role != "admin" and current_user.role != 'editor':
        flash("Accesso riservato agli amministratori.", "danger")
        return redirect(url_for("members"))

    selected = request.form.get("template")
    categoria = request.form.get("categoria", "tutti")
    conn = get_connection()
    cur = conn.cursor()


    # Recupera template scelto
    cur.execute("SELECT content FROM message_templates WHERE name = %s", (selected,))
    row = cur.fetchone()
    if not row:
        flash("Template non trovato.", "warning")
        return redirect(url_for("anteprima_lettera"))
    template = row[0]

    # Recupera i soci in base alla categoria
    if categoria == "tutti":
        cur.execute("SELECT member_id, surname, name, email, sex, stato FROM member_status ORDER BY surname")
    else:
        cur.execute("SELECT member_id, surname, name, email, sex, stato FROM member_status WHERE stato = %s ORDER BY surname", (categoria,))
    
    members = cur.fetchall()

    messages = []
    for m in members:
        member_id, surname, name, email, sex, stato = m
        titolo = "Gentile Sig.ra" if sex == "f" else "Gentile Sig."

        cur.execute("SELECT MAX(year) FROM subscriptions WHERE member_id = %s AND fee_paid = 'yes'", (member_id,))
        last_paid = cur.fetchone()[0] or 2022
        start_due = last_paid + 1

        context = {
            "titolo": titolo,
            "nome": name,
            "cognome": surname,
            "stato": "regolare",
            "ultimo_anno": last_paid,
            "anno_da_saldare": start_due,
            "a_debito": 35 * (datetime.now().year - last_paid)
        }
        msg = render_template_string(template, **context)
        messages.append([email, name, surname, stato, msg])

    cur.close()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Email", "Nome", "Cognome", "Stato","Messaggio"])
    writer.writerows(messages)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={selected}_lettere.csv"}
    )


@app.route("/")
def index():
    return render_template("index.html")
