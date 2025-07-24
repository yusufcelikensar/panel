# -*- coding: utf-8 -*-
import os
import sys
import psycopg2
from psycopg2.extras import DictCursor
import json
import csv
import datetime
from datetime import date, datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, send_file
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import io
import base64
from functools import wraps
import pandas as pd
from fpdf import FPDF

# --- PostgreSQL (Neon) Bağlantı Bilgileri ---
PG_HOST = "ep-steep-hall-a2pd2igk-pooler.eu-central-1.aws.neon.tech"
PG_DATABASE = "neondb"
PG_USER = "neondb_owner"
PG_PASSWORD = "npg_PJVQt78okRwG"
PG_PORT = "5432"

# Kulüp Bilgileri
CLUB_NAME = "Girişimcilik Kulübü"
CLUB_WEBSITE = "girisimcilikkulubu.com"
CLUB_INSTAGRAM = "instagram.com/augirisimcilik"

# Puan Sistemi Sabitleri
ATTENDANCE_POINTS = 10
TICKET_PURCHASE_POINTS = 5
REFERRAL_POINTS = 15

# Flask Uygulaması
app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Güvenlik için değiştirin

# Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Dosya yükleme ayarları
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Klasörleri oluştur
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

class User(UserMixin):
    def __init__(self, id, username):
        self.id = str(id)  # ID'yi string olarak sakla
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    # user_id string olarak gelir, veritabanından kullanıcıyı yükle
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor(cursor_factory=DictCursor)
            cursor.execute("SELECT * FROM admin_users WHERE id = %s", (int(user_id),))
            user_data = cursor.fetchone()
            
            if user_data:
                return User(user_data['id'], user_data['username'])
        except Exception as e:
            print(f"Kullanıcı yükleme hatası: {e}")
        finally:
            conn.close()
    return None

def get_db_connection():
    """PostgreSQL veritabanı bağlantısı oluşturur"""
    try:
        conn = psycopg2.connect(
            host=PG_HOST,
            database=PG_DATABASE,
            user=PG_USER,
            password=PG_PASSWORD,
            port=PG_PORT,
            sslmode='require'
        )
        return conn
    except Exception as e:
        print(f"Veritabanı bağlantı hatası: {e}")
        return None

def init_db():
    """Veritabanı tablolarını oluşturur"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cursor = conn.cursor()
        
        # Üyeler Tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS members (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                uid TEXT NOT NULL UNIQUE,
                role TEXT,
                photo_path TEXT,
                membership_date DATE,
                department TEXT,
                year INTEGER,
                email TEXT UNIQUE,
                phone TEXT,
                interests TEXT,
                points INTEGER DEFAULT 0,
                referred_by_member_id INTEGER,
                FOREIGN KEY (referred_by_member_id) REFERENCES members (id) ON DELETE SET NULL 
            )""")
        
        # Etkinlikler Tablosu
        print("--- DEBUG init_db: events tablosu oluşturuluyor (PostgreSQL - Kapasite YOK)...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                event_date DATE,                      -- DATE tipi
                location TEXT,
                description TEXT,
                category TEXT,
                status TEXT DEFAULT 'Aktif'           -- Status sütunu eklendi
                -- capacity INTEGER,                 -- Kaldırıldı
                -- tickets_sold INTEGER DEFAULT 0    -- Kaldırıldı
            )""")
        print("--- DEBUG init_db: events tablosu için CREATE komutu çalıştırıldı.")
        
        # Mevcut events tablosuna status sütunu ekle (eğer yoksa)
        try:
            cursor.execute("ALTER TABLE events ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'Aktif';")
            print("--- DEBUG init_db: events tablosuna status sütunu eklendi (eğer yoksa).")
        except Exception as e:
            print(f"--- DEBUG init_db: status sütunu eklenirken hata: {e}")
        
        # Katılım Tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id SERIAL PRIMARY KEY,
                member_id INTEGER NOT NULL,
                event_id INTEGER NOT NULL,
                "timestamp" TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (member_id) REFERENCES members (id) ON DELETE CASCADE,
                FOREIGN KEY (event_id) REFERENCES events (id) ON DELETE CASCADE,
                UNIQUE (member_id, event_id) 
            )""")
        
        # Bilet Satışları Tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ticket_sales (
                id SERIAL PRIMARY KEY,
                event_id INTEGER NOT NULL,
                member_id INTEGER NOT NULL,
                sale_timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                ticket_type TEXT DEFAULT 'Standart',
                price_paid NUMERIC(10, 2),
                payment_method TEXT,
                notes TEXT,
                FOREIGN KEY (event_id) REFERENCES events (id) ON DELETE CASCADE,
                FOREIGN KEY (member_id) REFERENCES members (id) ON DELETE CASCADE
            )""")
        
        # Puan Geçmişi Tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS points_log (
                id SERIAL PRIMARY KEY,
                member_id INTEGER NOT NULL,
                points_earned INTEGER NOT NULL, 
                reason TEXT NOT NULL,          
                related_event_id INTEGER,      
                related_sale_id INTEGER,       
                log_timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,   
                FOREIGN KEY (member_id) REFERENCES members (id) ON DELETE CASCADE, 
                FOREIGN KEY (related_event_id) REFERENCES events (id) ON DELETE SET NULL, 
                FOREIGN KEY (related_sale_id) REFERENCES ticket_sales (id) ON DELETE SET NULL 
            )""")
        
        # Admin kullanıcı tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            )""")
        
        # Varsayılan admin kullanıcısı oluşturma kaldırıldı
        # admin_password = generate_password_hash('admin123')
        # cursor.execute("""
        #     INSERT INTO admin_users (username, password_hash) 
        #     VALUES ('admin', %s) 
        #     ON CONFLICT (username) DO NOTHING
        # """, (admin_password,))
        # Ekstra admin kullanıcıları
        yusuf_password = generate_password_hash('yusuf123')
        cursor.execute("""
            INSERT INTO admin_users (username, password_hash) 
            VALUES ('yusufensar', %s) 
            ON CONFLICT (username) DO NOTHING
        """, (yusuf_password,))
        asif_password = generate_password_hash('asif123')
        cursor.execute("""
            INSERT INTO admin_users (username, password_hash) 
            VALUES ('asifasadulayev', %s) 
            ON CONFLICT (username) DO NOTHING
        """, (asif_password,))
        
        conn.commit()
        return True
        
    except Exception as e:
        print(f"Veritabanı başlatma hatası: {e}")
        return False
    finally:
        conn.close()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Ana sayfa
