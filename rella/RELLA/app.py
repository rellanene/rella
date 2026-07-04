# app.py
import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, g
import mysql.connector
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import random
import string
from flask import Response, send_file
import csv
import pdfkit
import io
import time
from flask import send_from_directory
import pdfkit
from datetime import datetime, timedelta
from decimal import Decimal
import json




app = Flask(__name__)

WKHTML_PATH = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
config = pdfkit.configuration(wkhtmltopdf=WKHTML_PATH)

import os

def ensure_folders():
    base = os.path.join(os.getenv("LOCALAPPDATA"), "RELLA", "uploads")
    os.makedirs(os.path.join(base, "hr"), exist_ok=True)
    os.makedirs(os.path.join(base, "tasks"), exist_ok=True)
    os.makedirs(os.path.join(os.getenv("LOCALAPPDATA"), "RELLA", "finance_docs"), exist_ok=True)

ensure_folders()




from functools import wraps
from flask import session, redirect, url_for

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper





# --- Configuration ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'Clement-88',
    'database': 'rella'
}

SECRET_KEY = os.environ.get('RELLA_SECRET', 'change_this_secret')

app = Flask(__name__)
app.secret_key = SECRET_KEY

# --- DB helper ---
def get_db():
    if "db" not in g:
        g.db = mysql.connector.connect(
            host="localhost",
            user="root",
            password="Clement-88",
            database="rella",
            autocommit=False
        )
    else:
        try:
            # ensure connection is alive BEFORE returning it
            g.db.ping(reconnect=True, attempts=3, delay=1)
        except:
            # if ping fails, reconnect
            g.db.reconnect(attempts=3, delay=1)

    return g.db


def query_one(sql, params=None):
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute(sql, params or ())
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row

def query_all(sql, params=None):
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute(sql, params or ())
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows

def execute(sql, params=None, commit=True):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(sql, params or ())
    if commit:
        conn.commit()
    last = cur.lastrowid
    cur.close()
    conn.close()
    return last

# --- Utilities ---
def log_action(user_id, action, details=''):
    execute("INSERT INTO action_logs (user_id, action, details) VALUES (%s,%s,%s)", (user_id, action, details))

def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    return query_one("SELECT * FROM users WHERE id=%s", (uid,))

