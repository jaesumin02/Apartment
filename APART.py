import sqlite3
import os
import random
import datetime
import csv
import json
import customtkinter as ctk
import tkinter as tk

try:
    import bcrypt
except Exception:
    bcrypt = None

from tkinter import ttk, messagebox, simpledialog, filedialog

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

DB_FILE = "apartment_system.db"

DORM_MAX_OCCUPANTS = 4
NOTICE_PERIOD_DAYS = 30

def ensure_column(db_conn, table, column, col_def):
    cur = db_conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    if column not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_def}")
        db_conn.commit()

class Database:
    def __init__(self, db_file=DB_FILE):
        self.db_file = db_file
        first_time = not os.path.exists(db_file)
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.setup_tables(first_time)

    def setup_tables(self, first_time=False):
        cur = self.conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS owners (
            owner_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            contact TEXT,
            address TEXT
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS units (
            unit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_code TEXT,
            type TEXT,
            price REAL,
            status TEXT
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            tenant_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            contact TEXT,
            unit_id INTEGER,
            tenant_type TEXT,
            move_in DATE,
            move_out DATE,
            status TEXT,
            guardian_name TEXT,
            guardian_contact TEXT,
            guardian_relation TEXT,
            emergency_contact TEXT,
            advance_paid REAL DEFAULT 0,
            deposit_paid REAL DEFAULT 0,
            FOREIGN KEY(unit_id) REFERENCES units(unit_id)
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS deleted_tenants (
            deleted_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER,
            name TEXT,
            contact TEXT,
            unit_id INTEGER,
            tenant_type TEXT,
            move_in DATE,
            move_out DATE,
            status TEXT,
            guardian_name TEXT,
            guardian_contact TEXT,
            guardian_relation TEXT,
            emergency_contact TEXT,
            deleted_date DATE,
            reason TEXT
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER,
            rent REAL,
            electricity REAL,
            water REAL,
            total REAL,
            date_paid DATE,
            status TEXT,
            note TEXT,
            FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id)
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS maintenance (
            request_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER,
            description TEXT,
            priority TEXT,
            date_requested DATE,
            status TEXT,
            assigned_staff INTEGER,
            fee REAL DEFAULT 0,
            FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id)
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS staff (
            staff_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            role TEXT,
            contact TEXT
        );
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            report_id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            generated_date DATE,
            filepath TEXT
        );
        """)
        self.conn.commit()

        ensure_column(self.conn, "tenants", "guardian_name", "TEXT DEFAULT ''")
        ensure_column(self.conn, "tenants", "guardian_contact", "TEXT DEFAULT ''")
        ensure_column(self.conn, "tenants", "guardian_relation", "TEXT DEFAULT ''")
        ensure_column(self.conn, "tenants", "emergency_contact", "TEXT DEFAULT ''")
        ensure_column(self.conn, "tenants", "advance_paid", "REAL DEFAULT 0")
        ensure_column(self.conn, "tenants", "deposit_paid", "REAL DEFAULT 0")
        ensure_column(self.conn, "payments", "note", "TEXT DEFAULT ''")

        self.seed_defaults()

        if bcrypt:
            try:
                self.migrate_user_passwords_to_bcrypt()
            except Exception:
                pass

    def seed_defaults(self):
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) as c FROM users")
        if cur.fetchone()["c"] == 0:
            cur.execute("INSERT INTO users (username,password,role) VALUES (?,?,?)", ("admin","admin","admin"))
        cur.execute("SELECT COUNT(*) as sc FROM staff")
        if cur.fetchone()["sc"] == 0:
            staff_names = [("Carlos", "Technician"), ("Liza", "Caretaker"), ("Rob", "Electrician")]
            for n, r in staff_names:
                cur.execute("INSERT INTO staff (name, role, contact) VALUES (?,?,?)", (n, r, "0917123456"))
        cur.execute("SELECT COUNT(*) as uc FROM units")
        if cur.fetchone()["uc"] == 0:
            unit_types = ["Family","Solo","Dorm"]
            for floor in range(1, 6):
                for i in range(1,6):
                    code = f"{chr(64+floor)}{i}"
                    utype = random.choice(unit_types)
                    price = random.choice([4500,5000,5500,6000,7000,8000])
                    cur.execute("INSERT INTO units (unit_code,type,price,status) VALUES (?,?,?,?)", (code, utype, price, "Vacant"))
        cur.execute("SELECT COUNT(*) as tc FROM tenants")
        if cur.fetchone()["tc"] == 0:
            cur2 = self.conn.cursor()
            cur2.execute("SELECT unit_id, type FROM units")
            units = cur2.fetchall()
            sample_names = ["Jasmine","Mariz","Rafael","Elaine","Mark","Jenny","Paolo","Carlos","April","Irene",
                            "Nathan","Hannah","Chris","Lara","Ricardo","Andrea","Melvin","Sophia","Aaron","Nina"]
            idx = 0
            for u in units:
                utype = u["type"]
                if utype == "Family":
                    occ = 1 if random.random() > 0.6 else 0
                elif utype == "Solo":
                    occ = 1 if random.random() > 0.4 else 0
                else:
                    occ = random.randint(0, min(3, DORM_MAX_OCCUPANTS))
                for j in range(occ):
                    name = f"{sample_names[idx % len(sample_names)]} {idx+1}"
                    contact = f"0917{random.randint(100000,999999)}"
                    move_in = (datetime.date.today() - datetime.timedelta(days=random.randint(0,400))).isoformat()
                    guardian_name = ""
                    guardian_contact = ""
                    guardian_relation = ""
                    if utype.lower() == "dorm":
                        guardian_name = f"Guardian {idx+1}"
                        guardian_contact = f"0917{random.randint(100000,999999)}"
                        guardian_relation = "Parent"
                    cur.execute("""INSERT INTO tenants (name, contact, unit_id, tenant_type, move_in, move_out, status,
                                   guardian_name, guardian_contact, guardian_relation, emergency_contact, advance_paid, deposit_paid)
                                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (name, contact, u["unit_id"], utype, move_in, None, "Active", guardian_name, guardian_contact, guardian_relation, "", random.choice([0,4500]), random.choice([0,4500])))
                    cur.execute("UPDATE units SET status=? WHERE unit_id=?", ("Occupied", u["unit_id"]))
                    idx += 1
            cur.execute("SELECT tenant_id FROM tenants")
            tids = [r["tenant_id"] for r in cur.fetchall()]
            for tid in tids:
                rent = random.choice([4500,5000,5500,6000,7000])
                elec = random.randint(200,900)
                water = random.randint(100,400)
                total = rent + elec + water
                date_paid = (datetime.date.today() - datetime.timedelta(days=random.randint(0,60))).isoformat()
                status = "Paid" if random.random()>0.15 else "Overdue"
                cur.execute("INSERT INTO payments (tenant_id, rent, electricity, water, total, date_paid, status) VALUES (?,?,?,?,?,?,?)",
                            (tid, rent, elec, water, total, date_paid, status))
            for tid in tids[:15]:
                desc = random.choice(["Broken door lock","Leaky faucet","Clogged drain"])
                pr = random.choice(["Low","Medium","High"])
                date_req = (datetime.date.today() - datetime.timedelta(days=random.randint(0,30))).isoformat()
                stat = random.choice(["Pending","Ongoing","Done"])
                fee = random.choice([0,150,250])
                cur.execute("INSERT INTO maintenance (tenant_id, description, priority, date_requested, status, assigned_staff, fee) VALUES (?,?,?,?,?,?,?)",
                            (tid, desc, pr, date_req, stat, random.choice([1,2,3]), fee))
        self.conn.commit()

    def execute(self, query, params=()):
        cur = self.conn.cursor()
        cur.execute(query, params)
        self.conn.commit()
        return cur

    def query(self, query, params=()):
        cur = self.conn.cursor()
        cur.execute(query, params)
        return cur.fetchall()

    def close(self):
        if self.conn:
            self.conn.close()

    def migrate_user_passwords_to_bcrypt(self):
        if not bcrypt:
            return
        try:
            cur = self.conn.cursor()
            cur.execute("SELECT user_id, password FROM users")
            rows = cur.fetchall()
            changed = False
            for r in rows:
                pw = r["password"] or ""
                if pw and not pw.startswith("$2b$") and not pw.startswith("$2y$"):
                    hashed = bcrypt.hashpw(pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    cur.execute("UPDATE users SET password=? WHERE user_id=?", (hashed, r["user_id"]))
                    changed = True
            if changed:
                self.conn.commit()
        except Exception:
            pass

class TenantModel:
    def __init__(self, db: Database):
        self.db = db

    def create(self, name, contact, unit_id, tenant_type, move_in, guardian_name="", guardian_contact="", guardian_relation="", emergency_contact="", advance_paid=0, deposit_paid=0, status="Active"):
        self.db.execute("""INSERT INTO tenants (name, contact, unit_id, tenant_type, move_in, move_out, status,
                           guardian_name, guardian_contact, guardian_relation, emergency_contact, advance_paid, deposit_paid)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (name, contact, unit_id, tenant_type, move_in, None, status, guardian_name, guardian_contact, guardian_relation, emergency_contact, advance_paid, deposit_paid))
        return True

    def update(self, tenant_id, **kwargs):
        if not kwargs:
            return False
        fields = ", ".join([f"{k}=?" for k in kwargs])
        values = list(kwargs.values())
        values.append(tenant_id)
        self.db.execute(f"UPDATE tenants SET {fields} WHERE tenant_id=?", tuple(values))
        return True

    def delete(self, tenant_id, reason="Deleted by admin"):
        row = self.get(tenant_id)
        if not row:
            return False
        def safe(r, key):
            try:
                return r[key] if key in r.keys() and r[key] is not None else ""
            except:
                return ""
        self.db.execute("""INSERT INTO deleted_tenants (tenant_id, name, contact, unit_id, tenant_type, move_in, move_out, status,
                              guardian_name, guardian_contact, guardian_relation, emergency_contact, deleted_date, reason)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (row["tenant_id"], row["name"], row["contact"], row["unit_id"], row["tenant_type"], row["move_in"], row["move_out"], row["status"],
                         safe(row,"guardian_name"), safe(row,"guardian_contact"), safe(row,"guardian_relation"), safe(row,"emergency_contact"),
                         datetime.date.today().isoformat(), reason))
        if row["unit_id"]:
            self.db.execute("UPDATE units SET status=? WHERE unit_id=?", ("Vacant", row["unit_id"]))
        self.db.execute("DELETE FROM tenants WHERE tenant_id=?", (tenant_id,))
        return True

    def restore(self, deleted_id):
        rows = self.db.query("SELECT * FROM deleted_tenants WHERE deleted_id=?", (deleted_id,))
        if not rows:
            return False
        r = rows[0]
        cur = self.db.execute("""INSERT INTO tenants (name, contact, unit_id, tenant_type, move_in, move_out, status,
                             guardian_name, guardian_contact, guardian_relation, emergency_contact, advance_paid, deposit_paid)
                             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                             (r["name"], r["contact"], r["unit_id"], r["tenant_type"], r["move_in"], r["move_out"], r["status"],
                              r["guardian_name"], r["guardian_contact"], r["guardian_relation"], r["emergency_contact"], 0, 0))
        new_tid = cur.lastrowid
        if r["unit_id"]:
            self.db.execute("UPDATE units SET status=? WHERE unit_id=?", ("Occupied", r["unit_id"]))
        self.db.execute("DELETE FROM deleted_tenants WHERE deleted_id=?", (deleted_id,))
        return new_tid

    def all(self):
        return self.db.query("SELECT t.*, u.unit_code, u.type as unit_type, u.price as unit_price FROM tenants t LEFT JOIN units u ON t.unit_id = u.unit_id ORDER BY t.tenant_id")

    def get(self, tenant_id):
        rows = self.db.query("SELECT * FROM tenants WHERE tenant_id=?", (tenant_id,))
        return rows[0] if rows else None

    def list_deleted(self):
        return self.db.query("SELECT * FROM deleted_tenants ORDER BY deleted_id DESC")

class PaymentModel:
    def __init__(self, db: Database):
        self.db = db

    def create(self, tenant_id, rent, electricity, water, date_paid, status, note=""):
        total = (rent or 0) + (electricity or 0) + (water or 0)
        self.db.execute("""INSERT INTO payments (tenant_id, rent, electricity, water, total, date_paid, status, note)
                           VALUES (?,?,?,?,?,?,?,?)""", (tenant_id, rent, electricity, water, total, date_paid, status, note))
        return True

    def all(self):
        return self.db.query("SELECT p.*, t.name FROM payments p LEFT JOIN tenants t ON p.tenant_id = t.tenant_id ORDER BY p.payment_id DESC")

    def stats_sum(self, since_days=30):
        since = (datetime.date.today() - datetime.timedelta(days=since_days)).isoformat()
        rows = self.db.query("SELECT sum(total) as total_income FROM payments WHERE date_paid >= ?", (since,))
        return rows[0]["total_income"] if rows else 0

    def last_payment_date(self, tenant_id):
        rows = self.db.query("SELECT date_paid FROM payments WHERE tenant_id=? ORDER BY date_paid DESC LIMIT 1", (tenant_id,))
        return rows[0]["date_paid"] if rows else None

    def unpaid_exists(self, tenant_id):
        rows = self.db.query("SELECT COUNT(*) as c FROM payments WHERE tenant_id=? AND status!='Paid'", (tenant_id,))
        return (rows[0]["c"] if rows else 0) > 0

class MaintenanceModel:
    def __init__(self, db: Database):
        self.db = db

    def create(self, tenant_id, description, priority, date_requested, status="Pending", assigned_staff=None, fee=0.0):
        self.db.execute("""INSERT INTO maintenance (tenant_id, description, priority, date_requested, status, assigned_staff, fee)
                           VALUES (?,?,?,?,?,?,?)""", (tenant_id, description, priority, date_requested, status, assigned_staff, fee))
        return True

    def all(self):
        return self.db.query("SELECT m.*, t.name as tenant_name, s.name as staff_name FROM maintenance m LEFT JOIN tenants t ON m.tenant_id = t.tenant_id LEFT JOIN staff s ON m.assigned_staff = s.staff_id ORDER BY m.request_id DESC")

    def update_status(self, request_id, status):
        self.db.execute("UPDATE maintenance SET status=? WHERE request_id=?", (status, request_id))
        return True

class UnitModel:
    def __init__(self, db: Database):
        self.db = db

    def all(self):
        return self.db.query("SELECT * FROM units ORDER BY unit_code")

    def available(self):
        return self.db.query("SELECT * FROM units WHERE status='Vacant' ORDER BY unit_code")

    def get(self, unit_id):
        rows = self.db.query("SELECT * FROM units WHERE unit_id=?", (unit_id,))
        return rows[0] if rows else None

class StaffModel:
    def __init__(self, db: Database):
        self.db = db

    def all(self):
        return self.db.query("SELECT * FROM staff ORDER BY staff_id")

class BillingController:
    def __init__(self, db: Database, payment_model: PaymentModel, tenant_model: TenantModel):
        self.db = db
        self.payment_model = payment_model
        self.tenant_model = tenant_model

    def compute_total(self, rent, electricity, water):
        return (rent or 0) + (electricity or 0) + (water or 0)

    def create_payment(self, tenant_id, rent, electricity, water, date_paid=None, status="Paid", note=""):
        if date_paid is None:
            date_paid = datetime.date.today().isoformat()
        total = self.compute_total(rent, electricity, water)
        self.payment_model.create(tenant_id, rent, electricity, water, date_paid, status, note)
        return total

    def overdue_list(self, policy_days=7):
        since = (datetime.date.today() - datetime.timedelta(days=policy_days)).isoformat()
        rows = self.db.query("""SELECT t.tenant_id, t.name, p.total, p.date_paid, p.status
                                FROM tenants t
                                LEFT JOIN payments p ON t.tenant_id = p.tenant_id
                                WHERE (p.status='Overdue') OR
                                      (p.date_paid IS NOT NULL AND p.date_paid < ?)
                                ORDER BY t.tenant_id""", (since,))
        none_paid = self.db.query("""SELECT tenant_id, name FROM tenants WHERE tenant_id NOT IN (SELECT tenant_id FROM payments)""")
        results = list(rows)
        for np in none_paid:
            t = self.tenant_model.get(np["tenant_id"])
            if t and t["move_in"]:
                try:
                    mi = datetime.date.fromisoformat(t["move_in"])
                    if (datetime.date.today() - mi).days > policy_days:
                        results.append({"tenant_id": t["tenant_id"], "name": t["name"], "total": None, "date_paid": None, "status": "No Payment"})
                except:
                    pass
        return results

class MaintenanceController:
    def __init__(self, maintenance_model: MaintenanceModel):
        self.maintenance_model = maintenance_model

    def submit_request(self, tenant_id, description, priority, fee=0.0):
        date_req = datetime.date.today().isoformat()
        return self.maintenance_model.create(tenant_id, description, priority, date_req, "Pending", None, fee)

    def update_status(self, request_id, status):
        return self.maintenance_model.update_status(request_id, status)

class LoginWindow(ctk.CTk):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.title("Apartment Billing System - Login")
        self.geometry("480x320")
        self.resizable(False, False)
        self.create_widgets()

    def create_widgets(self):
        frame = ctk.CTkFrame(self, corner_radius=8, width=420, height=260)
        frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        title = ctk.CTkLabel(frame, text="Apartment Billing System", font=ctk.CTkFont(size=18, weight="bold"))
        title.pack(pady=(12,4))
        ctk.CTkLabel(frame, text="Admin Login").pack(pady=(0,8))

        userfrm = ctk.CTkFrame(frame, corner_radius=6)
        userfrm.pack(pady=6, padx=12, fill="x")
        ctk.CTkLabel(userfrm, text="Username").grid(row=0, column=0, padx=8, pady=6, sticky="w")
        self.username_entry = ctk.CTkEntry(userfrm, width=260)
        self.username_entry.grid(row=0, column=1, padx=8, pady=6)
        ctk.CTkLabel(userfrm, text="Password").grid(row=1, column=0, padx=8, pady=6, sticky="w")
        self.password_entry = ctk.CTkEntry(userfrm, show="*", width=260)
        self.password_entry.grid(row=1, column=1, padx=8, pady=6)

        btnfrm = ctk.CTkFrame(frame, corner_radius=8)
        btnfrm.pack(pady=8)
        ctk.CTkButton(btnfrm, text="Login", width=120, command=self.login).grid(row=0, column=0, padx=8)
        ctk.CTkButton(btnfrm, text="Exit", width=120, command=self.quit).grid(row=0, column=1, padx=8)

        ctk.CTkLabel(frame, text="Default admin: username=admin password=admin", text_color="gray").pack(pady=(6,0))

    def login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        if not username or not password:
            messagebox.showwarning("Input required", "Please input username and password")
            return
        rows = self.db.query("SELECT * FROM users WHERE username=?", (username,))
        if not rows:
            messagebox.showerror("Login failed", "Invalid username or password")
            return
        user = rows[0]
        stored = user['password'] or ''
        ok = False
        try:
            if bcrypt and (stored.startswith('$2b$') or stored.startswith('$2y$')):
                ok = bcrypt.checkpw(password.encode('utf-8'), stored.encode('utf-8'))
            else:
                ok = (password == stored)
        except Exception:
            ok = (password == stored)
        if ok:
            if not self.show_policy_and_accept():
                return
            messagebox.showinfo("Login success", f"Welcome, {username}")
            self.destroy()
            root = AdminInterface(self.db, username)
            root.mainloop()
        else:
            messagebox.showerror("Login failed", "Invalid username or password")

    def show_policy_and_accept(self):
        txt = (
            "Apartment Rules & Policy (please accept to continue):\n\n"
            "1) Custom advance and deposit are supported per tenant.\n"
            "2) Dorm rooms have a maximum occupancy of 4 people per unit.\n"
            "3) Deposits may be refunded on move-out if conditions are met (no unpaid bills, no damages, notice period followed).\n"
            "4) Maintenance requests may incur fees.\n"
        )
        res = messagebox.askyesno("Apartment Policy - Accept to continue", txt)
        return res

class AdminInterface(ctk.CTk):
    def __init__(self, db: Database, username):
        super().__init__()
        self.db = db
        self.username = username
        self.title("Apartment Billing System - Admin Dashboard")
        self.geometry("1200x720")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.tenant_model = TenantModel(db)
        self.payment_model = PaymentModel(db)
        self.unit_model = UnitModel(db)
        self.maintenance_model = MaintenanceModel(db)
        self.staff_model = StaffModel(db)
        self.billing_ctrl = BillingController(db, self.payment_model, self.tenant_model)
        self.maintenance_ctrl = MaintenanceController(self.maintenance_model)
        self.auto_refresh_interval_ms = 7000
        self.create_widgets()
        self.load_tenants()
        self.load_units()
        self.load_payments()
        self.load_maintenance()
        self.load_deleted_tenants()

    def create_widgets(self):
        menubar = tk.Menu(self)
        account_menu = tk.Menu(menubar, tearoff=0)
        account_menu.add_command(label="Change Password", command=self.change_password_dialog)
        account_menu.add_command(label="Logout", command=self.logout)
        menubar.add_cascade(label="Account", menu=account_menu)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Export Payments CSV", command=self.export_payments_csv)
        file_menu.add_command(label="Exit", command=self.on_close)
        menubar.add_cascade(label="File", menu=file_menu)
        self.configure(menu=menubar)

        header = ctk.CTkFrame(self, corner_radius=8)
        header.pack(side="top", fill="x", padx=12, pady=8)
        ctk.CTkLabel(header, text="Admin Dashboard", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left", padx=8)
        ctk.CTkButton(header, text="Refresh", width=110, command=self.refresh_all).pack(side="right", padx=(8,6))
        ctk.CTkButton(header, text="Logout", width=110, command=self.logout).pack(side="right", padx=6)

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=12, pady=8)

        self.tab_tenants = ttk.Frame(self.tabs)
        self.tabs.add(self.tab_tenants, text="Tenants")
        self._build_tenants_tab()

        self.tab_billing = ttk.Frame(self.tabs)
        self.tabs.add(self.tab_billing, text="Billing")
        self._build_billing_tab()

        self.tab_maintenance = ttk.Frame(self.tabs)
        self.tabs.add(self.tab_maintenance, text="Maintenance")
        self._build_maintenance_tab()

        self.tab_reports = ttk.Frame(self.tabs)
        self.tabs.add(self.tab_reports, text="Reports")
        self._build_reports_tab()

        self.tab_recycle = ttk.Frame(self.tabs)
        self.tabs.add(self.tab_recycle, text="Recycle Bin")
        self._build_recycle_tab()

    def _build_tenants_tab(self):
        frame = self.tab_tenants
        top = ttk.Frame(frame, padding=6)
        top.pack(side="top", fill="x")
        ttk.Button(top, text="Add Tenant", command=self.add_tenant_dialog).pack(side="left", padx=4)
        ttk.Button(top, text="Edit Tenant", command=self.edit_tenant_dialog).pack(side="left", padx=4)
        ttk.Button(top, text="Delete Tenant (Move to Recycle Bin)", command=self.delete_tenant).pack(side="left", padx=4)
        ttk.Button(top, text="Show Units", command=self.show_units_window).pack(side="left", padx=4)
        ttk.Button(top, text="Assign Unit", command=self.assign_unit_dialog).pack(side="left", padx=4)
        ttk.Button(top, text="Mark Move-Out", command=self.mark_move_out_dialog).pack(side="left", padx=4)
        ttk.Button(top, text="Auto-detect Move-outs", command=self.detect_moveouts_now).pack(side="left", padx=4)
        ttk.Button(top, text="Show Available Units", command=self.show_available_units).pack(side="left", padx=4)

        cols = ("tenant_id","name","contact","unit","type","move_in","move_out","status","guardian","guardian_contact","advance","deposit","notes")
        self.tenants_tree = ttk.Treeview(frame, columns=cols, show="headings", height=18)
        for c in cols:
            self.tenants_tree.heading(c, text=c.title())
            if c == "name":
                self.tenants_tree.column(c, width=200)
            elif c == "notes":
                self.tenants_tree.column(c, width=260)
            else:
                self.tenants_tree.column(c, width=110)
        self.tenants_tree.pack(fill="both", expand=True, padx=8, pady=8)

    def detect_moveouts_now(self):
        rows = self.tenant_model.all()
        changed = False
        for r in rows:
            if r["move_out"]:
                try:
                    mo = datetime.date.fromisoformat(r["move_out"])
                    if mo <= datetime.date.today() and (r["status"] != "Moved out"):
                        self.tenant_model.update(r["tenant_id"], status="Moved out")
                        if r["unit_id"]:
                            self.db.execute("UPDATE units SET status=? WHERE unit_id=?", ("Vacant", r["unit_id"]))
                        changed = True
                except:
                    pass
        if changed:
            messagebox.showinfo("Detected", "Move-outs processed")
            self.load_tenants()
            self.load_units()
        else:
            messagebox.showinfo("No changes", "No move-outs detected for today")

    def check_moveouts(self):
        rows = self.tenant_model.all()
        for r in rows:
            if r["move_out"]:
                try:
                    mo = datetime.date.fromisoformat(r["move_out"])
                    if mo <= datetime.date.today() and r["status"] != "Moved out":
                        self.tenant_model.update(r["tenant_id"], status="Moved out")
                        if r["unit_id"]:
                            self.db.execute("UPDATE units SET status=? WHERE unit_id=?", ("Vacant", r["unit_id"]))
                except:
                    pass

    def load_tenants(self):
        self.check_moveouts()
        for r in self.tenants_tree.get_children():
            self.tenants_tree.delete(r)
        rows = self.tenant_model.all()
        unit_counts = {}
        for r in rows:
            uid = r["unit_id"]
            unit_counts[uid] = unit_counts.get(uid, 0) + 1
        for row in rows:
            guardian = row["guardian_name"] or "-"
            guard_contact = row["guardian_contact"] or "-"
            notes = ""
            try:
                if (row["unit_type"] or "").lower() == "dorm":
                    cnt = unit_counts.get(row["unit_id"], 0)
                    notes = f"Dorm - {cnt} occupant(s)"
            except:
                pass
            self.tenants_tree.insert("", tk.END, values=(row["tenant_id"], row["name"], row["contact"], row["unit_code"] or "-", row["unit_type"] or "-", row["move_in"], row["move_out"] or "-", row["status"] or "-", guardian, guard_contact, row["advance_paid"] or 0, row["deposit_paid"] or 0, notes))

    def add_tenant_dialog(self):
        dlg = TenantDialog(self, self.unit_model)
        self.wait_window(dlg)
        if dlg.saved:
            if dlg.tenant_type.lower() == "dorm" and dlg.unit_id:
                cnt = self.db.query("SELECT COUNT(*) as c FROM tenants WHERE unit_id=? AND tenant_type='Dorm' AND status='Active'", (dlg.unit_id,))[0]["c"]
                if cnt >= DORM_MAX_OCCUPANTS:
                    messagebox.showwarning("Limit Exceeded", f"This dorm unit already has {cnt} occupants (max {DORM_MAX_OCCUPANTS}).")
                    return
            self.tenant_model.create(dlg.name, dlg.contact, dlg.unit_id, dlg.tenant_type, dlg.move_in, dlg.guardian_name, dlg.guardian_contact, dlg.guardian_relation, dlg.emergency_contact, dlg.advance_paid, dlg.deposit_paid)
            if dlg.unit_id:
                self.db.execute("UPDATE units SET status=? WHERE unit_id=?", ("Occupied", dlg.unit_id))
            messagebox.showinfo("Saved", "Tenant added")
            self.load_tenants()

    def edit_tenant_dialog(self):
        sel = self.tenants_tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Please select a tenant to edit")
            return
        item = self.tenants_tree.item(sel[0])["values"]
        tenant_id = item[0]
        row = self.tenant_model.get(tenant_id)
        dlg = TenantDialog(self, self.unit_model, tenant=row)
        self.wait_window(dlg)
        if dlg.saved:
            prev_unit = row["unit_id"]
            new_unit = dlg.unit_id
            if dlg.tenant_type.lower() == "dorm" and new_unit and new_unit != prev_unit:
                cnt = self.db.query("SELECT COUNT(*) as c FROM tenants WHERE unit_id=? AND tenant_type='Dorm' AND status='Active'", (new_unit,))[0]["c"]
                if cnt >= DORM_MAX_OCCUPANTS:
                    messagebox.showwarning("Limit Exceeded", f"This dorm unit already has {cnt} occupants (max {DORM_MAX_OCCUPANTS}).")
                    return
            update_fields = {
                "name": dlg.name,
                "contact": dlg.contact,
                "unit_id": dlg.unit_id,
                "tenant_type": dlg.tenant_type,
                "guardian_name": dlg.guardian_name,
                "guardian_contact": dlg.guardian_contact,
                "guardian_relation": dlg.guardian_relation,
                "emergency_contact": dlg.emergency_contact,
                "move_in": dlg.move_in,
                "advance_paid": dlg.advance_paid,
                "deposit_paid": dlg.deposit_paid
            }
            self.tenant_model.update(tenant_id, **update_fields)
            if prev_unit != new_unit:
                if prev_unit:
                    self.db.execute("UPDATE units SET status=? WHERE unit_id=?", ("Vacant", prev_unit))
                if new_unit:
                    self.db.execute("UPDATE units SET status=? WHERE unit_id=?", ("Occupied", new_unit))
            messagebox.showinfo("Updated", "Tenant updated")
            self.load_tenants()

    def delete_tenant(self):
        sel = self.tenants_tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Select a tenant to delete")
            return
        item = self.tenants_tree.item(sel[0])["values"]
        tid = item[0]
        reason = simpledialog.askstring("Reason (optional)", "Reason for deleting / moving to recycle bin:")
        if messagebox.askyesno("Confirm", "Move tenant to Recycle Bin (soft-delete)?"):
            self.tenant_model.delete(tid, reason=reason or "Deleted")
            messagebox.showinfo("Deleted", "Tenant moved to Recycle Bin")
            self.load_tenants()
            self.load_deleted_tenants()

    def show_units_window(self):
        w = ctk.CTkToplevel(self)
        w.title("Apartment Units (Enhanced)")
        w.geometry("920x520")
        topfrm = ctk.CTkFrame(w, corner_radius=8)
        topfrm.pack(side="top", fill="x", padx=8, pady=8)
        filter_opt = ctk.CTkOptionMenu(topfrm, values=["All","Available"], command=lambda v: refresh_tree())
        filter_opt.set("All")
        filter_opt.pack(side="left", padx=8)
        avail_lbl = ctk.CTkLabel(topfrm, text="Available: 0")
        avail_lbl.pack(side="right", padx=10)
        left = ctk.CTkFrame(w, width=560, height=440)
        left.place(x=8, y=60)
        cols = ("unit_id","unit_code","type","price","status")
        tree = ttk.Treeview(left, columns=cols, show="headings")
        for c in cols:
            tree.heading(c, text=c.title())
            tree.column(c, width=100 if c!="unit_code" else 120)
        tree.pack(fill="both", expand=True)
        right = ctk.CTkFrame(w, corner_radius=8, width=320, height=440)
        right.place(x=580, y=60)
        detail_text = tk.Text(right, height=18, wrap="word")
        detail_text.pack(fill="both", expand=True)
        def refresh_tree():
            f = filter_opt.get()
            for r in tree.get_children():
                tree.delete(r)
            rows = self.unit_model.all()
            count_avail = 0
            for r in rows:
                if f == "Available" and (r["status"] or "").lower() != "vacant":
                    continue
                tree.insert("", tk.END, values=(r["unit_id"], r["unit_code"], r["type"], r["price"], r["status"]))
                if (r["status"] or "").lower() == "vacant":
                    count_avail += 1
            avail_lbl.configure(text=f"Available: {count_avail}")
            try:
                w.after(self.auto_refresh_interval_ms, refresh_tree)
            except:
                pass
        def on_select(event):
            sel = tree.selection()
            if not sel:
                return
            item = tree.item(sel[0])["values"]
            uid = item[0]
            unit = self.unit_model.get(uid)
            lines = []
            if unit:
                lines.append(f"Unit ID: {unit['unit_id']}")
                lines.append(f"Code: {unit['unit_code']}")
                lines.append(f"Type: {unit['type']}")
                lines.append(f"Price: ₱{unit['price']}")
                lines.append(f"Status: {unit['status']}")
                lines.append("")
                lines.append("Tenants in this unit:")
                rows = self.db.query("SELECT tenant_id, name, contact, tenant_type, status FROM tenants WHERE unit_id=?", (uid,))
                if rows:
                    for t in rows:
                        lines.append(f"- [{t['tenant_id']}] {t['name']} ({t['tenant_type']}) - {t['status']} - {t['contact']}")
                else:
                    lines.append("  (No tenants)")
                rows_m = self.db.query("""SELECT m.*, t.name as tenant_name FROM maintenance m LEFT JOIN tenants t ON m.tenant_id = t.tenant_id
                                         WHERE m.tenant_id IN (SELECT tenant_id FROM tenants WHERE unit_id=?)
                                         ORDER BY m.request_id DESC LIMIT 6""", (uid,))
                if rows_m:
                    lines.append("")
                    lines.append("Recent maintenance:")
                    for mm in rows_m:
                        lines.append(f"- {mm['date_requested']}: {mm['description']} ({mm['status']}) fee:₱{mm['fee']}")
            detail_text.delete(1.0, tk.END)
            detail_text.insert(tk.END, "\n".join(lines))
        tree.bind("<<TreeviewSelect>>", on_select)
        refresh_tree()

    def show_available_units(self):
        w = tk.Toplevel(self)
        w.title("Available Units")
        cols = ("unit_id","unit_code","type","price")
        tree = ttk.Treeview(w, columns=cols, show="headings")
        for c in cols:
            tree.heading(c, text=c.title())
            tree.column(c, width=120)
        tree.pack(fill="both", expand=True)
        rows = self.unit_model.available()
        for r in rows:
            tree.insert("", tk.END, values=(r["unit_id"], r["unit_code"], r["type"], r["price"]))

    def assign_unit_dialog(self):
        sel = self.tenants_tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Select a tenant first")
            return
        item = self.tenants_tree.item(sel[0])["values"]
        tenant_id = item[0]
        choice = simpledialog.askinteger("Assign Unit", "Enter Unit ID to assign (see Units list):")
        if choice is None:
            return
        prev = self.tenant_model.get(tenant_id)
        prev_unit = prev["unit_id"] if prev else None
        unit = self.unit_model.get(choice)
        if unit and unit["type"].lower() == "dorm":
            cnt = self.db.query("SELECT COUNT(*) as c FROM tenants WHERE unit_id=? AND tenant_type='Dorm' AND status='Active'", (choice,))[0]["c"]
            if cnt >= DORM_MAX_OCCUPANTS:
                messagebox.showwarning("Limit Exceeded", f"This dorm unit already has {cnt} occupants (max {DORM_MAX_OCCUPANTS}).")
                return
        self.tenant_model.update(tenant_id, unit_id=choice)
        self.db.execute("UPDATE units SET status=? WHERE unit_id=?", ("Occupied", choice))
        if prev_unit and prev_unit != choice:
            self.db.execute("UPDATE units SET status=? WHERE unit_id=?", ("Vacant", prev_unit))
        messagebox.showinfo("Assigned", "Unit assigned to tenant")
        self.load_tenants()

    def mark_move_out_dialog(self):
        sel = self.tenants_tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Select a tenant to mark move-out")
            return
        item = self.tenants_tree.item(sel[0])["values"]
        tenant_id = item[0]
        move_out_date = simpledialog.askstring("Move Out Date", "Enter move out date (YYYY-MM-DD) or leave blank for today:")
        if not move_out_date:
            move_out_date = datetime.date.today().isoformat()
        try:
            t = self.tenant_model.get(tenant_id)
            refund_possible = False
            refund_note_lines = []
            has_unpaid = self.payment_model.unpaid_exists(tenant_id)
            if has_unpaid:
                refund_note_lines.append("Unpaid bills exist; deposit cannot be refunded automatically.")
            try:
                mi = datetime.date.fromisoformat(t["move_in"]) if t["move_in"] else None
                mo = datetime.date.fromisoformat(move_out_date)
                if mi:
                    days_stayed = (mo - mi).days
                    if days_stayed >= NOTICE_PERIOD_DAYS:
                        notice_ok = True
                    else:
                        notice_ok = False
                        refund_note_lines.append(f"Notice period not met ({days_stayed} days stayed, requires {NOTICE_PERIOD_DAYS}).")
                else:
                    notice_ok = False
                    refund_note_lines.append("Move-in date unknown; cannot verify notice period.")
            except:
                notice_ok = False
                refund_note_lines.append("Move-out / Move-in date parse error.")
            inspected_ok = messagebox.askyesno("Inspect Unit", "Have you inspected the unit and confirmed there are NO damages / unpaid issues? (Yes = no damages/issues)")
            if not inspected_ok:
                refund_note_lines.append("Admin inspection indicates possible damages/issues.")
            if (not has_unpaid) and notice_ok and inspected_ok:
                refund_possible = True
            self.tenant_model.update(tenant_id, move_out=move_out_date, status="Moved out")
            if t and t["unit_id"]:
                self.db.execute("UPDATE units SET status=? WHERE unit_id=?", ("Vacant", t["unit_id"]))
            if refund_possible:
                deposit_amt = t["deposit_paid"] or 0
                if deposit_amt and deposit_amt > 0:
                    today = datetime.date.today().isoformat()
                    # record refund as a "Refund" payment with note; negative total is optional — here we record in note and zero deposit_paid
                    self.payment_model.create(tenant_id, 0, 0, 0, today, "Refund", note="Deposit refunded")
                    self.tenant_model.update(tenant_id, deposit_paid=0)
                    messagebox.showinfo("Refunded", f"Deposit of ₱{deposit_amt} refunded to tenant {t['name']}.")
                else:
                    messagebox.showinfo("No Deposit", "Tenant had no deposit recorded to refund.")
            else:
                messagebox.showwarning("Refund Not Processed", "Deposit refund not processed:\n" + ("\n".join(refund_note_lines) if refund_note_lines else "Conditions not met."))
            messagebox.showinfo("Updated", "Tenant marked as moved out")
            self.load_tenants()
            self.load_units()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to mark move-out: {e}")

    def _build_billing_tab(self):
        frame = self.tab_billing
        top = ttk.Frame(frame, padding=6)
        top.pack(side="top", fill="x")
        ttk.Button(top, text="New Payment", command=self.new_payment_dialog).pack(side="left", padx=4)
        ttk.Button(top, text="Show Overdue (1 week policy)", command=lambda: self.show_overdue(7)).pack(side="left", padx=4)
        ttk.Button(top, text="Export Payments CSV", command=self.export_payments_csv).pack(side="left", padx=4)
        cols = ("payment_id","tenant","rent","electricity","water","total","date_paid","status","note")
        self.pay_tree = ttk.Treeview(frame, columns=cols, show="headings", height=18)
        for c in cols:
            self.pay_tree.heading(c, text=c.title())
            self.pay_tree.column(c, width=120)
        self.pay_tree.pack(fill="both", expand=True, padx=8, pady=8)

    def load_payments(self):
        for r in self.pay_tree.get_children():
            self.pay_tree.delete(r)
        rows = self.payment_model.all()
        for row in rows:
            self.pay_tree.insert("", tk.END, values=(row["payment_id"], row["name"], row["rent"], row["electricity"], row["water"], row["total"], row["date_paid"], row["status"], row["note"] or ""))

    def new_payment_dialog(self):
        dlg = PaymentDialog(self)
        self.wait_window(dlg)
        if dlg.saved:
            self.billing_ctrl.create_payment(dlg.tenant_id, dlg.rent, dlg.electricity, dlg.water, dlg.date_paid, dlg.status, note=dlg.note)
            messagebox.showinfo("Saved", "Payment recorded")
            self.load_payments()

    def show_overdue(self, days=7):
        rows = self.billing_ctrl.overdue_list(policy_days=days)
        if not rows:
            messagebox.showinfo("Overdue", "Walang overdue payments!")
            return
        txt_lines = []
        for r in rows:
            pid = r.get("tenant_id") or r.get("payment_id") or "-"
            name = r.get("name","-")
            total = r.get("total")
            date_paid = r.get("date_paid") or "-"
            status = r.get("status") or "-"
            txt_lines.append(f"{pid} - {name} - ₱{total if total is not None else 'N/A'} - last paid: {date_paid} - {status}")
        messagebox.showinfo("Overdue (policy {} days)".format(days), "\n".join(txt_lines))

    def export_payments_csv(self):
        rows = self.payment_model.all()
        if not rows:
            messagebox.showwarning("No Data", "No payments to export")
            return
        filepath = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV","*.csv")], title="Save payments CSV")
        if not filepath:
            return
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["payment_id","tenant","rent","electricity","water","total","date_paid","status","note"])
            for r in rows:
                writer.writerow([r["payment_id"], r["name"], r["rent"], r["electricity"], r["water"], r["total"], r["date_paid"], r["status"], r["note"] or ""])
        messagebox.showinfo("Exported", f"Payments exported to {filepath}")
        self.db.execute("INSERT INTO reports (type, generated_date, filepath) VALUES (?,?,?)", ("Payments CSV", datetime.date.today().isoformat(), filepath))

    def _build_maintenance_tab(self):
        frame = self.tab_maintenance
        top = ttk.Frame(frame, padding=6)
        top.pack(side="top", fill="x")
        ttk.Button(top, text="New Request (with fee)", command=self.new_maintenance_dialog).pack(side="left", padx=4)
        ttk.Button(top, text="Refresh", command=self.load_maintenance).pack(side="left", padx=4)
        cols = ("request_id","tenant","description","priority","date_requested","status","staff","fee")
        self.maint_tree = ttk.Treeview(frame, columns=cols, show="headings", height=18)
        for c in cols:
            self.maint_tree.heading(c, text=c.title())
            self.maint_tree.column(c, width=120)
        self.maint_tree.pack(fill="both", expand=True, padx=8, pady=8)

    def load_maintenance(self):
        for r in self.maint_tree.get_children():
            self.maint_tree.delete(r)
        rows = self.maintenance_model.all()
        for row in rows:
            self.maint_tree.insert("", tk.END, values=(row["request_id"], row["tenant_name"], row["description"], row["priority"], row["date_requested"], row["status"], row["staff_name"] or "-", row["fee"] or 0))

    def new_maintenance_dialog(self):
        sel = self.tenants_tree.selection()
        tid = None
        if sel:
            item = self.tenants_tree.item(sel[0])["values"]
            tid = item[0]
        dlg = MaintenanceDialog(self, tenant_id=tid)
        self.wait_window(dlg)
        if dlg.saved:
            self.maintenance_model.create(dlg.tenant_id, dlg.description, dlg.priority, dlg.date_requested, dlg.status, dlg.assigned_staff, dlg.fee)
            messagebox.showinfo("Saved", "Maintenance request submitted")
            self.load_maintenance()

    def _build_reports_tab(self):
        frame = self.tab_reports
        top = ttk.Frame(frame, padding=6)
        top.pack(side="top", fill="x")
        ttk.Button(top, text="Generate Income Report (30 days)", command=self.report_income_30).pack(side="left", padx=4)
        ttk.Button(top, text="List Reports", command=self.list_reports).pack(side="left", padx=4)
        self.report_text = tk.Text(frame, wrap="none")
        self.report_text.pack(fill="both", expand=True, padx=8, pady=8)

    def list_reports(self):
        rows = self.db.query("SELECT * FROM reports ORDER BY report_id DESC")
        txt = "\n".join([f"{r['report_id']}: {r['type']} - {r['generated_date']} - {r['filepath']}" for r in rows])
        if not txt:
            txt = "No saved reports"
        self.report_text.delete(1.0, tk.END)
        self.report_text.insert(tk.END, txt)

    def report_income_30(self):
        total = self.payment_model.stats_sum(30) or 0
        txt = f"Income summary (last 30 days): ₱{total}\nGenerated: {datetime.date.today().isoformat()}"
        self.report_text.delete(1.0, tk.END)
        self.report_text.insert(tk.END, txt)
        if messagebox.askyesno("Save Report", "Save this report as text file?"):
            filepath = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text","*.txt")])
            if filepath:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(txt)
                self.db.execute("INSERT INTO reports (type, generated_date, filepath) VALUES (?,?,?)", ("Income 30 days", datetime.date.today().isoformat(), filepath))
                messagebox.showinfo("Saved", f"Report saved to {filepath}")

    def _build_recycle_tab(self):
        frame = self.tab_recycle
        top = ttk.Frame(frame, padding=6)
        top.pack(side="top", fill="x")
        ttk.Button(top, text="Refresh", command=self.load_deleted_tenants).pack(side="left", padx=4)
        ttk.Button(top, text="Restore Selected", command=self.restore_deleted_tenant).pack(side="left", padx=4)
        ttk.Button(top, text="Permanently Delete Selected", command=self.perm_delete).pack(side="left", padx=4)
        cols = ("deleted_id","tenant_id","name","unit_id","deleted_date","reason")
        self.recycle_tree = ttk.Treeview(frame, columns=cols, show="headings", height=18)
        for c in cols:
            self.recycle_tree.heading(c, text=c.title())
            self.recycle_tree.column(c, width=140)
        self.recycle_tree.pack(fill="both", expand=True, padx=8, pady=8)

    def load_deleted_tenants(self):
        for r in self.recycle_tree.get_children():
            self.recycle_tree.delete(r)
        rows = self.tenant_model.list_deleted()
        for r in rows:
            self.recycle_tree.insert("", tk.END, values=(r["deleted_id"], r["tenant_id"], r["name"], r["unit_id"], r["deleted_date"], r["reason"]))

    def restore_deleted_tenant(self):
        sel = self.recycle_tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Select a deleted tenant to restore")
            return
        item = self.recycle_tree.item(sel[0])["values"]
        deleted_id = item[0]
        new_tid = self.tenant_model.restore(deleted_id)
        if new_tid:
            messagebox.showinfo("Restored", f"Tenant restored with new tenant_id: {new_tid}")
            self.load_tenants()
            self.load_deleted_tenants()
        else:
            messagebox.showerror("Error", "Failed to restore tenant")

    def perm_delete(self):
        sel = self.recycle_tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Select a deleted tenant to permanently delete")
            return
        item = self.recycle_tree.item(sel[0])["values"]
        deleted_id = item[0]
        if messagebox.askyesno("Confirm", "Permanently delete this record? This cannot be undone."):
            self.db.execute("DELETE FROM deleted_tenants WHERE deleted_id=?", (deleted_id,))
            messagebox.showinfo("Deleted", "Record permanently deleted")
            self.load_deleted_tenants()

    def change_password_dialog(self):
        curpw = simpledialog.askstring("Change Password", "Enter current password:", show="*")
        if curpw is None:
            return
        rows = self.db.query("SELECT password FROM users WHERE username=?", (self.username,))
        if not rows:
            messagebox.showerror("Error", "User not found")
            return
        stored = rows[0]['password'] or ''
        try:
            ok = False
            if bcrypt and (stored.startswith('$2b$') or stored.startswith('$2y$')):
                ok = bcrypt.checkpw(curpw.encode('utf-8'), stored.encode('utf-8'))
            else:
                ok = (curpw == stored)
            if not ok:
                messagebox.showerror("Error", "Current password incorrect")
                return
            newp = simpledialog.askstring("Change Password", "Enter new password (min 6 chars):", show="*")
            if not newp or len(newp) < 6:
                messagebox.showwarning("Input", "Password not changed. Provide a password with at least 6 characters.")
                return
            confirm = simpledialog.askstring("Change Password", "Confirm new password:", show="*")
            if newp != confirm:
                messagebox.showerror("Error", "Passwords do not match")
                return
            if bcrypt:
                hashed = bcrypt.hashpw(newp.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                self.db.execute("UPDATE users SET password=? WHERE username=?", (hashed, self.username))
            else:
                self.db.execute("UPDATE users SET password=? WHERE username=?", (newp, self.username))
            messagebox.showinfo("Done", "Password changed")
        except Exception as e:
            messagebox.showerror("Error", f"Password change failed: {e}")

    def logout(self):
        if messagebox.askyesno("Logout", "Logout and return to login screen?"):
            self.destroy()
            login = LoginWindow(self.db)
            login.mainloop()

    def on_close(self):
        if messagebox.askyesno("Exit", "Exit application?"):
            try:
                self.db.close()
            except:
                pass
            self.destroy()

    def refresh_all(self):
        self.load_tenants()
        self.load_units()
        self.load_payments()
        self.load_maintenance()
        self.load_deleted_tenants()

    def load_units(self):
        self._units_cache = self.unit_model.all()

    def load_reports(self):
        return self.db.query("SELECT * FROM reports ORDER BY report_id DESC")

class TenantDialog(ctk.CTkToplevel):
    def __init__(self, parent, unit_model: UnitModel, tenant=None):
        super().__init__(parent)
        self.parent = parent
        self.unit_model = unit_model
        self.tenant = tenant
        self.saved = False
        self.name = ""
        self.contact = ""
        self.unit_id = None
        self.tenant_type = "Family"
        self.move_in = datetime.date.today().isoformat()
        self.guardian_name = ""
        self.guardian_contact = ""
        self.guardian_relation = ""
        self.emergency_contact = ""
        self.advance_paid = 0.0
        self.deposit_paid = 0.0
        self.build()

    def build(self):
        self.title("Tenant")
        self.geometry("620x520")
        frm = ctk.CTkFrame(self, corner_radius=8)
        frm.pack(fill="both", expand=True, padx=10, pady=10)
        ctk.CTkLabel(frm, text="Tenant Full Name").grid(row=0, column=0, sticky="w", pady=4, padx=6)
        self.name_e = ctk.CTkEntry(frm, width=360)
        self.name_e.grid(row=0, column=1, padx=6, pady=4)
        ctk.CTkLabel(frm, text="Contact").grid(row=1, column=0, sticky="w", pady=4, padx=6)
        self.contact_e = ctk.CTkEntry(frm, width=360)
        self.contact_e.grid(row=1, column=1, padx=6, pady=4)
        ctk.CTkLabel(frm, text="Unit").grid(row=2, column=0, sticky="w", pady=4, padx=6)
        units = self.unit_model.all()
        unit_list = [f"{u['unit_id']} - {u['unit_code']} ({u['type']}) - {u['status']}" for u in units]
        self.unit_var = tk.StringVar()
        self.unit_combo = ttk.Combobox(frm, values=unit_list, state="readonly", width=48, textvariable=self.unit_var)
        self.unit_combo.grid(row=2, column=1, padx=6, pady=4)
        ctk.CTkLabel(frm, text="Tenant Type").grid(row=3, column=0, sticky="w", pady=4, padx=6)
        self.type_combo = ttk.Combobox(frm, values=["Family","Solo","Dorm"], state="readonly")
        self.type_combo.current(0)
        self.type_combo.grid(row=3, column=1, padx=6, pady=4)
        ctk.CTkLabel(frm, text="Move in date (YYYY-MM-DD)").grid(row=4, column=0, sticky="w", pady=4, padx=6)
        self.movein_e = ctk.CTkEntry(frm, width=360)
        self.movein_e.insert(0, self.move_in)
        self.movein_e.grid(row=4, column=1, padx=6, pady=4)
        ctk.CTkLabel(frm, text="Guardian Full Name").grid(row=5, column=0, sticky="w", pady=4, padx=6)
        self.guard_e = ctk.CTkEntry(frm, width=360)
        self.guard_e.grid(row=5, column=1, padx=6, pady=4)
        ctk.CTkLabel(frm, text="Guardian Contact").grid(row=6, column=0, sticky="w", pady=4, padx=6)
        self.guard_contact_e = ctk.CTkEntry(frm, width=360)
        self.guard_contact_e.grid(row=6, column=1, padx=6, pady=4)
        ctk.CTkLabel(frm, text="Guardian Relation").grid(row=7, column=0, sticky="w", pady=4, padx=6)
        self.guard_rel_e = ctk.CTkEntry(frm, width=360)
        self.guard_rel_e.grid(row=7, column=1, padx=6, pady=4)
        ctk.CTkLabel(frm, text="Emergency Contact").grid(row=8, column=0, sticky="w", pady=4, padx=6)
        self.emer_e = ctk.CTkEntry(frm, width=360)
        self.emer_e.grid(row=8, column=1, padx=6, pady=4)
        ctk.CTkLabel(frm, text="Advance Paid").grid(row=9, column=0, sticky="w", pady=4, padx=6)
        self.advance_e = ctk.CTkEntry(frm, width=120)
        self.advance_e.insert(0, "0")
        self.advance_e.grid(row=9, column=1, sticky="w", padx=6, pady=4)
        ctk.CTkLabel(frm, text="Deposit Paid").grid(row=9, column=1, sticky="e", padx=(0,140))
        self.deposit_e = ctk.CTkEntry(frm, width=120)
        self.deposit_e.insert(0, "0")
        self.deposit_e.grid(row=9, column=1, sticky="e", padx=6, pady=4)

        btnfrm = ctk.CTkFrame(frm)
        btnfrm.grid(row=12, column=0, columnspan=2, pady=12)
        ctk.CTkButton(btnfrm, text="Save", width=120, command=self.save).pack(side="left", padx=8)
        ctk.CTkButton(btnfrm, text="Cancel", width=120, command=self.destroy).pack(side="left", padx=8)

        if self.tenant:
            self.name_e.insert(0, self.tenant["name"])
            self.contact_e.insert(0, self.tenant["contact"])
            if self.tenant["unit_id"]:
                u = self.unit_model.get(self.tenant["unit_id"])
                if u:
                    self.unit_var.set(f"{u['unit_id']} - {u['unit_code']} ({u['type']}) - {u['status']}")
                else:
                    self.unit_var.set(f"{self.tenant['unit_id']}")
            if self.tenant.get("tenant_type"):
                self.type_combo.set(self.tenant.get("tenant_type"))
            self.guard_e.insert(0, self.tenant.get("guardian_name","") or "")
            self.guard_contact_e.insert(0, self.tenant.get("guardian_contact","") or "")
            self.guard_rel_e.insert(0, self.tenant.get("guardian_relation","") or "")
            self.emer_e.insert(0, self.tenant.get("emergency_contact","") or "")
            self.advance_e.delete(0, tk.END)
            self.advance_e.insert(0, str(self.tenant.get("advance_paid",0) or 0))
            self.deposit_e.delete(0, tk.END)
            self.deposit_e.insert(0, str(self.tenant.get("deposit_paid",0) or 0))

    def save(self):
        self.name = self.name_e.get().strip()
        self.contact = self.contact_e.get().strip()
        unit_str = self.unit_var.get()
        if unit_str:
            try:
                self.unit_id = int(unit_str.split(" - ")[0])
            except:
                self.unit_id = None
        self.tenant_type = self.type_combo.get()
        self.move_in = self.movein_e.get().strip() or datetime.date.today().isoformat()
        self.guardian_name = self.guard_e.get().strip()
        self.guardian_contact = self.guard_contact_e.get().strip()
        self.guardian_relation = self.guard_rel_e.get().strip()
        self.emergency_contact = self.emer_e.get().strip()
        try:
            self.advance_paid = float(self.advance_e.get().strip() or 0)
            self.deposit_paid = float(self.deposit_e.get().strip() or 0)
        except:
            messagebox.showwarning("Input", "Advance and Deposit must be numeric")
            return

        if not self.name or len(self.name.split()) < 2:
            messagebox.showwarning("Input", "Tenant full name required (first and last name).")
            return
        if self.tenant_type.lower() == "dorm":
            if not self.guardian_name or len(self.guardian_name.split()) < 2:
                messagebox.showwarning("Input", "Dorm tenants require guardian full name (first and last).")
                return
            if not self.guardian_contact or not self.guardian_contact.isdigit():
                messagebox.showwarning("Input", "Guardian contact must be numeric (digits only).")
                return
        else:
            if self.guardian_name and len(self.guardian_name.split()) < 2:
                messagebox.showwarning("Input", "If guardian name is provided, please enter full name (first and last).")
                return
            if self.guardian_contact and not self.guardian_contact.isdigit():
                messagebox.showwarning("Input", "Guardian contact must be numeric (digits only).")
                return
        if self.contact and not any(ch.isdigit() for ch in self.contact):
            messagebox.showwarning("Input", "Tenant contact should contain numbers (phone).")
            return
        self.saved = True
        self.destroy()

class PaymentDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.saved = False
        self.tenant_id = None
        self.rent = 0
        self.electricity = 0
        self.water = 0
        self.date_paid = datetime.date.today().isoformat()
        self.status = "Paid"
        self.note = ""
        self.build()

    def build(self):
        self.title("New Payment")
        self.geometry("420x360")
        frm = ctk.CTkFrame(self, corner_radius=8)
        frm.pack(fill="both", expand=True, padx=10, pady=10)
        ctk.CTkLabel(frm, text="Tenant ID (see Tenants tab)").grid(row=0, column=0, sticky="w", pady=6, padx=6)
        self.tenant_e = ctk.CTkEntry(frm, width=220)
        self.tenant_e.grid(row=0, column=1, padx=6, pady=6)
        ctk.CTkLabel(frm, text="Rent").grid(row=1, column=0, sticky="w", pady=6, padx=6)
        self.rent_e = ctk.CTkEntry(frm, width=220)
        self.rent_e.grid(row=1, column=1, padx=6, pady=6)
        ctk.CTkLabel(frm, text="Electricity").grid(row=2, column=0, sticky="w", pady=6, padx=6)
        self.elec_e = ctk.CTkEntry(frm, width=220)
        self.elec_e.grid(row=2, column=1, padx=6, pady=6)
        ctk.CTkLabel(frm, text="Water").grid(row=3, column=0, sticky="w", pady=6, padx=6)
        self.water_e = ctk.CTkEntry(frm, width=220)
        self.water_e.grid(row=3, column=1, padx=6, pady=6)
        ctk.CTkLabel(frm, text="Status (Paid/Overdue/Refund)").grid(row=4, column=0, sticky="w", pady=6, padx=6)
        self.status_combo = ttk.Combobox(frm, values=["Paid","Overdue","Refund"], state="readonly")
        self.status_combo.current(0)
        self.status_combo.grid(row=4, column=1, padx=6, pady=6)
        ctk.CTkLabel(frm, text="Note (optional)").grid(row=5, column=0, sticky="w", pady=6, padx=6)
        self.note_e = ctk.CTkEntry(frm, width=220)
        self.note_e.grid(row=5, column=1, padx=6, pady=6)
        btnfrm = ctk.CTkFrame(frm)
        btnfrm.grid(row=7, column=0, columnspan=2, pady=10)
        ctk.CTkButton(btnfrm, text="Save", width=120, command=self.save).pack(side="left", padx=6)
        ctk.CTkButton(btnfrm, text="Cancel", width=120, command=self.destroy).pack(side="left", padx=6)

    def save(self):
        try:
            self.tenant_id = int(self.tenant_e.get().strip())
        except:
            messagebox.showerror("Input", "Tenant ID must be number")
            return
        try:
            self.rent = float(self.rent_e.get().strip() or 0)
            self.electricity = float(self.elec_e.get().strip() or 0)
            self.water = float(self.water_e.get().strip() or 0)
        except:
            messagebox.showerror("Input", "Numeric values required for amounts")
            return
        self.status = self.status_combo.get()
        self.note = self.note_e.get().strip() or ""
        self.date_paid = datetime.date.today().isoformat()
        self.saved = True
        self.destroy()

class MaintenanceDialog(ctk.CTkToplevel):
    def __init__(self, parent, tenant_id=None):
        super().__init__(parent)
        self.parent = parent
        self.saved = False
        self.tenant_id = tenant_id
        self.description = ""
        self.priority = "Low"
        self.date_requested = datetime.date.today().isoformat()
        self.status = "Pending"
        self.assigned_staff = None
        self.fee = 0.0
        self.build()

    def build(self):
        self.title("Maintenance Request")
        self.geometry("520x380")
        frm = ctk.CTkFrame(self, corner_radius=8)
        frm.pack(fill="both", expand=True, padx=8, pady=8)
        ctk.CTkLabel(frm, text="Tenant ID (optional)").grid(row=0, column=0, sticky="w", pady=6, padx=6)
        self.tenant_e = ctk.CTkEntry(frm, width=220)
        if self.tenant_id:
            self.tenant_e.insert(0, str(self.tenant_id))
        self.tenant_e.grid(row=0, column=1, padx=6, pady=6)
        ctk.CTkLabel(frm, text="Description").grid(row=1, column=0, sticky="w", pady=6, padx=6)
        self.desc_e = ctk.CTkEntry(frm, width=320)
        self.desc_e.grid(row=1, column=1, padx=6, pady=6)
        ctk.CTkLabel(frm, text="Priority").grid(row=2, column=0, sticky="w", pady=6, padx=6)
        self.prio_combo = ttk.Combobox(frm, values=["Low","Medium","High"], state="readonly")
        self.prio_combo.current(0)
        self.prio_combo.grid(row=2, column=1, padx=6, pady=6)
        ctk.CTkLabel(frm, text="Assign Staff ID (optional)").grid(row=3, column=0, sticky="w", pady=6, padx=6)
        self.staff_e = ctk.CTkEntry(frm, width=220)
        self.staff_e.grid(row=3, column=1, padx=6, pady=6)
        ctk.CTkLabel(frm, text="Fee (if any)").grid(row=4, column=0, sticky="w", pady=6, padx=6)
        self.fee_e = ctk.CTkEntry(frm, width=220)
        self.fee_e.insert(0, "0")
        self.fee_e.grid(row=4, column=1, padx=6, pady=6)
        btnfrm = ctk.CTkFrame(frm)
        btnfrm.grid(row=5, column=0, columnspan=2, pady=10)
        ctk.CTkButton(btnfrm, text="Submit", width=120, command=self.save).pack(side="left", padx=6)
        ctk.CTkButton(btnfrm, text="Cancel", width=120, command=self.destroy).pack(side="left", padx=6)

    def save(self):
        try:
            tid = int(self.tenant_e.get().strip()) if self.tenant_e.get().strip() else None
        except:
            messagebox.showerror("Input", "Tenant ID must be numeric")
            return
        desc = self.desc_e.get().strip()
        if not desc:
            messagebox.showwarning("Input", "Description required")
            return
        try:
            fee_val = float(self.fee_e.get().strip() or 0)
        except:
            messagebox.showerror("Input", "Fee must be numeric")
            return
        self.tenant_id = tid
        self.description = desc
        self.priority = self.prio_combo.get()
        try:
            self.assigned_staff = int(self.staff_e.get().strip()) if self.staff_e.get().strip() else None
        except:
            self.assigned_staff = None
        self.fee = fee_val
        self.saved = True
        self.destroy()

def main():
    db = Database()
    app = LoginWindow(db)
    app.mainloop()
    db.close()

if __name__ == "__main__":
    main()