@app.route('/')
@login_required
def index():
    conn = get_db_connection()
    if not conn:
        flash('Veritabanı bağlantı hatası', 'error')
        return render_template('error.html')
    
    try:
        cursor = conn.cursor(cursor_factory=DictCursor)
        
        # İstatistikler
        cursor.execute("SELECT COUNT(*) as count FROM members")
        total_members = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM events")
        total_events = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM attendance")
        total_attendances = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM ticket_sales")
        total_sales = cursor.fetchone()['count']
        
        # Yaklaşan etkinlikler
        cursor.execute("""
            SELECT * FROM events 
            WHERE event_date >= CURRENT_DATE 
            ORDER BY event_date ASC 
            LIMIT 5
        """)
        upcoming_events = cursor.fetchall()
        
        # Liderlik tablosu
        cursor.execute("""
            SELECT name, points, department 
            FROM members 
            ORDER BY points DESC 
            LIMIT 10
        """)
        leaderboard = cursor.fetchall()
        
        return render_template('index.html', 
                             total_members=total_members,
                             total_events=total_events,
                             total_attendances=total_attendances,
                             total_sales=total_sales,
                             upcoming_events=upcoming_events,
                             leaderboard=leaderboard,
                             club_name=CLUB_NAME)
                             
    except Exception as e:
        flash(f'Hata: {e}', 'error')
        return render_template('error.html')
    finally:
        conn.close()

# Giriş sayfası
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor(cursor_factory=DictCursor)
                cursor.execute("SELECT * FROM admin_users WHERE username = %s", (username,))
                user_data = cursor.fetchone()
                
                if user_data and check_password_hash(user_data['password_hash'], password):
                    user = User(user_data['id'], user_data['username'])
                    login_user(user)
                    next_page = request.args.get('next')
                    if next_page:
                        return redirect(next_page)
                    return redirect(url_for('index'))
                else:
                    flash('Geçersiz kullanıcı adı veya şifre', 'error')
            finally:
                conn.close()
        else:
            flash('Veritabanı bağlantı hatası', 'error')
    
    return render_template('login.html', club_name=CLUB_NAME)

# Çıkış
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Üyeler sayfası
@app.route('/members')
@login_required
def members():
    conn = get_db_connection()
    if not conn:
        flash('Veritabanı bağlantı hatası', 'error')
        return render_template('error.html')
    
    try:
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("""
            SELECT m.*, 
                   r.name as referrer_name,
                   COUNT(DISTINCT a.event_id) as events_attended,
                   COUNT(DISTINCT ts.id) as tickets_purchased
            FROM members m
            LEFT JOIN members r ON m.referred_by_member_id = r.id
            LEFT JOIN attendance a ON m.id = a.member_id
            LEFT JOIN ticket_sales ts ON m.id = ts.member_id
            GROUP BY m.id, r.name
            ORDER BY m.name
        """)
        members = cursor.fetchall()
        
        return render_template('members.html', members=members, club_name=CLUB_NAME)
        
    except Exception as e:
        flash(f'Hata: {e}', 'error')
        return render_template('error.html')
    finally:
        conn.close()

# Üye ekleme
@app.route('/members/add', methods=['GET', 'POST'])
@login_required
def add_member():
    if request.method == 'POST':
        name = request.form['name']
        uid = request.form['uid']
        email = request.form.get('email', '')
        if not email:
            email = None
        department = request.form.get('department', '')
        if not department:
            department = None
        year = request.form.get('year', '')
        if not year or not str(year).isdigit():
            year = None
        else:
            year = int(year)
        phone = request.form.get('phone', '')
        if not phone:
            phone = None
        interests = request.form.get('interests', '')
        if not interests:
            interests = None
        role = request.form.get('role', 'Aktif Üye')
        referred_by_member_id = request.form.get('referred_by_member_id')
        if not referred_by_member_id or not str(referred_by_member_id).isdigit():
            referred_by_member_id = None
        else:
            referred_by_member_id = int(referred_by_member_id)
        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO members (name, uid, email, department, year, phone, interests, role, membership_date, referred_by_member_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (name, uid, email, department, year, phone, interests, role, date.today(), referred_by_member_id))
                new_member_id_row = cursor.fetchone()
                new_member_id = new_member_id_row[0] if new_member_id_row else None
                # --- REFERANS PUAN EKLEME ---
                if referred_by_member_id is not None and new_member_id is not None:
                    try:
                        points_to_award = REFERRAL_POINTS
                        log_timestamp = datetime.now().isoformat()
                        # Yeni üyeye puan ekle
                        cursor.execute("UPDATE members SET points = points + %s WHERE id = %s", (points_to_award, new_member_id))
                        cursor.execute("INSERT INTO points_log (member_id, points_earned, reason, log_timestamp) VALUES (%s, %s, %s, %s)",
                                       (new_member_id, points_to_award, 'Referans ile katilim bonusu', log_timestamp))
                        # Referans üyeye puan ekle
                        cursor.execute("SELECT name FROM members WHERE id = %s", (new_member_id,))
                        new_member_name_row = cursor.fetchone()
                        new_member_name = new_member_name_row[0] if new_member_name_row else f"ID:{new_member_id}"
                        reason_referrer = f"Yeni uye referansi: {new_member_name}"
                        cursor.execute("UPDATE members SET points = points + %s WHERE id = %s", (points_to_award, referred_by_member_id))
                        cursor.execute("INSERT INTO points_log (member_id, points_earned, reason, log_timestamp) VALUES (%s, %s, %s, %s)",
                                       (referred_by_member_id, points_to_award, reason_referrer, log_timestamp))
                    except Exception as e:
                        conn.rollback()
                        flash(f'Referans puanları eklenirken hata: {e}', 'error')
                conn.commit()
                flash('Üye başarıyla eklendi', 'success')
                return redirect(url_for('members'))
            except Exception as e:
                flash(f'Üye eklenirken hata: {e}', 'error')
            finally:
                conn.close()
    return render_template('add_member.html', club_name=CLUB_NAME)