def require_login(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def has_permission(user_id, perm_code):
    
    # Admins have all permissions
    user = query_one("SELECT role FROM users WHERE id=%s", (user_id,))
    if not user:
        return False
    if user['role'] == 'admin':
        return True
    # check mapping
    perm = query_one("SELECT id FROM permissions WHERE code=%s", (perm_code,))
    if not perm:
        return False
    mapping = query_one("SELECT id FROM user_permissions WHERE user_id=%s AND permission_id=%s", (user_id, perm['id']))
    return bool(mapping)




@app.context_processor
def inject_permissions():
    return dict(has_permission=has_permission)


def permission_required(code):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            uid = session.get('user_id')
            if not uid:
                return redirect(url_for('login'))
            if not has_permission(uid, code):
                flash('Permission denied', 'error')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return wrapped
    return decorator

def generate_invoice_no():
    return 'INV' + datetime.now().strftime('%Y%m%d') + ''.join(random.choices(string.digits, k=4))

def generate_task_no():
    return ''.join(random.choices(string.digits, k=6))

import os
from flask import send_from_directory, abort

UPLOAD_BASE = os.path.join(os.getenv("LOCALAPPDATA"), "RELLA", "uploads")

@app.route("/uploads/<path:subpath>")
def serve_uploads(subpath):
    # Resolve full path
    file_path = os.path.join(UPLOAD_BASE, subpath)

    # Verify file exists
    if not os.path.isfile(file_path):
        abort(404)

    # Detect MIME type dynamically
    ext = subpath.lower().split(".")[-1]
    mime_map = {
        "pdf": "application/pdf",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
    }
    mimetype = mime_map.get(ext, "application/octet-stream")

    # Serve file with correct MIME type
    return send_from_directory(
        UPLOAD_BASE,
        subpath,
        as_attachment=False,      # opens directly in default app
        download_name=subpath,
        mimetype=mimetype
    )





@app.route("/")
def home():
    return redirect(url_for("dashboard"))




# --- Auth routes ---
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('identifier')  # username or email
        password = request.form.get('password')
        user = query_one("SELECT * FROM users WHERE username=%s OR email=%s", (identifier, identifier))
        if not user:
            flash('Invalid credentials', 'error')
            return redirect(url_for('login'))
        if user['role'] == 'staff' and not user['is_approved']:
            flash('Your account is pending approval by admin', 'error')
            return redirect(url_for('login'))
        if not check_password_hash(user['password_hash'], password):
            flash('Invalid credentials', 'error')
            return redirect(url_for('login'))
        if not user['is_active']:
            flash('Account suspended', 'error')
            return redirect(url_for('login'))
        session['user_id'] = user['id']
        log_action(user['id'], 'login', f'User logged in')
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/logout')
@require_login
def logout():
    uid = session.get('user_id')
    log_action(uid, 'logout', 'User logged out')
    session.clear()
    return render_template('logout.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = request.form.get('role','staff')
        business_id = request.form['business_id']
        q1,a1 = request.form['q1'], request.form['a1']
        q2,a2 = request.form['q2'], request.form['a2']
        q3,a3 = request.form['q3'], request.form['a3']

        # enforce admin count
        if role == 'admin':
            admins = query_one("SELECT COUNT(*) as c FROM users WHERE role='admin'")
            if admins and admins['c'] >= 3:
                flash('Maximum number of admins reached', 'error')
                return redirect(url_for('register'))

        pw_hash = generate_password_hash(password)
        is_approved = 1 if role == 'admin' else 0

        try:
            # Attempt to insert user
            user_id = execute("""
                INSERT INTO users
                (username,email,password_hash,role,business_id,is_approved,
                 q1,a1,q2,a2,q3,a3,created_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (username,email,pw_hash,role,business_id,is_approved,
                  q1,a1,q2,a2,q3,a3,None))

        except mysql.connector.IntegrityError as e:

            # Duplicate username or email
            if e.errno == 1062:
                if "username" in str(e):
                    flash("Username already exists. Please choose a different one.", "error")
                elif "email" in str(e):
                    flash("Email already registered. Try logging in or use another email.", "error")
                else:
                    flash("Duplicate entry detected.", "error")

                return redirect(url_for('register'))

            flash("A database integrity error occurred.", "error")
            return redirect(url_for('register'))

        except mysql.connector.DatabaseError as e:

            # Lock wait timeout (1205)
            if e.errno == 1205:
                flash("System busy. Please try again in a moment.", "error")
                return redirect(url_for('register'))

            flash("A database error occurred. Please try again.", "error")
            return redirect(url_for('register'))

        # If admin, grant all permissions
        if role == 'admin':
            perms = query_all("SELECT id FROM permissions")
            for p in perms:
                execute("""
                    INSERT INTO user_permissions (user_id,permission_id,granted_by)
                    VALUES (%s,%s,%s)
                """, (user_id, p['id'], user_id))

        log_action(user_id, 'register', f'User registered as {role}')
        flash('Registration successful. Await approval if staff.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/forgot-password', methods=['GET','POST'])
def forgot_password():
    if request.method == 'POST':
        step = request.form.get('step','1')
        email = request.form.get('email')
        if step == '1':
            user = query_one("SELECT id,email,q1,q2,q3 FROM users WHERE email=%s", (email,))
            if not user:
                flash('Email not found', 'error')
                return redirect(url_for('forgot_password'))
            # show questions
            return render_template('forgot_password.html', step=2, user=user)
        elif step == '2':
            uid = request.form.get('user_id')
            a1 = request.form.get('a1','').strip()
            a2 = request.form.get('a2','').strip()
            a3 = request.form.get('a3','').strip()
            user = query_one("SELECT * FROM users WHERE id=%s", (uid,))
            if not user:
                flash('User not found', 'error')
                return redirect(url_for('forgot_password'))
            # NOTE: in production answers should be hashed; here we compare directly
            if a1 != user['a1'] or a2 != user['a2'] or a3 != user['a3']:
                flash('Answers incorrect', 'error')
                return redirect(url_for('forgot_password'))
            return render_template('forgot_password.html', step=3, user=user)
        elif step == '3':
            uid = request.form.get('user_id')
            newpw = request.form.get('new_password')
            pw_hash = generate_password_hash(newpw)
            execute("UPDATE users SET password_hash=%s WHERE id=%s", (pw_hash, uid))
            log_action(uid, 'password_reset', 'Password reset via security questions')
            flash('Password updated. You can login now.', 'success')
            return redirect(url_for('login'))
    return render_template('forgot_password.html', step=1)

@app.route('/records/export')
@require_login
def export_records_csv():
    user = current_user()
    q = request.args.get('q','')
    start = request.args.get('start')
    end = request.args.get('end')

    sql = """
        SELECT s.invoice_no, c.name as client_name, s.total, s.created_at, u.username as user_name
        FROM sales s
        LEFT JOIN clients c ON s.client_id=c.id
        LEFT JOIN users u ON s.created_by=u.id
        WHERE 1=1
    """
    params = []

    if q:
        sql += " AND (s.invoice_no LIKE %s)"
        params.append(f'%{q}%')

    if start:
        sql += " AND s.created_at >= %s"
        params.append(start)

    if end:
        sql += " AND s.created_at <= %s"
        params.append(end)

    # ⭐ NEW: newest at top
    sql += " ORDER BY s.id DESC"

    rows = query_all(sql, params)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Invoice', 'Client', 'Total', 'Date & Time', 'User'])

    for r in rows:
        writer.writerow([r['invoice_no'], r['client_name'], r['total'], r['created_at'], r['user_name']])

    log_action(user['id'], 'export_records_csv', 'Exported records CSV')

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"records_{timestamp}.csv"

    resp = Response(output.getvalue(), mimetype='text/csv')
    resp.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return resp


@app.route("/invoice/<int:sale_id>")
@require_login
def invoice_view(sale_id):
    user = current_user()

    # Load sale header + store name
    sale = query_one("""
        SELECT 
            s.*, 
            c.name AS client_name, 
            u.username AS user_name,
            st.name AS store_name
        FROM sales s
        LEFT JOIN clients c ON s.client_id = c.id
        LEFT JOIN users u ON s.created_by = u.id
        LEFT JOIN stores st ON s.store_id = st.id
        WHERE s.id=%s
    """, (sale_id,))

    # Detect REAL column names in sale_items
    cols = query_all("SHOW COLUMNS FROM sale_items")
    colnames = [c["Field"] for c in cols]

    sale_id_col = next(c for c in colnames if "sale" in c.replace(" ", "").lower())
    product_id_col = next(c for c in colnames if "product" in c.replace(" ", "").lower())
    qty_col = next(c for c in colnames if "quantity" in c.replace(" ", "").lower())

    unit_price_col = next(
        c for c in colnames 
        if "unit" in c.replace(" ", "").lower() and "price" in c.replace(" ", "").lower()
    )

    total_price_col = next(
        c for c in colnames 
        if "total" in c.replace(" ", "").lower() and "price" in c.replace(" ", "").lower()
    )

    # Load raw sale items
    sql = f"SELECT * FROM sale_items WHERE `{sale_id_col}`=%s"
    items_raw = query_all(sql, (sale_id,))

    # GROUP ITEMS BY PRODUCT
    grouped = {}

    for it in items_raw:
        pid = it.get(product_id_col)
        qty = int(it.get(qty_col) or 0)
        price = float(it.get(unit_price_col) or 0)
        total = float(it.get(total_price_col) or 0)

        product = query_one("SELECT name FROM products WHERE id=%s", (pid,))
        product_name = product["name"] if product else "Unknown Product"

        if pid not in grouped:
            grouped[pid] = {
                "product_id": pid,
                "product_name": product_name,
                "qty": qty,
                "price": price,
                "total": total
            }
        else:
            grouped[pid]["qty"] += qty
            grouped[pid]["total"] += total

    items = list(grouped.values())

    return render_template("invoice.html", sale=sale, items=items, user=user)


@app.route("/invoice_whatsapp/<int:sale_id>")
def invoice_whatsapp(sale_id):
    pdf_path = generate_invoice_pdf(sale_id)
    phone = get_customer_phone(sale_id)

    if not phone:
        return "This customer has no phone number saved."

    os.system(f'start whatsapp://send?phone={phone}')

    return redirect(f"/invoice/{sale_id}")


@app.route("/invoice_email/<int:sale_id>")
def invoice_email(sale_id):
    # Simply open Classic Outlook — no attachment
    os.system('start "" outlook.exe')
    return redirect(f"/invoice/{sale_id}")


def get_customer_email(sale_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT c.email
        FROM sales s
        JOIN clients c ON c.id = s.client_id
        WHERE s.id = %s
    """, (sale_id,))

    row = cursor.fetchone()
    return row["email"] if row and row["email"] else None


def generate_invoice_pdf(sale_id):
    from flask import render_template
    import pdfkit
    import os

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT * FROM sales WHERE id=%s", (sale_id,))
    sale = cursor.fetchone()

    cursor.execute("""
        SELECT 
            p.name AS product_name,
            si.quantity AS qty,
            si.unit_price AS price,
            si.total_price AS total
        FROM sale_items si
        JOIN products p ON p.id = si.product_id
        WHERE si.sale_id = %s
    """, (sale_id,))
    items = cursor.fetchall()

    html = render_template("invoice.html", sale=sale, items=items)
    html = html.replace('/static/', 'C:/Users/rella/git/repository8/rella/RELLA/static/')

    output_path = f"generated_invoices/invoice_{sale_id}.pdf"
    os.makedirs("generated_invoices", exist_ok=True)

    WKHTML_PATH = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
    config = pdfkit.configuration(wkhtmltopdf=WKHTML_PATH)

    options = {
        "enable-local-file-access": None,
        "quiet": "",
        "load-error-handling": "ignore",
        "load-media-error-handling": "ignore"
    }

    pdfkit.from_string(html, output_path, configuration=config, options=options)

    return output_path

def get_customer_phone(sale_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT c.phone
        FROM sales s
        JOIN clients c ON c.id = s.client_id
        WHERE s.id = %s
    """, (sale_id,))

    row = cursor.fetchone()
    return row["phone"] if row and row["phone"] else None





@app.route('/invoice/<int:sale_id>/pdf')
@require_login
def invoice_pdf(sale_id):
    user = current_user()
    sale = query_one("SELECT s.*, c.name as client_name, c.email as client_email FROM sales s LEFT JOIN clients c ON s.client_id=c.id WHERE s.id=%s", (sale_id,))
    if not sale:
        flash('Invoice not found', 'error')
        return redirect(url_for('records'))
    items = query_all("""SELECT si.*, p.name as product_name
                         FROM sale_items si
                         LEFT JOIN products p ON si.product_id=p.id
                         WHERE si.sale_id=%s""", (sale_id,))

    html = render_template('invoice.html', sale=sale, items=items, user=user)
    pdf = pdfkit.from_string(html, False)
    log_action(user['id'], 'invoice_pdf', f'Generated PDF for sale {sale_id}')
    return Response(pdf, mimetype='application/pdf',
                    headers={'Content-Disposition': f'attachment; filename=invoice_{sale["invoice_no"]}.pdf'})



from datetime import datetime
import io
import csv

@app.route('/movements/export')
@require_login
def export_movements_csv():
    user = current_user()
    q = request.args.get('q','')
    start = request.args.get('start')
    end = request.args.get('end')

    sql = """
        SELECT 
            m.*,
            p.name AS product_name,
            u.username AS user_name,
            s.invoice_no,
            fs.name AS from_store_name,
            ts.name AS to_store_name
        FROM movements m
        LEFT JOIN products p ON m.product_id = p.id
        LEFT JOIN users u ON m.created_by = u.id
        LEFT JOIN sales s ON m.invoice_id = s.id
        LEFT JOIN stores fs ON m.from_store = fs.id
        LEFT JOIN stores ts ON m.to_store = ts.id
        WHERE 1=1
    """
    params = []

    if q:
        sql += " AND (s.invoice_no LIKE %s OR p.name LIKE %s)"
        params.extend((f'%{q}%', f'%{q}%'))

    if start:
        sql += " AND m.created_at >= %s"
        params.append(start)

    if end:
        sql += " AND m.created_at <= %s"
        params.append(end)

    sql += " ORDER BY m.id DESC"

    rows = query_all(sql, params)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date & Time', 'User', 'Product', 'Type', 'Qty', 'From', 'To', 'Invoice'])

    for r in rows:
        writer.writerow([
            r['created_at'],
            r['user_name'],
            r['product_name'],
            r['movement_type'],
            r['qty'],
            r['from_store_name'] if r['from_store_name'] else '',
            r['to_store_name'] if r['to_store_name'] else '',
            r['invoice_no'] if r['invoice_no'] else ''
        ])

    log_action(user['id'], 'export_movements_csv', 'Exported movements CSV')

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"movements_{timestamp}.csv"

    resp = Response(output.getvalue(), mimetype='text/csv')
    resp.headers['Content-Disposition'] = f'attachment; filename={filename}'
    return resp


def safe_cursor(db, dict=False):
    try:
        return db.cursor(dictionary=dict)
    except:
        # reconnect only when needed
        db.reconnect(attempts=3, delay=1)
        return db.cursor(dictionary=dict)


def safe_execute(cursor, query, params=None):
    try:
        cursor.execute(query, params)
    except mysql.connector.errors.ProgrammingError:
        # reconnect only when needed
        cursor.connection.reconnect(attempts=3, delay=1)
        cursor.execute(query, params)



# --- Dashboard ---
@app.route("/dashboard")
def dashboard():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()

    if not user:
        session.clear()
        return redirect(url_for("login"))

    role = user["role"]

    # ============================================================
    # STAFF DASHBOARD
    # ============================================================
    if role == "staff":
        cursor.execute("""
            SELECT 
                SUM(status='pending') AS pending,
                SUM(status='in_progress') AS in_progress,
                SUM(status='completed') AS completed
            FROM tasks
            WHERE assigned_to = %s
        """, (user_id,))
        row = cursor.fetchone() or {}

        tasks_status_data = [
            row.get("pending", 0),
            row.get("in_progress", 0),
            row.get("completed", 0)
        ]

        cursor.execute("""
            SELECT 
                SUM(priority='low') AS low,
                SUM(priority='medium') AS medium,
                SUM(priority='high') AS high
            FROM tasks
            WHERE assigned_to = %s
        """, (user_id,))
        row = cursor.fetchone() or {}

        tasks_priority_data = [
            row.get("low", 0),
            row.get("medium", 0),
            row.get("high", 0)
        ]

        return render_template(
            "dashboard.html",
            user=user,
            tasks_status_data=tasks_status_data,
            tasks_priority_data=tasks_priority_data
        )

    # ============================================================
    # ADMIN DASHBOARD
    # ============================================================
    else:

        # ============================================================
        # PRODUCTS — FIXED (SHOW STOCK LEVELS, NOT PRICES)
        # ============================================================
        cursor.execute("""
            SELECT 
                p.name AS product_name,
                COALESCE(SUM(ss.quantity), 0) AS total_stock
            FROM products p
            LEFT JOIN store_stock ss ON ss.product_id = p.id
            GROUP BY p.id, p.name
            ORDER BY p.name ASC
        """)
        rows = cursor.fetchall() or []
        products_labels = [r["product_name"] for r in rows] or ["No products"]
        products_data = [float(r["total_stock"] or 0) for r in rows] or [0.01]

        # ============================================================
        # CLIENTS
        # ============================================================
        cursor.execute("""
            SELECT DATE_FORMAT(created_at, '%Y-%m') AS month, COUNT(*) AS total
            FROM clients
            GROUP BY month
            ORDER BY month ASC
            LIMIT 6
        """)
        rows = cursor.fetchall() or []
        clients_labels = [r["month"] for r in rows] or ["No data"]
        clients_data = [r["total"] for r in rows] or [0]

        # ============================================================
        # SALES RECORDS (LAST 7 DAYS)
        # ============================================================
        cursor.execute("""
            SELECT DATE(created_at) AS day, SUM(total) AS total
            FROM sales
            WHERE created_at >= DATE(NOW()) - INTERVAL 6 DAY
            GROUP BY day
            ORDER BY day ASC
        """)
        rows = cursor.fetchall() or []
        sales_map = {str(r["day"]): float(r["total"] or 0) for r in rows}

        from datetime import datetime, timedelta
        records_labels = []
        records_data = []

        for i in range(6, -1, -1):
            day = (datetime.now() - timedelta(days=i)).date()
            day_str = str(day)
            records_labels.append(day_str)
            records_data.append(sales_map.get(day_str, 0))

        # ============================================================
        # STORES STOCK LEVELS
        # ============================================================
        cursor.execute("""
            SELECT s.name AS store_name, SUM(ss.quantity) AS total_stock
            FROM store_stock ss
            JOIN stores s ON s.id = ss.store_id
            GROUP BY s.name
        """)
        rows = cursor.fetchall() or []
        stores_labels = [r["store_name"] for r in rows] or ["No Stores"]
        stores_data = [float(r["total_stock"] or 0) for r in rows] or [0.01]

        # ============================================================
        # FINANCES SUMMARY
        # ============================================================
        cursor.execute("""
            SELECT 
                (SELECT COALESCE(SUM(amount),0) FROM external_entries WHERE entry_type='income') AS income,
                (SELECT COALESCE(SUM(amount),0) FROM external_entries WHERE entry_type='expense') AS expenses,
                (SELECT COALESCE(SUM(cost),0) FROM stock_in) AS stock_cost
        """)
        row = cursor.fetchone() or {}

        income = float(row.get("income", 0))
        expenses = float(row.get("expenses", 0))
        stock_cost = float(row.get("stock_cost", 0))

        finances_data = [
            income or 0.01,
            expenses or 0.01,
            stock_cost or 0.01
        ]

        # ============================================================
        # TASK INSIGHTS (COALESCE FIX)
        # ============================================================
        cursor.execute("""
            SELECT COALESCE(status, 'unspecified') AS status, COUNT(*) AS count
            FROM tasks
            GROUP BY status
        """)
        rows = cursor.fetchall() or []
        task_labels = [r["status"] for r in rows] or ["No Data"]
        task_values = [r["count"] for r in rows] or [0]

        # ============================================================
        # LAY‑BUY INSIGHTS
        # ============================================================
        cursor.execute("""
            SELECT 
                COALESCE(SUM(total_amount), 0) AS total_expected,
                COALESCE(SUM(paid_amount), 0) AS total_paid,
                COALESCE(SUM(total_amount - paid_amount), 0) AS total_outstanding
            FROM client_laybuys
        """)
        laybuy_data = cursor.fetchone() or {
            "total_expected": 0,
            "total_paid": 0,
            "total_outstanding": 0
        }

        return render_template(
            "dashboard.html",
            user=user,
            products_labels=products_labels,
            products_data=products_data,
            clients_labels=clients_labels,
            clients_data=clients_data,
            records_labels=records_labels,
            records_data=records_data,
            stores_labels=stores_labels,
            stores_data=stores_data,
            finances_data=finances_data,
            laybuy_data=laybuy_data,
            task_labels=task_labels,
            task_values=task_values
        )


        
@app.route("/api/insights/laybuys")
@require_login
def api_laybuy_insights():
    user = current_user()
    if user["role"] != "admin":
        return jsonify({"error": "Unauthorized"}), 403

    data = query_one("""
        SELECT 
            COUNT(*) AS total_laybuys,
            COALESCE(SUM(total_amount), 0) AS total_expected,
            COALESCE(SUM(paid_amount), 0) AS total_paid,
            COALESCE(SUM(total_amount - paid_amount), 0) AS total_outstanding
        FROM client_laybuys
    """)

    return jsonify(data)

@app.route("/dashboard/laybuy_chart_data")
@require_login
def laybuy_chart_data():
    user = current_user()
    if user["role"] != "admin":
        return jsonify({"error": "Unauthorized"}), 403

    data = query_one("""
        SELECT 
            COALESCE(SUM(total_amount), 0) AS total_expected,
            COALESCE(SUM(paid_amount), 0) AS total_paid,
            COALESCE(SUM(total_amount - paid_amount), 0) AS total_outstanding
        FROM client_laybuys
    """)

    return jsonify(data)

@app.route("/dashboard2", endpoint="dashboard_page")
@require_login
def dashboard_page():
    user = current_user()

    # Task insights
    task_rows = query_all("""
        SELECT status, COUNT(*) AS count
        FROM tasks
        GROUP BY status
    """)

    task_labels = [r["status"] for r in task_rows]
    task_values = [r["count"] for r in task_rows]

    # Lay‑Buy insights
    laybuy = query_one("""
        SELECT 
            COALESCE(SUM(total_amount), 0) AS total_expected,
            COALESCE(SUM(paid_amount), 0) AS total_paid,
            COALESCE(SUM(total_amount - paid_amount), 0) AS total_outstanding
        FROM client_laybuys
    """)

    return render_template(
        "dashboard.html",
        user=user,
        products_labels=products_labels,
        products_data=products_data,
        clients_labels=clients_labels,
        clients_data=clients_data,
        records_labels=records_labels,
        records_data=records_data,
        stores_labels=stores_labels,
        stores_data=stores_data,
        finances_data=finances_data,
        laybuy_data=laybuy,
        task_labels=task_labels,
        task_values=task_values
    )



@app.route("/api/insights/tasks")
@require_login
def api_task_insights():
    user = current_user()

    # Only admin can access this insight
    if user["role"] != "admin":
        return jsonify({"error": "Unauthorized"}), 403

    totals = query_one("SELECT COUNT(*) AS total_tasks FROM tasks")

    grouped = query_all("""
        SELECT status, COUNT(*) AS count
        FROM tasks
        GROUP BY status
    """)

    return jsonify({
        "total_tasks": totals["total_tasks"],
        "grouped": grouped
    })
        
@app.route('/task_report')
@require_login
def task_report():
    user = current_user()

    start = request.args.get('start')
    end = request.args.get('end')

    sql = """
        SELECT 
            t.*,
            u.username AS owner_name
        FROM tasks t
        LEFT JOIN users u ON t.assigned_to = u.id
        WHERE 1=1
    """

    params = []

    if start:
        sql += " AND t.created_at >= %s"
        params.append(start)

    if end:
        sql += " AND t.created_at <= %s"
        params.append(end)

    # ⭐ NEWEST FIRST
    sql += " ORDER BY t.created_at DESC"

    rows = query_all(sql, params)

    return render_template('task_report.html', tasks=rows, user=user)


@app.route('/export_task_report')
@require_login
def export_task_report():
    start = request.args.get('start')
    end = request.args.get('end')

    # Detect available columns in tasks table
    cols = query_all("SHOW COLUMNS FROM tasks")
    colnames = [c["Field"] for c in cols]

    has_duration = "duration" in colnames
    has_countdown = "countdown" in colnames

    # Build SELECT dynamically
    select_fields = """
        t.id,
        u.username AS owner,
        t.title,
        t.priority,
        t.status,
        t.created_at
    """

    if has_duration:
        select_fields += ", t.duration"

    if has_countdown:
        select_fields += ", t.countdown"

    sql = f"""
        SELECT {select_fields}
        FROM tasks t
        LEFT JOIN users u ON t.assigned_to = u.id
        WHERE 1=1
    """

    params = []

    if start:
        sql += " AND t.created_at >= %s"
        params.append(start)

    if end:
        sql += " AND t.created_at <= %s"
        params.append(end)

    # NEWEST FIRST
    sql += " ORDER BY t.created_at DESC"

    rows = query_all(sql, params)

    # Build CSV
    import csv
    from io import StringIO
    output = StringIO()
    writer = csv.writer(output)

    # Header row
    header = ["Task No", "Owner", "Title", "Priority", "Status", "Created At"]

    if has_duration:
        header.append("Duration")

    if has_countdown:
        header.append("Countdown")

    writer.writerow(header)

    # Data rows
    for r in rows:
        row = [
            r["id"],
            r["owner"],
            r["title"],
            r["priority"],
            r["status"],
            r["created_at"]
        ]

        if has_duration:
            row.append(r.get("duration", ""))

        if has_countdown:
            row.append(r.get("countdown", ""))

        writer.writerow(row)

    # Timestamped filename
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=task_report_{timestamp}.csv"
        }
    )

@app.route("/stores/<int:store_id>/edit", methods=["GET", "POST"])
@require_login
def edit_store(store_id):
    user = current_user()

    # ✅ Ensure admin flag is recognized (added exactly as requested)
    user["is_admin"] = (
        user.get("role") == "admin" or
        user.get("user_type") == "admin" or
        user.get("is_admin") in [1, True]
    )

    # Block non-admins
    if not user["is_admin"]:
        flash("You are not authorized to edit stores.", "danger")
        return redirect(url_for("stores"))

    # Load store
    store = query_one("SELECT * FROM stores WHERE id=%s", (store_id,))

    # Save changes
    if request.method == "POST":
        new_name = request.form["name"]
        execute("UPDATE stores SET name=%s WHERE id=%s", (new_name, store_id))
        flash("Store name updated successfully.", "success")
        return redirect(url_for("stores"))

    return render_template("edit_store.html", store=store, user=user)






# --- Products ---
# --- Products ---
@app.route('/products', methods=['GET','POST'])
@require_login
def products():
    user = current_user()

    if request.method == 'POST':
        barcode = request.form.get('barcode')
        name = request.form.get('name')
        wholesale = request.form.get('wholesale') or 0
        retail = request.form.get('retail') or 0

        db = get_db()  # ensure we can rollback

        try:
            execute("""
                INSERT INTO products (barcode, name, wholesale_price, retail_price, created_by)
                VALUES (%s, %s, %s, %s, %s)
            """, (barcode, name, wholesale, retail, user['id']))

            log_action(user['id'], 'add_product', f'Added product {name} ({barcode})')
            flash('Product added successfully', 'success')

        except mysql.connector.errors.IntegrityError as e:
            db.rollback()   # CRITICAL: release lock immediately

            if e.errno == 1062:
                flash(f"Barcode {barcode} already exists.", "error")
            else:
                flash("Database error occurred while adding product.", "error")

        except Exception:
            db.rollback()
            flash("Unexpected error occurred.", "error")

        # CRITICAL: ALWAYS return something
        return redirect(url_for('products'))

    # GET request → list products
    q = request.args.get('q','')
    if q:
        rows = query_all("""
            SELECT p.*, IFNULL(SUM(s.quantity),0) AS total_qty
            FROM products p
            LEFT JOIN store_stock s ON p.id = s.product_id
            WHERE p.name LIKE %s OR p.barcode LIKE %s
            GROUP BY p.id
            ORDER BY p.name ASC
        """, (f'%{q}%', f'%{q}%'))
    else:
        rows = query_all("""
            SELECT p.*, IFNULL(SUM(s.quantity),0) AS total_qty
            FROM products p
            LEFT JOIN store_stock s ON p.id = s.product_id
            GROUP BY p.id
            ORDER BY p.name ASC
        """)

    return render_template('products.html', products=rows, user=user)



@app.route('/products/edit/<int:pid>', methods=['POST'])
@require_login
def edit_product(pid):
    user = current_user()

    # Permission check
    if not has_permission(user['id'], 'products.manage'):
        flash('Permission denied', 'error')
        return redirect(url_for('products'))

    name = request.form.get('name')
    wholesale = request.form.get('wholesale')
    retail = request.form.get('retail')

    execute("""
        UPDATE products 
        SET name=%s, wholesale_price=%s, retail_price=%s, updated_by=%s 
        WHERE id=%s
    """, (name, wholesale, retail, user['id'], pid))

    log_action(user['id'], 'edit_product', f'Edited product {pid} — new wholesale {wholesale}, retail {retail}')
    flash('Product updated successfully', 'success')
    return redirect(url_for('products'))



#Add Kanban Route + Status Update
@app.route('/tasks/board')
@require_login
def task_board():
    user = current_user()

    tasks = query_all("""
        SELECT t.*, u.username AS assigned_name
        FROM tasks t
        LEFT JOIN users u ON t.assigned_to = u.id
        ORDER BY t.created_at DESC
    """)

    return render_template('task_board.html', tasks=tasks, user=user)

#AJAX endpoint for drag‑and‑drop status updates
@app.route('/tasks/update-status', methods=['POST'])
@require_login
def task_update_status_api():
    try:
        data = request.get_json(force=True)

        task_id = int(data.get('task_id'))
        new_status = data.get('status')

        allowed = ['open','in_progress','completed','archived']

        if new_status not in allowed:
            return jsonify({'success': False}), 400

        db = get_db()
        cursor = db.cursor()

        cursor.execute(
            "UPDATE tasks SET status=%s WHERE id=%s",
            (new_status, task_id)
        )

        db.commit()
        cursor.close()

        return jsonify({'success': True})

    except Exception as e:
        print("ERROR:", e)
        return jsonify({'success': False}), 500



@app.route('/products/delete/<int:pid>', methods=['POST'])
@require_login
def delete_product(pid):
    user = current_user()

    # Permission check
    if not has_permission(user['id'], 'products.manage'):
        flash('Permission denied', 'error')
        return redirect(url_for('products'))

    try:
        # Attempt to delete the product
        execute("DELETE FROM products WHERE id=%s", (pid,))
        log_action(user['id'], 'delete_product', f'Deleted product {pid}')
        flash('Product deleted successfully', 'success')

    except mysql.connector.errors.IntegrityError:
        # Product is linked to sale_items → cannot delete
        flash('You cannot delete this product because it has sales history.', 'error')
        log_action(user['id'], 'delete_product_blocked',
                   f'Blocked delete for product {pid} due to sales history')

    except Exception as e:
        # Any unexpected error
        flash('An unexpected error occurred while deleting the product.', 'error')
        log_action(user['id'], 'delete_product_error',
                   f'Error deleting product {pid}: {str(e)}')

    return redirect(url_for('products'))



# --- Clients ---
@app.route('/clients', methods=['GET','POST'])
@require_login
def clients():
    user = current_user()
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        cid = execute("INSERT INTO clients (name,email,phone,created_by) VALUES (%s,%s,%s,%s)", (name,email,phone,user['id']))
        log_action(user['id'], 'add_client', f'Added client {name}')
        flash('Client added', 'success')
        return redirect(url_for('clients'))
    q = request.args.get('q','')
    if q:
        rows = query_all("SELECT * FROM clients WHERE name LIKE %s OR email LIKE %s OR phone LIKE %s", (f'%{q}%', f'%{q}%', f'%{q}%'))
    else:
        rows = query_all("SELECT * FROM clients")
    return render_template('clients.html', clients=rows, user=user)

@app.route('/client/<int:client_id>')
@require_login
def client_portfolio(client_id):
    user = current_user()

    # 1️⃣ Load client
    client = query_one("SELECT * FROM clients WHERE id=%s", (client_id,))
    if not client:
        flash("Client not found", "danger")
        return redirect(url_for('clients'))

    # 2️⃣ Documents
    documents = query_all("""
        SELECT d.*, u.username AS uploaded_by_name
        FROM client_documents d
        LEFT JOIN users u ON d.uploaded_by = u.id
        WHERE d.client_id=%s
        ORDER BY d.uploaded_at DESC
    """, (client_id,))

    # 3️⃣ Sales History
    sales = query_all("""
        SELECT invoice_no, total, vat, created_at
        FROM sales
        WHERE client_id=%s
        ORDER BY id DESC
    """, (client_id,))

    # 4️⃣ Communication Log
    comms = query_all("""
        SELECT c.*, u.username AS staff_name
        FROM client_comms c
        LEFT JOIN users u ON c.created_by = u.id
        WHERE c.client_id=%s
        ORDER BY c.created_at DESC
    """, (client_id,))

    # 5️⃣ Tasks assigned to this client
    tasks = query_all("""
        SELECT *
        FROM tasks
        WHERE assigned_to=%s
        ORDER BY id DESC
    """, (client_id,))

    # 6️⃣ Timeline (full audit trail)
    timeline = query_all("""
        SELECT t.*, u.username AS staff_name
        FROM client_timeline t
        LEFT JOIN users u ON t.created_by = u.id
        WHERE t.client_id=%s
        ORDER BY t.created_at DESC
    """, (client_id,))

    # 7️⃣ Financial Overview
    invoice_total = query_one("""
        SELECT COALESCE(SUM(total),0) AS total
        FROM sales
        WHERE client_id=%s
    """, (client_id,))['total']

    payment_total = query_one("""
        SELECT COALESCE(SUM(amount),0) AS total
        FROM payments
        WHERE client_id=%s
    """, (client_id,))['total']

    outstanding = invoice_total - payment_total

    # 8️⃣ Render Portfolio Page
    return render_template(
        "client_portfolio.html",
        client=client,
        documents=documents,
        sales=sales,
        comms=comms,
        tasks=tasks,
        timeline=timeline,
        invoice_total=invoice_total,
        payment_total=payment_total,
        outstanding=outstanding
    )



@app.route('/client/<int:client_id>/upload', methods=['POST'])
@require_login
def client_upload(client_id):
    user = current_user()
    file = request.files.get('file')

    if not file:
        flash("No file selected", "danger")
        return redirect(url_for('client_portfolio', client_id=client_id))

    # Absolute upload directory for packaged app
    BASE_UPLOAD_PATH = r"C:\Program Files (x86)\RELLA8.1\RELLA8.1\uploads"
    upload_dir = os.path.join(BASE_UPLOAD_PATH, "clients")
    os.makedirs(upload_dir, exist_ok=True)

    # Secure filename and save
    filename = secure_filename(file.filename)
    stored_name = f"{int(time.time())}_{filename}"
    path = os.path.join(upload_dir, stored_name)
    file.save(path)

    # Insert document record
    execute("""
        INSERT INTO client_documents (client_id, filename, uploaded_by)
        VALUES (%s, %s, %s)
    """, (client_id, stored_name, user['id']))

    # Log timeline event
    execute("""
        INSERT INTO client_timeline (client_id, event_type, description, created_by)
        VALUES (%s, 'document', %s, %s)
    """, (client_id, f"Uploaded document {filename}", user['id']))

    flash("Document uploaded successfully.", "success")
    return redirect(url_for('client_portfolio', client_id=client_id))




@app.route('/client/<int:client_id>/add_comm', methods=['POST'])
@require_login
def add_client_comm(client_id):
    user = current_user()
    note = request.form.get("note")

    execute("""
        INSERT INTO client_comms (client_id, note, created_by)
        VALUES (%s, %s, %s)
    """, (client_id, note, user['id']))

    execute("""
        INSERT INTO client_timeline (client_id, event_type, description, created_by)
        VALUES (%s, 'communication', %s, %s)
    """, (client_id, f"Added communication note", user['id']))

    flash("Communication logged", "success")
    return redirect(url_for('client_portfolio', client_id=client_id))


@app.route('/client/<int:client_id>/add_note', methods=['POST'])
@require_login
def add_client_note(client_id):
    user = current_user()
    note = request.form.get("note")

    execute("""
        UPDATE clients SET notes=%s WHERE id=%s
    """, (note, client_id))

    execute("""
        INSERT INTO client_timeline (client_id, event_type, description, created_by)
        VALUES (%s, 'note', %s, %s)
    """, (client_id, "Updated client notes", user['id']))

    flash("Client notes updated", "success")
    return redirect(url_for('client_portfolio', client_id=client_id))


@app.route('/client/<int:client_id>/edit', methods=['GET','POST'])
@require_login
def edit_client(client_id):
    user = current_user()

    client = query_one("SELECT * FROM clients WHERE id=%s", (client_id,))
    if not client:
        flash("Client not found", "danger")
        return redirect(url_for('clients'))

    if request.method == 'POST':
        name = request.form.get("name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        client_type = request.form.get("client_type")
        vat_no = request.form.get("vat_no")
        address = request.form.get("address")
        notes = request.form.get("notes")
        status = request.form.get("status")

        execute("""
            UPDATE clients
            SET name=%s, email=%s, phone=%s, client_type=%s, vat_no=%s,
                address=%s, notes=%s, status=%s
            WHERE id=%s
        """, (name, email, phone, client_type, vat_no, address, notes, status, client_id))

        execute("""
            INSERT INTO client_timeline (client_id, event_type, description, created_by)
            VALUES (%s, 'edit', %s, %s)
        """, (client_id, "Client profile updated", user['id']))

        flash("Client updated successfully", "success")
        return redirect(url_for('client_portfolio', client_id=client_id))

    return render_template("client_edit.html", client=client)


def get_client_statement_data(client_id, start_date=None, end_date=None):
    client = query_one("SELECT * FROM clients WHERE id=%s", (client_id,))
    if not client:
        return None, None

    # Build invoice query
    invoice_sql = """
        SELECT id, invoice_no, total, created_at
        FROM sales
        WHERE client_id=%s
    """
    params = [client_id]

    if start_date:
        invoice_sql += " AND DATE(created_at) >= %s"
        params.append(start_date)

    if end_date:
        invoice_sql += " AND DATE(created_at) <= %s"
        params.append(end_date)

    invoice_sql += " ORDER BY created_at ASC"
    invoices = query_all(invoice_sql, tuple(params))

    # Build payment query
    payment_sql = """
        SELECT id, amount, payment_method, created_at
        FROM payments
        WHERE client_id=%s
    """
    params2 = [client_id]

    if start_date:
        payment_sql += " AND DATE(created_at) >= %s"
        params2.append(start_date)

    if end_date:
        payment_sql += " AND DATE(created_at) <= %s"
        params2.append(end_date)

    payment_sql += " ORDER BY created_at ASC"
    payments = query_all(payment_sql, tuple(params2))

    # Merge timeline
    timeline = []

    for i in invoices:
        timeline.append({
            "type": "invoice",
            "date": i['created_at'],
            "amount": i['total'],
            "ref": i['invoice_no']
        })

    for p in payments:
        timeline.append({
            "type": "payment",
            "date": p['created_at'],
            "amount": p['amount'],
            "ref": p['payment_method']
        })

    # Sort by date
    timeline = sorted(timeline, key=lambda x: x['date'])

    # Running balance
    balance = 0
    for t in timeline:
        if t['type'] == 'invoice':
            balance += t['amount']
        else:
            balance -= t['amount']
        t['balance'] = balance

    return client, timeline

from datetime import datetime

@app.route('/client/<int:client_id>/statement/export_csv')
@require_login
def export_client_statement_csv(client_id):
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    client, timeline = get_client_statement_data(client_id, start_date, end_date)

    if not client:
        flash("Client not found", "danger")
        return redirect(url_for('clients'))

    # Build CSV
    csv_data = "Date,Type,Reference,Amount,Running Balance\n"
    for t in timeline:
        csv_data += f"{t['date']},{t['type']},{t['ref']},{t['amount']},{t['balance']}\n"

    # Timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Final filename
    filename = f"client_statement_{client_id}_{timestamp}.csv"

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
from datetime import datetime
from flask import send_from_directory







@app.route("/client/<int:client_id>/credit/export_csv")
def client_credit_export_csv(client_id):
    # Fetch credit transactions
    rows = query_all("""
        SELECT id, amount, opening_balance, closing_balance, reference, note, pop_filename, created_at, created_by
        FROM client_credit_payments
        WHERE client_id=%s
        ORDER BY id DESC
    """, (client_id,))

    # Build CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow([
        "ID", "Amount", "Opening Balance", "Closing Balance",
        "Reference", "Note", "POP Filename", "Date", "Created By"
    ])

    # Data rows
    for r in rows:
        writer.writerow([
            r["id"], r["amount"], r["opening_balance"], r["closing_balance"],
            r["reference"], r["note"], r["pop_filename"], r["created_at"], r["created_by"]
        ])

    # Prepare response
    csv_data = output.getvalue()
    output.close()

    filename = f"client_{client_id}_credit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


    # similar filter logic as view
    # build CSV string and return Response with timestamped filename
    ...

@app.route("/client/<int:client_id>/credit/print", endpoint="client_credit_print_page")
@require_login
def client_credit_print(client_id):
    # same data as client_credit, but render print template
    return render_template("client_credit_print.html", ...)

BASE_UPLOAD_PATH = r"C:\Program Files (x86)\RELLA8.1\RELLA8.1\uploads"

app.config["CLIENT_UPLOAD_FOLDER"] = os.path.join(BASE_UPLOAD_PATH, "client_credit")
os.makedirs(app.config["CLIENT_UPLOAD_FOLDER"], exist_ok=True)


@app.route("/client/credit/pop/<filename>", endpoint="client_credit_pop_download_file")
@require_login
def client_credit_pop_download(filename):

    return send_from_directory(app.config["CLIENT_UPLOAD_FOLDER"], filename, as_attachment=True)


from datetime import datetime
import random

def generate_q_number():
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    rnd = random.randint(100, 999)
    return f"Q{ts}{rnd}"


def generate_q_number():
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    rnd = random.randint(100, 999)
    return f"Q{ts}{rnd}"


@app.route("/client/<int:client_id>/credit", endpoint="client_credit_page")
@require_login
def client_credit(client_id):
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    client = query_one("SELECT * FROM clients WHERE id=%s", (client_id,))
    credit = query_one("SELECT * FROM client_credits WHERE client_id=%s", (client_id,))

    sql = """
        SELECT p.*, u.username AS staff_name
        FROM client_credit_payments p
        LEFT JOIN users u ON u.id = p.created_by
        WHERE p.client_id=%s
    """
    params = [client_id]

    if start_date:
        sql += " AND DATE(p.created_at) >= %s"
        params.append(start_date)
    if end_date:
        sql += " AND DATE(p.created_at) <= %s"
        params.append(end_date)

    sql += " ORDER BY p.created_at DESC"
    payments = query_all(sql, tuple(params))

    return render_template(
        "client_credit.html",
        client=client,
        credit=credit,
        payments=payments,
        start_date=start_date,
        end_date=end_date
    )



@app.route("/client/<int:client_id>/credit/pay", methods=["POST"])
@require_login
def client_credit_pay(client_id):
    amount = Decimal(request.form.get("amount") or "0")
    note = request.form.get("note") or ""

    # Use session directly (your decorator guarantees this exists)
    user_id = session.get("user_id")

    # Ensure credit record exists
    credit = query_one("SELECT * FROM client_credits WHERE client_id=%s", (client_id,))
    if not credit:
        execute("""
            INSERT INTO client_credits (client_id, opening_balance, current_balance, credit_limit, created_by, updated_by)
            VALUES (%s, 0, 0, 0, %s, %s)
        """, (client_id, user_id, user_id))
        credit = query_one("SELECT * FROM client_credits WHERE client_id=%s", (client_id,))

    opening = credit["current_balance"]
    closing = opening - amount

    # POP file upload
    pop_filename = None
    file = request.files.get("pop_file")
    if file and file.filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = f"credit_pop_{client_id}_{ts}_{file.filename}"
        file.save(os.path.join(app.config["CLIENT_UPLOAD_FOLDER"], safe_name))
        pop_filename = safe_name

    # Insert payment record
    execute("""
        INSERT INTO client_credit_payments
        (client_id, amount, opening_balance, closing_balance, note, pop_filename, created_by)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
    """, (client_id, amount, opening, closing, note, pop_filename, user_id))

    # Update credit balance
    execute("""
        UPDATE client_credits SET current_balance=%s, updated_by=%s WHERE id=%s
    """, (closing, user_id, credit["id"]))

    flash("Client credit payment captured", "success")

    # SAFE redirect — avoids BuildError
    return redirect(f"/client/{client_id}/credit")



@app.route("/client/<int:client_id>/laybuy/<int:laybuy_id>/export_csv")
@require_login
def laybuy_export_csv(client_id, laybuy_id):
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    sql = """
        SELECT *
        FROM client_laybuy_payments
        WHERE laybuy_id=%s
    """
    params = [laybuy_id]

    if start_date:
        sql += " AND DATE(created_at) >= %s"
        params.append(start_date)

    if end_date:
        sql += " AND DATE(created_at) <= %s"
        params.append(end_date)

    sql += " ORDER BY created_at DESC"
    rows = query_all(sql, tuple(params))

    csv_data = "Date,Amount,Note,Created By\n"
    for r in rows:
        csv_data += f"{r['created_at']},{r['amount']},{r['note']},{r['created_by']}\n"

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"laybuy_{laybuy_id}_{ts}.csv"

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.route("/client/<int:client_id>/credit/print")
@require_login
def client_credit_print(client_id):
    client = query_one("SELECT * FROM clients WHERE id=%s", (client_id,))
    credit = query_one("SELECT * FROM client_credits WHERE client_id=%s", (client_id,))
    payments = query_all("""
        SELECT * FROM client_credit_payments
        WHERE client_id=%s ORDER BY created_at ASC
    """, (client_id,))

    return render_template("client_credit_print.html",
                           client=client,
                           credit=credit,
                           payments=payments)

BASE_UPLOAD_PATH = r"C:\Program Files (x86)\RELLA8.1\RELLA8.1\uploads"

app.config["CLIENT_UPLOAD_FOLDER"] = os.path.join(BASE_UPLOAD_PATH, "client_credit")
os.makedirs(app.config["CLIENT_UPLOAD_FOLDER"], exist_ok=True)


@app.route("/client/credit/pop/<filename>")
@require_login
def client_credit_pop_download(filename):
    return send_from_directory(app.config["CLIENT_UPLOAD_FOLDER"], filename, as_attachment=True)

@app.route("/client/<int:client_id>/laybuy")
@require_login
def client_laybuy(client_id):
    # Load client info
    client = query_one("SELECT * FROM clients WHERE id=%s", (client_id,))
    if not client:
        flash("Client not found", "danger")
        return redirect(url_for("clients"))

    # Try to load the client's first lay-buy record
    laybuy = query_one("""
        SELECT *
        FROM client_laybuys
        WHERE client_id=%s
        ORDER BY id ASC
        LIMIT 1
    """, (client_id,))

    # If no lay-buy exists, create the first one
    if not laybuy:
        user_id = session.get("user_id")

        execute("""
            INSERT INTO client_laybuys
                (client_id, status, start_date, expiry_date,
                 total_amount, paid_amount, created_at, updated_at,
                 created_by, updated_by)
            VALUES
                (%s, 'active', CURDATE(), DATE_ADD(CURDATE(), INTERVAL 3 MONTH),
                 0, 0, NOW(), NOW(),
                 %s, %s)
        """, (client_id, user_id, user_id))

        # Reload the newly created lay-buy
        laybuy = query_one("""
            SELECT *
            FROM client_laybuys
            WHERE client_id=%s
            ORDER BY id ASC
            LIMIT 1
        """, (client_id,))

    # Load lay-buy items
    items = query_all("""
        SELECT li.*, p.name AS product_name
        FROM client_laybuy_items li
        LEFT JOIN products p ON p.id = li.product_id
        WHERE li.laybuy_id=%s
    """, (laybuy["id"],))

    # Load lay-buy payments
    payments = query_all("""
        SELECT lp.*, u.username AS staff_name
        FROM client_laybuy_payments lp
        LEFT JOIN users u ON u.id = lp.created_by
        WHERE lp.laybuy_id=%s
        ORDER BY lp.created_at DESC
    """, (laybuy["id"],))

    # 🔥 Load products with the correct retail price column
    products = query_all("""
        SELECT id, name, retail_price
        FROM products
        ORDER BY name ASC
    """)

    return render_template(
        "client_laybuy.html",
        client=client,
        laybuy=laybuy,
        items=items,
        payments=payments,
        products=products
    )








@app.route("/laybuy/<int:laybuy_id>/pay", methods=["POST"])
@require_login
def laybuy_pay(laybuy_id):
    amount = Decimal(request.form.get("amount") or "0")
    note = request.form.get("note") or ""
    user_id = session.get("user_id")   # FIXED: g.user does not exist

    # Load lay-buy record
    laybuy = query_one("SELECT * FROM client_laybuys WHERE id=%s", (laybuy_id,))
    opening = laybuy["total_amount"] - laybuy["paid_amount"]
    closing = opening - amount

    # Handle POP upload
    pop_filename = None
    file = request.files.get("pop_file")
    if file and file.filename:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = f"laybuy_pop_{laybuy_id}_{ts}_{file.filename}"
        file.save(os.path.join(app.config["LAYBUY_UPLOAD_FOLDER"], safe_name))
        pop_filename = safe_name

    # Insert payment
    execute("""
        INSERT INTO client_laybuy_payments
        (laybuy_id, amount, opening_balance, closing_balance, note, pop_filename, created_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (laybuy_id, amount, opening, closing, note, pop_filename, user_id))

    # Update lay-buy totals
    execute("""
        UPDATE client_laybuys
        SET paid_amount = paid_amount + %s
        WHERE id=%s
    """, (amount, laybuy_id))

    flash("Lay‑buy payment captured", "success")
    return redirect(url_for("client_laybuy", client_id=laybuy["client_id"]))

#alone
# Absolute path for packaged app uploads
BASE_UPLOAD_PATH = r"C:\Program Files (x86)\RELLA8.1\RELLA8.1\uploads"

# Lay‑Buy upload folder
app.config["LAYBUY_UPLOAD_FOLDER"] = os.path.join(BASE_UPLOAD_PATH, "laybuy")
os.makedirs(app.config["LAYBUY_UPLOAD_FOLDER"], exist_ok=True)

BASE_UPLOAD_PATH = r"C:\Program Files (x86)\RELLA8.1\RELLA8.1\uploads"

app.config["LAYBUY_UPLOAD_FOLDER"] = os.path.join(BASE_UPLOAD_PATH, "laybuy")
os.makedirs(app.config["LAYBUY_UPLOAD_FOLDER"], exist_ok=True)


@app.route("/laybuy/upload", methods=["POST"])
@require_login
def laybuy_upload():
    file = request.files.get("file")
    if not file or not file.filename:
        flash("No file selected.", "danger")
        return redirect(request.referrer)

    save_path = os.path.join(app.config["LAYBUY_UPLOAD_FOLDER"], secure_filename(file.filename))
    file.save(save_path)

    flash("Lay‑Buy file uploaded successfully.", "success")
    return redirect(request.referrer)





@app.route("/client/<int:client_id>/laybuy/choice")
@require_login
def client_laybuy_choice(client_id):
    client = query_one("SELECT * FROM clients WHERE id=%s", (client_id,))
    if not client:
        flash("Client not found", "danger")
        return redirect(url_for("clients"))
    return render_template("client_laybuy_choice.html", client=client)


@app.route("/client/<int:client_id>/laybuy/create")
@require_login
def client_laybuy_create(client_id):
    client = query_one("SELECT * FROM clients WHERE id=%s", (client_id,))
    if not client:
        flash("Client not found", "danger")
        return redirect(url_for("clients"))

    user_id = session.get("user_id")

    # create shell lay‑buy
    execute("""
        INSERT INTO client_laybuys
            (client_id, status, start_date, expiry_date,
             total_amount, paid_amount, created_at, updated_at, created_by, updated_by)
        VALUES
            (%s, 'active', CURDATE(), DATE_ADD(CURDATE(), INTERVAL 3 MONTH),
             0, 0, NOW(), NOW(), %s, %s)
    """, (client_id, user_id, user_id))

    laybuy = query_one("""
        SELECT * FROM client_laybuys
        WHERE client_id=%s
        ORDER BY id DESC
        LIMIT 1
    """, (client_id,))

    # assign lay‑buy number
    execute("""
        UPDATE client_laybuys
        SET laybuy_number = %s
        WHERE id=%s
    """, (f"LB{laybuy['id']}", laybuy["id"]))

    flash(f"New Lay‑Buy created: LB{laybuy['id']}", "success")
    return redirect(url_for("laybuy_view", laybuy_id=laybuy["id"]))


@app.route("/laybuy/<int:laybuy_id>")
@require_login
def laybuy_view(laybuy_id):
    laybuy = query_one("SELECT * FROM client_laybuys WHERE id=%s", (laybuy_id,))
    if not laybuy:
        flash("Lay‑Buy not found", "danger")
        return redirect(url_for("clients"))

    client = query_one("SELECT * FROM clients WHERE id=%s", (laybuy["client_id"],))

    items = query_all("""
        SELECT li.*, p.name AS product_name
        FROM client_laybuy_items li
        LEFT JOIN products p ON p.id = li.product_id
        WHERE li.laybuy_id=%s
    """, (laybuy_id,))

    payments = query_all("""
        SELECT lp.*, u.username AS staff_name
        FROM client_laybuy_payments lp
        LEFT JOIN users u ON u.id = lp.created_by
        WHERE lp.laybuy_id=%s
        ORDER BY lp.created_at DESC
    """, (laybuy_id,))

    products = query_all("""
        SELECT id, name, retail_price
        FROM products
        ORDER BY name ASC
    """)

    return render_template(
        "client_laybuy.html",
        client=client,
        laybuy=laybuy,
        items=items,
        payments=payments,
        products=products
    )



@app.route("/laybuy/<int:laybuy_id>/archive", methods=["POST"])
@require_login
def laybuy_archive(laybuy_id):
    laybuy = query_one("SELECT * FROM client_laybuys WHERE id=%s", (laybuy_id,))
    if not laybuy:
        flash("Lay‑Buy not found", "danger")
        return redirect(url_for("clients"))

    execute("""
        UPDATE client_laybuys
        SET status='archived', archived_at=NOW()
        WHERE id=%s
    """, (laybuy_id,))

    flash("Lay‑Buy archived.", "success")
    return redirect(url_for("laybuy_view", laybuy_id=laybuy_id))


@app.route("/client/<int:client_id>/laybuy/manage", methods=["GET", "POST"])
@require_login
def client_laybuy_manage(client_id):
    client = query_one("SELECT * FROM clients WHERE id=%s", (client_id,))
    if not client:
        flash("Client not found", "danger")
        return redirect(url_for("clients"))

    # Load all lay-buys for this client
    laybuys = query_all("""
        SELECT laybuy_number, status
        FROM client_laybuys
        WHERE client_id=%s
        ORDER BY id DESC
    """, (client_id,))

    if request.method == "POST":
        number = request.form.get("laybuy_number")
        laybuy = query_one("""
            SELECT * FROM client_laybuys
            WHERE client_id=%s AND laybuy_number=%s
        """, (client_id, number))

        if not laybuy:
            flash("Lay‑Buy not found for this client.", "danger")
            return redirect(url_for("client_laybuy_manage", client_id=client_id))

        return redirect(url_for("laybuy_view", laybuy_id=laybuy["id"]))

    return render_template("client_laybuy_manage.html", client=client, laybuys=laybuys)


@app.route("/laybuy/print", methods=["GET"])
@require_login
def laybuy_print_statement():
    laybuy_number = request.args.get("laybuy_number")
    if not laybuy_number:
        flash("Please select a Lay‑Buy number to print.", "danger")
        return redirect(request.referrer or url_for("clients"))

    laybuy = query_one("SELECT * FROM client_laybuys WHERE laybuy_number=%s", (laybuy_number,))
    if not laybuy:
        flash("Lay‑Buy not found.", "danger")
        return redirect(request.referrer or url_for("clients"))

    client = query_one("SELECT * FROM clients WHERE id=%s", (laybuy["client_id"],))

    items = query_all("""
        SELECT li.*, p.name AS product_name
        FROM client_laybuy_items li
        LEFT JOIN products p ON p.id = li.product_id
        WHERE li.laybuy_id=%s
    """, (laybuy["id"],))

    payments = query_all("""
        SELECT *
        FROM client_laybuy_payments
        WHERE laybuy_id=%s
        ORDER BY created_at ASC
    """, (laybuy["id"],))

    return render_template(
        "laybuy_statement.html",
        client=client,
        laybuy=laybuy,
        items=items,
        payments=payments
    )





@app.route("/client/<int:client_id>/laybuy/<int:laybuy_id>/add_item", methods=["POST"])
@require_login
def laybuy_add_item(client_id, laybuy_id):
    product_id = request.form["product_id"]
    qty = float(request.form["qty"])
    unit_price = float(request.form["unit_price"])
    line_total = qty * unit_price

    # Insert item (NO created_by column)
    execute("""
        INSERT INTO client_laybuy_items (laybuy_id, product_id, qty, unit_price, line_total)
        VALUES (%s, %s, %s, %s, %s)
    """, (laybuy_id, product_id, qty, unit_price, line_total))

    # Update lay-buy total
    execute("""
        UPDATE client_laybuys
        SET total_amount = total_amount + %s
        WHERE id=%s
    """, (line_total, laybuy_id))

    flash("Item added to lay‑buy.", "success")
    return redirect(url_for("client_laybuy", client_id=client_id))





@app.route("/laybuy/<int:laybuy_id>/export_csv", endpoint="laybuy_export_csv_page")
@require_login
def laybuy_export_csv(laybuy_id):

    rows = query_all("""
        SELECT * FROM client_laybuy_payments
        WHERE laybuy_id=%s ORDER BY created_at ASC
    """, (laybuy_id,))

    csv_data = "Date,Amount,Opening,Closing,Note\n"
    for r in rows:
        csv_data += f"{r['created_at']},{r['amount']},{r['opening_balance']},{r['closing_balance']},{r['note']}\n"

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"laybuy_{laybuy_id}_{ts}.csv"

    return Response(csv_data, mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.route("/laybuy/<int:laybuy_id>/print")
@require_login
def laybuy_print(laybuy_id):
    laybuy = query_one("SELECT * FROM client_laybuys WHERE id=%s", (laybuy_id,))
    items = query_all("SELECT * FROM client_laybuy_items WHERE laybuy_id=%s", (laybuy_id,))
    payments = query_all("SELECT * FROM client_laybuy_payments WHERE laybuy_id=%s ORDER BY created_at ASC", (laybuy_id,))

    return render_template("laybuy_print.html",
                           laybuy=laybuy,
                           items=items,
                           payments=payments)


@app.route("/laybuy/pop/<path:filename>")
@require_login
def laybuy_pop_download(filename):
    # Absolute path for packaged app uploads
    BASE_UPLOAD_PATH = r"C:\Program Files (x86)\RELLA8.1\RELLA8.1\uploads"
    laybuy_folder = os.path.join(BASE_UPLOAD_PATH, "laybuy")

    # Ensure folder exists
    os.makedirs(laybuy_folder, exist_ok=True)

    # Serve file from laybuy folder
    return send_from_directory(laybuy_folder, filename, as_attachment=True)



@app.route("/client/<int:client_id>/quotation/new", methods=["GET", "POST"])
@require_login
def quotation_new(client_id):
    if request.method == "POST":
        items_json = request.form.get("items_json")
        items = json.loads(items_json or "[]")

        # Calculate total
        total = sum(item["total"] for item in items)

        # Generate quotation number
        q_number = generate_q_number()

        # Save quotation header
        execute("""
            INSERT INTO client_quotations 
            (client_id, q_number, total_amount, status, valid_until, created_by)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            client_id,
            q_number,
            total,
            "Draft",
            datetime.now().date(),
            session["user_id"]
        ))

        # Fetch quotation ID
        quotation = query_one(
            "SELECT id FROM client_quotations WHERE q_number=%s",
            (q_number,)
        )

        # Save quotation items (FIXED HERE)
        for item in items:

            # Lookup product_id using product name
            product = query_one(
                "SELECT id FROM products WHERE name=%s",
                (item["name"],)
            )

            execute("""
                INSERT INTO client_quotation_items 
                (quotation_id, product_id, qty, unit_price, line_total)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                quotation["id"],
                product["id"],      # resolved from DB
                item["qty"],
                item["price"],
                item["total"]
            ))

        flash("Quotation saved successfully", "success")
        return redirect(f"/client/{client_id}/quotation")

    # GET request — render form
    client = query_one("SELECT * FROM clients WHERE id=%s", (client_id,))
    products = query_all("SELECT * FROM products ORDER BY name ASC")
    q_number = generate_q_number()
    valid_until = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

    return render_template(
        "quotation_new.html",
        client=client,
        products=products,
        q_number=q_number,
        valid_until=valid_until
    )




    
@app.route("/client/<int:client_id>/quotation", endpoint="client_quotation_page")
@require_login
def client_quotation(client_id):
    q = request.args.get("q")

    # Fetch client
    client = query_one("SELECT * FROM clients WHERE id=%s", (client_id,))
    if not client:
        flash("Client not found", "error")
        return redirect(url_for("clients_page"))

    # Base query
    sql = """
        SELECT *
        FROM client_quotations
        WHERE client_id=%s
    """
    params = [client_id]

    # Search filter
    if q:
        sql += " AND (q_number LIKE %s OR status LIKE %s)"
        params.extend([f"%{q}%", f"%{q}%"])

    # Final ordering
    sql += " ORDER BY id DESC"

    # Execute query
    quotations = query_all(sql, tuple(params))

    return render_template(
        "client_quotation.html",
        client=client,
        quotations=quotations,
        q=q
    )

    







@app.route("/quotation/save", methods=["POST"])
@require_login
def quotation_save():
    client_id = request.form.get("client_id")
    q_number = request.form.get("q_number")
    valid_until = request.form.get("valid_until")
    total = Decimal(request.form.get("total") or "0")
    user_id = g.user["id"]

    execute("""
        INSERT INTO client_quotations
        (client_id, q_number, total_amount, valid_until, created_by)
        VALUES (%s,%s,%s,%s,%s)
    """, (client_id, q_number, total, valid_until, user_id))

    quotation_id = query_one("SELECT LAST_INSERT_ID() AS id")["id"]

    items = json.loads(request.form.get("items_json"))

    for item in items:
        execute("""
            INSERT INTO client_quotation_items
            (quotation_id, product_id, qty, unit_price, line_total)
            VALUES (%s,%s,%s,%s,%s)
        """, (quotation_id, item["id"], item["qty"], item["price"], item["total"]))

    flash("Quotation saved", "success")
    return jsonify({"success": True, "quotation_id": quotation_id})


@app.route("/quotation/<int:quotation_id>/print")
@require_login
def quotation_print(quotation_id):
    quotation = query_one("SELECT * FROM client_quotations WHERE id=%s", (quotation_id,))
    client = query_one("SELECT * FROM clients WHERE id=%s", (quotation["client_id"],))
    items = query_all("""
        SELECT qi.*, p.name AS product_name
        FROM client_quotation_items qi
        LEFT JOIN products p ON p.id = qi.product_id
        WHERE qi.quotation_id=%s
    """, (quotation_id,))

    return render_template("quotation_print.html",
                           quotation=quotation,
                           client=client,
                           items=items)


#Alone
# Absolute base path for packaged app
BASE_UPLOAD_PATH = r"C:\Program Files (x86)\RELLA8.1\RELLA8.1\uploads"

# Quotation upload folder
app.config["QUOTATION_UPLOAD_FOLDER"] = os.path.join(BASE_UPLOAD_PATH, "quotations")
os.makedirs(app.config["QUOTATION_UPLOAD_FOLDER"], exist_ok=True)


@app.route("/quotation/<int:quotation_id>/files/upload", methods=["GET", "POST"])
def quotation_file_upload(quotation_id):

    user_id = session.get("user_id")
    if not user_id:
        return redirect("/login")

    if request.method == "POST":
        file = request.files.get("file")

        if file and file.filename:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = f"quotation_{quotation_id}_{ts}_{file.filename}"

            # Save to absolute folder
            file.save(os.path.join(app.config["QUOTATION_UPLOAD_FOLDER"], safe_name))

            execute("""
                INSERT INTO client_quotation_files (quotation_id, filename, uploaded_by)
                VALUES (%s, %s, %s)
            """, (quotation_id, safe_name, user_id))

            flash("File uploaded", "success")
            return redirect(url_for("quotation_file_upload", quotation_id=quotation_id))

    files = query_all("""
        SELECT * FROM client_quotation_files
        WHERE quotation_id=%s
        ORDER BY id DESC
    """, (quotation_id,))

    return render_template("quotation_files.html", quotation_id=quotation_id, files=files)



app.config["CLIENT_UPLOAD_FOLDER"] = os.path.join("uploads", "client_credit")
os.makedirs(app.config["CLIENT_UPLOAD_FOLDER"], exist_ok=True)

BASE_UPLOAD_PATH = r"C:\Program Files (x86)\RELLA8.1\RELLA8.1\uploads"

# Quotation uploads
app.config["QUOTATION_UPLOAD_FOLDER"] = os.path.join(BASE_UPLOAD_PATH, "quotations")
os.makedirs(app.config["QUOTATION_UPLOAD_FOLDER"], exist_ok=True)

# Client credit uploads
app.config["CLIENT_UPLOAD_FOLDER"] = os.path.join(BASE_UPLOAD_PATH, "client_credit")
os.makedirs(app.config["CLIENT_UPLOAD_FOLDER"], exist_ok=True)






@app.route('/client/<int:client_id>/statement/print')
@require_login
def print_client_statement(client_id):
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    client, timeline = get_client_statement_data(client_id, start_date, end_date)

    if not client:
        flash("Client not found", "danger")
        return redirect(url_for('clients'))

    return render_template(
        "client_statement_print.html",
        client=client,
        timeline=timeline,
        start_date=start_date,
        end_date=end_date
    )




def get_client_statement_data(client_id, start_date=None, end_date=None):
    client = query_one("SELECT * FROM clients WHERE id=%s", (client_id,))
    if not client:
        return None, None

    # Build invoice query
    invoice_sql = """
        SELECT id, invoice_no, total, created_at
        FROM sales
        WHERE client_id=%s
    """
    params = [client_id]

    if start_date:
        invoice_sql += " AND DATE(created_at) >= %s"
        params.append(start_date)

    if end_date:
        invoice_sql += " AND DATE(created_at) <= %s"
        params.append(end_date)

    invoice_sql += " ORDER BY created_at ASC"
    invoices = query_all(invoice_sql, tuple(params))

    # Build payment query
    payment_sql = """
        SELECT id, amount, payment_method, created_at
        FROM payments
        WHERE client_id=%s
    """
    params2 = [client_id]

    if start_date:
        payment_sql += " AND DATE(created_at) >= %s"
        params2.append(start_date)

    if end_date:
        payment_sql += " AND DATE(created_at) <= %s"
        params2.append(end_date)

    payment_sql += " ORDER BY created_at ASC"
    payments = query_all(payment_sql, tuple(params2))

    # Merge timeline
    timeline = []

    for i in invoices:
        timeline.append({
            "type": "invoice",
            "date": i['created_at'],
            "amount": i['total'],
            "ref": i['invoice_no']
        })

    for p in payments:
        timeline.append({
            "type": "payment",
            "date": p['created_at'],
            "amount": p['amount'],
            "ref": p['payment_method']
        })

    # Sort
    timeline = sorted(timeline, key=lambda x: x['date'])

    # Running balance
    balance = 0
    for t in timeline:
        if t['type'] == 'invoice':
            balance += t['amount']
        else:
            balance -= t['amount']
        t['balance'] = balance

    return client, timeline

BASE_UPLOAD_PATH = r"C:\Program Files (x86)\RELLA8.1\RELLA8.1\uploads"
app.config["QUOTATION_UPLOAD_FOLDER"] = os.path.join(BASE_UPLOAD_PATH, "quotations")
os.makedirs(app.config["QUOTATION_UPLOAD_FOLDER"], exist_ok=True)

@app.route("/quotation/files/download/<path:filename>", endpoint="quotation_file_download")
@require_login
def quotation_file_download(filename):
    folder = app.config["QUOTATION_UPLOAD_FOLDER"]
    return send_from_directory(folder, filename, as_attachment=True)





@app.route('/client/<int:client_id>/statement')
@require_login
def client_statement(client_id):
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    client, timeline = get_client_statement_data(client_id, start_date, end_date)

    if not client:
        flash("Client not found", "danger")
        return redirect(url_for('clients'))

    return render_template(
        "client_statement.html",
        client=client,
        timeline=timeline,
        start_date=start_date,
        end_date=end_date
    )





# --- Sales (simple flow) ---
@app.route('/sales', methods=['GET'])
@require_login
def sales():
    user = current_user()

    stores = query_all("SELECT id, name FROM stores ORDER BY name ASC")
    clients = query_all("SELECT id, name FROM clients ORDER BY name ASC")

    raw_products = query_all("SELECT * FROM products ORDER BY name ASC")

    products = []

    for p in raw_products:
        detected_price = None

        # Auto-detect retail price column (handles ALL hidden spaces)
        for key in p.keys():
            cleaned = (
                key.replace(" ", "")
                   .replace("\u00A0", "")
                   .replace("\t", "")
                   .replace("\u2007", "")
                   .replace("\u202F", "")
                   .lower()
            )

            if "retail" in cleaned and "price" in cleaned:
                detected_price = p[key]
                break

        # Fallback to legacy "price" column
        if detected_price is None:
            detected_price = p.get("price", 0)

        # Guarantee numeric value
        try:
            detected_price = float(detected_price)
        except:
            detected_price = 0.00

        # FINAL guaranteed product dict
        products.append({
            "id": p["id"],
            "name": p["name"],
            "barcode": p["barcode"],
            "price": detected_price   # ALWAYS exists now
        })

    return render_template(
        "sales.html",
        stores=stores,
        products=products,
        clients=clients,
        user=user
    )





# --- POS (placeholder) ---
@app.route('/pos')
@require_login
def pos():
    user = current_user()
    db = get_db()
    cursor = db.cursor(dictionary=True)

    # Pull clients
    cursor.execute("SELECT id, name FROM clients ORDER BY name ASC")
    clients = cursor.fetchall()

    # Pull products
    cursor.execute("SELECT * FROM products ORDER BY name ASC")
    products = cursor.fetchall()

    # Pull stores
    cursor.execute("SELECT * FROM stores ORDER BY name ASC")
    stores = cursor.fetchall()

    cursor.close()

    return render_template(
        'pos.html',
        clients=clients,
        products=products,
        stores=stores,
        user=user
    )


# --- Records ---
@app.route('/records')
@require_login
def records():
    user = current_user()
    q = request.args.get('q', '')
    start = request.args.get('start')
    end = request.args.get('end')

    # Base query
    sql = """
        SELECT 
            s.id,
            s.invoice_no,
            s.client_id,
            s.subtotal,
            s.vat,
            s.total,
            s.created_at,
            c.name AS client_name,
            u.username AS user_name
        FROM sales s
        LEFT JOIN clients c ON s.client_id = c.id
        LEFT JOIN users u ON s.created_by = u.id
        WHERE 1=1
    """

    params = []

    # Invoice search
    if q:
        sql += " AND s.invoice_no LIKE %s"
        params.append(f"%{q}%")

    # Date range filters
    if start:
        sql += " AND DATE(s.created_at) >= %s"
        params.append(start)
    if end:
        sql += " AND DATE(s.created_at) <= %s"
        params.append(end)

    # Order newest first
    sql += " ORDER BY s.created_at DESC"

    rows = query_all(sql, params)

    # --- Totals for finances integration ---
    totals_sql = """
        SELECT 
            COALESCE(SUM(s.subtotal), 0) AS total_subtotal,
            COALESCE(SUM(s.vat), 0) AS total_vat,
            COALESCE(SUM(s.total), 0) AS total_incl_vat
        FROM sales s
        WHERE 1=1
    """
    totals_params = []

    if start:
        totals_sql += " AND DATE(s.created_at) >= %s"
        totals_params.append(start)
    if end:
        totals_sql += " AND DATE(s.created_at) <= %s"
        totals_params.append(end)

    totals = query_one(totals_sql, totals_params)

    return render_template(
        'records.html',
        records=rows,
        totals=totals,
        user=user
    )


@app.route('/pos', methods=['GET'])
@require_login
def pos_page():
    user = current_user()
    products = query_all("""
        SELECT id, name, barcode, retail_price
        FROM products
        ORDER BY name
    """)
    stores = query_all("SELECT * FROM stores ORDER BY name")
    return render_template('pos.html', user=user, products=products, stores=stores)
from flask import Response
import csv
from io import StringIO
from datetime import datetime

# --- Unified Finances Route (View + CSV Export) ---
@app.route('/finances', methods=['GET'], endpoint='finances_page')
@require_login
def finances_page():
    user = current_user()

    # Filters
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    user_id = request.args.get('user_id', '')
    store_id = request.args.get('store_id', '')
    mode = request.args.get('mode', 'view')   # view or csv

    # Build WHERE clause for sales-based queries
    where = ["1=1"]
    params = []

    if start_date:
        where.append("DATE(s.created_at) >= %s")
        params.append(start_date)
    if end_date:
        where.append("DATE(s.created_at) <= %s")
        params.append(end_date)
    if user_id:
        where.append("s.created_by = %s")
        params.append(user_id)
    if store_id:
        where.append("s.store_id = %s")
        params.append(store_id)

    where_sql = " AND ".join(where)

    # Base query for sales records
    base_query = f"""
        SELECT 
            s.id,
            s.invoice_no,
            s.subtotal,
            s.vat,
            s.total,
            s.created_at,
            s.store_id,
            u.username AS user_name,
            st.name AS store_name
        FROM sales s
        LEFT JOIN users u ON s.created_by = u.id
        LEFT JOIN stores st ON s.store_id = st.id
        WHERE {where_sql}
        ORDER BY s.created_at DESC
    """

    # -----------------------------
    # CSV EXPORT MODE
    # -----------------------------
    if mode == "csv":
        rows = query_all(base_query, params)

        si = StringIO()
        writer = csv.writer(si)
        writer.writerow(["Invoice", "Subtotal", "VAT", "Total", "Date", "User", "Store"])

        for r in rows:
            writer.writerow([
                r['invoice_no'],
                r['subtotal'],
                r['vat'],
                r['total'],
                r['created_at'],
                r['user_name'],
                r['store_name']
            ])

        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"finances_{start_date or 'all'}_{end_date or 'all'}_{ts}.csv"

        output = si.getvalue()
        resp = Response(output, mimetype="text/csv")
        resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
        return resp

    # -----------------------------
    # NORMAL PAGE VIEW
    # -----------------------------
    records = query_all(base_query, params)

    totals = query_one(f"""
        SELECT
            COALESCE(SUM(s.subtotal), 0) AS total_subtotal,
            COALESCE(SUM(s.vat), 0) AS total_vat,
            COALESCE(SUM(s.total), 0) AS total_incl_vat
        FROM sales s
        WHERE {where_sql}
    """, params)

    per_user = query_all(f"""
        SELECT 
            u.id,
            u.username,
            COALESCE(SUM(s.total), 0) AS total_sales
        FROM sales s
        LEFT JOIN users u ON s.created_by = u.id
        WHERE {where_sql}
        GROUP BY u.id, u.username
        ORDER BY u.username
    """, params)

    per_store = query_all(f"""
        SELECT 
            st.id,
            st.name,
            COALESCE(SUM(s.total), 0) AS total_sales
        FROM sales s
        LEFT JOIN stores st ON s.store_id = st.id
        WHERE {where_sql}
        GROUP BY st.id, st.name
        ORDER BY st.name
    """, params)

    users_list = query_all("SELECT id, username FROM users ORDER BY username")
    stores_list = query_all("SELECT id, name FROM stores ORDER BY name")

    # -----------------------------
    # BALANCE STATEMENT
    # -----------------------------
    assets = query_one("""
        SELECT COALESCE(SUM(amount),0) AS total
        FROM external_entries
        WHERE entry_type='asset'
    """)['total']

    liabilities = query_one("""
        SELECT COALESCE(SUM(amount),0) AS total
        FROM external_entries
        WHERE entry_type='liability'
    """)['total']

    equity = assets - liabilities

    # -----------------------------
    # INCOME STATEMENT
    # -----------------------------
    total_sales = query_one("""
        SELECT COALESCE(SUM(total),0) AS total
        FROM sales
    """)['total']

    total_expenses = query_one("""
        SELECT COALESCE(SUM(amount),0) AS total
        FROM external_entries
        WHERE entry_type='expense'
    """)['total']

    total_stock_in = query_one("""
        SELECT COALESCE(SUM(cost),0) AS total
        FROM stock_in
    """)['total']

    net_income = total_sales - total_expenses - total_stock_in

    # -----------------------------
    # MANUAL EXTERNAL ENTRIES LIST
    # -----------------------------
    external = query_all("""
        SELECT *
        FROM external_entries
        ORDER BY entry_date DESC
    """)

    # -----------------------------
    # FINANCIAL RECORDS
    # -----------------------------
    records_financial = query_all("""
        SELECT *
        FROM records
        ORDER BY created_at DESC
    """)

    # -----------------------------
    # FINANCIAL DOCUMENTS
    # -----------------------------
    files = query_all("""
        SELECT f.*, u.username
        FROM finance_files f
        LEFT JOIN users u ON f.uploaded_by = u.id
        ORDER BY f.uploaded_at DESC
    """)

    return render_template(
        'finances.html',
        user=user,

        # Sales Records
        records=records,
        totals=totals,
        per_user=per_user,
        per_store=per_store,

        # Filters
        users_list=users_list,
        stores_list=stores_list,
        start_date=start_date,
        end_date=end_date,
        selected_user_id=user_id,
        selected_store_id=store_id,

        # Balance Statement
        assets=assets,
        liabilities=liabilities,
        equity=equity,

        # Income Statement
        total_sales=total_sales,
        total_expenses=total_expenses,
        total_stock_in=total_stock_in,
        net_income=net_income,

        # External Entries
        external=external,

        # Financial Records
        records_financial=records_financial,

        # Financial Documents
        files=files
    )






from datetime import datetime
import time
import random
from mysql.connector.errors import IntegrityError

@app.route('/pos_submit', methods=['POST'])
@require_login
def pos_submit():
    user = current_user()
    db = get_db()
    cursor = db.cursor(dictionary=True)

    store_id = request.form.get('store_id')
    client_id = request.form.get('client_id') or None

    cart_product_ids = request.form.getlist('product_id[]')
    cart_quantities = request.form.getlist('quantity[]')
    cart_prices = request.form.getlist('price[]')
    cart_totals = request.form.getlist('line_total[]')

    grand_total = float(request.form.get('grand_total') or 0)
    payment_method = request.form.get('payment_method')
    cash_received = float(request.form.get('cash_received') or 0)
    change_due = float(request.form.get('change_due') or 0)

    # 1️⃣ Calculate subtotal + VAT
    subtotal = round(grand_total / 1.15, 2)
    vat = round(grand_total - subtotal, 2)

    # 2️⃣ Generate invoice number with retry protection
    max_attempts = 5
    attempt = 0
    sale_id = None

    while attempt < max_attempts:
        try:
            invoice_no = "INV" + datetime.now().strftime("%Y%m%d%H%M%S") + str(random.randint(100, 999))

            cursor.execute("""
                INSERT INTO sales
                (invoice_no, client_id, subtotal, vat, total, created_by, store_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                invoice_no,
                client_id,
                subtotal,
                vat,
                grand_total,
                user['id'],
                store_id
            ))

            sale_id = cursor.lastrowid
            break  # success

        except IntegrityError as e:
            if "Duplicate entry" in str(e):
                attempt += 1
                time.sleep(0.1)
                continue
            else:
                raise

    if attempt == max_attempts:
        flash("System busy. Please try again.", "danger")
        cursor.close()
        return redirect(url_for('pos_page'))

    # 3️⃣ Insert sale items + stock + movements
    for product_id, qty, price, line_total in zip(cart_product_ids, cart_quantities, cart_prices, cart_totals):
        qty = int(qty)

        cursor.execute("""
            INSERT INTO sale_items
            (sale_id, product_id, quantity, unit_price, total_price)
            VALUES (%s, %s, %s, %s, %s)
        """, (sale_id, product_id, qty, price, line_total))

        cursor.execute("""
            SELECT id, quantity FROM store_stock
            WHERE product_id=%s AND store_id=%s
        """, (product_id, store_id))
        existing = cursor.fetchone()

        if existing:
            cursor.execute("""
                UPDATE store_stock
                SET quantity = quantity - %s, updated_by=%s
                WHERE id=%s
            """, (qty, user['id'], existing['id']))
        else:
            cursor.execute("""
                INSERT INTO store_stock (store_id, product_id, quantity, updated_by)
                VALUES (%s, %s, %s, %s)
            """, (store_id, product_id, -qty, user['id']))

        cursor.execute("""
            INSERT INTO movements
            (product_id, movement_type, qty, from_store, created_by, invoice_id)
            VALUES (%s, 'sale', %s, %s, %s, %s)
        """, (product_id, qty, store_id, user['id'], sale_id))

    # 4️⃣ Record payment (NEW)
    if client_id and payment_method:
        cursor.execute("""
            INSERT INTO payments (client_id, amount, payment_method, reference, created_by)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            client_id,
            cash_received or grand_total,  # handle partial or full payment
            payment_method,
            invoice_no,
            user['id']
        ))

    db.commit()
    cursor.close()

    flash("Sale completed successfully!", "success")
    return redirect(url_for('pos_page'))











from datetime import datetime
import time
import random
from mysql.connector.errors import IntegrityError

@app.route('/record_sale', methods=['POST'])
@require_login
def record_sale():
    user = current_user()

    client_id = request.form.get("client_id")
    store_id = request.form.get("store_id")

    product_ids = request.form.getlist("product_id[]")
    qtys = request.form.getlist("qty[]")
    prices = request.form.getlist("price[]")
    totals = request.form.getlist("total[]")

    subtotal = request.form.get("subtotal")
    vat = request.form.get("vat")
    total = request.form.get("total")

    # ----------------------------------------------------
    # 1️⃣ Insert sale header with retry-safe invoice number
    # ----------------------------------------------------
    max_attempts = 5
    attempt = 0

    while attempt < max_attempts:
        try:
            # Add randomness to avoid collisions
            invoice_no = "INV" + datetime.now().strftime("%Y%m%d%H%M%S") + str(random.randint(100, 999))

            sale_id = execute("""
                INSERT INTO sales (invoice_no, client_id, store_id, subtotal, vat, total, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (invoice_no, client_id, store_id, subtotal, vat, total, user["id"]))

            break  # SUCCESS → exit retry loop

        except IntegrityError as e:
            if "Duplicate entry" in str(e):
                attempt += 1
                time.sleep(0.1)  # small delay to avoid collision
                continue
            else:
                raise  # real error → rethrow

    if attempt == max_attempts:
        return jsonify(success=False, error="System busy. Please try again.")

    # ----------------------------------------------------
    # 2️⃣ Insert sale items
    # ----------------------------------------------------
    cols = query_all("SHOW COLUMNS FROM sale_items")
    colnames = [c['Field'] for c in cols]

    sale_id_col = next(c for c in colnames if "sale" in c.replace(" ", "").lower())
    product_id_col = next(c for c in colnames if "product" in c.replace(" ", "").lower())
    qty_col = next(c for c in colnames if "quantity" in c.replace(" ", "").lower())
    unit_price_col = next(c for c in colnames if "unit" in c.replace(" ", "").lower() and "price" in c.replace(" ", "").lower())
    total_price_col = next(c for c in colnames if "total" in c.replace(" ", "").lower() and "price" in c.replace(" ", "").lower())

    insert_sql = f"""
        INSERT INTO sale_items (`{sale_id_col}`, `{product_id_col}`, `{qty_col}`, `{unit_price_col}`, `{total_price_col}`)
        VALUES (%s, %s, %s, %s, %s)
    """

    for pid, qty, price, line_total in zip(product_ids, qtys, prices, totals):
        execute(insert_sql, (sale_id, pid, qty, price, line_total))

    # ----------------------------------------------------
    # 3️⃣ Insert movement logs
    # ----------------------------------------------------
    for pid, qty in zip(product_ids, qtys):
        execute("""
            INSERT INTO movements (product_id, qty, movement_type, from_store, to_store, invoice_id, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            pid,
            qty,
            "SALE",
            store_id,
            None,
            sale_id,
            user["id"]
        ))

    return jsonify(success=True)






@app.route('/check_barcode')
def check_barcode():
    code = request.args.get('code')

    # Load full product row
    product = query_one("""
        SELECT *
        FROM products
        WHERE barcode = %s
    """, (code,))

    if not product:
        return jsonify(found=False)

    # Detect the correct retail price column
    price = None
    for key in product.keys():
        cleaned = key.replace(" ", "").lower()
        if "retail" in cleaned and "price" in cleaned:
            price = product[key]
            break

    # Fallback if needed
    if price is None:
        price = product.get("price", 0)

    return jsonify(
        found=True,
        id=product['id'],
        name=product['name'],
        barcode=product['barcode'],
        price=float(price)
    )



    
    

# --- Stores ---
@app.route('/stores', methods=['GET','POST'])
@require_login
def stores():
    user = current_user()

    # Ensure admin flag exists
    # Adjust this line depending on your users table structure
    user["is_admin"] = (
        user.get("role") == "admin" or 
        user.get("is_admin") == 1 or 
        user.get("is_admin") is True
    )

    if request.method == 'POST':
        name = request.form.get('name')
        execute("INSERT INTO stores (name, created_by) VALUES (%s, %s)", (name, user['id']))
        flash('Store added', 'success')
        return redirect(url_for('stores'))

    rows = query_all("SELECT * FROM stores")
    return render_template('stores.html', stores=rows, user=user)


# --- Stock in ---
# --- Stock in ---
# --- Stock in ---
@app.route('/stock_in', methods=['GET','POST'])
@require_login
def stock_in():
    user = current_user()
    products = query_all("SELECT * FROM products")
    stores = query_all("SELECT * FROM stores")

    if request.method == 'POST':

        product_ids = request.form.getlist('product_id[]')
        quantities = request.form.getlist('quantity[]')
        store_id = request.form.get('store_id')

        is_return = request.form.get("is_return", "0")
        is_remove = request.form.get("is_remove", "0")

        if not store_id:
            flash("Please select a store", "danger")
            return redirect(url_for('stock_in'))

        # ----------------------------------------------------
        # REMOVE MODE (stock decreases)
        # ----------------------------------------------------
        if is_remove == "1":

            for pid, qty in zip(product_ids, quantities):

                qty = int(qty)

                existing = query_one("""
                    SELECT id, quantity FROM store_stock
                    WHERE product_id=%s AND store_id=%s
                """, (pid, store_id))

                if existing:
                    new_qty = max(existing['quantity'] - qty, 0)

                    execute("""
                        UPDATE store_stock
                        SET quantity=%s, updated_by=%s
                        WHERE id=%s
                    """, (new_qty, user['id'], existing['id']))

                # SAVE AS 'adjustment' (displayed as Removed)
                execute("""
                    INSERT INTO movements (product_id, movement_type, qty, from_store, created_by)
                    VALUES (%s, 'adjustment', %s, %s, %s)
                """, (pid, qty, store_id, user['id']))

                log_action(
                    user['id'],
                    'adjustment',
                    f'Removed product {pid} qty {qty} from store {store_id}'
                )

            flash("Product removed successfully", "success")
            return redirect(url_for('stock_in'))

        # ----------------------------------------------------
        # RETURN MODE (stock increases)
        # ----------------------------------------------------
        if is_return == "1":

            for pid, qty in zip(product_ids, quantities):

                qty = int(qty)

                existing = query_one("""
                    SELECT id, quantity FROM store_stock
                    WHERE product_id=%s AND store_id=%s
                """, (pid, store_id))

                if existing:
                    new_qty = existing['quantity'] + qty
                    execute("""
                        UPDATE store_stock
                        SET quantity=%s, updated_by=%s
                        WHERE id=%s
                    """, (new_qty, user['id'], existing['id']))
                else:
                    execute("""
                        INSERT INTO store_stock (store_id, product_id, quantity, updated_by)
                        VALUES (%s, %s, %s, %s)
                    """, (store_id, pid, qty, user['id']))

                execute("""
                    INSERT INTO movements (product_id, movement_type, qty, to_store, created_by)
                    VALUES (%s, 'return', %s, %s, %s)
                """, (pid, qty, store_id, user['id']))

                log_action(
                    user['id'],
                    'return',
                    f'Returned product {pid} qty {qty} to store {store_id}'
                )

            flash("Return processed successfully", "success")
            return redirect(url_for('stock_in'))

        # ----------------------------------------------------
        # NORMAL STOCK-IN MODE
        # ----------------------------------------------------
        for pid, qty in zip(product_ids, quantities):

            qty = int(qty)

            product = query_one(
                "SELECT wholesale_price FROM products WHERE id=%s",
                (pid,)
            )

            if not product:
                continue

            wholesale = product['wholesale_price']
            cost = qty * wholesale

            # ⭐ FIX: remove business_id (your DB does not have it)
            execute("""
                INSERT INTO stock_in (product_id, store_id, quantity, cost)
                VALUES (%s, %s, %s, %s)
            """, (pid, store_id, qty, cost))

            existing = query_one("""
                SELECT id FROM store_stock
                WHERE product_id=%s AND store_id=%s
            """, (pid, store_id))

            if existing:
                execute("""
                    UPDATE store_stock
                    SET quantity = quantity + %s, updated_by=%s
                    WHERE id=%s
                """, (qty, user['id'], existing['id']))
            else:
                execute("""
                    INSERT INTO store_stock (store_id, product_id, quantity, updated_by)
                    VALUES (%s, %s, %s, %s)
                """, (store_id, pid, qty, user['id']))

            execute("""
                INSERT INTO movements (product_id, movement_type, qty, to_store, created_by)
                VALUES (%s, 'stock_in', %s, %s, %s)
            """, (pid, qty, store_id, user['id']))

            log_action(
                user['id'],
                'stock_in',
                f'Stock in product {pid} qty {qty} to store {store_id}'
            )

        flash('Stock received successfully', 'success')
        return redirect(url_for('stock_in'))

    return render_template('stock_in.html', products=products, stores=stores, user=user)





@app.route('/remove_stock', methods=['POST'])
@require_login
def remove_stock():
    user = current_user()

    product_ids = request.form.getlist('product_id[]')
    quantities = request.form.getlist('quantity[]')
    store_id = request.form.get('store_id')

    for pid, qty in zip(product_ids, quantities):

        qty = int(qty)

        # 1️⃣ FETCH EXISTING STOCK
        existing = query_one("""
            SELECT id, quantity FROM store_stock
            WHERE product_id=%s AND store_id=%s
        """, (pid, store_id))

        if existing:
            new_qty = max(existing['quantity'] - qty, 0)

            execute("""
                UPDATE store_stock
                SET quantity=%s, updated_by=%s
                WHERE id=%s
            """, (new_qty, user['id'], existing['id']))

        # 2️⃣ MOVEMENT LOG
        execute("""
            INSERT INTO movements (product_id, movement_type, qty, from_store, created_by)
            VALUES (%s, 'removed', %s, %s, %s)
        """, (pid, qty, store_id, user['id']))

        # 3️⃣ AUDIT LOG
        log_action(
            user['id'],
            'removed',
            f'Removed product {pid} qty {qty} from store {store_id}'
        )

    flash("Product removed successfully", "success")
    return redirect(url_for('stock_in'))





# --- Store Details ---
@app.route('/store/<int:store_id>', methods=['GET'])
@require_login
def store_details(store_id):
    user = current_user()

    # Store info
    store = query_one("SELECT * FROM stores WHERE id=%s", (store_id,))
    if not store:
        flash("Store not found", "error")
        return redirect(url_for('stores'))

    # Search inside store
    q = request.args.get("q", "")

    if q:
        products = query_all("""
            SELECT 
                p.id,
                p.name,
                p.barcode,
                p.retail_price,
                COALESCE(ss.quantity, 0) AS qty
            FROM products p
            LEFT JOIN store_stock ss 
                ON ss.product_id = p.id AND ss.store_id = %s
            WHERE p.name LIKE %s OR p.barcode LIKE %s
            ORDER BY p.name ASC
        """, (store_id, f"%{q}%", f"%{q}%"))
    else:
        products = query_all("""
            SELECT 
                p.id,
                p.name,
                p.barcode,
                p.retail_price,
                COALESCE(ss.quantity, 0) AS qty
            FROM products p
            LEFT JOIN store_stock ss 
                ON ss.product_id = p.id AND ss.store_id = %s
            ORDER BY p.name ASC
        """, (store_id,))

    return render_template(
        "store_details.html",
        store=store,
        products=products,
        user=user
    )



@app.route('/stock_in', methods=['GET','POST'])
@require_login
def stock_in_page():
    user = current_user()
    products = query_all("SELECT * FROM products")
    stores = query_all("SELECT * FROM stores")

    if request.method == 'POST':

        store_id = request.form.get('store_id')
        is_return = request.form.get('is_return', '0')  # NEW

        product_ids = request.form.getlist('product_id[]')
        quantities = request.form.getlist('quantity[]')

        for product_id, qty in zip(product_ids, quantities):

            qty = int(qty)

            # ----------------------------------------------------
            # RETURN MODE (FIXED: stock must INCREASE)
            # ----------------------------------------------------
            if is_return == "1":

                # 1️⃣ INCREASE STOCK (product is coming back)
                existing = query_one("""
                    SELECT id, quantity FROM store_stock 
                    WHERE product_id=%s AND store_id=%s
                """, (product_id, store_id))

                if existing:
                    new_qty = existing['quantity'] + qty
                    execute("""
                        UPDATE store_stock 
                        SET quantity = %s, updated_by=%s 
                        WHERE id=%s
                    """, (new_qty, user['id'], existing['id']))
                else:
                    # If no record exists, create it with the returned qty
                    execute("""
                        INSERT INTO store_stock (store_id, product_id, quantity, updated_by)
                        VALUES (%s, %s, %s, %s)
                    """, (store_id, product_id, qty, user['id']))

                # 2️⃣ MOVEMENT LOG
                execute("""
                    INSERT INTO movements 
                    (product_id, movement_type, qty, to_store, created_by)
                    VALUES (%s, 'return', %s, %s, %s)
                """, (product_id, qty, store_id, user['id']))

                # 3️⃣ RETURNS TABLE
                execute("""
                    INSERT INTO returns (product_id, store_id, qty, returned_by)
                    VALUES (%s, %s, %s, %s)
                """, (product_id, store_id, qty, user['id']))

                continue  # Skip normal stock-in logic

            # ----------------------------------------------------
            # NORMAL STOCK-IN MODE
            # ----------------------------------------------------
            existing = query_one("""
                SELECT id FROM store_stock 
                WHERE product_id=%s AND store_id=%s
            """, (product_id, store_id))

            if existing:
                execute("""
                    UPDATE store_stock 
                    SET quantity = quantity + %s, updated_by=%s 
                    WHERE id=%s
                """, (qty, user['id'], existing['id']))
            else:
                execute("""
                    INSERT INTO store_stock (store_id, product_id, quantity, updated_by)
                    VALUES (%s, %s, %s, %s)
                """, (store_id, product_id, qty, user['id']))

            # MOVEMENT LOG
            execute("""
                INSERT INTO movements 
                (product_id, movement_type, qty, to_store, created_by)
                VALUES (%s, 'stock_in', %s, %s, %s)
            """, (product_id, qty, store_id, user['id']))

        # SUCCESS MESSAGE
        if is_return == "1":
            flash("Return processed successfully", "success")
        else:
            flash("Stock-in completed", "success")

        return redirect(url_for('stock_in_page'))

    return render_template('stock_in.html', products=products, stores=stores, user=user)





# --- Transfer ---
@app.route('/transfer', methods=['GET', 'POST'])
@require_login
def transfer():
    user = current_user()
    products = query_all("SELECT * FROM products")
    stores = query_all("SELECT * FROM stores")

    if request.method == 'POST':
        from_store = request.form.get('from_store')
        to_store = request.form.get('to_store')

        product_ids = request.form.getlist('product_id[]')
        quantities = request.form.getlist('quantity[]')

        # Validation
        if from_store == to_store:
            flash("Source and destination store cannot be the same", "danger")
            return redirect(url_for('transfer'))

        # Loop through all scanned products
        for product_id, qty in zip(product_ids, quantities):
            qty = int(qty)

            # Decrement from source store
            execute("""
                UPDATE store_stock
                SET quantity = quantity - %s, updated_by=%s
                WHERE product_id=%s AND store_id=%s
            """, (qty, user['id'], product_id, from_store))

            # Increment destination store
            existing = query_one("""
                SELECT id FROM store_stock
                WHERE product_id=%s AND store_id=%s
            """, (product_id, to_store))

            if existing:
                execute("""
                    UPDATE store_stock
                    SET quantity = quantity + %s, updated_by=%s
                    WHERE id=%s
                """, (qty, user['id'], existing['id']))
            else:
                execute("""
                    INSERT INTO store_stock (store_id, product_id, quantity, updated_by)
                    VALUES (%s, %s, %s, %s)
                """, (to_store, product_id, qty, user['id']))

            # Accurate movement logging (one per product)
            execute("""
                INSERT INTO movements
                (product_id, movement_type, qty, from_store, to_store, created_by)
                VALUES (%s, 'transfer', %s, %s, %s, %s)
            """, (product_id, qty, from_store, to_store, user['id']))

            # Log action
            log_action(
                user['id'],
                'transfer',
                f'Transferred product {product_id} qty {qty} from store {from_store} to {to_store}'
            )

        flash('Transfer completed successfully.', 'success')
        return redirect(url_for('transfer'))

    return render_template('transfer.html', products=products, stores=stores, user=user)

@app.route('/returns/process', methods=['POST'])
@require_login
def process_return():
    user = current_user()

    store_id = request.form.get("store_id")
    product_ids = request.form.getlist("product_id[]")
    quantities = request.form.getlist("quantity[]")

    for pid, qty in zip(product_ids, quantities):
        qty = int(qty)

        # 1. Increase stock back (return)
        execute("""
            UPDATE stock 
            SET quantity = quantity + %s 
            WHERE product_id=%s AND store_id=%s
        """, (qty, pid, store_id))

        # 2. Log movement
        execute("""
            INSERT INTO stock_movement (product_id, store_id, quantity, movement_type, user_id)
            VALUES (%s, %s, %s, 'RETURN', %s)
        """, (pid, store_id, qty, user['id']))

        # 3. Insert into returns table
        execute("""
            INSERT INTO returns (product_id, store_id, quantity, returned_by)
            VALUES (%s, %s, %s, %s)
        """, (pid, store_id, qty, user['id']))

    flash("Return processed successfully", "success")
    return redirect(url_for('stock_in'))




# --- Movements ---
@app.route('/movements')
@require_login
def movements():
    user = current_user()
    q = request.args.get('q','')
    start = request.args.get('start')
    end = request.args.get('end')

    sql = """
        SELECT 
            m.*,
            p.name AS product_name,
            u.username AS user_name,
            s.id AS invoice_id,
            s.invoice_no,

            -- Store names (corrected column names)
            fs.name AS from_store,
            ts.name AS to_store

        FROM movements m
        LEFT JOIN products p ON m.product_id = p.id
        LEFT JOIN users u ON m.created_by = u.id
        LEFT JOIN sales s ON m.invoice_id = s.id

        -- FIX: use your real column names
        LEFT JOIN stores fs ON m.from_store = fs.id
        LEFT JOIN stores ts ON m.to_store = ts.id

        WHERE 1=1
    """

    params = []

    if q:
        sql += " AND (s.invoice_no LIKE %s OR p.name LIKE %s)"
        params.extend((f'%{q}%', f'%{q}%'))

    if start:
        sql += " AND m.created_at >= %s"
        params.append(start)

    if end:
        sql += " AND m.created_at <= %s"
        params.append(end)

    sql += " ORDER BY m.id DESC"

    rows = query_all(sql, params)

    return render_template('movements.html', movements=rows, user=user)


@app.post("/hr/overtime/create")
@login_required
def staff_overtime_create():
    db = get_db()
    cursor = db.cursor()

    user_id = session["user_id"]
    hours = request.form["hours"]
    date = request.form["date"]          # <-- user-selected date
    comment = request.form.get("comment")

    cursor.execute("""
        INSERT INTO overtime_requests (user_id, hours, comment, date, status)
        VALUES (%s, %s, %s, %s, 'pending')
    """, (user_id, hours, comment, date))

    db.commit()
    return redirect(url_for("human"))

@app.route("/hr/history/leave")
@login_required
def hr_history_leave():
    user_id = session["user_id"]

    db = get_db()
    cursor = db.cursor(dictionary=True)

    start = request.args.get("start")
    end = request.args.get("end")
    staff_id = request.args.get("staff_id")

    sql = """
        SELECT 
            l.id,
            u.username AS staff_name,
            c.name AS leave_type_name,
            l.start_date,
            l.end_date,
            l.status
        FROM leave_requests l
        JOIN users u ON u.id = l.user_id
        LEFT JOIN leave_categories c ON c.id = l.category_id
        WHERE 1=1
    """
    params = []

    # Only apply staff filter if provided
    if staff_id and staff_id.strip() != "":
        sql += " AND l.user_id = %s"
        params.append(staff_id)

    # Only apply date filters if valid
    if start and start.strip() != "":
        sql += " AND l.start_date >= %s"
        params.append(start)

    if end and end.strip() != "":
        sql += " AND l.end_date <= %s"
        params.append(end)

    sql += " ORDER BY l.start_date DESC"

    cursor.execute(sql, params)
    rows = cursor.fetchall()

    print("LEAVE DEBUG:", rows)
    return jsonify({"rows": rows})











@app.route("/hr/history/overtime")
@login_required
def hr_history_overtime():
    user_id = session["user_id"]

    db = get_db()
    cursor = db.cursor(dictionary=True)

    start = request.args.get("start")
    end = request.args.get("end")
    staff_id = request.args.get("staff_id")

    sql = """
        SELECT 
            o.id,
            u.username AS staff_name,
            o.date,
            o.hours,
            o.status
        FROM overtime_requests o
        JOIN users u ON u.id = o.user_id
        WHERE 1=1
    """
    params = []

    if staff_id and staff_id.strip() != "":
        sql += " AND o.user_id = %s"
        params.append(staff_id)

    if start and start.strip() != "":
        sql += " AND o.date >= %s"
        params.append(start)

    if end and end.strip() != "":
        sql += " AND o.date <= %s"
        params.append(end)

    sql += " ORDER BY o.date DESC"

    cursor.execute(sql, params)
    rows = cursor.fetchall()

    print("OVERTIME DEBUG:", rows)
    return jsonify({"rows": rows})











@app.route("/hr/vacancy/admin/<int:vacancy_id>/edit", methods=["GET", "POST"])
@login_required
def admin_vacancy_edit(vacancy_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    if request.method == "POST":
        title = request.form["title"]
        department = request.form["department"]
        closing_date = request.form["closing_date"]
        status = request.form["status"]
        description = request.form["description"]

        cursor.execute("""
            UPDATE job_vacancies
            SET title=%s, department=%s, closing_date=%s, status=%s, description=%s
            WHERE id=%s
        """, (title, department, closing_date, status, description, vacancy_id))

        db.commit()
        return redirect(url_for("human", tab="vacancies"))

    # GET request → load vacancy
    cursor.execute("SELECT * FROM job_vacancies WHERE id=%s", (vacancy_id,))
    vacancy = cursor.fetchone()

    return render_template("admin_vacancy_edit.html", vacancy=vacancy)





@app.route("/hr/vacancy/admin/<int:vacancy_id>/delete", methods=["POST"])
@login_required
def admin_vacancy_delete(vacancy_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    # Delete linked applications first
    cursor.execute("DELETE FROM vacancy_applications WHERE vacancy_id=%s", (vacancy_id,))
    cursor.execute("DELETE FROM job_vacancies WHERE id=%s", (vacancy_id,))
    db.commit()

    flash("Vacancy and all related applications deleted successfully.", "success")
    return redirect(url_for("human", tab="vacancies"))









@app.post("/hr/overtime/<int:id>/approve")
@login_required
def admin_overtime_approve(id):
    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("UPDATE overtime_requests SET status='approved' WHERE id=%s", (id,))
        db.commit()
    except Exception as e:
        db.rollback()
        print("ERROR:", e)

    return redirect(url_for("human"))





@app.post("/hr/overtime/admin/create")
@login_required
def admin_overtime_create():
    user_id = request.form["user_id"]
    date = request.form["date"]
    hours = request.form["hours"]
    comment = request.form.get("comment")

    cursor = get_db().cursor()
    cursor.execute("""
        INSERT INTO overtime_requests (user_id, date, hours, comment, status)
        VALUES (%s, %s, %s, %s, 'pending')
    """, (user_id, date, hours, comment))
    get_db().commit()

    return redirect(url_for("human"))

#-----------------HRENGINE
@app.post("/hr/leave/balance/update")
@login_required
def admin_leave_balance_update():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    try:
        user_id = request.form["user_id"]

        cursor.execute("SELECT id FROM leave_categories")
        categories = cursor.fetchall()

        for cat in categories:
            cat_id = cat["id"]
            field = f"leave_{cat_id}"
            days = request.form.get(field)

            if not days:
                continue

            days = float(days)

            cursor.execute("""
                SELECT id FROM leave_balances
                WHERE user_id=%s AND category_id=%s
            """, (user_id, cat_id))
            exists = cursor.fetchone()

            if exists:
                cursor.execute("""
                    UPDATE leave_balances
                    SET days_available=%s
                    WHERE user_id=%s AND category_id=%s
                """, (days, user_id, cat_id))
            else:
                cursor.execute("""
                    INSERT INTO leave_balances (user_id, category_id, days_available)
                    VALUES (%s, %s, %s)
                """, (user_id, cat_id, days))

        db.commit()

    except Exception as e:
        db.rollback()
        print("ERROR:", e)

    return redirect(url_for("human"))



@app.route('/hr/leave/admin/create', methods=['POST'])
@require_login
def admin_leave_create():
    user = current_user()

    user_id = request.form["user_id"]          # ✔ matches <select name="user_id">
    leave_type = request.form["leave_type"]    # ✔ matches <select name="leave_type">
    start_date = request.form["start_date"]    # ✔ matches <input name="start_date">
    end_date = request.form["end_date"]        # ✔ matches <input name="end_date">
    comment = request.form.get("comment")      # ✔ matches <textarea name="comment">

    execute("""
        INSERT INTO leave_requests (user_id, category_id, start_date, end_date, comment, status)
        VALUES (%s, %s, %s, %s, %s, 'pending')
    """, (user_id, leave_type, start_date, end_date, comment))

    log_action(user['id'], 'admin_leave_create', f'Leave request created for user {user_id}')
    flash('Leave request captured', 'success')
    return redirect(url_for('human'))

@app.route('/hr/leave/balance/view')
@require_login
def admin_leave_balance_view():
    user_id = request.args.get('user_id')

    if not user_id:
        flash('Please select a user first.', 'warning')
        return redirect(url_for('human'))

    selected_user = query_one("SELECT id, username FROM users WHERE id=%s", (user_id,))

    balances = query_all("""
        SELECT lc.name AS category_name, lb.days_available
        FROM leave_balances lb
        LEFT JOIN leave_categories lc ON lb.category_id = lc.id
        WHERE lb.user_id=%s
    """, (user_id,))

    return render_template('leave_balance_view.html', selected_user=selected_user, balances=balances)






@app.route('/hr/leave/balance/view')
@require_login
def admin_view_leave_balance():
    user_id = request.args.get('user_id')

    if not user_id:
        flash('Please select a user first.', 'warning')
        return redirect(url_for('human'))

    # FIXED: no more full_name
    user = query_one("SELECT id, username, name FROM users WHERE id=%s", (user_id,))

    balances = query_all("""
        SELECT lc.name AS category_name, lb.days_available
        FROM leave_balances lb
        LEFT JOIN leave_categories lc ON lb.category_id = lc.id
        WHERE lb.user_id=%s
    """, (user_id,))

    return render_template('leave_balance_view.html', user=user, balances=balances)









@app.post("/hr/leave/create")
@login_required
def staff_leave_create():
    db = get_db()
    cursor = db.cursor()

    user_id = session["user_id"]
    category_id = request.form["leave_type"]
    start_date = request.form["start_date"]
    end_date = request.form["end_date"]
    comment = request.form.get("comment")
    file = request.files.get("attachment")

    file_path = None
    if file and file.filename:
        filename = secure_filename(file.filename)
        os.makedirs("uploads/hr", exist_ok=True)
        file_path = os.path.join("uploads/hr", filename)
        file.save(file_path)

    cursor.execute("""
        INSERT INTO leave_requests (user_id, category_id, start_date, end_date, comment, attachment, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'pending')
    """, (user_id, category_id, start_date, end_date, comment, file_path))

    db.commit()
    return redirect(url_for("human"))






@app.route("/admin/leave/approve/<int:leave_id>", methods=["POST"])
@login_required
def admin_leave_approve(leave_id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        UPDATE leave_requests
        SET status='approved'
        WHERE id=%s
    """, (leave_id,))
    db.commit()

    flash("Leave request approved successfully.", "success")
    return redirect(url_for("human", tab="leave"))



@app.route("/admin/leave/decline/<int:leave_id>", methods=["POST"])
@login_required
def admin_leave_decline(leave_id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        UPDATE leave_requests
        SET status='declined'
        WHERE id=%s
    """, (leave_id,))
    db.commit()

    flash("Leave request declined successfully.", "success")
    return redirect(url_for("human", tab="leave"))



#create vacancy
def safe_date(value):
    return value if value and value.strip() else None


def safe_date(value):
    return value if value and value.strip() else None


@app.route("/hr/vacancy/create", methods=["GET", "POST"])
@login_required
def admin_vacancy_create():
    if request.method == "POST":
        try:
            title = request.form.get("title")
            dept = request.form.get("department")
            desc = request.form.get("description")
            closing = safe_date(request.form.get("closing_date"))

            # Basic validation
            if not title or not dept or not desc:
                flash("Please fill in all required fields.", "error")
                return redirect(url_for("admin_vacancy_create"))

            db = get_db()
            cursor = db.cursor()

            cursor.execute("""
                INSERT INTO job_vacancies (title, department, description, closing_date)
                VALUES (%s, %s, %s, %s)
            """, (title, dept, desc, closing))

            db.commit()
            flash("Vacancy created successfully.", "success")
            return redirect(url_for("human"))

        except mysql.connector.DataError as e:
            if e.errno == 1292:
                flash("Invalid or missing closing date. Please enter a valid date.", "error")
            else:
                flash("Invalid data submitted. Please check all fields.", "error")
            return redirect(url_for("admin_vacancy_create"))

        except mysql.connector.DatabaseError as e:
            if e.errno == 1205:
                flash("System busy. Please try again in a moment.", "error")
            else:
                flash("Database error occurred. Please try again.", "error")
            return redirect(url_for("admin_vacancy_create"))

        except Exception:
            flash("Unexpected error. Please check your inputs.", "error")
            return redirect(url_for("admin_vacancy_create"))

        finally:
            try:
                cursor.close()
            except:
                pass

    # GET request — show the vacancy creation form
    return render_template("hr_vacancy_create.html")



    

@app.route('/admin/salary/inline')
def admin_salary_inline():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    # ✅ Fetch salary statements joined with username from users table
    cursor.execute("""
        SELECT s.*, u.username AS user_name
        FROM salary_statements s
        JOIN users u ON s.user_id = u.id
        ORDER BY s.id DESC
    """)
    salary_statements = cursor.fetchall()

    return render_template("admin_salary_inline.html", salary_statements=salary_statements)




###############




@app.route('/admin/salary/<int:statement_id>/generate-pdf')
def salary_generate_pdf(statement_id):
    # Create a fresh MySQL connection JUST for this request
    db = mysql.connector.connect(**DB_CONFIG)
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT s.*, u.username, u.email
        FROM salary_statements s
        JOIN users u ON s.user_id = u.id
        WHERE s.id=%s
    """, (statement_id,))
    statement = cursor.fetchone()

    if not statement:
        cursor.close()
        db.close()
        flash("Salary statement not found.", "error")
        return redirect(url_for('admin_salary_inline'))

    # Render HTML template for PDF
    rendered = render_template("salary_pdf_template.html", statement=statement)

    # PDF CONFIG
    import pdfkit
    WKHTML_PATH = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe"
    config = pdfkit.configuration(wkhtmltopdf=WKHTML_PATH)

    # Output path
    filename = f"salary_{statement_id}_{statement['username']}.pdf"
    output_path = os.path.join(app.root_path, "finance_docs", filename)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Generate PDF
    pdfkit.from_string(rendered, output_path, configuration=config)

    # Save filename in DB
    cursor.execute("""
        UPDATE salary_statements
        SET document_path=%s
        WHERE id=%s
    """, (filename, statement_id))
    db.commit()

    cursor.close()
    db.close()

    flash("Salary PDF generated successfully.", "success")
    return redirect(url_for('admin_salary_inline'))









@app.route('/admin/salary/<int:statement_id>/inline-update', methods=['POST'])
def admin_salary_inline_update(statement_id):
    db = get_db()
    cursor = db.cursor()

    basic_salary = request.form.get('basic_salary')
    overtime_pay = request.form.get('overtime_pay')
    allowances = request.form.get('allowances')
    deductions = request.form.get('deductions')
    net_pay = request.form.get('net_pay')

    cursor.execute("""
        UPDATE salary_statements
        SET basic_salary=%s,
            overtime_pay=%s,
            allowances=%s,
            deductions=%s,
            net_pay=%s
        WHERE id=%s
    """, (basic_salary, overtime_pay, allowances, deductions, net_pay, statement_id))

    db.commit()
    return redirect(url_for('human'))


#create salary
# Safe float converter to avoid ValueError
def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


@app.route('/admin/salary/create', methods=['POST'])
def admin_salary_create():
    try:
        db = mysql.connector.connect(**DB_CONFIG)
        cursor = db.cursor()

        user_id = request.form['user_id']
        period_label = request.form['period_label']
        statement_date = request.form['statement_date']

        # SAFE conversion (no more ValueError)
        basic_salary = to_float(request.form.get('basic_salary'))
        overtime_pay = to_float(request.form.get('overtime_pay'))
        allowances = to_float(request.form.get('allowances'))
        deductions = to_float(request.form.get('deductions'))

        # Auto-calc net pay
        net_pay = basic_salary + overtime_pay + allowances - deductions

        notes = request.form.get('notes', '')

        cursor.execute("""
            INSERT INTO salary_statements 
            (user_id, period_label, statement_date, basic_salary, overtime_pay, allowances, deductions, net_pay, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            user_id, period_label, statement_date,
            basic_salary, overtime_pay, allowances, deductions,
            net_pay, notes
        ))

        db.commit()
        flash("Salary statement created successfully.", "success")
        return redirect(url_for('admin_salary_inline'))

    # Duplicate entry, constraint errors, etc.
    except mysql.connector.IntegrityError as e:
        flash("A salary record for this period already exists.", "error")
        return redirect(url_for('admin_salary_inline'))

    # Lock wait timeout or other DB errors
    except mysql.connector.DatabaseError as e:
        if e.errno == 1205:
            flash("System busy. Please try again in a moment.", "error")
        else:
            flash("Database error occurred. Please try again.", "error")
        return redirect(url_for('admin_salary_inline'))

    # Any other unexpected error
    except Exception as e:
        flash("Invalid input. Please check all fields.", "error")
        return redirect(url_for('admin_salary_inline'))

    finally:
        try:
            cursor.close()
            db.close()
        except:
            pass

    # ⭐ REQUIRED





@app.route("/admin/salary/<int:statement_id>/edit", methods=["GET", "POST"])
@login_required
def admin_salary_edit(statement_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    if request.method == "POST":
        amount = request.form["amount"]
        comment = request.form["comment"]

        cursor.execute("""
            UPDATE salary_statements
            SET amount=%s, comment=%s
            WHERE id=%s
        """, (amount, comment, statement_id))
        db.commit()

        flash("Salary statement updated successfully.", "success")
        return redirect(url_for("human", tab="salaries"))

    # GET: load existing data
    cursor.execute("SELECT * FROM salary_statements WHERE id=%s", (statement_id,))
    statement = cursor.fetchone()
    return render_template("admin_salary_edit.html", statement=statement)


@app.route("/admin/salary/<int:statement_id>/download")
@login_required
def salary_download(statement_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("SELECT document_path FROM salary_statements WHERE id=%s", (statement_id,))
    row = cursor.fetchone()

    if not row or not row["document_path"]:
        flash("File not found.", "error")
        return redirect(url_for("human", tab="salaries"))

    directory = os.path.join(app.root_path, "finance_docs")
    filename = row["document_path"]

    return send_from_directory(directory, filename, as_attachment=True)

@app.route("/admin/salary/<int:statement_id>/upload", methods=["POST"])
@login_required
def salary_upload(statement_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    # Check if a file was uploaded
    if "file" not in request.files:
        flash("No file part in the request.", "error")
        return redirect(url_for("human", tab="salaries"))

    file = request.files["file"]

    if file.filename == "":
        flash("No file selected.", "error")
        return redirect(url_for("human", tab="salaries"))

    # Save file securely
    filename = secure_filename(file.filename)
    upload_dir = os.path.join(app.root_path, "finance_docs")
    os.makedirs(upload_dir, exist_ok=True)

    file.save(os.path.join(upload_dir, filename))

    # Update database record
    cursor.execute("""
        UPDATE salary_statements
        SET document_path=%s
        WHERE id=%s
    """, (filename, statement_id))
    db.commit()

    flash("Salary document uploaded successfully.", "success")
    return redirect(url_for("human", tab="salaries"))




@app.post("/hr/payroll/update")
@login_required
def admin_payroll_update():
    rate = request.form["rate_per_hour"]
    overtime = request.form["overtime_rate_per_hour"]

    cursor = get_db().cursor()
    cursor.execute("DELETE FROM payroll_settings")
    cursor.execute("""
        INSERT INTO payroll_settings (rate_per_hour, overtime_rate_per_hour)
        VALUES (%s, %s)
    """, (rate, overtime))
    get_db().commit()

    return redirect(url_for("human"))

@app.post("/hr/leave/category/create")
@login_required
def admin_leave_category_create():
    name = request.form["name"]
    cursor = get_db().cursor()
    cursor.execute("INSERT INTO leave_categories (name) VALUES (%s)", (name,))
    get_db().commit()
    return redirect(url_for("human"))


from mysql.connector.errors import IntegrityError

@app.route("/admin/leave/category/delete/<int:category_id>", methods=["POST"])
@login_required
def admin_leave_category_delete(category_id):
    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("DELETE FROM leave_categories WHERE id=%s", (category_id,))
        db.commit()
        flash("Leave category deleted successfully.", "success")

    except IntegrityError:
        # Category is still referenced in leave_balances
        flash("Cannot delete this leave category because it is still in use.", "error")

    return redirect(url_for("human", tab="leave_categories"))




@app.post("/hr/profile/update")
@login_required
def profile_update():
    user_id = session["user_id"]
    data = request.form

    cursor = get_db().cursor()
    cursor.execute("""
        UPDATE users SET full_name=%s, email=%s, contact=%s, address=%s, qualifications=%s
        WHERE id=%s
    """, (
        data["full_name"], data["email"], data["contact"],
        data["address"], data["qualifications"], user_id
    ))

    # documents
    files = request.files.getlist("documents")
    for f in files:
        if f.filename:
            filename = secure_filename(f.filename)
            f.save(os.path.join("uploads/profile_docs", filename))
            cursor.execute("""
                INSERT INTO user_documents (user_id, filename, filepath)
                VALUES (%s, %s, %s)
            """, (user_id, filename, filename))

    get_db().commit()
    return redirect(url_for("human"))




@app.route("/vacancy/apply/<int:vacancy_id>", methods=["GET", "POST"])
@login_required
def vacancy_apply(vacancy_id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("""
        INSERT INTO vacancy_applications (user_id, vacancy_id)
        VALUES (%s, %s)
    """, (session["user_id"], vacancy_id))

    db.commit()
    return redirect(url_for("human"))
@app.get("/admin/vacancies")
@login_required
def admin_vacancies():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            j.id,
            j.title,
            j.department,
            j.closing_date,
            j.status,
            COUNT(va.id) AS applications_count
        FROM job_vacancies j
        LEFT JOIN vacancy_applications va ON va.vacancy_id = j.id
        GROUP BY j.id, j.title, j.department, j.closing_date, j.status
        ORDER BY j.id DESC
    """)
    vacancies = cursor.fetchall()

    return render_template("admin_vacancies.html", vacancies=vacancies)


@app.get("/admin/vacancy/<int:vacancy_id>/applications")
@login_required
def admin_view_applications(vacancy_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            va.id AS application_id,
            u.username AS applicant_name,
            u.email AS applicant_email,
            va.applied_at,
            va.status,
            va.comment
        FROM vacancy_applications va
        JOIN users u ON va.user_id = u.id
        WHERE va.vacancy_id = %s
        ORDER BY va.applied_at DESC
    """, (vacancy_id,))
    applications = cursor.fetchall()

    cursor.execute("SELECT title FROM job_vacancies WHERE id = %s", (vacancy_id,))
    vacancy = cursor.fetchone()

    return render_template("admin_vacancy_applications.html",
                           applications=applications,
                           vacancy=vacancy)


@app.route("/admin/application/<int:application_id>/update", methods=["POST"])
@login_required
def admin_update_application(application_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    # Match ENUM values from your DB
    valid_statuses = ["pending", "reviewed", "shortlisted", "declined"]

    # Normalize and validate
    status = request.form["status"].strip().lower()

    # Map alternate labels if needed
    if status == "approved":
        status = "reviewed"
    elif status == "rejected":
        status = "declined"

    if status not in valid_statuses:
        flash("Invalid application status.", "error")
        return redirect(url_for("human", tab="applications"))

    # Update safely
    cursor.execute("""
        UPDATE vacancy_applications
        SET status=%s
        WHERE id=%s
    """, (status, application_id))

    db.commit()
    flash(f"Application {status.capitalize()} successfully.", "success")
    return redirect(url_for("human", tab="applications"))







@app.get("/admin/vacancy/applications")
@login_required
def admin_vacancy_applications():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            va.id AS application_id,
            va.applied_at,
            va.status,
            c.fullname AS applicant_name,
            j.title AS vacancy_title
        FROM vacancy_applications va
        JOIN clients c ON va.user_id = c.id
        JOIN job_vacancies j ON va.vacancy_id = j.id
        ORDER BY va.id DESC
    """)
    
    applications = cursor.fetchall()

    return render_template("admin_vacancy_applications.html", applications=applications)






# --- Tasks ---
from datetime import datetime
import time
import random
from mysql.connector.errors import IntegrityError

@app.route('/tasks', methods=['GET','POST'])
@require_login
def tasks():
    user = current_user()

    # Load all users for assignment dropdown
    users = query_all("SELECT id, username FROM users WHERE is_active=1 AND is_approved=1")

    if request.method == 'POST':
        title = request.form.get('title')
        desc = request.form.get('description')
        assigned_to = request.form.get('assigned_to')
        priority = request.form.get('priority', 'medium')
        status = 'open'

        # ----------------------------------------------------
        # SAFE TASK NUMBER GENERATION (NO DUPLICATES)
        # ----------------------------------------------------
        max_attempts = 5
        attempt = 0

        while attempt < max_attempts:
            try:
                # Timestamp + randomness to avoid collisions
                task_no = datetime.now().strftime("%Y%m%d%H%M%S") + str(random.randint(100, 999))

                execute("""
                    INSERT INTO tasks (task_no, title, description, assigned_to, priority, status)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (task_no, title, desc, assigned_to, priority, status))

                log_action(user['id'], 'create_task', f'Created task {task_no}')
                flash('Task created', 'success')
                return redirect(url_for('tasks'))

            except IntegrityError as e:
                if "Duplicate entry" in str(e):
                    attempt += 1
                    time.sleep(0.1)
                    continue
                else:
                    raise

        flash("System busy. Please try again.", "danger")
        return redirect(url_for('tasks'))

    # ----------------------------------------------------
    # SEARCH MODE
    # ----------------------------------------------------
    q = request.args.get('q','')
    if q:
        rows = query_all("""
            SELECT t.*, u.username as assigned_name
            FROM tasks t
            LEFT JOIN users u ON t.assigned_to=u.id
            WHERE t.task_no LIKE %s OR t.title LIKE %s
            ORDER BY t.id DESC
        """, (f'%{q}%', f'%{q}%'))
    else:
        # NORMAL MODE — NEWEST FIRST
        rows = query_all("""
            SELECT t.*, u.username as assigned_name
            FROM tasks t
            LEFT JOIN users u ON t.assigned_to=u.id
            ORDER BY t.id DESC
        """)

    return render_template("tasks.html", users=users, tasks=rows)



@app.route('/tasks/<int:task_id>')
@require_login
def task_view(task_id):
    user = current_user()

    task = query_one("""
        SELECT t.*, u.username AS assigned_name
        FROM tasks t
        LEFT JOIN users u ON t.assigned_to = u.id
        WHERE t.id=%s
    """, (task_id,))

    comments = query_all("""
        SELECT tc.*, u.username
        FROM task_comments tc
        LEFT JOIN users u ON tc.user_id=u.id
        WHERE tc.task_id=%s
        ORDER BY tc.created_at DESC
    """, (task_id,))

    files = query_all("""
        SELECT * FROM task_files WHERE task_id=%s
    """, (task_id,))

    users = query_all("SELECT id, username FROM users WHERE is_active=1 AND is_approved=1")

    history = query_all("""
        SELECT h.*, u.username
        FROM task_history h
        LEFT JOIN users u ON h.user_id=u.id
        WHERE h.task_id=%s
        ORDER BY h.created_at DESC
    """, (task_id,))

    return render_template('task_view.html',
                           task=task,
                           comments=comments,
                           files=files,
                           users=users,
                           history=history,
                           user=user)
    
@app.post('/tasks/<int:task_id>/countdown/start')
def countdown_start(task_id):
    data = request.get_json()
    minutes = data.get("minutes", 0)
    seconds = minutes * 60

    execute("""
        UPDATE tasks
        SET countdown_start = NOW(),
            countdown_seconds = %s,
            countdown_active = 1
        WHERE id=%s
    """, (seconds, task_id))

    return "OK"

@app.post('/tasks/<int:task_id>/countdown/pause')
def countdown_pause(task_id):
    # Get current countdown state
    task = query_one("""
        SELECT countdown_start, countdown_seconds
        FROM tasks
        WHERE id=%s
    """, (task_id,))

    if task["countdown_start"]:
        start_time = task["countdown_start"]
        now = datetime.now()
        elapsed = int((now - start_time).total_seconds())
        remaining = task["countdown_seconds"] - elapsed
    else:
        remaining = task["countdown_seconds"]

    # Prevent negative values
    if remaining < 0:
        remaining = 0

    execute("""
        UPDATE tasks
        SET countdown_seconds = %s,
            countdown_start = NULL,
            countdown_active = 0
        WHERE id=%s
    """, (remaining, task_id))

    return "OK"


@app.post('/tasks/<int:task_id>/countdown/resume')
def countdown_resume(task_id):
    execute("""
        UPDATE tasks
        SET countdown_active = 1,
            countdown_start = NOW()
        WHERE id=%s
    """, (task_id,))
    return "OK"



@app.post('/tasks/<int:task_id>/countdown/extend')
def countdown_extend(task_id):
    execute("""
        UPDATE tasks
        SET countdown_seconds = countdown_seconds + 300
        WHERE id=%s
    """, (task_id,))
    return "OK"

    

@app.route('/tasks/<int:task_id>/status', methods=['POST'])
@require_login
def task_update_status(task_id):
    user = current_user()
    status = request.form.get('status')

    execute("""
        UPDATE tasks 
        SET status=%s 
        WHERE id=%s
    """, (status, task_id))

    execute("""
        INSERT INTO task_history (task_id, user_id, action, details)
        VALUES (%s,%s,'status_update',%s)
    """, (task_id, user['id'], f"Status changed to {status}"))

    flash('Task status updated', 'success')
    return redirect(url_for('task_view', task_id=task_id))


@app.route('/tasks/<int:task_id>/comment', methods=['POST'])
@require_login
def task_add_comment(task_id):
    user = current_user()
    comment = request.form.get('comment')

    execute("""
        INSERT INTO task_comments (task_id, user_id, comment)
        VALUES (%s,%s,%s)
    """, (task_id, user['id'], comment))

    execute("""
        INSERT INTO task_history (task_id, user_id, action, details)
        VALUES (%s,%s,'comment','Added a comment')
    """, (task_id, user['id']))

    flash('Comment added', 'success')
    return redirect(url_for('task_view', task_id=task_id))

@app.route('/tasks/<int:task_id>/transfer', methods=['POST'])
@require_login
def task_transfer(task_id):
    user = current_user()
    new_user = request.form.get('assigned_to')

    execute("""
        UPDATE tasks 
        SET assigned_to=%s 
        WHERE id=%s
    """, (new_user, task_id))

    execute("""
        INSERT INTO task_history (task_id, user_id, action, details)
        VALUES (%s,%s,'transfer',%s)
    """, (task_id, user['id'], f"Transferred to user {new_user}"))

    flash('Task transferred', 'success')
    return redirect(url_for('task_view', task_id=task_id))

#My Tasks
@app.route('/my-tasks')
@require_login
def my_tasks():
    user = current_user()

    rows = query_all("""
        SELECT t.*, u.username AS assigned_name
        FROM tasks t
        LEFT JOIN users u ON t.assigned_to = u.id
        WHERE t.assigned_to = %s
        ORDER BY t.id DESC
    """, (user['id'],))

    users = query_all("SELECT id, username FROM users WHERE is_active=1 AND is_approved=1")

    return render_template("tasks.html", users=users, tasks=rows)

from flask import send_from_directory, abort
import os

@app.route("/uploads/tasks/<path:filename>")
def download_task_file(filename):
    import os
    from flask import send_from_directory, abort

    # APPROACH 2: Use the actual Program Files path
    directory = r"C:\Program Files (x86)\RELLA8.1\RELLA8.1\uploads\tasks"

    # Full path
    file_path = os.path.join(directory, filename)

    # If missing extension, try to find the real file
    if not os.path.isfile(file_path):
        # Try PDF
        if os.path.isfile(file_path + ".pdf"):
            filename += ".pdf"
            file_path = file_path + ".pdf"
        # Try Excel
        elif os.path.isfile(file_path + ".xlsx"):
            filename += ".xlsx"
            file_path = file_path + ".xlsx"
        else:
            abort(404)

    # Detect MIME type
    ext = filename.lower().split(".")[-1]

    if ext == "pdf":
        mimetype = "application/pdf"
    elif ext == "xlsx":
        mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        mimetype = "application/octet-stream"

    return send_from_directory(
        directory,
        filename,
        as_attachment=True,
        download_name=filename,
        mimetype=mimetype
    )





#--------Comms main page
import os
from werkzeug.utils import secure_filename

UPLOAD_EMAIL = "static/uploads/email/"
UPLOAD_CHAT = "static/uploads/chat/"

def save_attachment(file, folder):
    if not file or file.filename == "":
        return None
    filename = secure_filename(file.filename)
    path = os.path.join(folder, filename)
    file.save(path)
    return path

def execute_returning_id(sql, params=None):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(sql, params or ())
    db.commit()
    last_id = cursor.lastrowid
    cursor.close()
    return last_id






#Send email


#View thread + reply
@app.route('/comms/email/thread/<int:thread_id>')
@require_login
def comms_email_thread(thread_id):
    user = current_user()

    messages = query_all("""
        SELECT em.*, u.username AS sender_name
        FROM email_messages em
        JOIN users u ON em.sender_id = u.id
        WHERE em.thread_id = %s
        ORDER BY em.created_at ASC
    """, (thread_id,))

    execute("""
        UPDATE email_recipients er
        JOIN email_messages em ON er.message_id = em.id
        SET er.is_read = 1
        WHERE er.user_id = %s AND em.thread_id = %s
    """, (user['id'], thread_id))

    subject = query_one("SELECT subject FROM email_threads WHERE id=%s", (thread_id,))

    return render_template("comms_thread.html", messages=messages, subject=subject['subject'], thread_id=thread_id)

@app.route("/email/download/<path:filename>")
@login_required
def email_download(filename):
    import os
    from flask import send_from_directory, abort, flash, redirect, url_for

    # APPROACH 2: Use the actual Program Files path
    directory = r"C:\Program Files (x86)\RELLA8.1\RELLA8.1\static\uploads\email"

    # Full path
    file_path = os.path.join(directory, filename)

    # If file without extension was passed, try to detect the real file
    if not os.path.isfile(file_path):
        for ext in [".pdf", ".xlsx", ".xls", ".docx", ".doc", ".png", ".jpg", ".jpeg"]:
            if os.path.isfile(file_path + ext):
                filename = filename + ext
                file_path = file_path + ext
                break
        else:
            flash("Attachment not found.", "error")
            return redirect(url_for("comms_page"))

    # Detect MIME type
    ext = filename.lower().split(".")[-1]

    mime_map = {
        "pdf": "application/pdf",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
    }

    mimetype = mime_map.get(ext, "application/octet-stream")

    return send_from_directory(
        directory,
        filename,
        as_attachment=True,
        download_name=filename,
        mimetype=mimetype
    )







#Chat: load messages + send message (AJAX)
@app.route('/comms/chat/<int:room_id>/messages')
@require_login
def comms_chat_messages(room_id):
    msgs = query_all("""
        SELECT m.*, u.username AS sender_name
        FROM chat_messages m
        JOIN users u ON m.sender_id = u.id
        WHERE m.room_id = %s
        ORDER BY m.created_at ASC
    """, (room_id,))
    return jsonify(msgs)



@app.route('/comms/chat/<int:room_id>/send', methods=['POST'])
@require_login
def comms_chat_send(room_id):
    user = current_user()
    file = request.files.get('attachment')
    data = request.form or request.get_json()

    text = data.get('message', '').strip()
    attachment_path = save_attachment(file, UPLOAD_CHAT)

    execute("""
        INSERT INTO chat_messages (room_id, sender_id, message, attachment_path)
        VALUES (%s, %s, %s, %s)
    """, (room_id, user['id'], text, attachment_path))

    return jsonify({'success': True})
@app.context_processor
def inject_user():
    try:
        return {'current_user': current_user()}
    except:
        return {'current_user': None}
    
@app.route('/comms/email/reply/<int:thread_id>', methods=['POST'])
@require_login
def comms_email_reply(thread_id):
    user = current_user()
    body = request.form.get('body')
    file = request.files.get('attachment')

    attachment_path = save_attachment(file, UPLOAD_EMAIL)

    message_id = execute_returning_id("""
        INSERT INTO email_messages (thread_id, sender_id, body, attachment_path)
        VALUES (%s, %s, %s, %s)
    """, (thread_id, user['id'], body, attachment_path))

    # Add to sender's sent folder
    execute("""
        INSERT INTO email_recipients (message_id, user_id, folder, is_read)
        VALUES (%s, %s, 'sent', 1)
    """, (message_id, user['id']))

    # Add to all recipients in the thread
    recipients = query_all("""
        SELECT DISTINCT er.user_id
        FROM email_recipients er
        JOIN email_messages em ON er.message_id = em.id
        WHERE em.thread_id = %s AND er.user_id != %s
    """, (thread_id, user['id']))

    for r in recipients:
        execute("""
            INSERT INTO email_recipients (message_id, user_id, folder, is_read)
            VALUES (%s, %s, 'inbox', 0)
        """, (message_id, r['user_id']))

    return redirect(f"/comms/email/thread/{thread_id}")




import os
from werkzeug.utils import secure_filename

UPLOAD_EMAIL = "static/uploads/email/"
UPLOAD_CHAT = "static/uploads/chat/"

def save_attachment(file, folder):
    if not file or file.filename == "":
        return None
    filename = secure_filename(file.filename)
    path = os.path.join(folder, filename)
    file.save(path)
    return path



@app.route('/comms/email/send', methods=['POST'])
@require_login
def comms_email_send():
    user = current_user()
    subject = request.form.get('subject')
    body = request.form.get('body')
    to_ids = request.form.getlist('to')
    file = request.files.get('attachment')

    attachment_path = save_attachment(file, UPLOAD_EMAIL)

    thread_id = execute_returning_id("""
        INSERT INTO email_threads (subject) VALUES (%s)
    """, (subject,))

    message_id = execute_returning_id("""
        INSERT INTO email_messages (thread_id, sender_id, body, attachment_path)
        VALUES (%s, %s, %s, %s)
    """, (thread_id, user['id'], body, attachment_path))

    execute("""
        INSERT INTO email_recipients (message_id, user_id, folder, is_read)
        VALUES (%s, %s, 'sent', 1)
    """, (message_id, user['id']))

    for uid in to_ids:
        execute("""
            INSERT INTO email_recipients (message_id, user_id, folder, is_read)
            VALUES (%s, %s, 'inbox', 0)
        """, (message_id, uid))

    flash("Email sent", "success")
    return redirect(url_for('comms_page'))


@app.route('/comms')
@require_login
def comms_page():
    user = current_user()

    inbox = query_all("""
        SELECT em.id AS message_id, et.id AS thread_id, et.subject,
               em.body, em.attachment_path, em.created_at,
               u.username AS sender_name, er.is_read
        FROM email_recipients er
        JOIN email_messages em ON er.message_id = em.id
        JOIN email_threads et ON em.thread_id = et.id
        JOIN users u ON em.sender_id = u.id
        WHERE er.user_id = %s AND er.folder = 'inbox'
        ORDER BY em.created_at DESC
    """, (user['id'],))

    sent = query_all("""
        SELECT em.id AS message_id, et.id AS thread_id, et.subject,
               em.body, em.attachment_path, em.created_at
        FROM email_messages em
        JOIN email_threads et ON em.thread_id = et.id
        WHERE em.sender_id = %s
        ORDER BY em.created_at DESC
    """, (user['id'],))

    users = query_all("SELECT id, username FROM users WHERE is_active=1 AND is_approved=1")

    rooms = query_all("""
        SELECT r.id, r.name, r.is_direct
        FROM chat_rooms r
        JOIN chat_room_members m ON r.id = m.room_id
        WHERE m.user_id = %s
        ORDER BY r.name
    """, (user['id'],))

    return render_template("comms.html", inbox=inbox, sent=sent, users=users, rooms=rooms)










@app.route('/comms/search')
@require_login
def comms_search():
    q = "%" + request.args.get("q", "") + "%"

    email_results = query_all("""
        SELECT et.subject, em.body, em.attachment_path, em.created_at
        FROM email_messages em
        JOIN email_threads et ON em.thread_id = et.id
        WHERE em.body LIKE %s OR et.subject LIKE %s
        ORDER BY em.created_at DESC
    """, (q, q))

    chat_results = query_all("""
        SELECT m.message, m.attachment_path, m.created_at, u.username
        FROM chat_messages m
        JOIN users u ON m.sender_id = u.id
        WHERE m.message LIKE %s
        ORDER BY m.created_at DESC
    """, (q,))

    return render_template("comms_search.html", email=email_results, chat=chat_results)





import os
UPLOAD_FOLDER = "uploads/tasks"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/tasks/<int:task_id>/upload', methods=['POST'])
@require_login
def task_upload(task_id):
    user = current_user()
    file = request.files.get('file')

    if not file:
        flash('No file selected', 'error')
        return redirect(url_for('task_view', task_id=task_id))

    filename = file.filename
    path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(path)

    execute("""
        INSERT INTO task_files (task_id, user_id, file_name, file_path)
        VALUES (%s,%s,%s,%s)
    """, (task_id, user['id'], filename, path))

    execute("""
        INSERT INTO task_history (task_id, user_id, action, details)
        VALUES (%s,%s,'file_upload',%s)
    """, (task_id, user['id'], filename))

    flash('File uploaded', 'success')
    return redirect(url_for('task_view', task_id=task_id))




# --- Permissions management (admin only) ---
@app.route('/permissions', methods=['GET', 'POST'])
@require_login
def permissions_page():
    user = current_user()

    # Only admins allowed
    if user['role'] != 'admin':
        flash('Only admins can access permissions', 'error')
        return redirect(url_for('dashboard'))

    # ============================
    # HANDLE POST ACTIONS
    # ============================
    if request.method == 'POST':
        action = request.form.get('action')
        uid = request.form.get('user_id')

        # APPROVE USER
        if action == 'approve_user':
            execute("UPDATE users SET is_approved=1 WHERE id=%s", (uid,))
            log_action(user['id'], 'approve_user', f'Approved user {uid}')
            flash('User approved', 'success')

        # ACTIVATE USER
        elif action == 'activate_user':
            execute("UPDATE users SET is_active=1 WHERE id=%s", (uid,))
            log_action(user['id'], 'activate_user', f'Activated user {uid}')
            flash('User activated', 'success')

        # SUSPEND USER
        elif action == 'suspend_user':
            execute("UPDATE users SET is_active=0 WHERE id=%s", (uid,))
            log_action(user['id'], 'suspend_user', f'Suspended user {uid}')
            flash('User suspended', 'success')

        # DELETE USER (SAFE DELETE)
        elif action == 'delete_user':
            linked = query_one("""
                SELECT COUNT(*) AS total
                FROM salary_statements
                WHERE user_id=%s
            """, (uid,))

            if linked['total'] > 0:
                flash("Cannot delete user — linked salary statements exist.", "error")
            else:
                execute("DELETE FROM user_permissions WHERE user_id=%s", (uid,))
                execute("DELETE FROM users WHERE id=%s", (uid,))
                log_action(user['id'], 'delete_user', f'Deleted user {uid}')
                flash('User deleted', 'success')

        # ============================
        # UPDATE ROLE (NEW)
        # ============================
        elif action == 'update_role':
            new_role = request.form.get('new_role')

            execute("UPDATE users SET role=%s WHERE id=%s", (new_role, uid))
            log_action(user['id'], 'update_role', f'Changed role for user {uid} to {new_role}')
            flash('Role updated successfully', 'success')

        # GRANT PERMISSION (single)
        elif action == 'grant_perm':
            perm_code = request.form.get('perm_code')
            perm = query_one("SELECT id FROM permissions WHERE code=%s", (perm_code,))
            if perm:
                execute("""
                    INSERT IGNORE INTO user_permissions (user_id, permission_id, granted_by)
                    VALUES (%s, %s, %s)
                """, (uid, perm['id'], user['id']))
                log_action(user['id'], 'grant_permission', f'Granted {perm_code} to {uid}')
                flash('Permission granted', 'success')

        # REMOVE PERMISSION (single)
        elif action == 'remove_perm':
            perm_code = request.form.get('perm_code')
            perm = query_one("SELECT id FROM permissions WHERE code=%s", (perm_code,))
            if perm:
                execute("""
                    DELETE FROM user_permissions
                    WHERE user_id=%s AND permission_id=%s
                """, (uid, perm['id']))
                log_action(user['id'], 'remove_permission', f'Removed {perm_code} from {uid}')
                flash('Permission removed', 'success')

        # ============================
        # BULK GRANT PERMISSIONS
        # ============================
        elif action == 'bulk_grant':
            user_ids = request.form.getlist('user_ids')
            perm_codes = request.form.getlist('perm_codes')

            for uid in user_ids:
                for code in perm_codes:
                    perm = query_one("SELECT id FROM permissions WHERE code=%s", (code,))
                    if perm:
                        execute("""
                            INSERT IGNORE INTO user_permissions (user_id, permission_id, granted_by)
                            VALUES (%s, %s, %s)
                        """, (uid, perm['id'], user['id']))

            log_action(user['id'], 'bulk_grant', f'Granted {perm_codes} to users {user_ids}')
            flash('Bulk permissions granted successfully.', 'success')

        # ============================
        # BULK REMOVE PERMISSIONS
        # ============================
        elif action == 'bulk_remove':
            user_ids = request.form.getlist('user_ids')
            perm_codes = request.form.getlist('perm_codes')

            for uid in user_ids:
                for code in perm_codes:
                    perm = query_one("SELECT id FROM permissions WHERE code=%s", (code,))
                    if perm:
                        execute("""
                            DELETE FROM user_permissions
                            WHERE user_id=%s AND permission_id=%s
                        """, (uid, perm['id']))

            log_action(user['id'], 'bulk_remove', f'Removed {perm_codes} from users {user_ids}')
            flash('Bulk permissions removed successfully.', 'success')

        return redirect(url_for('permissions_page'))

    # ============================
    # LOAD DATA FOR PAGE
    # ============================
    users = query_all("SELECT * FROM users ORDER BY username ASC")
    perms = query_all("SELECT * FROM permissions ORDER BY code ASC")

    user_perms = query_all("""
        SELECT user_id, permission_id
        FROM user_permissions
    """)

    perm_map = {}
    for p in user_perms:
        perm_map.setdefault(p['user_id'], set()).add(p['permission_id'])

    return render_template(
        'permissions.html',
        users=users,
        perms=perms,
        perm_map=perm_map,
        user=user
    )


    
ROUTE_PERMISSIONS = {
    '/dashboard': 'view_dashboard',
    '/sales': 'view_sales',
    '/stock': 'view_stock',
    '/products': 'view_products',
    '/finances': 'view_finances',
    '/reports': 'view_reports',
    '/settings': 'view_settings',
    '/clients': 'view_clients',
    '/pos': 'view_pos',
    '/records': 'view_records',
    '/stores': 'view_stores',
    '/stock-in': 'view_stock_in',
    '/transfer': 'view_transfer',
    '/movements': 'view_movements',
    '/human': 'view_human',
    '/comms': 'view_comms',
    '/tasks': 'view_tasks',
    '/permissions': 'view_permissions'
}


@app.before_request
def enforce_permissions():
    path = request.path

    # Allow static files
    if path.startswith('/static/'):
        return

    # Allow login, register, logout
    if path in ['/login', '/register', '/logout']:
        return

    # Allow admin to access permissions page
    if path.startswith('/permissions'):
        return

    # If route requires a permission
    if path in ROUTE_PERMISSIONS:

        # Must be logged in
        if not session.get('user_id'):
            return redirect(url_for('login'))

        user = current_user()

        # Admin bypass
        if user['role'] == 'admin':
            return

        required_perm = ROUTE_PERMISSIONS[path]

        # Load user permissions
        rows = query_all("""
            SELECT p.code
            FROM user_permissions up
            JOIN permissions p ON p.id = up.permission_id
            WHERE up.user_id = %s
        """, (user['id'],))

        user_perms = {r['code'] for r in rows}

        # Dashboard always allowed
        user_perms.add('view_dashboard')

        # If user lacks permission → redirect to dashboard
        if required_perm not in user_perms:
            flash("You do not have permission to access this page.", "error")
            return redirect(url_for('dashboard'))



    


# --- Placeholder pages for HR, Comms, Finances, etc. ---
@app.route("/human")
@login_required
def human():
    db = get_db()
    cursor = db.cursor(dictionary=True)

    user_id = session["user_id"]

    # Load logged-in user
    cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    user = cursor.fetchone()

    if not user:
        return redirect(url_for("login"))

    # ============================================================
    # COMMON DATA FOR BOTH STAFF + ADMIN
    # ============================================================

    # Leave categories
    cursor.execute("SELECT * FROM leave_categories ORDER BY name ASC")
    leave_categories = cursor.fetchall() or []

    # Payroll settings
    cursor.execute("SELECT * FROM payroll_settings LIMIT 1")
    payroll = cursor.fetchone() or {
        "rate_per_hour": 0,
        "overtime_rate_per_hour": 0
    }

    # Job vacancies
    cursor.execute("""
        SELECT 
            v.*,
            (SELECT COUNT(*) FROM job_applications a WHERE a.vacancy_id = v.id) AS applications_count
        FROM job_vacancies v
        ORDER BY v.created_at DESC
    """)
    vacancies = cursor.fetchall() or []

    # ============================================================
    # STAFF VIEW
    # ============================================================
    if user["role"] == "staff":

        # Staff overtime list
        cursor.execute("""
            SELECT * FROM overtime_requests
            WHERE user_id=%s
            ORDER BY created_at DESC
        """, (user_id,))
        staff_overtime_list = cursor.fetchall() or []

        # Staff leave list
        cursor.execute("""
            SELECT lr.*, lc.name AS leave_type_name
            FROM leave_requests lr
            JOIN leave_categories lc ON lc.id = lr.category_id
            WHERE lr.user_id=%s
            ORDER BY lr.created_at DESC
        """, (user_id,))
        staff_leave_list = cursor.fetchall() or []

        # Staff salary statements
        cursor.execute("""
            SELECT id, period_label, net_pay, statement_date
            FROM salary_statements
            WHERE user_id=%s
            ORDER BY statement_date DESC
        """, (user_id,))
        staff_salary_statements = cursor.fetchall() or []

        # Staff leave balance
        cursor.execute("""
            SELECT lb.*, lc.name AS leave_type_name
            FROM leave_balances lb
            JOIN leave_categories lc ON lc.id = lb.category_id
            WHERE lb.user_id=%s
        """, (user_id,))
        staff_leave_balance = cursor.fetchall() or []

        # Staff job applications
        cursor.execute("""
            SELECT a.*, v.title, v.department, v.closing_date
            FROM job_applications a
            JOIN job_vacancies v ON v.id = a.vacancy_id
            WHERE a.user_id=%s
        """, (user_id,))
        staff_applications = cursor.fetchall() or []

        # Staff profile
        cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
        profile = cursor.fetchone()
        if profile:
            profile["full_name"] = profile["username"]

        # Staff documents
        cursor.execute("SELECT * FROM user_documents WHERE user_id=%s", (user_id,))
        profile_documents = cursor.fetchall() or []

        return render_template(
            "human.html",
            user=user,
            leave_categories=leave_categories,
            payroll=payroll,
            vacancies=vacancies,
            staff_overtime_list=staff_overtime_list,
            staff_leave_list=staff_leave_list,
            staff_salary_statements=staff_salary_statements,
            staff_leave_balance=staff_leave_balance,
            staff_applications=staff_applications,
            profile=profile,
            profile_documents=profile_documents
        )

    # ============================================================
    # ADMIN VIEW
    # ============================================================
    else:

        # All users (admin selection)
        cursor.execute("""
            SELECT id, username AS full_name, email, contact
            FROM users
            ORDER BY username ASC
        """)
        users = cursor.fetchall() or []

        # Pending overtime approvals
        cursor.execute("""
            SELECT o.*, u.username AS user_name
            FROM overtime_requests o
            JOIN users u ON u.id = o.user_id
            WHERE o.status='pending'
            ORDER BY o.created_at DESC
        """)
        overtime_pending = cursor.fetchall() or []

        # Pending leave approvals
        cursor.execute("""
            SELECT lr.*, u.username AS user_name, lc.name AS leave_type_name
            FROM leave_requests lr
            JOIN users u ON u.id = lr.user_id
            JOIN leave_categories lc ON lc.id = lr.category_id
            WHERE lr.status='pending'
            ORDER BY lr.created_at DESC
        """)
        leave_pending = cursor.fetchall() or []

        # All salary statements
        cursor.execute("""
            SELECT s.*, u.username AS user_name
            FROM salary_statements s
            JOIN users u ON u.id = s.user_id
            ORDER BY s.statement_date DESC
        """)
        salary_statements = cursor.fetchall() or []

        # Admin does not use staff profile, but template expects variables
        profile = None
        profile_documents = []

        return render_template(
            "human.html",
            user=user,
            users=users,
            leave_categories=leave_categories,
            payroll=payroll,
            vacancies=vacancies,
            overtime_pending=overtime_pending,
            leave_pending=leave_pending,
            salary_statements=salary_statements,
            profile=profile,
            profile_documents=profile_documents
        )

@app.post("/hr/overtime/<int:id>/decline")
@login_required
def admin_overtime_decline(id):
    db = get_db()
    cursor = db.cursor()

    try:
        cursor.execute("UPDATE overtime_requests SET status='declined' WHERE id=%s", (id,))
        db.commit()
    except Exception as e:
        db.rollback()
        print("ERROR:", e)

    return redirect(url_for("human"))


@app.context_processor
def inject_all_staff():
    user = session.get("user")

    # Only owner should see staff list
    if not user or user.get("role") != "owner":
        return {"all_staff": []}

    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(
        "SELECT id, name FROM users WHERE business_id=%s ORDER BY name ASC",
        (user["business_id"],)
    )
    staff = cursor.fetchall()

    return {"all_staff": staff}



@app.route("/hr/profile/admin/<int:user_id>/edit")
@login_required
def admin_profile_edit(user_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    # Load user being edited
    cursor.execute("SELECT * FROM users WHERE id=%s", (user_id,))
    profile = cursor.fetchone()

    if not profile:
        return redirect(url_for("human"))

    # Load documents
    cursor.execute("SELECT * FROM user_documents WHERE user_id=%s", (user_id,))
    profile_documents = cursor.fetchall() or []

    return render_template(
        "admin_profile_edit.html",
        profile=profile,
        profile_documents=profile_documents
    )


@app.route('/hr/profile/admin/<int:user_id>/update', methods=['POST'])
def admin_profile_update(user_id):
    db = get_db()
    cursor = db.cursor()

    # Read form fields
    username = request.form.get('username')
    email = request.form.get('email')
    contact = request.form.get('contact')
    address = request.form.get('address')
    qualifications = request.form.get('qualifications')

    # Update user
    cursor.execute("""
        UPDATE users
        SET username=%s, email=%s, contact=%s, address=%s, qualifications=%s
        WHERE id=%s
    """, (username, email, contact, address, qualifications, user_id))

    # Handle file uploads
    upload_dir = os.path.join("uploads")
    os.makedirs(upload_dir, exist_ok=True)

    files = request.files.getlist('documents')
    for f in files:
        if f.filename:
            filepath = os.path.join(upload_dir, f.filename)
            f.save(filepath)
            cursor.execute("""
                INSERT INTO user_documents (user_id, filename, filepath)
                VALUES (%s, %s, %s)
            """, (user_id, f.filename, filepath))

    db.commit()

    # ⭐ THIS LINE IS THE FIX ⭐
    return redirect(url_for('human'))

from flask import send_from_directory
import os

from flask import send_from_directory, abort
import os

@app.route('/hr/profile/download/<path:filename>')
def download_document(filename):
    import os
    from flask import send_from_directory, abort

    # Base uploads folder
    upload_dir = os.path.join(app.root_path, "uploads")
    file_path = os.path.join(upload_dir, filename)

    # If file without extension was passed, try to detect the real file
    if not os.path.isfile(file_path):
        # Try common extensions
        for ext in [".pdf", ".xlsx", ".xls", ".docx", ".doc", ".png", ".jpg", ".jpeg"]:
            if os.path.isfile(file_path + ext):
                filename = filename + ext
                file_path = file_path + ext
                break
        else:
            abort(404)

    # Detect MIME type
    ext = filename.lower().split(".")[-1]

    mime_map = {
        "pdf": "application/pdf",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
    }

    mimetype = mime_map.get(ext, "application/octet-stream")

    return send_from_directory(
        upload_dir,
        filename,
        as_attachment=False,          # open directly in default app
        download_name=filename,
        mimetype=mimetype
    )





from fpdf import FPDF
import time
import os

def generate_salary_pdf(statement_id, profile, salary_data):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(200, 10, txt="Salary Statement", ln=True, align="C")
    pdf.ln(5)

    pdf.cell(200, 10, txt=f"Employee: {profile.full_name}", ln=True)
    pdf.cell(200, 10, txt=f"Email: {profile.email}", ln=True)
    pdf.cell(200, 10, txt=f"Contact: {profile.contact}", ln=True)
    pdf.ln(5)

    pdf.cell(200, 10, txt=f"Basic Salary: R {salary_data['basic_salary']}", ln=True)
    pdf.cell(200, 10, txt=f"Overtime Pay: R {salary_data['overtime_pay']}", ln=True)
    pdf.cell(200, 10, txt=f"Allowances: R {salary_data['allowances']}", ln=True)
    pdf.cell(200, 10, txt=f"Deductions: R {salary_data['deductions']}", ln=True)
    pdf.ln(5)

    pdf.cell(200, 10, txt=f"Net Salary: R {salary_data['net_salary']}", ln=True)

    # Save PDF
    filename = f"salary_{statement_id}_{int(time.time())}.pdf"
    save_path = os.path.join("finance_docs", filename)
    os.makedirs("finance_docs", exist_ok=True)
    pdf.output(save_path)

    return filename


    db.commit()
    flash("Profile updated successfully!", "success")
    return redirect(url_for('human'))










@app.route('/comms')
@require_login
def comms():
    user = current_user()
    return render_template('comms.html', user=user)

@app.route('/admin/salary/<int:statement_id>/update', methods=['POST'])
def admin_salary_update(statement_id):
    db = get_db()
    cursor = db.cursor()

    basic_salary = request.form.get('basic_salary')
    overtime_pay = request.form.get('overtime_pay')
    allowances = request.form.get('allowances')
    deductions = request.form.get('deductions')
    notes = request.form.get('notes')

    # Recalculate net pay
    net_pay = (
        float(basic_salary or 0)
        + float(overtime_pay or 0)
        + float(allowances or 0)
        - float(deductions or 0)
    )

    cursor.execute("""
        UPDATE salary_statements
        SET basic_salary=%s, overtime_pay=%s, allowances=%s,
            deductions=%s, notes=%s, net_pay=%s
        WHERE id=%s
    """, (basic_salary, overtime_pay, allowances, deductions, notes, net_pay, statement_id))

    db.commit()

    return redirect(url_for('admin_salary'))


# --- Finances main page ---
@app.route('/finances', methods=['GET', 'POST'])
@require_login
def finances():
    user = current_user()

    # Date filters
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    cashier_id = request.args.get('cashier_id', '')

    # TODO: wire this to your real records table
    # Example: records table with type: 'sale', 'expense', 'stock_in', etc.
    params = []
    where = []

    if start_date:
        where.append("r.created_at >= %s")
        params.append(start_date + " 00:00:00")
    if end_date:
        where.append("r.created_at <= %s")
        params.append(end_date + " 23:59:59")
    if cashier_id:
        where.append("r.user_id = %s")
        params.append(cashier_id)

    where_sql = "WHERE " + " AND ".join(where) if where else ""

    # Company‑wide financial records (from records.html logic)
    records = query_all(f"""
        SELECT r.*
        FROM records r
        {where_sql}
        ORDER BY r.created_at DESC
    """, tuple(params))

    # Example aggregates (you’ll refine based on your schema)
    totals = query_one(f"""
        SELECT
            COALESCE(SUM(CASE WHEN r.type = 'sale' THEN r.amount ELSE 0 END), 0) AS total_sales,
            COALESCE(SUM(CASE WHEN r.type = 'expense' THEN r.amount ELSE 0 END), 0) AS total_expenses,
            COALESCE(SUM(CASE WHEN r.type = 'stock_in' THEN r.amount ELSE 0 END), 0) AS total_stock_in
        FROM records r
        {where_sql}
    """, tuple(params))

    # Cashiers for reconciliation filter
    cashiers = query_all("SELECT id, name FROM users ORDER BY name ASC")

    return render_template(
        'finances.html',
        user=user,
        records=records,
        totals=totals,
        cashiers=cashiers,
        start_date=start_date,
        end_date=end_date,
        cashier_id=cashier_id
    )
@app.route('/finances/reconcile/company')
@require_login
def run_company_reconciliation():
    user = current_user()

    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    user_id = request.args.get('user_id', '')
    store_id = request.args.get('store_id', '')

    where = ["1=1"]
    params = []

    if start_date:
        where.append("DATE(s.created_at) >= %s")
        params.append(start_date)
    if end_date:
        where.append("DATE(s.created_at) <= %s")
        params.append(end_date)
    if user_id:
        where.append("s.created_by = %s")
        params.append(user_id)
    if store_id:
        where.append("s.store_id = %s")
        params.append(store_id)

    where_sql = " AND ".join(where)

    totals = query_one(f"""
        SELECT
            COALESCE(SUM(s.subtotal), 0) AS subtotal,
            COALESCE(SUM(s.vat), 0) AS vat,
            COALESCE(SUM(s.total), 0) AS total
        FROM sales s
        WHERE {where_sql}
    """, params)

    transactions = query_all(f"""
        SELECT 
            s.invoice_no,
            s.subtotal,
            s.vat,
            s.total,
            s.created_at,
            u.username AS user_name,
            st.name AS store_name
        FROM sales s
        LEFT JOIN users u ON s.created_by = u.id
        LEFT JOIN stores st ON s.store_id = st.id
        WHERE {where_sql}
        ORDER BY s.created_at DESC
    """, params)

    return render_template(
        'reconcile_company.html',
        totals=totals,
        transactions=transactions,
        start_date=start_date,
        end_date=end_date,
        user=user
    )

@app.route('/finances/reconcile/user')
@require_login
def run_user_reconciliation():
    user = current_user()

    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    user_id = request.args.get('user_id', '')
    store_id = request.args.get('store_id', '')

    where = ["1=1"]
    params = []

    if start_date:
        where.append("DATE(s.created_at) >= %s")
        params.append(start_date)
    if end_date:
        where.append("DATE(s.created_at) <= %s")
        params.append(end_date)
    if user_id:
        where.append("s.created_by = %s")
        params.append(user_id)
    if store_id:
        where.append("s.store_id = %s")
        params.append(store_id)

    where_sql = " AND ".join(where)

    # Totals for this cashier
    totals = query_one(f"""
        SELECT
            COALESCE(SUM(s.subtotal), 0) AS subtotal,
            COALESCE(SUM(s.vat), 0) AS vat,
            COALESCE(SUM(s.total), 0) AS total
        FROM sales s
        WHERE {where_sql}
    """, params)

    # Transactions for this cashier
    transactions = query_all(f"""
        SELECT 
            s.invoice_no,
            s.subtotal,
            s.vat,
            s.total,
            s.created_at,
            u.username AS user_name,
            st.name AS store_name
        FROM sales s
        LEFT JOIN users u ON s.created_by = u.id
        LEFT JOIN stores st ON s.store_id = st.id
        WHERE {where_sql}
        ORDER BY s.created_at DESC
    """, params)

    return render_template(
        'reconcile_user.html',
        totals=totals,
        transactions=transactions,
        start_date=start_date,
        end_date=end_date,
        user=user
    )
@app.route('/finances/external', methods=['POST'])
@require_login
def finances_external():
    user = current_user()

    # Safely read form fields
    entry_date = request.form.get('entry_date')
    description = request.form.get('description')
    amount = request.form.get('amount')
    entry_type = request.form.get('entry_type')  # income / expense / adjustment

    # Insert into external_entries table
    execute("""
        INSERT INTO external_entries (entry_date, description, amount, entry_type, created_by)
        VALUES (%s, %s, %s, %s, %s)
    """, (entry_date, description, amount, entry_type, user['id']))

    # Optional: also insert into records table later if needed
    # execute("""
    #     INSERT INTO records (type, description, amount, created_at, user_id, source)
    #     VALUES (%s, %s, %s, %s, %s, %s)
    # """, (entry_type, description, amount, entry_date, user['id'], 'external'))

    flash("External financial entry captured successfully.", "success")
    return redirect(url_for('finances_page'))



def get_balance_statement():
    assets = query_one("SELECT COALESCE(SUM(amount),0) AS total FROM external_entries WHERE entry_type='asset'")
    liabilities = query_one("SELECT COALESCE(SUM(amount),0) AS total FROM external_entries WHERE entry_type='liability'")
    equity = assets['total'] - liabilities['total']
    return assets['total'], liabilities['total'], equity


def get_income_statement():
    sales = query_one("SELECT COALESCE(SUM(total),0) AS total FROM sales")
    expenses = query_one("SELECT COALESCE(SUM(amount),0) AS total FROM external_entries WHERE entry_type='expense'")
    stock_in = query_one("SELECT COALESCE(SUM(cost),0) AS total FROM stock_in")
    net_income = sales['total'] - expenses['total'] - stock_in['total']
    return sales['total'], expenses['total'], stock_in['total'], net_income





from flask import send_file, abort
import os
import mimetypes

@app.route("/finances/download/<int:file_id>")
@login_required
def finances_download(file_id):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        "SELECT stored_name, filename FROM finance_files WHERE id=%s",
        (file_id,)
    )
    row = cursor.fetchone()

    if not row:
        flash("File not found.", "error")
        return redirect(url_for("human", tab="finances"))

    directory = os.path.join(app.root_path, "finance_docs")
    file_path = os.path.join(directory, row["stored_name"])

    if not os.path.isfile(file_path):
        flash("File missing on server.", "error")
        return redirect(url_for("human", tab="finances"))

    # Detect MIME type automatically
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type is None:
        mime_type = "application/octet-stream"  # fallback for unknown types

    # Force OS default app to open the file
    return send_file(
        file_path,
        mimetype=mime_type,
        as_attachment=True,              # forces download → OS opens it
        download_name=row["filename"]    # correct filename
    )





    
@app.route('/finances/export/excel', endpoint='finances_export_excel')
@require_login
def finances_export_excel():
    return finances_export_excel_file()  # if your logic is in another function

@app.route('/finances/balance/export/csv', endpoint='balance_export_csv')
@require_login
def balance_export_csv():
    assets = query_one("SELECT COALESCE(SUM(amount),0) AS total FROM external_entries WHERE entry_type='asset'")
    liabilities = query_one("SELECT COALESCE(SUM(amount),0) AS total FROM external_entries WHERE entry_type='liability'")
    equity = assets['total'] - liabilities['total']

    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(["Category", "Amount"])
    writer.writerow(["Total Assets", assets['total']])
    writer.writerow(["Total Liabilities", liabilities['total']])
    writer.writerow(["Equity", equity])

    output = si.getvalue()
    resp = Response(output, mimetype="text/csv")
    resp.headers["Content-Disposition"] = "attachment; filename=balance_statement.csv"
    return resp

@app.route('/finances/external/export/csv', endpoint='external_export_csv')
@require_login
def external_export_csv():
    entries = query_all("""
        SELECT entry_date, description, amount, entry_type
        FROM external_entries
        ORDER BY entry_date DESC
    """)

    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(["Date", "Description", "Amount", "Type"])

    for e in entries:
        writer.writerow([e['entry_date'], e['description'], e['amount'], e['entry_type']])

    output = si.getvalue()
    resp = Response(output, mimetype="text/csv")
    resp.headers["Content-Disposition"] = "attachment; filename=external_entries.csv"
    return resp

os.makedirs("finance_docs", exist_ok=True)



    


    


# --- Export finances to CSV ---
@app.route("/finances/export/csv")
@require_login
def finances_export_csv():
    from datetime import datetime
    start_date = request.args.get("start_date") or None
    end_date = request.args.get("end_date") or None
    user_id = request.args.get("user_id") or None

    # Default date range if empty
    if not start_date:
        start_date = "1900-01-01"
    if not end_date:
        end_date = datetime.today().strftime("%Y-%m-%d")

    db = get_db()
    cursor = db.cursor(dictionary=True)

    sql = """
        SELECT s.created_at, s.invoice_no, u.username AS user_name,
               st.name AS store_name, s.subtotal, s.vat, s.total
        FROM sales s
        LEFT JOIN users u ON s.created_by = u.id
        LEFT JOIN stores st ON s.store_id = st.id
        WHERE DATE(s.created_at) BETWEEN %s AND %s
    """
    params = [start_date, end_date]

    if user_id:
        sql += " AND s.created_by = %s"
        params.append(user_id)

    sql += " ORDER BY s.created_at DESC"

    cursor.execute(sql, params)
    rows = cursor.fetchall()

    # Build CSV
    import csv
    from io import StringIO
    output = StringIO()
    writer = csv.writer(output)

    writer.writerow(["Date", "Invoice", "User", "Store", "Subtotal", "VAT", "Total"])

    for r in rows:
        writer.writerow([
            r["created_at"],
            r["invoice_no"],
            r["user_name"],
            r["store_name"],
            "%.2f" % r["subtotal"],
            "%.2f" % r["vat"],
            "%.2f" % r["total"]
        ])

    output.seek(0)

    # ✅ Add date & time stamp to filename
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"finances_{start_date}_to_{end_date}_{timestamp}.csv"

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
    
@app.route('/finances/balance/export/csv', endpoint='finances_balance_export_csv_final')
@require_login
def finances_balance_export_csv_final():
    from datetime import datetime
    import csv
    from io import StringIO

    start_date = request.args.get('start_date') or "1900-01-01"
    end_date = request.args.get('end_date') or datetime.today().strftime("%Y-%m-%d")
    cashier_id = request.args.get('cashier_id') or None

    db = get_db()
    cursor = db.cursor(dictionary=True)

    sql = """
        SELECT s.created_at, s.invoice_no, u.username AS user_name,
               st.name AS store_name, s.subtotal, s.vat, s.total
        FROM sales s
        LEFT JOIN users u ON s.created_by = u.id
        LEFT JOIN stores st ON s.store_id = st.id
        WHERE DATE(s.created_at) BETWEEN %s AND %s
    """
    params = [start_date, end_date]

    if cashier_id:
        sql += " AND s.created_by = %s"
        params.append(cashier_id)

    sql += " ORDER BY s.created_at DESC"
    cursor.execute(sql, params)
    rows = cursor.fetchall()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Invoice", "User", "Store", "Subtotal", "VAT", "Total"])

    for r in rows:
        writer.writerow([
            r["created_at"],
            r["invoice_no"],
            r["user_name"],
            r["store_name"],
            "%.2f" % r["subtotal"],
            "%.2f" % r["vat"],
            "%.2f" % r["total"]
        ])

    output.seek(0)

    # ⭐ Guaranteed timestamp logic
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"balance_statement_{start_date}_to_{end_date}_{timestamp}.csv"

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

    
    
@app.route('/finances/income/export/csv', endpoint='income_export_csv')
@require_login
def income_export_csv():
    from datetime import datetime
    import csv
    from io import StringIO

    # Fetch values
    sales = query_one("SELECT COALESCE(SUM(total),0) AS total FROM sales")
    expenses = query_one("SELECT COALESCE(SUM(amount),0) AS total FROM external_entries WHERE entry_type='expense'")
    stock_in = query_one("SELECT COALESCE(SUM(cost),0) AS total FROM stock_in")

    net_income = sales['total'] - expenses['total'] - stock_in['total']

    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(["Category", "Amount"])
    writer.writerow(["Total Sales", sales['total']])
    writer.writerow(["Total Expenses", expenses['total']])
    writer.writerow(["Stock In (Cost)", stock_in['total']])
    writer.writerow(["Net Income", net_income])

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"income_statement_{timestamp}.csv"

    resp = Response(si.getvalue(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return resp
    



# --- Export finances to PDF ---
@app.route('/finances/export/pdf')
@require_login
def finances_export_pdf():
    user = current_user()
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    cashier_id = request.args.get('cashier_id', '')

    # TODO: generate PDF (e.g. using WeasyPrint / xhtml2pdf)
    # Use finances.html sections or a dedicated PDF template

    flash("PDF export not yet implemented", "info")
    return redirect(url_for('finances'))


# --- Manual external financial entry ---



# --- File upload for financial docs ---
@app.route('/finances/upload', methods=['POST'])
@require_login
def finances_upload():
    user = current_user()
    file = request.files.get('file')

    if not file or file.filename.strip() == "":
        flash("No file selected.", "error")
        return redirect(url_for('finances_page'))

    # PyInstaller‑safe absolute path
    upload_dir = os.path.join(app.root_path, "finance_docs")
    os.makedirs(upload_dir, exist_ok=True)

    # Timestamped stored filename
    stored_name = f"{int(time.time())}_{file.filename}"

    # Full save path
    save_path = os.path.join(upload_dir, stored_name)

    # Save file safely
    file.save(save_path)

    # Log into DB
    execute("""
        INSERT INTO finance_files (filename, stored_name, uploaded_by)
        VALUES (%s, %s, %s)
    """, (file.filename, stored_name, user['id']))

    flash("File uploaded successfully.", "success")
    return redirect(url_for('finances_page'))



# ChatBot
from flask import request, jsonify, session

@app.route("/rellabot/query", methods=["POST"])
@require_login
def rellabot_query():
    data = request.get_json()
    user_message = data.get("message", "").lower().strip()

    print("BOT ROUTE HIT")
    print("USER MESSAGE:", user_message)

    reply = None
    options = []
    last_topic = session.get("last_topic")

    # Load permissions into session if missing
    if "permissions" not in session:
        perms = query_all("""
            SELECT p.code
            FROM user_permissions up
            JOIN permissions p ON p.id = up.permission_id
            WHERE up.user_id = %s
        """, (session["user_id"],))
        session["permissions"] = [p["code"].lower() for p in perms]
        print("Loaded permissions:", session["permissions"])

    def has_permission(code):
        return code.lower() in session.get("permissions", [])

    # -------------------------
    # 1. GREETINGS / MAIN MENU
    # -------------------------
    if any(word in user_message for word in ["hi", "hello", "hey", "main menu", "back to main menu"]):
        reply = "Main Menu — What would you like to access?"
        options = [
            "Sales", "Products", "Clients", "Stores",
            "Stock In", "Transfers", "Movements",
            "Tasks", "Lay-buys", "Credits"
        ]
        session["last_topic"] = "main_menu"

    # -------------------------
    # 2. SALES
    # -------------------------
    elif "sales" in user_message:
        if not has_permission("view_sales"):
            reply = "You don't have permission to view sales information."
        else:
            reply = "Sales module accessed. What would you like to view?"
            options = ["Today's Summary", "Recent Transactions", "Back to Main Menu"]
            session["last_topic"] = "sales"
    
    elif ("today" in user_message or "today's summary" in user_message) and last_topic == "sales":
        if not has_permission("view_sales"):
            reply = "You don't have permission to view sales information."
        else:
            result = bot_safe_query(
                "sales",
                """
                SELECT 
                    COUNT(id) AS total_invoices,
                    COALESCE(SUM(subtotal), 0) AS total_subtotal,
                    COALESCE(SUM(vat), 0) AS total_vat,
                    COALESCE(SUM(total), 0) AS total_sales
                FROM sales
                WHERE DATE(created_at) = CURDATE()
                """
            )
            if isinstance(result, str):
                reply = result
            else:
                s = result[0]
                reply = (
                    f"Today's Sales Summary:<br>"
                    f"Invoices: {s['total_invoices']}<br>"
                    f"Subtotal: R{(s['total_subtotal'] or 0):.2f}<br>"
                    f"VAT: R{(s['total_vat'] or 0):.2f}<br>"
                    f"Total Sales: R{(s['total_sales'] or 0):.2f}"
                )
            options = ["Recent Transactions", "Back to Main Menu"]
            session["last_topic"] = "sales_today"
    
    elif (
        (
            "recent" in user_message or
            "recent transactions" in user_message or
            "show recent" in user_message or
            "view recent" in user_message or
            "last 10" in user_message or
            "last ten" in user_message or
            "view last" in user_message or
            "show last" in user_message or
            "latest sales" in user_message or
            "latest transactions" in user_message or
            "view last 10 invoices" in user_message or
            "show last 10 invoices" in user_message or
            "transactions" in user_message or
            "sales history" in user_message or
            "past sales" in user_message
        )
        and last_topic == "sales"
    ):
        if not has_permission("view_sales"):
            reply = "You don't have permission to view sales information."
        else:
            result = bot_safe_query(
                "sales",
                """
                SELECT invoice_no, total, vat, created_at
                FROM sales
                ORDER BY created_at DESC
                LIMIT 10
                """
            )
            if isinstance(result, str):
                reply = result
            else:
                if not result:
                    reply = "No recent transactions found."
                else:
                    reply = "<br>".join([
                        f"Invoice {r['invoice_no']} — Total: R{(r['total'] or 0):.2f} "
                        f"(VAT: R{(r['vat'] or 0):.2f}) — {r['created_at']}"
                        for r in result
                    ])
            options = ["Today's Summary", "Back to Main Menu"]
            session["last_topic"] = "sales_recent"


    # -------------------------
    # 3. PRODUCTS
    # -------------------------
    elif "product" in user_message or "products" in user_message:
    
        if not has_permission("view_products"):
            reply = "You don't have permission to view product information."
    
        else:
            # ⭐ DIRECT: "list products"
            if "list" in user_message:
                result = bot_safe_query("products", "SELECT id, name, retail_price FROM rella.products LIMIT 10")
                if isinstance(result, str):
                    reply = result
                else:
                    reply = "<br>".join([
                        f"{r['id']}. {r['name']} — R{r['retail_price']:.2f}"
                        for r in result
                    ])
                options = ["Search Product by Name", "Search Product by Barcode", "Back to Main Menu"]
                session["last_topic"] = "products_list"
    
            # ⭐ DIRECT: "search product by name"
            elif "search" in user_message and "name" in user_message:
                reply = "Please enter the product name you want to search."
                options = ["Back to Main Menu"]
                session["last_topic"] = "product_search_name"
    
            # ⭐ DIRECT: "search product by barcode"
            elif "search" in user_message and "barcode" in user_message:
                reply = "Please enter the product barcode you want to search."
                options = ["Back to Main Menu"]
                session["last_topic"] = "product_search_barcode"
    
            # ⭐ SEARCH BY NAME (text input)
            elif last_topic in ["product_search_name", "products"]:
                pname = user_message.strip()
                if pname:
                    result = bot_safe_query(
                        "products",
                        f"SELECT id, name, retail_price FROM rella.products WHERE name LIKE '%{pname}%'"
                    )
                    if isinstance(result, str) or not result:
                        reply = f"No product found matching '{pname}'."
                    else:
                        reply = "<br>".join([
                            f"{r['id']}. {r['name']} — R{r['retail_price']:.2f}"
                            for r in result
                        ])
                    options = ["List Products", "Search Product by Barcode", "Back to Main Menu"]
                    session["last_topic"] = "products"
                else:
                    reply = "Please enter a valid product name."
                    options = ["Back to Main Menu"]
                    session["last_topic"] = "product_search_name"
    
            # ⭐ SEARCH BY BARCODE (numeric input)
            elif last_topic == "product_search_barcode":
                barcode = user_message.strip()
                if barcode:
                    result = bot_safe_query(
                        "products",
                        f"SELECT id, name, retail_price FROM rella.products WHERE barcode LIKE '%{barcode}%'"
                    )
                    if isinstance(result, str) or not result:
                        reply = f"No product found with barcode '{barcode}'."
                    else:
                        reply = "<br>".join([
                            f"{r['id']}. {r['name']} — R{r['retail_price']:.2f}"
                            for r in result
                        ])
                    options = ["List Products", "Search Product by Name", "Back to Main Menu"]
                    session["last_topic"] = "products"
                else:
                    reply = "Please enter a valid barcode."
                    options = ["Back to Main Menu"]
                    session["last_topic"] = "product_search_barcode"
    
            # ⭐ DEFAULT ENTRY
            else:
                reply = "Products module accessed. What would you like to do?"
                options = ["List Products", "Search Product by Name", "Search Product by Barcode", "Back to Main Menu"]
                session["last_topic"] = "products"




    # -------------------------
    # 4. CLIENTS
    # -------------------------
    elif "client" in user_message or "clients" in user_message:
        if not has_permission("view_clients"):
            reply = "You don't have permission to view client information."
        else:
            reply = "Clients module accessed. What would you like to do?"
            options = ["List Clients", "Search Client by ID", "Back to Main Menu"]
            session["last_topic"] = "clients"

    elif "list" in user_message and last_topic == "clients":
        if not has_permission("view_clients"):
            reply = "You don't have permission to view client information."
        else:
            result = bot_safe_query("clients", "SELECT id, name, phone FROM clients LIMIT 10")
            if isinstance(result, str):
                reply = result
            else:
                reply = "<br>".join([f"{r['id']}. {r['name']} — {r['phone']}" for r in result])
            options = ["Search Client by ID", "Back to Main Menu"]
            session["last_topic"] = "clients_list"

    # -------------------------
    # 5. STORES
    # -------------------------
    elif "store" in user_message or "stores" in user_message:
        if not has_permission("view_stores"):
            reply = "You don't have permission to view store information."
        else:
            result = bot_safe_query("stores", "SELECT COUNT(id) AS total_stores FROM stores")
            if isinstance(result, str):
                reply = result
            else:
                reply = f"You have {result[0]['total_stores']} store(s) registered."
            options = ["Check Stock Levels", "Back to Main Menu"]
            session["last_topic"] = "stores"

    # -------------------------
    # 5B. STOCK LEVELS (CORRECTED)
    # -------------------------
    elif (
        ("stock" in user_message or "check stock" in user_message or "stock levels" in user_message)
        and last_topic == "stores"
    ):
        if not has_permission("view_stock"):
            reply = "You don't have permission to view stock information."
        else:
            result = bot_safe_query(
                "stock",
                """
                SELECT p.name, ss.quantity, s.name AS store_name
                FROM products p
                JOIN store_stock ss ON ss.product_id = p.id
                JOIN stores s ON s.id = ss.store_id
                ORDER BY ss.quantity ASC
                LIMIT 10
                """
            )

            if isinstance(result, str):
                reply = result
            else:
                reply = "<br>".join([
                    f"{r['store_name']}: {r['name']} — Qty: {r['quantity']}"
                    for r in result
                ])

            options = ["Suggest Restock", "Back to Main Menu"]
            session["last_topic"] = "stock_levels"

    # -------------------------
    # 5C. SUGGEST RESTOCK (CORRECTED)
    # -------------------------
    elif "suggest" in user_message and last_topic == "stock_levels":
        if not has_permission("view_stock"):
            reply = "You don't have permission to view stock information."
        else:
            result = bot_safe_query(
                "stock",
                """
                SELECT p.name, ss.quantity, s.name AS store_name
                FROM products p
                JOIN store_stock ss ON ss.product_id = p.id
                JOIN stores s ON s.id = ss.store_id
                WHERE ss.quantity < 5
                ORDER BY ss.quantity ASC
                LIMIT 10
                """
            )

            if isinstance(result, str):
                reply = result
            else:
                reply = "<br>".join([
                    f"{r['store_name']}: {r['name']} — Qty: {r['quantity']} (Low stock!)"
                    for r in result
                ])

            options = ["Back to Main Menu"]
            session["last_topic"] = "stock_suggestions"

    # -------------------------
    # 6. STOCK IN
    # -------------------------
    elif "stock in" in user_message or "received" in user_message:
        if not has_permission("view_stock_in"):
            reply = "You don't have permission to view stock-in information."
        else:
            result = bot_safe_query(
                "movements",
                """
                SELECT 
                    SUM(CASE WHEN movement_type='stock_in' THEN 1 ELSE 0 END) AS received,
                    SUM(CASE WHEN movement_type='return' THEN 1 ELSE 0 END) AS returned,
                    SUM(CASE WHEN movement_type='adjustment' THEN 1 ELSE 0 END) AS adjusted
                FROM rella.movements
                WHERE DATE(created_at) = CURDATE()
                """
            )
    
            if isinstance(result, str) or not result:
                reply = "No stock-in records found for today."
            else:
                r = result[0]
                reply = (
                    f"Today: Received {r['received']}, "
                    f"Returned {r['returned']}, "
                    f"Adjusted {r['adjusted']}."
                )
    
            options = ["Back to Main Menu"]
            session["last_topic"] = "stock_in"


    # -------------------------
    # 7. TRANSFERS
    # -------------------------
    elif "transfer" in user_message or "transfers" in user_message:
    
        # Permission check (same pattern as Products)
        if not has_permission("view_transfers"):
            reply = "You don't have permission to view transfer information."
    
        else:
    
            # ⭐ DIRECT: "today transfers"
            if "today" in user_message or "summary" in user_message:
    
                # 1) Daily totals
                totals = bot_safe_query(
                    "movements",
                    """
                    SELECT 
                        COUNT(id) AS total_transfers,
                        COALESCE(SUM(qty), 0) AS total_qty
                    FROM rella.movements
                    WHERE movement_type = 'transfer'
                      AND DATE(created_at) = CURDATE()
                    """
                )
    
                # 2) Store-to-store breakdown
                breakdown = bot_safe_query(
                    "movements",
                    """
                    SELECT 
                        from_store,
                        to_store,
                        COALESCE(SUM(qty), 0) AS total_qty
                    FROM rella.movements
                    WHERE movement_type = 'transfer'
                      AND DATE(created_at) = CURDATE()
                    GROUP BY from_store, to_store
                    ORDER BY from_store, to_store
                    """
                )
    
                # Build reply
                if isinstance(totals, str) or not totals:
                    reply = "No transfers recorded today."
                else:
                    t = totals[0]
                    total_transfers = int(t.get("total_transfers", 0))
                    total_qty = int(t.get("total_qty", 0))
    
                    if total_transfers == 0:
                        reply = "No transfers recorded today."
                    elif total_transfers == 1:
                        reply = f"Today: 1 transfer recorded with {total_qty} item(s) moved."
                    else:
                        reply = (
                            f"Today: {total_transfers} transfers recorded "
                            f"with a total of {total_qty} item(s) moved."
                        )
    
                # Breakdown section
                if isinstance(breakdown, list) and breakdown:
                    reply += "\n\nTransfer Breakdown:\n"
                    for row in breakdown:
                        fs = row.get("from_store", "Unknown")
                        ts = row.get("to_store", "Unknown")
                        qty = int(row.get("total_qty", 0))
                        reply += f"- {fs} → {ts}: {qty} item(s)\n"
                else:
                    reply += "\n\nNo store-to-store transfer breakdown available today."
    
                options = ["Back to Main Menu"]
                session["last_topic"] = "transfer_summary"
    
            # ⭐ DEFAULT ENTRY (same pattern as Products)
            else:
                reply = "Transfers module accessed. What would you like to do?"
                options = ["Today's Transfers Summary", "Back to Main Menu"]
                session["last_topic"] = "transfer"





    # -------------------------
    # 8. MOVEMENTS
    # -------------------------
    elif "movement" in user_message or "movements" in user_message:
        if not has_permission("view_movements"):
            reply = "You don't have permission to view movement information."
        else:
            reply = "Movements module accessed. What would you like to view?"
            options = ["Today's Summary", "Recent Movements", "Back to Main Menu"]
            session["last_topic"] = "movements"
    
    elif ("today" in user_message or "summary" in user_message) and last_topic == "movements":
        if not has_permission("view_movements"):
            reply = "You don't have permission to view movement information."
        else:
            result = bot_safe_query(
                "stock_movements",
                """
                SELECT 
                    SUM(CASE WHEN type='transfer' THEN 1 ELSE 0 END) AS transfers,
                    SUM(CASE WHEN type='sale' THEN 1 ELSE 0 END) AS sales,
                    SUM(CASE WHEN type='stock_in' THEN 1 ELSE 0 END) AS stock_in,
                    SUM(CASE WHEN type='remove' THEN 1 ELSE 0 END) AS removed,
                    SUM(CASE WHEN type='adjustment' THEN 1 ELSE 0 END) AS adjusted
                FROM stock_movements
                WHERE DATE(created_at)=CURDATE()
                """
            )
    
            if isinstance(result, str):
                reply = result
            else:
                m = result[0]
                reply = (
                    f"Today's Movements Summary:<br>"
                    f"Transfers: {m['transfers']}<br>"
                    f"Sales: {m['sales']}<br>"
                    f"Stock In: {m['stock_in']}<br>"
                    f"Removed: {m['removed']}<br>"
                    f"Adjusted: {m['adjusted']}"
                )
    
            options = ["Recent Movements", "Back to Main Menu"]
            session["last_topic"] = "movements_today"
    
    elif ("recent" in user_message or "movement" in user_message or "movements" in user_message) and last_topic == "movements":
        if not has_permission("view_movements"):
            reply = "You don't have permission to view movement information."
        else:
            result = bot_safe_query(
                "stock_movements",
                """
                SELECT type, reference_no, created_at
                FROM stock_movements
                ORDER BY created_at DESC
                LIMIT 10
                """
            )
    
            if isinstance(result, str):
                reply = result
            else:
                reply = "<br>".join([
                    f"{r['type'].capitalize()} — Ref: {r['reference_no']} — {r['created_at']}"
                    for r in result
                ])
    
            options = ["Today's Summary", "Back to Main Menu"]
            session["last_topic"] = "movements_recent"
            
#CREDITS
    elif "credit" in user_message or "credits" in user_message:
        if not has_permission("view_credits"):
            reply = "You don't have permission to view credit information."
        else:
            reply = "Credits module accessed. What would you like to view?"
            options = ["Today's Summary", "Recent Credits", "Back to Main Menu"]
            session["last_topic"] = "credits"
    
    elif ("today" in user_message or "summary" in user_message) and last_topic == "credits":
        if not has_permission("view_credits"):
            reply = "You don't have permission to view credit information."
        else:
            result = bot_safe_query(
                "credits",
                """
                SELECT COUNT(id) AS total_credits,
                       SUM(amount) AS total_amount,
                       SUM(balance) AS total_balance
                FROM credits
                WHERE DATE(created_at) = CURDATE()
                """
            )
    
            if isinstance(result, str):
                reply = result
            else:
                c = result[0]
                reply = (
                    f"Today's Credit Summary:<br>"
                    f"Total Credits: {c['total_credits']}<br>"
                    f"Total Amount: R{c['total_amount']:.2f}<br>"
                    f"Outstanding Balance: R{c['total_balance']:.2f}"
                )
    
            options = ["Recent Credits", "Back to Main Menu"]
            session["last_topic"] = "credits_today"
    
    elif ("recent" in user_message) and last_topic == "credits":
        if not has_permission("view_credits"):
            reply = "You don't have permission to view credit information."
        else:
            result = bot_safe_query(
                "credits",
                """
                SELECT reference_no, client_name, amount, balance, created_at
                FROM credits
                ORDER BY created_at DESC
                LIMIT 10
                """
            )
    
            if isinstance(result, str):
                reply = result
            else:
                reply = "<br>".join([
                    f"Ref {r['reference_no']} — {r['client_name']} — Amount: R{r['amount']:.2f} — "
                    f"Balance: R{r['balance']:.2f} — {r['created_at']}"
                    for r in result
                ])
    
            options = ["Today's Summary", "Back to Main Menu"]
            session["last_topic"] = "credits_recent"
               


    # -------------------------
    # DEFAULT FALLBACK
    # -------------------------
    if reply is None:
        reply = "I'm not sure I understood that. Try selecting an option."
        options = [
            "Sales", "Products", "Clients", "Stores",
            "Stock In", "Transfers", "Movements",
            "Tasks", "Lay-buys", "Credits"
        ]

    print("REPLY:", reply)
    return jsonify({"reply": reply, "options": options})








def bot_safe_query(section, sql, params=()):
    user_id = session.get("user_id")
    if not user_id:
        return "You are not logged in."

    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT LOWER(p.code) AS code
        FROM rella.user_permissions up
        JOIN rella.permissions p ON up.permission_id = p.id
        WHERE up.user_id = %s
    """, (user_id,))
    permissions = [r["code"] for r in cursor.fetchall()]

    required = f"view_{section.lower()}"
    if required not in permissions:
        cursor.close()
        db.close()
        return "You do not have permission to access this information."

    cursor.execute(sql, params)
    result = cursor.fetchall()
    cursor.close()
    db.close()

    return result if result else "No results found."







def safe_query(user, section, sql, params=()):
    if section not in user["permissions"]:
        return "You do not have access to this data."

    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(sql, params)
    return cursor.fetchall()




# --- Run ---


if __name__ == "__main__":
    
    app.run(host="0.0.0.0", port=5000, debug=True)