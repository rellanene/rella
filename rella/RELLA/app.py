# app.py
import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import mysql.connector
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import random
import string
from flask import Response, send_file
import csv
import pdfkit




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
    conn = mysql.connector.connect(**DB_CONFIG)
    return conn

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
        # staff must be approved before login
        is_approved = 1 if role == 'admin' else 0
        user_id = execute("""INSERT INTO users
            (username,email,password_hash,role,business_id,is_approved,q1,a1,q2,a2,q3,a3,created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (username,email,pw_hash,role,business_id,is_approved,q1,a1,q2,a2,q3,a3,None))
        # if admin, grant all permissions (application logic: insert all permission rows)
        if role == 'admin':
            perms = query_all("SELECT id FROM permissions")
            for p in perms:
                execute("INSERT INTO user_permissions (user_id,permission_id,granted_by) VALUES (%s,%s,%s)", (user_id,p['id'],user_id))
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
    sql = "SELECT s.invoice_no, c.name as client_name, s.total, s.created_at, u.username as user_name FROM sales s LEFT JOIN clients c ON s.client_id=c.id LEFT JOIN users u ON s.created_by=u.id WHERE 1=1"
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
    rows = query_all(sql, params)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Invoice', 'Client', 'Total', 'Date & Time', 'User'])
    for r in rows:
        writer.writerow([r['invoice_no'], r['client_name'], r['total'], r['created_at'], r['user_name']])

    log_action(user['id'], 'export_records_csv', 'Exported records CSV')
    resp = Response(output.getvalue(), mimetype='text/csv')
    resp.headers['Content-Disposition'] = 'attachment; filename=records.csv'
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



@app.route('/movements/export')
@require_login
def export_movements_csv():
    user = current_user()
    q = request.args.get('q','')
    start = request.args.get('start')
    end = request.args.get('end')
    sql = """SELECT m.created_at, u.username as user_name, p.name as product_name,
             m.movement_type, m.qty, m.from_store, m.to_store, m.invoice_id
             FROM movements m
             LEFT JOIN users u ON m.created_by=u.id
             LEFT JOIN products p ON m.product_id=p.id
             WHERE 1=1"""
    params = []
    if q:
        sql += " AND (m.invoice_id LIKE %s OR p.name LIKE %s)"
        params.extend((f'%{q}%', f'%{q}%'))
    if start:
        sql += " AND m.created_at >= %s"
        params.append(start)
    if end:
        sql += " AND m.created_at <= %s"
        params.append(end)
    rows = query_all(sql, params)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date & Time','User','Product','Type','Quantity','From','To','Invoice'])
    for r in rows:
        writer.writerow([r['created_at'], r['user_name'], r['product_name'], r['movement_type'],
                         r['qty'], r['from_store'], r['to_store'], r['invoice_id']])

    log_action(user['id'], 'export_movements_csv', 'Exported movements CSV')
    resp = Response(output.getvalue(), mimetype='text/csv')
    resp.headers['Content-Disposition'] = 'attachment; filename=movements.csv'
    return resp



# --- Dashboard ---
@app.route('/')
@app.route('/dashboard')
@require_login
def dashboard():
    user = current_user()
    # sample stats
    total_products = query_one("SELECT COUNT(*) as c FROM products")['c']
    total_clients = query_one("SELECT COUNT(*) as c FROM clients")['c']
    total_sales = query_one("SELECT COUNT(*) as c FROM sales")['c']
    return render_template('dashboard.html', user=user, total_products=total_products,
                           total_clients=total_clients, total_sales=total_sales)

# --- Products ---
@app.route('/products', methods=['GET','POST'])
@require_login
def products():
    user = current_user()
    if request.method == 'POST':
        # add product
        barcode = request.form.get('barcode')
        name = request.form.get('name')
        wholesale = request.form.get('wholesale') or 0
        retail = request.form.get('retail') or 0
        pid = execute("INSERT INTO products (barcode,name,wholesale_price,retail_price,created_by) VALUES (%s,%s,%s,%s,%s)",
                      (barcode,name,wholesale,retail,user['id']))
        log_action(user['id'], 'add_product', f'Added product {name} ({barcode})')
        flash('Product added', 'success')
        return redirect(url_for('products'))
    q = request.args.get('q','')
    if q:
        rows = query_all("SELECT p.*, IFNULL(SUM(s.quantity),0) as total_qty FROM products p LEFT JOIN store_stock s ON p.id=s.product_id WHERE p.name LIKE %s OR p.barcode LIKE %s GROUP BY p.id", (f'%{q}%', f'%{q}%'))
    else:
        rows = query_all("SELECT p.*, IFNULL(SUM(s.quantity),0) as total_qty FROM products p LEFT JOIN store_stock s ON p.id=s.product_id GROUP BY p.id")
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

    execute("DELETE FROM products WHERE id=%s", (pid,))
    log_action(user['id'], 'delete_product', f'Deleted product {pid}')

    flash('Product deleted successfully', 'success')
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
    products = query_all("SELECT * FROM products")
    stores = query_all("SELECT * FROM stores")
    return render_template('pos.html', products=products, stores=stores, user=user)

# --- Records ---
@app.route('/records')
@require_login
def records():
    user = current_user()
    q = request.args.get('q','')
    start = request.args.get('start')
    end = request.args.get('end')

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

    if q:
        sql += " AND s.invoice_no LIKE %s"
        params.append(f'%{q}%')

    if start:
        sql += " AND DATE(s.created_at) >= %s"
        params.append(start)

    if end:
        sql += " AND DATE(s.created_at) <= %s"
        params.append(end)

    sql += " ORDER BY s.created_at DESC"

    rows = query_all(sql, params)

    return render_template('records.html', records=rows, user=user)


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

    # ⭐ Generate invoice number
    invoice_no = f"INV-{sale_id:06d}"
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
@app.route('/stock-in', methods=['GET','POST'])
@require_login
def stock_in():
    user = current_user()
    products = query_all("SELECT * FROM products")
    stores = query_all("SELECT * FROM stores")
    if request.method == 'POST':
        product_id = request.form.get('product_id')
        store_id = request.form.get('store_id')
        qty = int(request.form.get('qty',0))
        # upsert store_stock
        existing = query_one("SELECT id FROM store_stock WHERE product_id=%s AND store_id=%s", (product_id, store_id))
        if existing:
            execute("UPDATE store_stock SET quantity = quantity + %s, updated_by=%s WHERE id=%s", (qty, user['id'], existing['id']))
        else:
            execute("INSERT INTO store_stock (store_id,product_id,quantity,updated_by) VALUES (%s,%s,%s,%s)", (store_id,product_id,qty,user['id']))
        execute("INSERT INTO movements (product_id,movement_type,qty,from_store,to_store,created_by) VALUES (%s,%s,%s,%s,%s,%s)", (product_id,'stock_in',qty,None,store_id,user['id']))
        log_action(user['id'], 'stock_in', f'Stock in product {product_id} qty {qty} to store {store_id}')
        flash('Stock received', 'success')
        return redirect(url_for('stock_in'))
    return render_template('stock_in.html', products=products, stores=stores, user=user)

# --- Transfer ---
@app.route('/transfer', methods=['GET','POST'])
@require_login
def transfer():
    user = current_user()
    products = query_all("SELECT * FROM products")
    stores = query_all("SELECT * FROM stores")
    if request.method == 'POST':
        product_id = request.form.get('product_id')
        from_store = request.form.get('from_store')
        to_store = request.form.get('to_store')
        qty = int(request.form.get('qty',0))
        # decrement from_store
        execute("UPDATE store_stock SET quantity = quantity - %s, updated_by=%s WHERE product_id=%s AND store_id=%s", (qty,user['id'],product_id,from_store))
        # increment to_store
        existing = query_one("SELECT id FROM store_stock WHERE product_id=%s AND store_id=%s", (product_id, to_store))
        if existing:
            execute("UPDATE store_stock SET quantity = quantity + %s, updated_by=%s WHERE id=%s", (qty,user['id'],existing['id']))
        else:
            execute("INSERT INTO store_stock (store_id,product_id,quantity,updated_by) VALUES (%s,%s,%s,%s)", (to_store,product_id,qty,user['id']))
        execute("INSERT INTO movements (product_id,movement_type,qty,from_store,to_store,created_by) VALUES (%s,%s,%s,%s,%s,%s)", (product_id,'transfer',qty,from_store,to_store,user['id']))
        log_action(user['id'], 'transfer', f'Transferred product {product_id} qty {qty} from {from_store} to {to_store}')
        flash('Transfer completed', 'success')
        return redirect(url_for('transfer'))
    return render_template('transfer.html', products=products, stores=stores, user=user)

# --- Movements ---
@app.route('/movements')
@require_login
def movements():
    user = current_user()
    q = request.args.get('q','')
    start = request.args.get('start')
    end = request.args.get('end')
    sql = "SELECT m.*, p.name as product_name, u.username as user_name FROM movements m LEFT JOIN products p ON m.product_id=p.id LEFT JOIN users u ON m.created_by=u.id WHERE 1=1"
    params = []
    if q:
        sql += " AND (m.invoice_id LIKE %s OR p.name LIKE %s)"
        params.extend((f'%{q}%', f'%{q}%'))
    if start:
        sql += " AND m.created_at >= %s"
        params.append(start)
    if end:
        sql += " AND m.created_at <= %s"
        params.append(end)
    rows = query_all(sql, params)
    return render_template('movements.html', movements=rows, user=user)

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
        task_no = generate_task_no()

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




    return render_template('tasks.html', tasks=rows, users=users, user=user)
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
@app.route('/permissions', methods=['GET','POST'])
@require_login
def permissions_page():
    user = current_user()
    if user['role'] != 'admin':
        flash('Only admins can access permissions', 'error')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'approve_user':
            uid = request.form.get('user_id')
            execute("UPDATE users SET is_approved=1 WHERE id=%s", (uid,))
            log_action(user['id'], 'approve_user', f'Approved user {uid}')
            flash('User approved', 'success')
        elif action == 'grant_perm':
            uid = request.form.get('user_id')
            perm_code = request.form.get('perm_code')
            perm = query_one("SELECT id FROM permissions WHERE code=%s", (perm_code,))
            if perm:
                execute("INSERT INTO user_permissions (user_id,permission_id,granted_by) VALUES (%s,%s,%s)", (uid,perm['id'],user['id']))
                log_action(user['id'], 'grant_permission', f'Granted {perm_code} to {uid}')
                flash('Permission granted', 'success')
        elif action == 'suspend_user':
            uid = request.form.get('user_id')
            execute("UPDATE users SET is_active=0 WHERE id=%s", (uid,))
            log_action(user['id'], 'suspend_user', f'Suspended user {uid}')
            flash('User suspended', 'success')
        elif action == 'activate_user':
            uid = request.form.get('user_id')
            execute("UPDATE users SET is_active=1 WHERE id=%s", (uid,))
            log_action(user['id'], 'activate_user', f'Activated user {uid}')
            flash('User activated', 'success')
        elif action == 'delete_user':
            uid = request.form.get('user_id')
            execute("DELETE FROM users WHERE id=%s", (uid,))
            log_action(user['id'], 'delete_user', f'Deleted user {uid}')
            flash('User deleted', 'success')
        return redirect(url_for('permissions_page'))
    users = query_all("SELECT * FROM users")
    perms = query_all("SELECT * FROM permissions")
    return render_template('permissions.html', users=users, perms=perms, user=user)

# --- Placeholder pages for HR, Comms, Finances, etc. ---
@app.route('/human')
@require_login
def human():
    user = current_user()
    return render_template('human.html', user=user)

@app.route('/comms')
@require_login
def comms():
    user = current_user()
    return render_template('comms.html', user=user)

@app.route('/finances')
@require_login
def finances():
    user = current_user()
    return render_template('finances.html', user=user)

# --- Run ---
if __name__ == '__main__':
    app.run(debug=True)