# Üye düzenleme
@app.route('/members/<int:member_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_member(member_id):
    conn = get_db_connection()
    if not conn:
        flash('Veritabanı bağlantı hatası', 'error')
        return render_template('error.html')
    try:
        cursor = conn.cursor(cursor_factory=DictCursor)
        if request.method == 'POST':
            name = request.form['name']
            uid = request.form['uid']
            email = request.form.get('email', '')
            if not email:
                email = None
            department = request.form.get('department', '')
            if not department:
                department = None
            year = request.form.get('year', '')
            if not year or not str(year).isdigit():
                year = None
            else:
                year = int(year)
            phone = request.form.get('phone', '')
            if not phone:
                phone = None
            interests = request.form.get('interests', '')
            if not interests:
                interests = None
            role = request.form.get('role', 'Aktif Üye')
            referred_by_member_id = request.form.get('referred_by_member_id')
            if not referred_by_member_id or not str(referred_by_member_id).isdigit():
                referred_by_member_id = None
            else:
                referred_by_member_id = int(referred_by_member_id)

            cursor.execute("""
                UPDATE members 
                SET name=%s, uid=%s, email=%s, department=%s, year=%s, phone=%s, interests=%s, role=%s, referred_by_member_id=%s
                WHERE id=%s
            """, (name, uid, email, department, year, phone, interests, role, referred_by_member_id, member_id))
            conn.commit()

            # --- REFERANS PUAN EKLEME ---
            if referred_by_member_id is None:
                pass
            elif referred_by_member_id is not None:
                try:
                    points_to_award = REFERRAL_POINTS
                    log_timestamp = datetime.now().isoformat()
                    # Üyeye puan ekle
                    cursor.execute("UPDATE members SET points = points + %s WHERE id = %s", (points_to_award, member_id))
                    cursor.execute("INSERT INTO points_log (member_id, points_earned, reason, log_timestamp) VALUES (%s, %s, %s, %s)",
                                   (member_id, points_to_award, 'Referans ile katilim bonusu', log_timestamp))
                    # Referans üyeye puan ekle
                    cursor.execute("SELECT name FROM members WHERE id = %s", (member_id,))
                    new_member_name_row = cursor.fetchone()
                    new_member_name = new_member_name_row['name'] if new_member_name_row else f"ID:{member_id}"
                    reason_referrer = f"Yeni uye referansi: {new_member_name}"
                    cursor.execute("UPDATE members SET points = points + %s WHERE id = %s", (points_to_award, referred_by_member_id))
                    cursor.execute("INSERT INTO points_log (member_id, points_earned, reason, log_timestamp) VALUES (%s, %s, %s, %s)",
                                   (referred_by_member_id, points_to_award, reason_referrer, log_timestamp))
                    conn.commit()
                    flash('Referans puanları başarıyla eklendi.', 'success')
                except Exception as e:
                    conn.rollback()
                    flash(f'Referans puanları eklenirken hata: {e}', 'error')

            flash('Üye başarıyla güncellendi', 'success')
            return redirect(url_for('members'))
        # Üye bilgilerini getir
        cursor.execute("SELECT m.*, r.name as referrer_name FROM members m LEFT JOIN members r ON m.referred_by_member_id = r.id WHERE m.id = %s", (member_id,))
        member = cursor.fetchone()
        if not member:
            flash('Üye bulunamadı', 'error')
            return redirect(url_for('members'))
        return render_template('edit_member.html', member=member, club_name=CLUB_NAME)
    except Exception as e:
        flash(f'Hata: {e}', 'error')
        return render_template('error.html')
    finally:
        conn.close()

# Üye silme
@app.route('/members/<int:member_id>/delete', methods=['POST'])
@login_required
def delete_member(member_id):
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM members WHERE id = %s", (member_id,))
            conn.commit()
            flash('Üye başarıyla silindi', 'success')
        except Exception as e:
            flash(f'Üye silinirken hata: {e}', 'error')
        finally:
            conn.close()
    
    return redirect(url_for('members'))

# Etkinlikler sayfası
@app.route('/events')
@login_required
def events():
    conn = get_db_connection()
    if not conn:
        flash('Veritabanı bağlantı hatası', 'error')
        return render_template('error.html')
    
    try:
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("""
            SELECT e.*, 
                   COUNT(DISTINCT a.member_id) as participants_count,
                   COUNT(DISTINCT ts.id) as tickets_sold
            FROM events e
            LEFT JOIN attendance a ON e.id = a.event_id
            LEFT JOIN ticket_sales ts ON e.id = ts.event_id
            GROUP BY e.id
            ORDER BY e.event_date DESC
        """)
        events = cursor.fetchall()
        
        return render_template('events.html', events=events, club_name=CLUB_NAME)
        
    except Exception as e:
        flash(f'Hata: {e}', 'error')
        return render_template('error.html')
    finally:
        conn.close()

# Etkinlik ekleme
@app.route('/events/add', methods=['GET', 'POST'])
@login_required
def add_event():
    if request.method == 'POST':
        name = request.form['name']
        event_date = request.form['event_date']
        location = request.form.get('location', '')
        description = request.form.get('description', '')
        category = request.form.get('category', '')
        
        conn = get_db_connection()
        if conn:
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO events (name, event_date, location, description, category)
                    VALUES (%s, %s, %s, %s, %s)
                """, (name, event_date, location, description, category))
                conn.commit()
                flash('Etkinlik başarıyla eklendi', 'success')
                return redirect(url_for('events'))
            except Exception as e:
                flash(f'Etkinlik eklenirken hata: {e}', 'error')
            finally:
                conn.close()
    
    return render_template('add_event.html', club_name=CLUB_NAME)

# Etkinlik düzenleme
@app.route('/events/<int:event_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_event(event_id):
    conn = get_db_connection()
    if not conn:
        flash('Veritabanı bağlantı hatası', 'error')
        return render_template('error.html')
    
    try:
        cursor = conn.cursor(cursor_factory=DictCursor)
        
        if request.method == 'POST':
            name = request.form['name']
            event_date = request.form['event_date']
            location = request.form.get('location', '')
            description = request.form.get('description', '')
            category = request.form.get('category', '')
            
            cursor.execute("""
                UPDATE events 
                SET name=%s, event_date=%s, location=%s, description=%s, category=%s
                WHERE id=%s
            """, (name, event_date, location, description, category, event_id))
            conn.commit()
            flash('Etkinlik başarıyla güncellendi', 'success')
            return redirect(url_for('events'))
        
        # Etkinlik bilgilerini getir
        cursor.execute("SELECT * FROM events WHERE id = %s", (event_id,))
        event = cursor.fetchone()
        
        if not event:
            flash('Etkinlik bulunamadı', 'error')
            return redirect(url_for('events'))
        
        return render_template('edit_event.html', event=event, club_name=CLUB_NAME)
        
    except Exception as e:
        flash(f'Hata: {e}', 'error')
        return render_template('error.html')
    finally:
        conn.close()

# Etkinlik silme
@app.route('/events/<int:event_id>/delete', methods=['POST'])
@login_required
def delete_event(event_id):
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM events WHERE id = %s", (event_id,))
            conn.commit()
            flash('Etkinlik başarıyla silindi', 'success')
        except Exception as e:
            flash(f'Etkinlik silinirken hata: {e}', 'error')
        finally:
            conn.close()
    
    return redirect(url_for('events'))

# Katılım kaydetme
@app.route('/attendance', methods=['GET', 'POST'])
def attendance():
    selected_event_id = request.args.get('selected_event_id')
    if request.method == 'POST':
        member_search = request.form.get('member_search')
        event_id = request.form.get('event_id')
        print('DEBUG attendance:', 'member_search:', member_search, 'event_id:', event_id)
        if not member_search or not event_id:
            flash('Üye ve etkinlik seçimi gerekli', 'error')
            return redirect(url_for('attendance', selected_event_id=event_id or ''))
        conn = get_db_connection()
        if not conn:
            flash('Veritabanı bağlantı hatası', 'error')
            return redirect(url_for('attendance', selected_event_id=event_id or ''))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM members WHERE uid = %s", (member_search,))
            member = cursor.fetchone()
            if not member:
                flash('Üye bulunamadı', 'error')
                return redirect(url_for('attendance', selected_event_id=event_id or ''))
            member_id = member[0]
            # Önce bilet kontrolü: Üye bu etkinlik için bilet almış mı?
            cursor.execute("SELECT id FROM ticket_sales WHERE member_id = %s AND event_id = %s", (member_id, event_id))
            ticket = cursor.fetchone()
            if not ticket:
                flash('Bu üyenin bu etkinlik için bileti yok. Önce bilet satışı yapılmalı!', 'error')
                return redirect(url_for('attendance', selected_event_id=event_id or ''))
            cursor.execute("""
                SELECT id FROM attendance 
                WHERE member_id = %s AND event_id = %s
            """, (member_id, event_id))
            existing = cursor.fetchone()
            if existing:
                flash('Bu üye zaten bu etkinliğe katılmış.', 'error')
                return redirect(url_for('attendance', selected_event_id=event_id or ''))
            cursor.execute("""
                INSERT INTO attendance (member_id, event_id)
                VALUES (%s, %s)
            """, (member_id, event_id))
            # Üyenin puanını artır
            cursor.execute("UPDATE members SET points = points + %s WHERE id = %s", (ATTENDANCE_POINTS, member_id))
            # Puan logu ekle
            cursor.execute(
                "INSERT INTO points_log (member_id, points_earned, reason, related_event_id) VALUES (%s, %s, %s, %s)",
                (member_id, ATTENDANCE_POINTS, 'Etkinlik katılımı', event_id)
            )
            conn.commit()
            flash('Katılım kaydedildi', 'success')
            return redirect(url_for('attendance', selected_event_id=event_id))
        except Exception as e:
            flash(f'Hata oluştu: {str(e)}', 'error')
            return redirect(url_for('attendance', selected_event_id=event_id or ''))
        finally:
            conn.close()
    # GET request - normal attendance sayfası
    conn = get_db_connection()
    if not conn:
        flash('Veritabanı bağlantı hatası', 'error')
        return render_template('error.html')
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, event_date FROM events ORDER BY event_date DESC")
        rows = cursor.fetchall()
        events = [
            {
                'id': row[0],
                'name': row[1],
                'event_date': row[2]
            } for row in rows
        ]
        cursor.execute("""
            SELECT a.id, m.name as member_name, e.name as event_name, a.timestamp, m.id as member_id, e.id as event_id
            FROM attendance a
            JOIN members m ON a.member_id = m.id
            JOIN events e ON a.event_id = e.id
            ORDER BY a.timestamp DESC, a.id DESC
            LIMIT 50
        """)
        rows = cursor.fetchall()
        recent_attendance = [
            {
                'id': r[0],
                'member_name': r[1],
                'event_name': r[2],
                'timestamp': r[3],
                'member_id': r[4],
                'event_id': r[5],
            } for r in rows
        ]
        conn.close()
        return render_template('attendance.html', events=events, recent_attendance=recent_attendance, selected_event_id=selected_event_id)
    except Exception as e:
        conn.close()
        return f"Hata oluştu: {str(e)}", 500

# Katılım silme
@app.route('/attendance/delete/<int:member_id>/<int:event_id>', methods=['POST'])
@login_required
def delete_attendance(member_id, event_id):
    conn = get_db_connection()
    if not conn:
        flash('Veritabanı bağlantı hatası', 'error')
        return redirect(url_for('attendance'))
    try:
        cursor = conn.cursor()
        # Katılımı sil
        cursor.execute("DELETE FROM attendance WHERE member_id = %s AND event_id = %s", (member_id, event_id))
        # Puanı geri al
        cursor.execute("UPDATE members SET points = points - %s WHERE id = %s", (ATTENDANCE_POINTS, member_id))
        # Puan logunu sil
        cursor.execute("DELETE FROM points_log WHERE member_id = %s AND related_event_id = %s AND reason = %s", (member_id, event_id, 'Etkinlik katılımı'))
        conn.commit()
        flash('Katılım kaydı silindi ve puan geri alındı.', 'success')
    except Exception as e:
        flash(f'Katılım silinirken hata: {e}', 'error')
        import traceback
        traceback.print_exc()
    finally:
        conn.close()
    return redirect(url_for('attendance'))

# Bilet satışları
@app.route('/ticket_sales', methods=['GET', 'POST'])
@login_required
def ticket_sales():
    conn = get_db_connection()
    if not conn:
        flash('Veritabanı bağlantı hatası', 'error')
        return render_template('error.html')
    
    try:
        cursor = conn.cursor(cursor_factory=DictCursor)
        
        if request.method == 'POST':
            member_input = request.form['member_search']
            if member_input.isdigit():
                cursor.execute("SELECT id FROM members WHERE uid = %s", (member_input,))
            else:
                cursor.execute("SELECT id FROM members WHERE LOWER(name) LIKE %s LIMIT 1", ('%' + member_input.lower() + '%',))
            member = cursor.fetchone()
            if not member:
                flash('Üye bulunamadı', 'error')
                return redirect(url_for('ticket_sales'))
            
            event_id = request.form['event_id']
            ticket_type = request.form.get('ticket_type', 'Standart')
            price_paid = request.form.get('price_paid', 0)
            payment_method = request.form.get('payment_method', '')
            notes = request.form.get('notes', '')
            
            # Bilet satışı kaydet
            cursor.execute("""
                INSERT INTO ticket_sales (event_id, member_id, ticket_type, price_paid, payment_method, notes)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (event_id, member['id'], ticket_type, price_paid, payment_method, notes))
            
            sale_id = cursor.fetchone()[0]
            
            # Puan ekle
            cursor.execute("""
                UPDATE members SET points = points + %s WHERE id = %s
            """, (TICKET_PURCHASE_POINTS, member['id']))
            
            # Puan logu
            cursor.execute("""
                INSERT INTO points_log (member_id, points_earned, reason, related_sale_id)
                VALUES (%s, %s, %s, %s)
            """, (member['id'], TICKET_PURCHASE_POINTS, f'Bilet satın alma', sale_id))
            
            conn.commit()
            flash('Bilet satışı başarıyla kaydedildi', 'success')
        
        # Etkinlikleri getir
        cursor.execute("SELECT * FROM events ORDER BY event_date DESC")
        rows = cursor.fetchall()
        # Dict olarak dönüştür
        events = [
            {
                'id': row[0],
                'name': row[1],
                'event_date': row[2],
                'location': row[3],
                'description': row[4],
                'category': row[5],
                'status': row[6] if len(row) > 6 else 'Aktif'
            } for row in rows
        ]
        
        # Son satışları getir
        cursor.execute("""
            SELECT ts.*, m.name as member_name, e.name as event_name
            FROM ticket_sales ts
            JOIN members m ON ts.member_id = m.id
            JOIN events e ON ts.event_id = e.id
            ORDER BY ts.sale_timestamp DESC
            LIMIT 20
        """)
        recent_sales = cursor.fetchall()
        
        return render_template('ticket_sales.html', events=events, recent_sales=recent_sales, club_name=CLUB_NAME)
        
    except Exception as e:
        flash(f'Hata: {e}', 'error')
        return render_template('error.html')
    finally:
        conn.close()

