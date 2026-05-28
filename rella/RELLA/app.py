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

    # Load sale header
    sale = query_one("""
        SELECT 
            s.*, 
            c.name AS client_name, 
            u.username AS user_name
        FROM sales s
        LEFT JOIN clients c ON s.client_id = c.id
        LEFT JOIN users u ON s.created_by = u.id
        WHERE s.id=%s
    """, (sale_id,))

    # Detect REAL column names in sale_items
    cols = query_all("SHOW COLUMNS FROM sale_items")
    colnames = [c["Field"] for c in cols]

    # Detect sale_id column
    sale_id_col = next(c for c in colnames if "sale" in c.replace(" ", "").lower())

    # Detect product_id column
    product_id_col = next(c for c in colnames if "product" in c.replace(" ", "").lower())

    # Detect quantity column
    qty_col = next(c for c in colnames if "quantity" in c.replace(" ", "").lower())

    # Detect unit price column
    unit_price_col = next(
        c for c in colnames 
        if "unit" in c.replace(" ", "").lower() and "price" in c.replace(" ", "").lower()
    )

    # Detect total price column
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

        # Fetch product name
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

    # Convert dict to list
    items = list(grouped.values())

    return render_template("invoice.html", sale=sale, items=items, user=user)



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
            s.invoice_no
        FROM movements m
        LEFT JOIN products p ON m.product_id = p.id
        LEFT JOIN users u ON m.created_by = u.id
        LEFT JOIN sales s ON m.invoice_id = s.id
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
            r['from_store'],
            r['to_store'],
            r['invoice_no'] if r['invoice_no'] else ''
        ])

    log_action(user['id'], 'export_movements_csv', 'Exported movements CSV')

    # ⭐ Timestamp filename
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
    
        # PRODUCTS
        cursor.execute("""
            SELECT name, price
            FROM products
        """)
        rows = cursor.fetchall() or []
        products_labels = [r["name"] for r in rows] or ["No products"]
        products_data = [float(r["price"] or 0) for r in rows] or [0]
    
        # CLIENTS
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
    
        # SALES RECORDS
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
    
        # STORES STOCK LEVELS
        cursor.execute("""
            SELECT s.name AS store_name, SUM(ss.quantity) AS total_stock
            FROM store_stock ss
            JOIN stores s ON s.id = ss.store_id
            GROUP BY s.name
        """)
        rows = cursor.fetchall() or []
        stores_labels = [r["store_name"] for r in rows] or ["No Stores"]
        stores_data = [float(r["total_stock"] or 0) for r in rows] or [0.01]
    
        # FINANCES SUMMARY
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
    
        if income == 0 and expenses == 0 and stock_cost == 0:
            finances_data = [0.01, 0.01, 0.01]
        else:
            finances_data = [income, expenses, stock_cost]
    
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
            finances_data=finances_data
        )



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

    # 0️⃣ Generate invoice number (timestamp)
    invoice_no = "INV" + datetime.now().strftime("%Y%m%d%H%M%S")

    # 1️⃣ Calculate subtotal + VAT
    subtotal = round(grand_total / 1.15, 2)
    vat = round(grand_total - subtotal, 2)

    # 2️⃣ Insert sale header
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

    sale_id = cursor.lastrowid   # ⭐ THIS IS THE REAL INVOICE ID

    # 3️⃣ Insert sale items + stock + movements
    for product_id, qty, price, line_total in zip(cart_product_ids, cart_quantities, cart_prices, cart_totals):
        qty = int(qty)

        # 3.1 Sale item
        cursor.execute("""
            INSERT INTO sale_items
            (sale_id, product_id, quantity, unit_price, total_price)
            VALUES (%s, %s, %s, %s, %s)
        """, (sale_id, product_id, qty, price, line_total))

        # 3.2 Update stock
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

        # 3.3 Movement log (⭐ now includes invoice_id)
        cursor.execute("""
            INSERT INTO movements
            (product_id, movement_type, qty, from_store, created_by, invoice_id)
            VALUES (%s, 'sale', %s, %s, %s, %s)
        """, (product_id, qty, store_id, user['id'], sale_id))

    db.commit()
    cursor.close()

    flash("Sale completed successfully!", "success")
    return redirect(url_for('pos_page'))









from datetime import datetime

from datetime import datetime

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

    # Insert sale header
    sale_id = execute("""
        INSERT INTO sales (client_id, store_id, subtotal, vat, total, created_by)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (client_id, store_id, subtotal, vat, total, user["id"]))

    # Timestamp invoice number
    invoice_no = "INV" + datetime.now().strftime("%Y%m%d%H%M%S")
    execute("UPDATE sales SET invoice_no=%s WHERE id=%s", (invoice_no, sale_id))

    # Insert sale items
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

    # ⭐ INSERT MOVEMENT RECORDS (this was missing)
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
    if request.method == 'POST':
        name = request.form.get('name')
        execute("INSERT INTO stores (name,created_by) VALUES (%s,%s)", (name,user['id']))
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

                # SAVE AS 'adjustment' (we will display it as 'Removed')
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
            s.invoice_no
        FROM movements m
        LEFT JOIN products p ON m.product_id = p.id
        LEFT JOIN users u ON m.created_by = u.id
        LEFT JOIN sales s ON m.invoice_id = s.id
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

    # newest first
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


@app.route("/admin/leave/category/delete/<int:category_id>", methods=["POST"])
@login_required
def admin_leave_category_delete(category_id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("DELETE FROM leave_categories WHERE id=%s", (category_id,))
    db.commit()

    flash("Leave category deleted successfully.", "success")
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

        # NEW: Task number = timestamp (no spaces, no special characters)
        from datetime import datetime
        task_no = datetime.now().strftime("%Y%m%d%H%M%S")   # Example: 20260513161522

        execute("""
            INSERT INTO tasks (task_no, title, description, assigned_to, priority, status)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (task_no, title, desc, assigned_to, priority, status))

        log_action(user['id'], 'create_task', f'Created task {task_no}')
        flash('Task created', 'success')
        return redirect(url_for('tasks'))

    # SEARCH MODE
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
            # Check foreign key dependencies
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

    # Load all user-permission mappings
    user_perms = query_all("""
        SELECT user_id, permission_id
        FROM user_permissions
    """)

    # Build perm_map = { user_id: {permission_id, ...}, ... }
    perm_map = {}
    for p in user_perms:
        perm_map.setdefault(p['user_id'], set()).add(p['permission_id'])

    # Render page
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



# --- Download financial file ---



# --- Run ---


if __name__ == "__main__":
    
    app.run(host="0.0.0.0", port=5000, debug=True)