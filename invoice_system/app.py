from flask import Flask, render_template, request, redirect, flash, send_file, url_for
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, io, csv
from models import init_db, get_db

app = Flask(__name__)
app.secret_key = "secure_secret_key"

ADMIN_EMAIL = "satsemender@gmail.com"

# --------- Login Manager ---------
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

# --------- User Class ---------
class User(UserMixin):
    def __init__(self, id, full_name, email, password):
        self.id = id
        self.full_name = full_name
        self.email = email
        self.password = password

    @property
    def is_admin(self):
        return self.email == ADMIN_EMAIL

@login_manager.user_loader
def load_user(user_id):
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM users WHERE id=?", (user_id,))
    u = cur.fetchone()
    con.close()
    return User(*u) if u else None

# --------- Routes ---------
@app.route("/", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email = request.form["email"]
        password = request.form["password"]
        con = get_db()
        cur = con.cursor()
        cur.execute("SELECT * FROM users WHERE email=?", (email,))
        u = cur.fetchone()
        con.close()
        if not u:
            flash("Account not found. Please register.")
            return redirect("/register")
        if not check_password_hash(u["password"], password):
            flash("Incorrect password")
            return redirect("/")
        login_user(User(*u))
        return redirect("/admin" if email==ADMIN_EMAIL else "/dashboard")
    return render_template("login.html", admin_email=ADMIN_EMAIL)

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        try:
            full_name = request.form["full_name"]
            email = request.form["email"]
            password = generate_password_hash(request.form["password"])
            con = get_db()
            cur = con.cursor()
            cur.execute("INSERT INTO users(full_name,email,password) VALUES(?,?,?)",
                        (full_name,email,password))
            con.commit()
            con.close()
            flash("Account created successfully")
            return redirect("/")
        except sqlite3.IntegrityError:
            flash("Email already exists")
    return render_template("register.html")

# --------- Dashboard ---------
@app.route("/dashboard")
@login_required
def dashboard():
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM invoices WHERE user_id=?",(current_user.id,))
    invoices = cur.fetchall()
    con.close()
    return render_template("dashboard.html", invoices=invoices, user=current_user)

# --------- Create Invoice ---------
@app.route("/invoice/create", methods=["GET","POST"])
@login_required
def create_invoice():
    if request.method=="POST":
        customer_name = request.form["customer_name"]
        customer_address = request.form["customer_address"]
        phone = request.form["phone"]
        ntn = request.form.get("ntn","")
        gst = request.form.get("gst","")
        invoice_no = request.form["invoice_no"]
        date = request.form["date"]
        po_number = request.form.get("po_number","")
        products = request.form.getlist("product_name[]")
        qtys = request.form.getlist("qty[]")
        unit_costs = request.form.getlist("unit_cost[]")

        total = sum([int(qtys[i])*float(unit_costs[i]) for i in range(len(products))])

        con = get_db()
        cur = con.cursor()
        cur.execute("""INSERT INTO invoices(user_id,customer_name,customer_address,phone,ntn,gst,
                       invoice_no,date,po_number,total)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (current_user.id,customer_name,customer_address,phone,ntn,gst,
                     invoice_no,date,po_number,total))
        invoice_id = cur.lastrowid
        for i in range(len(products)):
            cur.execute("INSERT INTO products(invoice_id,name,qty,unit_cost) VALUES(?,?,?,?)",
                        (invoice_id,products[i],qtys[i],unit_costs[i]))
        con.commit()
        con.close()
        flash("Invoice created successfully")
        return redirect("/dashboard")
    return render_template("create_invoice.html", user=current_user)

# --------- Edit Invoice ---------
@app.route("/invoice/edit/<int:invoice_id>", methods=["GET","POST"])
@login_required
def edit_invoice(invoice_id):
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM invoices WHERE id=? AND user_id=?",(invoice_id,current_user.id))
    invoice = cur.fetchone()
    if not invoice:
        flash("Invoice not found")
        return redirect("/dashboard")
    if request.method=="POST":
        customer_name = request.form["customer_name"]
        customer_address = request.form["customer_address"]
        phone = request.form["phone"]
        ntn = request.form.get("ntn","")
        gst = request.form.get("gst","")
        invoice_no = request.form["invoice_no"]
        date = request.form["date"]
        po_number = request.form.get("po_number","")
        products = request.form.getlist("product_name[]")
        qtys = request.form.getlist("qty[]")
        unit_costs = request.form.getlist("unit_cost[]")
        total = sum([int(qtys[i])*float(unit_costs[i]) for i in range(len(products))])
        cur.execute("""UPDATE invoices SET customer_name=?,customer_address=?,phone=?,ntn=?,gst=?,
                       invoice_no=?,date=?,po_number=?,total=? WHERE id=?""",
                    (customer_name,customer_address,phone,ntn,gst,invoice_no,date,po_number,total,invoice_id))
        cur.execute("DELETE FROM products WHERE invoice_id=?", (invoice_id,))
        for i in range(len(products)):
            cur.execute("INSERT INTO products(invoice_id,name,qty,unit_cost) VALUES(?,?,?,?)",
                        (invoice_id,products[i],qtys[i],unit_costs[i]))
        con.commit()
        con.close()
        flash("Invoice updated successfully")
        return redirect("/dashboard")
    cur.execute("SELECT id, name AS product_name, qty, unit_cost FROM products WHERE invoice_id=?",(invoice_id,))
    products = cur.fetchall()
    con.close()
    return render_template("edit_invoice.html", invoice=invoice, products=products, user=current_user)

# --------- View Invoice ---------
@app.route("/invoice/view/<int:invoice_id>")
@login_required
def view_invoice(invoice_id):
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM invoices WHERE id=? AND user_id=?",(invoice_id,current_user.id))
    invoice = cur.fetchone()
    if not invoice:
        flash("Invoice not found")
        return redirect("/dashboard")
    cur.execute("SELECT id, name AS product_name, qty, unit_cost FROM products WHERE invoice_id=?",(invoice_id,))
    products = cur.fetchall()
    con.close()
    return render_template("view_invoice.html", invoice=invoice, products=products, user=current_user)

# --------- Delete Invoice ---------
@app.route("/invoice/delete/<int:invoice_id>")
@login_required
def delete_invoice(invoice_id):
    con = get_db()
    cur = con.cursor()
    cur.execute("DELETE FROM invoices WHERE id=? AND user_id=?",(invoice_id,current_user.id))
    cur.execute("DELETE FROM products WHERE invoice_id=?",(invoice_id,))
    con.commit()
    con.close()
    flash("Invoice deleted successfully")
    return redirect("/dashboard")

# --------- Warranty Card ---------
@app.route("/invoice/warranty/<int:invoice_id>")
@login_required
def warranty_card(invoice_id):
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM invoices WHERE id=? AND user_id=?",(invoice_id,current_user.id))
    invoice = cur.fetchone()
    if not invoice:
        flash("Invoice not found")
        return redirect("/dashboard")
    cur.execute("SELECT id, name AS product_name, qty, unit_cost FROM products WHERE invoice_id=?",(invoice_id,))
    products = cur.fetchall()
    con.close()
    return render_template("warranty_card.html", invoice=invoice, products=products, user=current_user)

# --------- Admin Panel ---------
@app.route("/admin")
@login_required
def admin():
    if not current_user.is_admin:
        return redirect("/dashboard")
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT * FROM users")
    users = cur.fetchall()

    # Fetch all invoices
    cur.execute("""SELECT invoices.*, users.full_name, users.email
                   FROM invoices JOIN users ON invoices.user_id=users.id""")
    invoices = cur.fetchall()

    # Fetch products for each invoice
    invoice_products = {}
    for invoice in invoices:
        cur.execute("SELECT id, name AS product_name, qty, unit_cost FROM products WHERE invoice_id=?",
                    (invoice['id'],))
        invoice_products[invoice['id']] = cur.fetchall()

    con.close()
    return render_template("admin_dashboard.html", users=users, invoices=invoices,
                           invoice_products=invoice_products, user=current_user)

# --------- Reset User Password ---------
@app.route("/admin/reset-password/<int:user_id>", methods=["POST"])
@login_required
def reset_password(user_id):
    if not current_user.is_admin:
        return redirect("/dashboard")
    new_password = generate_password_hash(request.form["password"])
    con = get_db()
    cur = con.cursor()
    cur.execute("UPDATE users SET password=? WHERE id=?",(new_password,user_id))
    con.commit()
    con.close()
    flash("Password reset successfully")
    return redirect("/admin")

# --------- Export Invoices (CSV) ---------
@app.route("/admin/export")
@login_required
def export_invoices():
    if not current_user.is_admin:
        return redirect("/dashboard")
    con = get_db()
    cur = con.cursor()
    cur.execute("""SELECT users.full_name, users.email, invoices.invoice_no, invoices.date, invoices.total
                   FROM invoices JOIN users ON invoices.user_id=users.id""")
    rows = cur.fetchall()
    con.close()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["User","Email","Invoice No","Date","Total"])
    writer.writerows(rows)
    return send_file(io.BytesIO(output.getvalue().encode()), mimetype="text/csv", as_attachment=True, download_name="all_invoices.csv")

# --------- Logout ---------
@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/")

# --------- Run App ---------
if __name__=="__main__":
    init_db()
    app.run(debug=True)