# Raporlar
@app.route('/reports')
@login_required
def reports():
    conn = get_db_connection()
    cursor = conn.cursor()
    # Üye istatistikleri
    cursor.execute("SELECT COUNT(*) FROM members")
    total_members = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM members WHERE role = 'Aktif Üye'")
    active_members = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM members WHERE role = 'Yönetici'")
    admin_members = cursor.fetchone()[0]
    cursor.execute("SELECT SUM(points) FROM members")
    total_points = cursor.fetchone()[0] or 0
    cursor.execute("SELECT AVG(points) FROM members")
    avg_points = cursor.fetchone()[0] or 0
    member_stats = {
        'total_members': total_members,
        'active_members': active_members,
        'admin_members': admin_members,
        'total_points': total_points,
        'avg_points': round(avg_points, 2)
    }
    # Etkinlik istatistikleri
    cursor.execute("SELECT COUNT(*) FROM events")
    total_events = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM events WHERE event_date >= CURRENT_DATE")
    upcoming_events = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM events WHERE event_date < CURRENT_DATE")
    past_events = cursor.fetchone()[0]
    event_stats = {
        'total_events': total_events,
        'upcoming_events': upcoming_events,
        'past_events': past_events
    }
    # Katılım istatistikleri
    cursor.execute("SELECT COUNT(*) FROM attendance")
    total_attendance = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT member_id) FROM attendance")
    unique_attendees = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT event_id) FROM attendance")
    unique_events = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT member_id) FROM attendance")
    unique_participants = cursor.fetchone()[0]
    attendance_stats = {
        'total_attendance': total_attendance,
        'total_attendances': total_attendance,  # olası template kullanımı için
        'unique_attendees': unique_attendees,
        'unique_events': unique_events,
        'unique_participants': unique_participants
    }
    conn.close()
    return render_template(
        'reports.html',
        club_name=CLUB_NAME,
        member_stats=member_stats,
        event_stats=event_stats,
        attendance_stats=attendance_stats
    )

@app.route('/api/report/attendance_monthly')
@login_required
def api_attendance_monthly():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DATE_TRUNC('month', a.timestamp) as month, COUNT(*) as count
        FROM attendance a
        GROUP BY month
        ORDER BY month
    """)
    data = cursor.fetchall()
    conn.close()
    return jsonify([{ 'month': str(row[0]), 'count': row[1] } for row in data])

@app.route('/api/report/points_pie')
@login_required
def api_points_pie():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT role, COUNT(*) FROM members GROUP BY role")
    data = cursor.fetchall()
    conn.close()
    return jsonify([{ 'role': row[0], 'count': row[1] } for row in data])

@app.route('/api/report/event_performance')
@login_required
def api_event_performance():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT e.name, COUNT(a.id) as attendance
        FROM events e
        LEFT JOIN attendance a ON e.id = a.event_id
        GROUP BY e.id
        ORDER BY attendance DESC
    """)
    data = cursor.fetchall()
    conn.close()
    return jsonify([{ 'event': row[0], 'attendance': row[1] } for row in data])

@app.route('/api/export/excel')
@login_required
def export_excel():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, uid, email, department, year, role, points FROM members ORDER BY id")
    members = cursor.fetchall()
    df = pd.DataFrame(members, columns=["ID", "Ad Soyad", "UID", "E-posta", "Bölüm", "Sınıf/Yıl", "Rol", "Puan"])
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Uyeler')
    output.seek(0)
    conn.close()
    return send_file(output, as_attachment=True, download_name="uyeler_raporu.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route('/api/export/pdf')
@login_required
def export_pdf():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, uid, email, department, year, role, points FROM members ORDER BY id")
    members = cursor.fetchall()
    pdf = FPDF()
    pdf.add_font('DejaVu', '', 'static/fonts/DejaVuSans.ttf', uni=True)
    pdf.set_font('DejaVu', '', 12)
    pdf.add_page()
    pdf.cell(200, 10, txt="Üye Raporu", ln=True, align='C')
    pdf.ln(10)
    col_widths = [10, 40, 30, 40, 30, 20, 20, 15]
    headers = ["ID", "Ad Soyad", "UID", "E-posta", "Bölüm", "Sınıf/Yıl", "Rol", "Puan"]
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 10, h, 1, 0, 'C')
    pdf.ln()
    for row in members:
        for i, val in enumerate(row):
            pdf.cell(col_widths[i], 10, str(val), 1, 0, 'C')
        pdf.ln()
    output = io.BytesIO()
    pdf.output(output)
    output.seek(0)
    return send_file(output, as_attachment=True, download_name="uyeler_raporu.pdf", mimetype="application/pdf")

@app.route('/api/export/emails')
@login_required
def export_emails():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM members WHERE email IS NOT NULL AND email <> ''")
    emails = [row[0] for row in cursor.fetchall()]
    conn.close()
    return jsonify({'emails': emails})

# API endpoint'leri
@app.route('/api/members')
@login_required
def api_members():
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Veritabanı bağlantı hatası'}), 500
    
    try:
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("SELECT * FROM members ORDER BY name")
        members = cursor.fetchall()
        return jsonify([dict(member) for member in members])
    finally:
        conn.close()

@app.route('/api/events')
@login_required
def api_events():
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Veritabanı bağlantı hatası'}), 500
    
    try:
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("SELECT * FROM events ORDER BY event_date DESC")
        events = cursor.fetchall()
        return jsonify([dict(event) for event in events])
    finally:
        conn.close()

@app.route('/api/member_search')
@login_required
def api_member_search():
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return jsonify([])
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    try:
        cursor = conn.cursor(cursor_factory=DictCursor)
        cursor.execute("SELECT id, name, uid FROM members WHERE LOWER(name) LIKE %s ORDER BY name LIMIT 10", (f'%{q.lower()}%',))
        results = cursor.fetchall()
        return jsonify([{'id': r['id'], 'name': r['name'], 'uid': r['uid']} for r in results])
    finally:
        conn.close()

@app.route('/members/adjust_points', methods=['POST'])
@login_required
def adjust_points():
    member_id = request.form.get('member_id')
    action = request.form.get('action')
    try:
        point_value = int(request.form.get('point_value', 0))
    except Exception:
        point_value = 0
    point_reason = request.form.get('point_reason', '').strip() or ("Manuel puan ekleme" if action == 'add' else "Manuel puan çıkarma")
    print('DEBUG adjust_points:', 'member_id:', member_id, 'action:', action, 'point_value:', point_value)
    if not member_id or not point_value or action not in ('add', 'subtract'):
        return 'Hatalı istek', 400
    conn = get_db_connection()
    if not conn:
        return 'Veritabanı hatası', 500
    try:
        cursor = conn.cursor()
        if action == 'add':
            cursor.execute("UPDATE members SET points = points + %s WHERE id = %s", (point_value, member_id))
            cursor.execute("INSERT INTO points_log (member_id, points_earned, reason) VALUES (%s, %s, %s)", (member_id, point_value, point_reason))
        else:
            cursor.execute("UPDATE members SET points = points - %s WHERE id = %s", (point_value, member_id))
            cursor.execute("INSERT INTO points_log (member_id, points_earned, reason) VALUES (%s, %s, %s)", (member_id, -point_value, point_reason))
        conn.commit()
        # AJAX isteği mi kontrolü
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return 'OK'
        else:
            from flask import redirect, url_for
            return redirect(url_for('edit_member', member_id=member_id))
    except Exception as e:
        import traceback
        traceback.print_exc()
        return 'Hata', 500
    finally:
        conn.close()

@app.route('/welcome_screen')
def welcome_screen():
    return '''
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="utf-8">
        <title>Hoşgeldiniz</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css" rel="stylesheet">
        <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@700;400&display=swap" rel="stylesheet">
        <style>
            html, body { height:100%; margin:0; padding:0; }
            body {
                min-height: 100vh;
                background: linear-gradient(135deg, #0d6efd 0%, #6f42c1 100%);
                font-family: 'Montserrat', sans-serif;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .welcome-card {
                background: rgba(255,255,255,0.97);
                border-radius: 2rem;
                box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.18);
                padding: 3rem 2.5rem 2.5rem 2.5rem;
                max-width: 420px;
                width: 100%;
                text-align: center;
                position: relative;
                animation: fadeIn 0.7s cubic-bezier(.4,0,.2,1);
            }
            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(40px); }
                to { opacity: 1; transform: translateY(0); }
            }
            .welcome-icon {
                font-size: 4.5rem;
                color: #0d6efd;
                margin-bottom: 1.2rem;
                filter: drop-shadow(0 2px 8px #0d6efd33);
            }
            .welcome-title {
                font-size: 2.2rem;
                font-weight: 700;
                color: #222;
                margin-bottom: 0.5rem;
            }
            .welcome-message {
                font-size: 1.3rem;
                color: #444;
                margin-bottom: 2rem;
                min-height: 2.5em;
                transition: color 0.3s;
            }
            .form-control {
                font-size: 1.3rem;
                padding: 0.8em 1.2em;
                border-radius: 1.2rem;
                border: 1.5px solid #0d6efd44;
                margin-bottom: 1.2rem;
                text-align: center;
                box-shadow: 0 2px 8px #0d6efd11;
            }
            .btn-check-uid {
                font-size: 1.2rem;
                padding: 0.7em 2.5em;
                border-radius: 1.2rem;
                background: linear-gradient(90deg, #0d6efd 60%, #6f42c1 100%);
                color: #fff;
                border: none;
                font-weight: 600;
                box-shadow: 0 2px 8px #0d6efd22;
                transition: background 0.2s, color 0.2s;
            }
            .btn-check-uid:hover {
                background: linear-gradient(90deg, #6f42c1 0%, #0d6efd 100%);
                color: #fff;
            }
            .btn-close-panel {
                position: absolute;
                top: 1.2rem;
                right: 1.2rem;
                background: none;
                border: none;
                font-size: 1.5rem;
                color: #888;
                transition: color 0.2s;
            }
            .btn-close-panel:hover {
                color: #0d6efd;
            }
        </style>
    </head>
    <body>
        <div class="welcome-card">
            <button id="closeBtn" class="btn-close-panel" title="Kapat"><i class="fas fa-times"></i></button>
            <div class="welcome-icon"><i class="fas fa-id-card"></i></div>
            <div class="welcome-title">Hoşgeldiniz</div>
            <div id="welcomeMessage" class="welcome-message">Lütfen kartı okutun veya UID girin</div>
            <input id="uidInput" type="text" maxlength="11" class="form-control" placeholder="UID veya kart okutun..." autofocus />
        </div>
        <script>
        document.getElementById('closeBtn').onclick = function() { window.close(); };
        function checkUid() {
            var uid = document.getElementById('uidInput').value.trim();
            var msg = document.getElementById('welcomeMessage');
            if (!uid) {
                msg.innerText = 'Lütfen UID girin veya kart okutun!';
                msg.style.color = '#c00';
                return;
            }
            msg.innerText = 'Sorgulanıyor...';
            msg.style.color = '#444';
            fetch(`/api/member_by_uid/${uid}`)
                .then(resp => resp.json())
                .then(data => {
                    if (data && data.name) {
                        msg.innerHTML = `<span style='color:#0d6efd;font-weight:700;font-size:1.5em;'>Hoşgeldiniz ${data.name} !</span>`;
                        // Üye bulundu, şimdi aktif etkinliklere katılımcı olarak ekle
                        addMemberToActiveEvent(data.id, data.name);
                    } else {
                        msg.innerHTML = `<span style='color:#c00;'>Üye bulunamadı!</span>`;
                    }
                })
                .catch(error => {
                    msg.innerHTML = `<span style='color:#c00;'>Hata oluştu!</span>`;
                });
        }
        
        function addMemberToActiveEvent(memberId, memberName) {
            // Önce aktif etkinlikleri getir
            fetch('/api/active_events')
                .then(resp => resp.json())
                .then(events => {
                    if (events && events.length > 0) {
                        // İlk aktif etkinliğe katılımcı olarak ekle
                        const eventId = events[0].id;
                        const eventName = events[0].name;
                        
                        fetch('/attendance', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/x-www-form-urlencoded',
                            },
                            body: `member_id=${memberId}&event_id=${eventId}`
                        })
                        .then(resp => resp.json())
                        .then(result => {
                            if (result.success) {
                                // Başarılı mesajı göster
                                setTimeout(() => {
                                    document.getElementById('welcomeMessage').innerHTML = 
                                        `<span style='color:#28a745;font-weight:700;font-size:1.2em;'>${memberName} - ${eventName} etkinliğine katılımcı olarak eklendi!</span>`;
                                }, 500);
                            } else {
                                // Hata mesajı göster
                                setTimeout(() => {
                                    document.getElementById('welcomeMessage').innerHTML = 
                                        `<span style='color:#ffc107;font-weight:700;font-size:1.2em;'>${result.message || 'Katılımcı eklenirken hata oluştu!'}</span>`;
                                }, 500);
                            }
                        })
                        .catch(error => {
                            console.error('Katılım kaydı hatası:', error);
                            setTimeout(() => {
                                document.getElementById('welcomeMessage').innerHTML = 
                                    `<span style='color:#c00;font-weight:700;font-size:1.2em;'>Katılımcı eklenirken hata oluştu!</span>`;
                            }, 500);
                        });
                    } else {
                        // Aktif etkinlik yok
                        setTimeout(() => {
                            document.getElementById('welcomeMessage').innerHTML = 
                                `<span style='color:#ffc107;font-weight:700;font-size:1.2em;'>Aktif etkinlik bulunamadı!</span>`;
                        }, 500);
                    }
                })
                .catch(error => {
                    console.error('Etkinlik bilgisi hatası:', error);
                    setTimeout(() => {
                        document.getElementById('welcomeMessage').innerHTML = 
                            `<span style='color:#c00;font-weight:700;font-size:1.2em;'>Etkinlik bilgisi alınırken hata oluştu!</span>`;
                    }, 500);
                });
        }
        document.getElementById('uidInput').addEventListener('keydown', function(e) {
            if (e.key === 'Enter') { checkUid(); }
        });
        // Otomatik arama - 11 karaktere ulaşınca veya her karakter girildiğinde
        document.getElementById('uidInput').addEventListener('input', function(e) {
            var uid = this.value.trim();
            // 11 karakterden fazla girilmesini engelle
            if (uid.length > 11) {
                this.value = uid.substring(0, 11);
                uid = this.value.trim();
            }
            if (uid.length >= 11) {
                // 11 karaktere ulaşınca otomatik ara
                setTimeout(checkUid, 100);
            } else if (uid.length > 0) {
                // Her karakter girildiğinde mesajı güncelle
                document.getElementById('welcomeMessage').innerText = 'UID okutuluyor...';
                document.getElementById('welcomeMessage').style.color = '#444';
            }
        });
        document.getElementById('uidInput').focus();
        </script>
    </body>
    </html>
    '''

@app.route('/api/member_by_uid/<uid>')
def get_member_by_uid(uid):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, email, phone, role, points, uid FROM members WHERE uid = %s", (uid,))
        member = cursor.fetchone()
        conn.close()
        
        if member:
            return jsonify({
                'id': member[0],
                'name': member[1],
                'email': member[2],
                'phone': member[3],
                'role': member[4],
                'points': member[5],
                'uid': member[6]
            })
        else:
            return jsonify(None)
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500

@app.route('/api/test_add_member')
def test_add_member():
    """Test amaçlı örnek üye ekler"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Veritabanı bağlantı hatası'})
    
    try:
        cursor = conn.cursor()
        
        # Test üyesi ekle
        cursor.execute("""
            INSERT INTO members (name, uid, email, department, role, points)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (uid) DO NOTHING
        """, ('Test Üye', '1234567890', 'test@example.com', 'Bilgisayar Mühendisliği', 'Aktif Üye', 0))
        
        conn.commit()
        return jsonify({'success': 'Test üyesi eklendi', 'uid': '1234567890'})
        
    except Exception as e:
        return jsonify({'error': str(e)})
    finally:
        conn.close()

@app.route('/api/test_add_member2')
def test_add_member2():
    """Test amaçlı ikinci örnek üye ekler"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Veritabanı bağlantı hatası'})
    
    try:
        cursor = conn.cursor()
        
        # İkinci test üyesi ekle
        cursor.execute("""
            INSERT INTO members (name, uid, email, department, role, points)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (uid) DO NOTHING
        """, ('Test Üye 2', '9876543210', 'test2@example.com', 'Bilgisayar Mühendisliği', 'Aktif Üye', 0))
        
        conn.commit()
        return jsonify({'success': 'Test üyesi 2 eklendi', 'uid': '9876543210'})
        
    except Exception as e:
        return jsonify({'error': str(e)})
    finally:
        conn.close()

@app.route('/api/active_events')
def get_active_events():
    """Aktif etkinlikleri getir"""
    conn = get_db_connection()
    if not conn:
        return jsonify([])
    
    try:
        cursor = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        
        cursor.execute("""
            SELECT id, name, event_date, location, description 
            FROM events 
            WHERE event_date = %s AND status = 'Aktif'
            ORDER BY id DESC
        """, (today,))
        
        events = []
        for row in cursor.fetchall():
            events.append({
                'id': row[0],
                'name': row[1],
                'date': row[2],
                'location': row[3],
                'description': row[4]
            })
        
        conn.close()
        return jsonify(events)
        
    except Exception as e:
        conn.close()
        return jsonify([])

@app.route('/api/test_add_event')
def test_add_event():
    """Test amaçlı bugünün tarihi için aktif etkinlik ekler"""
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Veritabanı bağlantı hatası'})
    
    try:
        cursor = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Test etkinliği ekle
        cursor.execute("""
            INSERT INTO events (name, event_date, status, location, description)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (name) DO NOTHING
        """, ('Test Etkinliği', today, 'Aktif', 'Test Lokasyon', 'Test açıklama'))
        
        conn.commit()
        return jsonify({'success': 'Test etkinliği eklendi', 'date': today})
        
    except Exception as e:
        return jsonify({'error': str(e)})
    finally:
        conn.close()

@app.route('/tutorial')
def tutorial():
    return render_template('tutorial.html')

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        new_password2 = request.form['new_password2']
        if new_password != new_password2:
            flash('Yeni şifreler eşleşmiyor.', 'error')
            return redirect(url_for('change_password'))
        conn = get_db_connection()
        if not conn:
            flash('Veritabanı bağlantı hatası', 'error')
            return redirect(url_for('change_password'))
        try:
            cursor = conn.cursor(cursor_factory=DictCursor)
            cursor.execute("SELECT * FROM admin_users WHERE id = %s", (int(current_user.id),))
            user_data = cursor.fetchone()
            if not user_data or not check_password_hash(user_data['password_hash'], current_password):
                flash('Mevcut şifre yanlış.', 'error')
                return redirect(url_for('change_password'))
            if len(new_password) < 6:
                flash('Yeni şifre en az 6 karakter olmalı.', 'error')
                return redirect(url_for('change_password'))
            new_hash = generate_password_hash(new_password)
            cursor.execute("UPDATE admin_users SET password_hash = %s WHERE id = %s", (new_hash, int(current_user.id)))
            conn.commit()
            flash('Şifre başarıyla değiştirildi.', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f'Hata: {e}', 'error')
            return redirect(url_for('change_password'))
        finally:
            conn.close()
    return render_template('change_password.html', club_name=CLUB_NAME)

if __name__ == '__main__':
    print("Veritabanı başlatılıyor...")
    if init_db():
        print("Veritabanı başarıyla başlatıldı")
        app.run(debug=True, host='0.0.0.0', port=5000)
    else:
        print("Veritabanı başlatılamadı!")
        sys.exit(1) 