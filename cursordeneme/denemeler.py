# -*- coding: utf-8 -*-
import sys
import psycopg2
from psycopg2.extras import DictCursor
import shutil
import os
import shutil
import os
import json
import csv
import datetime
from PyQt6.QtCore import Qt, QPoint, QDate, QDateTime, QUrl
from PyQt6.QtGui import QPixmap, QIcon, QColor, QKeySequence, QAction, QDesktopServices, QDoubleValidator
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QStackedWidget, QComboBox, QTableWidget,
    QTableWidgetItem, QMenu, QWidgetAction, QFileDialog, QDateEdit, QDialog,
    QTextEdit, QListWidget, QListWidgetItem, QFrame, QGridLayout, QGroupBox, QSizePolicy,
    QSpinBox, QHeaderView
)

# --- Matplotlib ve FPDF Kontrolü ---
try:
    import matplotlib; matplotlib.use('QtAgg'); import matplotlib.pyplot as plt
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure; MATPLOTLIB_AVAILABLE = True
except ImportError: MATPLOTLIB_AVAILABLE = False; FigureCanvas, Figure = object, object
try: from fpdf import FPDF, FPDFException; FPDF_AVAILABLE = True
except ImportError: FPDF_AVAILABLE = False; FPDF, FPDFException = object, Exception
import traceback

# --- PostgreSQL (Neon) Bağlantı Bilgileri ---
# DİKKAT: Şifreyi doğrudan koda yazmak güvensizdir!
PG_HOST = "ep-steep-hall-a2pd2igk-pooler.eu-central-1.aws.neon.tech" # KENDİ BİLGİNİZLE DEĞİŞTİRİN
PG_DATABASE = "neondb"                # KENDİ BİLGİNİZLE DEĞİŞTİRİN
PG_USER = "neondb_owner"              # KENDİ BİLGİNİZLE DEĞİŞTİRİN
PG_PASSWORD = "npg_PJVQt78okRwG" 
PG_PORT = "5432"                    # Genellikle 5432


SETTINGS_FILE = "settings.json"

# Kulüp Bilgileri (İstediğiniz gibi değiştirin)
CLUB_NAME = "Girişimcilik Kulübü"
CLUB_WEBSITE = "girisimcilikkulubu.com"
CLUB_INSTAGRAM = "instagram.com/augirisimcilik"

# PDF Font Ayarı (Standart fontlara geçtiğimiz için bu artık doğrudan kullanılmıyor olabilir)
DEFAULT_FONT_PATH = "DejaVuSans.ttf" 

# --- Puan Sistemi Sabitleri ---
ATTENDANCE_POINTS = 10      # Etkinlik katılımı için verilecek puan
TICKET_PURCHASE_POINTS = 5
REFERRAL_POINTS = 15  # Bilet alımı için verilecek puan (bir sonraki adımda kullanacağız)
# Bu değerleri istediğiniz zaman değiştirebilirsiniz.

# Varsayılan Ayarlar (settings.json dosyası için başlangıç değerleri)
DEFAULT_SETTINGS = {
    "logo_path": "", 
    "pdf_font_path": DEFAULT_FONT_PATH, # Ayarlarda hala tutulabilir
    "default_backup_path": "", 
    "default_export_path": "", 
    "default_member_role": "Aktif Üye", 
    "upcoming_events_limit": 5, 
    "theme": "light",
    # İleride puanları da ayarlardan okunabilir hale getirebiliriz:
    # "points_attendance": ATTENDANCE_POINTS,
    # "points_ticket": TICKET_PURCHASE_POINTS
}

def load_settings():
    """Ayarları JSON dosyasından yükler, yoksa varsayılanları döndürür."""
    if not os.path.exists(SETTINGS_FILE): return DEFAULT_SETTINGS.copy()
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f: settings = json.load(f)
        # Eksik ayarları varsayılanlarla tamamla
        for key, value in DEFAULT_SETTINGS.items(): settings.setdefault(key, value)
        print(f"Ayarlar '{SETTINGS_FILE}' dosyasından yüklendi."); return settings
    except (json.JSONDecodeError, IOError) as e: print(f"Ayarlar ('{SETTINGS_FILE}') okunurken hata: {e}. Varsayılanlar."); return DEFAULT_SETTINGS.copy()

def save_settings(settings_dict):
    """Ayarları JSON dosyasına kaydeder."""
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f: json.dump(settings_dict, f, ensure_ascii=False, indent=4)
        print(f"Ayarlar '{SETTINGS_FILE}' dosyasına kaydedildi."); return True
    except IOError as e: print(f"Ayarlar kaydedilirken hata: {e}"); QMessageBox.critical(None, "Hata", f"Ayarlar kaydedilemedi:\n{e}"); return False

# Bu fonksiyon artık AdminPanel dışında, global alanda duruyor
def init_db():
    """PostgreSQL veritabanını ve gerekli tabloları oluşturur/başlatır."""

    # Bağlantı bilgilerini global sabitlerden alıyoruz
    # (PG_HOST, PG_DATABASE, PG_USER, PG_PASSWORD, PG_PORT)
    conn = None # Başlangıçta bağlantı yok
    try:
        print("--- DEBUG init_db (PostgreSQL): Veritabanına bağlanılıyor...")
        conn = psycopg2.connect(
            host=PG_HOST,
            database=PG_DATABASE,
            user=PG_USER,
            password=PG_PASSWORD,
            port=PG_PORT
        )
        conn.autocommit = True # CREATE TABLE gibi komutlar için autocommit açık olabilir
        cursor = conn.cursor() 
        print("--- DEBUG init_db (PostgreSQL): Bağlantı başarılı. Tablolar oluşturuluyor/kontrol ediliyor...")

        # --- Tablo Oluşturma Komutları (PostgreSQL Sözdizimi) ---

        # Üyeler Tablosu
        print("--- DEBUG init_db: members tablosu oluşturuluyor (PostgreSQL)...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS members (
                id SERIAL PRIMARY KEY,                   -- Otomatik artan ID için SERIAL
                name TEXT NOT NULL,
                uid TEXT NOT NULL UNIQUE,
                role TEXT,
                photo_path TEXT,                      -- Dosya adı
                membership_date DATE,                 -- DATE tipi daha uygun olabilir
                department TEXT,
                year INTEGER,
                email TEXT UNIQUE,
                phone TEXT,
                interests TEXT,
                points INTEGER DEFAULT 0,             -- Puan sütunu
                referred_by_member_id INTEGER,        -- Referans sütunu
                FOREIGN KEY (referred_by_member_id) REFERENCES members (id) ON DELETE SET NULL 
            )""")
        print("--- DEBUG init_db: members tablosu için CREATE komutu çalıştırıldı.")

        # Etkinlikler Tablosu
        print("--- DEBUG init_db: events tablosu oluşturuluyor (PostgreSQL - Kapasite YOK)...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                event_date DATE,                      -- DATE tipi
                location TEXT,
                description TEXT,
                category TEXT 
                -- capacity INTEGER,                 -- Kaldırıldı
                -- tickets_sold INTEGER DEFAULT 0    -- Kaldırıldı
            )""")
        print("--- DEBUG init_db: events tablosu için CREATE komutu çalıştırıldı.")

        # Katılım Tablosu
        print("--- DEBUG init_db: attendance tablosu oluşturuluyor (PostgreSQL)...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id SERIAL PRIMARY KEY,
                member_id INTEGER NOT NULL,
                event_id INTEGER NOT NULL,
                "timestamp" TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, -- Zaman damgası için daha iyi tip + varsayılan
                FOREIGN KEY (member_id) REFERENCES members (id) ON DELETE CASCADE,
                FOREIGN KEY (event_id) REFERENCES events (id) ON DELETE CASCADE,
                UNIQUE (member_id, event_id) 
            )""")
         # Not: timestamp kelimesi SQL'de rezerve olabileceğinden çift tırnak içine almak iyi bir pratiktir.
        print("--- DEBUG init_db: attendance tablosu için CREATE komutu çalıştırıldı.")

        # Bilet Satışları Tablosu
        print("--- DEBUG init_db: ticket_sales tablosu oluşturuluyor (PostgreSQL)...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ticket_sales (
                id SERIAL PRIMARY KEY,
                event_id INTEGER NOT NULL,
                member_id INTEGER NOT NULL,
                sale_timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, -- Zaman damgası
                ticket_type TEXT DEFAULT 'Standart',
                price_paid NUMERIC(10, 2),          -- Ondalıklı sayılar için NUMERIC daha iyi olabilir
                payment_method TEXT,
                notes TEXT,
                FOREIGN KEY (event_id) REFERENCES events (id) ON DELETE CASCADE,
                FOREIGN KEY (member_id) REFERENCES members (id) ON DELETE CASCADE
            )""")
        print("--- DEBUG init_db: ticket_sales tablosu için CREATE komutu çalıştırıldı.")

        # Puan Geçmişi Tablosu
        print("--- DEBUG init_db: points_log tablosu oluşturuluyor (PostgreSQL)...")
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
        print("--- DEBUG init_db: points_log tablosu için CREATE komutu çalıştırıldı.")

        # İndexler (PostgreSQL'de genellikle otomatik olarak oluşturulur ama yine de ekleyebiliriz)
        print("--- DEBUG init_db: İndexler kontrol ediliyor/oluşturuluyor...")
        # PostgreSQL'de index oluşturma syntax'ı biraz farklı olabilir veya gerekmeyebilir.
        # Şimdilik bu kısmı atlayabilir veya PostgreSQL dokümantasyonuna bakabilirsiniz.
        # Örnek index (syntax SQLite ile aynı):
        # cursor.execute("CREATE INDEX IF NOT EXISTS idx_members_uid ON members (uid)") 
        print("--- DEBUG init_db: İndex adımı tamamlandı (veya atlandı).")

        print(f"--- DEBUG init_db (PostgreSQL): Veritabanı şeması başarıyla oluşturuldu/kontrol edildi. ---")

    except psycopg2.Error as e_pg: 
        print(f"!!! DB BAŞLATMA HATASI (PostgreSQL): {e_pg} !!!") 
        QMessageBox.critical(None, "DB Hatası", f"Veritabanı şeması oluşturulamadı: {e_pg}\nUygulama kapatılacak.")
        # Bağlantıyı kapatmayı dene (eğer açıksa)
        if conn:
            conn.close()
        sys.exit(f"Kritik DB Hatası: {e_pg}")
    except Exception as e_gen:
        print(f"!!! DB BAŞLATMA SIRASINDA BEKLENMEDİK HATA: {e_gen} !!!")
        QMessageBox.critical(None, "DB Hatası", f"Veritabanı başlatılırken beklenmedik hata: {e_gen}\nUygulama kapatılacak.")
        traceback.print_exc()
        if conn:
            conn.close()
        sys.exit(f"Kritik DB Hatası: {e_gen}")
    finally:
        # Bağlantıyı her zaman kapat (açılmışsa)
        if conn:
            conn.close()
            print("--- DEBUG init_db (PostgreSQL): Veritabanı bağlantısı kapatıldı. ---")
class LoginWindow(QWidget):
    """Kullanıcı giriş ekranı."""
    def __init__(self):
        super().__init__();
        self.setWindowTitle(f"{CLUB_NAME} - Admin Girişi");
        self.setGeometry(100, 100, 320, 240);
        self.admin_panel = None # AdminPanel referansı, henüz yok
        self.settings = load_settings();
        self.apply_login_style(self.settings.get("theme", "light")) # Temayı uygula

        layout = QVBoxLayout();
        layout.setContentsMargins(20, 20, 20, 20);
        layout.setSpacing(10);

        # Logo
        self.logo_label = QLabel();
        self.load_logo(); # Logoyu ayarlardan yükle
        layout.addWidget(self.logo_label, alignment=Qt.AlignmentFlag.AlignCenter);
        layout.addSpacing(10);

        # Giriş Alanları
        self.username_label = QLabel("Kullanıcı Adı:");
        self.username_input = QLineEdit();
        self.password_label = QLabel("Şifre:");
        self.password_input = QLineEdit();
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password);
        self.password_input.returnPressed.connect(self.login); # Enter ile giriş

        # Giriş Butonu
        self.login_button = QPushButton("Giriş Yap");
        self.login_button.clicked.connect(self.login);

        layout.addWidget(self.username_label);
        layout.addWidget(self.username_input);
        layout.addWidget(self.password_label);
        layout.addWidget(self.password_input);
        layout.addSpacing(15);
        layout.addWidget(self.login_button);
        self.setLayout(layout)

    def load_logo(self):
        """Ayarlarda belirtilen logo dosyasını yükler."""
        logo_path = self.settings.get('logo_path', ''); logo_loaded = False
        if logo_path and os.path.exists(logo_path):
            try: logo_pixmap = QPixmap(logo_path);
            except Exception as e: print(f"Logo QPixmap hatası: {e}"); logo_pixmap = None # Hata durumunda None

            if logo_pixmap and not logo_pixmap.isNull():
                self.logo_label.setPixmap(logo_pixmap.scaledToWidth(100, Qt.TransformationMode.SmoothTransformation));
                logo_loaded = True
            else: print(f"Uyarı: Logo yüklenemedi veya geçersiz ({logo_path})")
        if not logo_loaded: self.logo_label.setText("Logo") # Logo yoksa veya yüklenemezse metin göster

    def apply_login_style(self, theme):
        """Açık veya koyu tema stilini uygular."""
        light_style = """
            QWidget { background-color: #f0f4f8; font-family: Arial; font-size: 14px; }
            QLabel { color: #333; padding-bottom: 2px; }
            QLineEdit { background-color: white; border: 1px solid #ccc; padding: 6px; border-radius: 4px; min-height: 24px; }
            QPushButton { background-color: #007bff; color: white; border: none; padding: 10px 18px; border-radius: 5px; min-height: 24px; font-weight: bold; }
            QPushButton:hover { background-color: #0056b3; }
        """
        dark_style = """
            QWidget { background-color: #2d2d2d; font-family: Arial; font-size: 14px; color: #e0e0e0;}
            QLabel { color: #e0e0e0; padding-bottom: 2px; }
            QLineEdit { background-color: #3c3c3c; border: 1px solid #555; padding: 6px; border-radius: 4px; min-height: 24px; color: #e0e0e0; }
            QPushButton { background-color: #005cbf; color: white; border: none; padding: 10px 18px; border-radius: 5px; min-height: 24px; font-weight: bold; }
            QPushButton:hover { background-color: #00418c; }
        """
        if theme == "dark": self.setStyleSheet(dark_style)
        else: self.setStyleSheet(light_style)

    def login(self):
        """Giriş bilgilerini kontrol eder."""
        username = self.username_input.text().strip(); password = self.password_input.text().strip()
        # !!! GÜVENLİK UYARISI: Bu yöntem kesinlikle güvenli değildir. !!!
        # Gerçek bir uygulamada şifre hashlenmeli ve güvenli bir şekilde saklanmalıdır.
        if username == "yusuf" and password == "1234":
            self.accept_login() # Giriş başarılı
        else:
            QMessageBox.warning(self, "Hata", "Yanlış kullanıcı adı veya şifre!")
            self.password_input.clear() # Şifre alanını temizle

    # LoginWindow sınıfı içinde:
    def accept_login(self):
        """Giriş başarılı olduğunda AdminPanel'i açar."""
        print("DEBUG: Giriş başarılı, accept_login çalışıyor...")
        self.hide() # Login penceresini gizle

        # AdminPanel nesnesi daha önce oluşturulmuş mu kontrol et
        if not hasattr(self, 'admin_panel') or self.admin_panel is None:
            print("DEBUG: AdminPanel ilk kez oluşturuluyor...")
            try:
                # ÖNEMLİ: init_db() çağrısı burada olmamalı. 
                # Veritabanı şeması ya program başında ya da ilk DB bağlantısı 
                # kurulduğunda (AdminPanel __init__ içinde) kontrol edilmeli.
                # Eğer __main__ bloğunda init_db() çağrısı yoksa ve DB yoksa,
                # AdminPanel __init__ içindeki ilk bağlantı hataya düşebilir.
                # Ancak şu anki akışımızda AdminPanel bağlantıyı kuruyor.
                # init_db() # Bu satırı burada ÇAĞIRMIYORUZ.

                # AdminPanel sınıfının aynı dosyada olduğunu varsayıyoruz.
                # Eğer farklı dosyadaysa import düzgün yapılmalı.
                # from __main__ import AdminPanel # Bu satır yerine sınıfın zaten tanımlı olduğunu varsayalım
                
                # AdminPanel'i oluştur (Bu __init__ içinde veritabanı bağlantısı kurulacak)
                self.admin_panel = AdminPanel(self, self.settings) 
                
                # AdminPanel başarıyla oluşturulduysa göster ve ilk güncellemeleri yap
                self.admin_panel.show()
                
                # Bu çağrılar artık AdminPanel __init__ sonunda yapıldığı için burada tekrarlamaya gerek yok
                # if hasattr(self.admin_panel, 'update_main_page_stats'): self.admin_panel.update_main_page_stats() 
                # if hasattr(self.admin_panel, 'update_leaderboard'): self.admin_panel.update_leaderboard()

                print("DEBUG: AdminPanel başarıyla oluşturuldu ve gösterildi.")

            except ImportError:
                 # Bu hata artık olmamalı eğer AdminPanel aynı dosyadaysa
                 QMessageBox.critical(None, "Import Hatası", "AdminPanel sınıfı bulunamadı.")
                 print("HATA: AdminPanel sınıfı import edilemedi.")
                 self.show() # Hata olursa login penceresini tekrar göster
            except Exception as e:
                 # AdminPanel __init__ sırasında bir hata oluşursa (örn: DB bağlantı hatası)
                 QMessageBox.critical(None, "Kritik Hata", f"Admin paneli başlatılamadı: {e}\nUygulama kapatılacak.")
                 print(f"HATA: AdminPanel başlatılamadı: {e}")
                 traceback.print_exc() # Hatanın detayını yazdır
                 QApplication.instance().quit() # Uygulamayı güvenli kapat
                 sys.exit(f"AdminPanel başlatma hatası: {e}")
        
        else: # Admin panel zaten varsa (örneğin çıkış yapılıp tekrar girildiyse)
            print("DEBUG: Mevcut AdminPanel tekrar gösteriliyor...")
            try:
                # Veritabanı bağlantısını kontrol et ve gerekirse yeniden kur
                # get_cursor metodu bunu zaten yapıyor olmalı, ama burada da yapabiliriz.
                if self.admin_panel.db_connection is None or self.admin_panel.db_connection.closed != 0:
                    print("DEBUG accept_login: DB bağlantısı kapalı, yeniden kuruluyor...")
                    # Bağlantı bilgilerini global sabitlerden al
                    self.admin_panel.db_connection = psycopg2.connect(
                        host=PG_HOST, database=PG_DATABASE, user=PG_USER,
                        password=PG_PASSWORD, port=PG_PORT, sslmode='require'
                    )
                    self.admin_panel.db_connection.autocommit = False
                    print("DEBUG accept_login: Veritabanı bağlantısı başarıyla yeniden kuruldu.")
                else:
                     print("DEBUG accept_login: Mevcut DB bağlantısı açık.")

                # AdminPanel'deki bilgileri ve görünümü güncelle
                self.admin_panel.settings = load_settings() 
                self.admin_panel.apply_style() 
                if hasattr(self.admin_panel, 'update_main_page_logo'): self.admin_panel.update_main_page_logo() 
                if hasattr(self.admin_panel, 'update_main_page_stats'): self.admin_panel.update_main_page_stats() 
                if hasattr(self.admin_panel, 'update_leaderboard'): self.admin_panel.update_leaderboard() 
                
                self.admin_panel.show() # Paneli tekrar göster
                print("DEBUG: Mevcut AdminPanel başarıyla tekrar gösterildi.")

            except Exception as e:
                 QMessageBox.critical(None, "Hata", f"Admin paneli tekrar gösterilirken hata: {e}")
                 print(f"HATA: Admin paneli tekrar gösterilemedi: {e}")
                 traceback.print_exc()
                 self.show() # Hata olursa login'e dön

    def clear_login_fields(self):
        """Giriş alanlarını temizler."""
        self.username_input.clear();
        self.password_input.clear()

    def closeEvent(self, event):
        """Login penceresi kapatıldığında uygulamayı tamamen kapatır."""
        if self.admin_panel and self.admin_panel.isVisible():
            self.admin_panel.close() # Admin paneli açıksa onu da kapat
        QApplication.instance().quit(); # Tüm uygulamayı sonlandır
        event.accept()

# --- Grafik Penceresi ---
class ChartDialog(QDialog):
    """Matplotlib grafiği göstermek için kullanılan diyalog penceresi."""
    def __init__(self, parent=None):
        super().__init__(parent);
        self.setWindowTitle("Grafik");
        self.setMinimumSize(600, 450);
        layout = QVBoxLayout(self)
        if MATPLOTLIB_AVAILABLE:
            self.figure = Figure(figsize=(5, 4), dpi=100);
            self.canvas = FigureCanvas(self.figure); # Matplotlib çizim alanı
            layout.addWidget(self.canvas)
        else:
            # Matplotlib yoksa uyarı göster
            layout.addWidget(QLabel("Grafik oluşturmak için Matplotlib kütüphanesi kurulu değil."))

    # AdminPanel sınıfının içine (diğer metodlarla birlikte):
 
    def plot_pie(self, labels, sizes, title="Pasta Grafik"):
        """Verilen etiketler ve boyutlarla pasta grafik çizer."""
        if not MATPLOTLIB_AVAILABLE: return # Kütüphane yoksa çizme
        try:
            self.figure.clear(); # Önceki çizimi temizle
            ax = self.figure.add_subplot(111)
            # Yüzdesi %3'ten küçük olan dilimleri gösterme (autopct)
            wedges, texts, autotexts = ax.pie(sizes, autopct=lambda p: '{:.1f}%'.format(p) if p > 3 else '', startangle=90, pctdistance=0.85)
            ax.set_title(title);
            ax.axis('equal') # Daire şeklinde görünmesini sağla
            # Lejantı grafik alanının dışına, sağına yerleştir
            self.figure.legend(wedges, labels, title="Kategoriler", loc="center left", bbox_to_anchor=(1, 0.5))
            # Lejantın sığması için grafik alanını ayarla (sağda %20 boşluk)
            self.figure.tight_layout(rect=[0, 0, 0.8, 1])
            self.canvas.draw() # Grafiği çiz/güncelle
        except Exception as e:
            print(f"Pasta grafik çizilirken hata: {e}")
            QMessageBox.critical(self, "Grafik Hatası", f"Pasta grafik oluşturulamadı: {e}")

# --- PDF Yardımcı Sınıfı (FPDF kullanarak) ---
# --- PDF Yardımcı Sınıfı (FPDF kullanarak - STANDART FONT VERSİYONU) ---
# Bu sınıfın çalışması için dosyanızın başında "from fpdf import FPDF, FPDFException" satırının
# ve "FPDF_AVAILABLE = True" (veya False) değişkeninin olması gerekir.

# --- PDF Yardımcı Sınıfı (FPDF kullanarak - MAKSİMUM BASİTLEŞTİRİLMİŞ FONT AYARI) ---
class PDF(FPDF):
    def __init__(self, orientation='P', unit='mm', format='A4'):
        super().__init__(orientation, unit, format)
        # Font ayarını en basit ve doğrudan şekilde yapmayı deneyelim
        try:
            print("DEBUG PDF __init__: 'Helvetica', '', 10 ayarlanmaya çalışılıyor...")
            self.set_font('Helvetica', '', 10) # Stil ve boyut basitçe ayarlandı
            print("DEBUG PDF __init__: 'Helvetica' başarıyla ayarlandı.")
            self.current_font_family = 'Helvetica' # Takip için
            self.current_font_style = ''
            self.current_font_size = 10
        except RuntimeError as e:
            print(f"PDF __init__: KRİTİK HATA - Temel 'Helvetica' fontu ayarlanamadı: {e}")
            # Hata durumunda, belki FPDF'in en temel varsayılanına güvenelim
            # ve hiçbir şey yapmayalım ya da alternatif bir temel font deneyelim.
            # Bu durumda FPDFException zaten fırlatılmış olabilir.
            raise # Hatayı tekrar fırlat ki görebilelim
        except Exception as e_gen:
            print(f"PDF __init__: BEKLENMEDİK HATA - Font ayarlanırken: {e_gen}")
            raise


    def setup_font(self, font_path_setting=None):
        # Bu metot artık neredeyse hiçbir şey yapmayacak, __init__ içinde font ayarlandı.
        # Sadece mevcut fontu teyit edebiliriz.
        try:
            # print(f"PDF setup_font: Mevcut font ailesi: {self.font_family}")
            if not self.font_family: # Eğer __init__ başarısız olduysa ve font ayarlanmadıysa
                print("PDF setup_font: Font ailesi boş, Helvetica tekrar deneniyor.")
                self.set_font('Helvetica', '', 10)
                self.current_font_family = 'Helvetica'
                self.current_font_style = ''
                self.current_font_size = 10

        except Exception as e:
            print(f"PDF setup_font: Font teyit edilirken hata: {e}")


    def header(self):
        pass

    def footer(self):
        self.set_y(-15)
        try:
            self.set_font('Helvetica', 'I', 8)
        except RuntimeError: # Bu olmamalı
            pass # Hata durumunda bir şey yapma
        self.cell(0, 10, f'Sayfa {self.page_no()}/{{nb}}', 0, 0, 'C')

    def chapter_title(self, title_text_converted):
        try:
            self.set_font('Helvetica', 'B', 14)
        except RuntimeError: # Bu olmamalı
            pass
        page_width = self.w - 2 * self.l_margin
        self.multi_cell(page_width, 10, title_text_converted, 0, 'L')
        self.ln(5)
        try: # Önceki fonta dön
            self.set_font(self.current_font_family, self.current_font_style, self.current_font_size)
        except RuntimeError:
            self.set_font('Helvetica', '', 10)


    def create_table(self, table_data_converted, headers_converted, column_widths):
        # Başlık Satırı
        try:
            self.set_font('Helvetica', 'B', 10)
        except RuntimeError: # Bu olmamalı
            pass
        self.set_fill_color(220, 220, 220)
        header_line_height = 7
        for i, header_text in enumerate(headers_converted):
            self.cell(column_widths[i], header_line_height, str(header_text), 1, 0, 'C', True)
        self.ln(header_line_height)

        # Veri Satırları
        try:
            self.set_font('Helvetica', '', 9)
        except RuntimeError: # Bu olmamalı
            pass
        data_line_height = 6
        for row_data in table_data_converted:
            if self.get_y() + data_line_height > self.page_break_trigger:
                self.add_page(self.cur_orientation)
                try:
                    self.set_font('Helvetica', 'B', 10)
                except RuntimeError: pass
                self.set_fill_color(220, 220, 220)
                for i, header_text_again in enumerate(headers_converted):
                    self.cell(column_widths[i], header_line_height, str(header_text_again), 1, 0, 'C', True)
                self.ln(header_line_height)
                try:
                    self.set_font('Helvetica', '', 9)
                except RuntimeError: pass
            for col_index, cell_text in enumerate(row_data):
                self.cell(column_widths[col_index], data_line_height, str(cell_text), 1, 0, 'L')
            self.ln(data_line_height)
        self.ln(data_line_height / 2)
# --- Referans Seçme Diyalog Penceresi ---
class SelectReferrerDialog(QDialog):
    """Birden fazla referans bulunduğunda seçim yapmak için kullanılan diyalog."""
    def __init__(self, members_list, parent=None):
        # members_list: Bulunan üyelerin (sqlite3.Row nesneleri) listesi
        super().__init__(parent)
        self.setWindowTitle("Referans Üye Seçin")
        self.setMinimumWidth(450)

        self.selected_id = None   # Seçilen üyenin ID'si
        self.selected_name = None # Seçilen üyenin adı

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Aramanızla birden fazla üye eşleşti. Lütfen referans olan üyeyi seçin:"))

        self.member_list_widget = QListWidget()
        # self.member_list_widget.itemDoubleClicked.connect(self.accept_selection) # Çift tıklama ile de seçilebilir

        for member in members_list:
            # Her üye için ayırt edici bilgileri gösterelim
            display_text = f"{member['name']} (E-posta: {member['email'] or 'Yok'}, Bölüm: {member['department'] or 'Yok'})"
            list_item = QListWidgetItem(display_text)
            # ID'yi userData olarak sakla
            list_item.setData(Qt.ItemDataRole.UserRole, member['id']) 
            self.member_list_widget.addItem(list_item)

        layout.addWidget(self.member_list_widget)

        # Butonlar için layout
        button_layout = QHBoxLayout()
        select_button = QPushButton("Seç")
        select_button.clicked.connect(self.accept_selection)
        cancel_button = QPushButton("İptal")
        cancel_button.clicked.connect(self.reject) # QDialog'un kendi reject metodu

        button_layout.addStretch()
        button_layout.addWidget(select_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)

    def accept_selection(self):
        """Kullanıcı birini seçip 'Seç' butonuna bastığında çağrılır."""
        selected_items = self.member_list_widget.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Seçim Yapılmadı", "Lütfen listeden bir üye seçin.")
            return

        selected_item = selected_items[0]
        self.selected_id = selected_item.data(Qt.ItemDataRole.UserRole)
        # Seçilen ismin sadece adını almak için metni parçalayabiliriz (ilk '(' karakterine kadar)
        full_text = selected_item.text()
        self.selected_name = full_text.split(' (E-posta:')[0] if ' (E-posta:' in full_text else full_text

        self.accept() # QDialog'u "Kabul Edildi" durumuyla kapatır

    def get_selected_referrer(self):
        """Diyalog kapandıktan sonra seçilen ID ve ismi döndürür."""
        return self.selected_id, self.selected_name

class AdminPanel(QWidget):
    """Ana yönetim paneli arayüzü ve işlevselliği."""
    # AdminPanel sınıfı içinde:
    def __init__(self, login_window_ref, settings):
        """Ana yönetim paneli arayüzü ve işlevselliği."""
        super().__init__();
        self.login_window = login_window_ref; # Login penceresine referans
        self.settings = settings # Ayarları al
        self.setWindowTitle(f"{CLUB_NAME} Yönetim Paneli");
        self.setGeometry(50, 50, 950, 700) # Pencere boyutu ve konumu

        # --- Değişkenleri Başlat ---
        self.edit_member_id = None
        self.current_event_id = None
        self.uid_check_dialog = None
        self.current_profile_member_id = None
        # Bilet satışı için değişkenler
        self.current_sale_event_id = None 
        self.current_sale_member_id = None 
        self.current_editing_sale_id = None # Satış düzenleme modu için
        # Referans sistemi için değişkenler
        self.referrer_search_input = None 
        self.referrer_info_label = None   
        self.selected_referrer_id = None  
        
        # Fotoğraf klasörü
        self.MEMBER_PHOTOS_DIR = "member_photos"
        if not os.path.exists(self.MEMBER_PHOTOS_DIR):
            try:
                os.makedirs(self.MEMBER_PHOTOS_DIR)
                print(f"'{self.MEMBER_PHOTOS_DIR}' klasörü oluşturuldu.")
            except OSError as e:
                print(f"HATA: '{self.MEMBER_PHOTOS_DIR}' klasörü oluşturulamadı: {e}")
                QMessageBox.critical(self, "Klasör Hatası", 
                                     f"Üye fotoğrafları için '{self.MEMBER_PHOTOS_DIR}' klasörü oluşturulamadı.\n"
                                     f"Lütfen programın yazma izni olduğundan emin olun veya klasörü manuel oluşturun.\n{e}")

        # --- Veritabanı Bağlantısını Kur (PostgreSQL) ---
        self.db_connection = None 
        try:
            print("DEBUG: PostgreSQL (Neon/Supabase) veritabanına bağlanılıyor...")
            # Bağlantı bilgilerini global sabitlerden al (PG_HOST, PG_DATABASE vb.)
            # Bu sabitlerin dosyanın başında doğru bilgilerle tanımlı olduğundan emin olun.
            self.db_connection = psycopg2.connect(
                host=PG_HOST,
                database=PG_DATABASE,
                user=PG_USER,
                password=PG_PASSWORD,
                port=PG_PORT,
                sslmode='require' # Çoğu bulut sağlayıcı için gereklidir
            )
            self.db_connection.autocommit = False # Commit'leri manuel yapacağız
            print("DEBUG: PostgreSQL veritabanı bağlantısı başarıyla kuruldu.")
            
            # Bağlantıyı basit bir sorgu ile test et
            with self.db_connection.cursor() as cursor:
                cursor.execute("SELECT 1") 
                print("DEBUG: Veritabanı bağlantısı test sorgusu başarılı.")
            
        except psycopg2.OperationalError as e_op:
            print(f"KRİTİK VERİTABANI BAĞLANTI HATASI: {e_op}")
            QMessageBox.critical(None, "Veritabanı Bağlantı Hatası", 
                                 f"PostgreSQL veritabanına bağlanılamadı:\n{e_op}\n"
                                 f"Lütfen girdiğiniz bağlantı bilgilerini (PG_HOST, şifre vb.) ve internetinizi kontrol edin.\n"
                                 f"Uygulama kapatılacak.")
            QApplication.instance().quit()
            sys.exit(f"Kritik DB Bağlantı Hatası: {e_op}")
        except Exception as e:
            print(f"KRİTİK VERİTABANI HATASI (__init__): {e}")
            QMessageBox.critical(None, "Veritabanı Hatası", f"Veritabanı işlemleri sırasında beklenmedik hata: {e}\nUygulama kapatılacak.")
            traceback.print_exc()
            QApplication.instance().quit()
            sys.exit(f"Veritabanı başlatma hatası: {e}")

        # --- Arayüz Ayarları ---
        # Ana layout ve sayfa yönetimi
        self.layout = QVBoxLayout(self); 
        self.stacked_widget = QStackedWidget(self);
        self.layout.addWidget(self.stacked_widget);

        # Sayfa widget'larını oluştur
        self.main_page = QWidget()
        self.member_form_page = QWidget()
        self.event_form_page = QWidget()
        self.edit_member_page = QWidget()
        self.event_details_page = QWidget()
        self.member_profile_page = QWidget()
        self.settings_page = QWidget()
        self.ticket_sales_page = QWidget() # Bilet satış sayfası

        # Widget referanslarını None olarak başlatmak iyi bir pratiktir
        # (init_* metotlarında oluşturulacaklar)
        self.stats_total_members_label = None; self.stats_total_events_label = None 
        self.stats_upcoming_events_label = None; self.upcoming_events_list = None
        self.main_logo_label = None; self.upcoming_events_label_widget = None
        self.member_search_input = None; self.role_filter_combo = None
        self.member_table = None; self.name_input = None; self.uid_input = None
        self.department_input = None; self.year_input = None; self.interests_input = None
        self.email_input = None; self.phone_input = None; self.role_combo = None
        self.photo_input = None; self.membership_date_edit = None
        self.edit_event_id_label = None; self.event_name_input = None
        self.event_date_edit = None; self.event_location_input = None
        self.event_category_combo = None; self.event_capacity_spinbox = None # Kapasiteyi kaldırdık, ama referans kalmış olabilir, None yapalım
        self.event_description_input = None; self.event_add_update_button = None
        self.event_list_widget = None; self.edit_photo_label = None
        self.edit_name_input = None; self.edit_uid_input = None
        self.edit_department_input = None; self.edit_year_input = None
        self.edit_interests_input = None; self.edit_email_input = None
        self.edit_phone_input = None; self.edit_role_combo = None
        self.edit_photo_input = None; self.edit_membership_date_edit = None
        self.profile_photo_label = None; self.profile_name_label = None
        # ... (Diğer profil sayfası etiketleri için de None atamaları eklenebilir)

        # Sayfaların arayüzlerini oluştur (init metodları çağrılır)
        # Bu çağrıların sırası, widget'ların oluşturulma ve referans edilme sırası açısından önemli olabilir.
        print("DEBUG: Sayfa arayüzleri başlatılıyor...")
        self.init_main_page();        print("DEBUG: init_main_page tamamlandı.")
        self.init_member_form();      print("DEBUG: init_member_form tamamlandı.")
        self.init_event_form();       print("DEBUG: init_event_form tamamlandı.")
        self.init_edit_member_form(); print("DEBUG: init_edit_member_form tamamlandı.")
        self.init_event_details_page(); print("DEBUG: init_event_details_page tamamlandı.")
        self.init_member_profile_page();print("DEBUG: init_member_profile_page tamamlandı.")
        self.init_settings_page();      print("DEBUG: init_settings_page tamamlandı.")
        self.init_ticket_sales_page();  print("DEBUG: init_ticket_sales_page tamamlandı.")
        print("DEBUG: Tüm sayfa arayüzleri başlatıldı.")

        # Başlangıçta ana sayfayı göster
        # setCurrentWidget çağırmadan önce main_page'in stack'e eklendiğinden emin olmalıyız.
        # init_main_page sonunda ekliyor olmalı.
        if self.stacked_widget.indexOf(self.main_page) != -1:
            self.stacked_widget.setCurrentWidget(self.main_page)
            print("DEBUG: Başlangıç sayfası main_page olarak ayarlandı.")
        else:
             print("HATA: main_page başlatılamadı veya stack'e eklenemedi! İlk sayfa gösteriliyor.")
             # Eğer main_page eklenemezse, ilk eklenen sayfa (muhtemelen member_form_page) gösterilir.
             # Bu durumu kontrol etmek için __init__ sonunda main_page'in index'ine bakılabilir.

        # Kısayolları ve stili ayarla
        self.create_shortcuts();
        self.apply_style() 
        
        # İlk açılışta güncellenmesi gerekenler
        if hasattr(self, 'update_leaderboard'): self.update_leaderboard()
        if hasattr(self, 'update_main_page_stats'): self.update_main_page_stats()
        if hasattr(self, 'update_main_page_logo'): self.update_main_page_logo()

        print("DEBUG: AdminPanel __init__ tamamlandı.")
    # --- __init__ metodu burada biter ---
    def show_ticket_sales_page(self):
        """Bilet Satış Paneli sayfasını gösterir ve bazı başlangıç ayarlarını yapar."""
        print("DEBUG: show_ticket_sales_page çağrıldı.")

        # Sayfa her açıldığında etkinlikleri ComboBox'a yeniden yükleyelim (güncel liste için)
        if hasattr(self, 'load_events_into_sales_combo'): # Metodun var olduğundan emin olalım
            self.load_events_into_sales_combo()
        else:
            print("DEBUG: HATA - load_events_into_sales_combo metodu AdminPanel'de bulunamadı!")

        # Diğer başlangıç alanlarını temizle/ayarla
        if hasattr(self, 'sales_uid_input'): self.sales_uid_input.clear()
        if hasattr(self, 'sales_member_info_label'): self.sales_member_info_label.setText("Lütfen bir etkinlik seçin ve kart okutun/UID girin.")
        if hasattr(self, 'sales_price_paid_input'): self.sales_price_paid_input.clear()
        if hasattr(self, 'sales_notes_input'): self.sales_notes_input.clear()

        self.current_sale_event_id = None # Yeni sayfa açıldığında seçili etkinliği sıfırla
        self.current_sale_member_id = None # ve seçili üyeyi sıfırla

        if hasattr(self, 'update_recent_sales_list'): self.update_recent_sales_list() 
        if hasattr(self, 'check_sale_button_status'): self.check_sale_button_status() 

        if hasattr(self, 'ticket_sales_page'): # Sayfanın varlığını kontrol et
            self.stacked_widget.setCurrentWidget(self.ticket_sales_page)
        else:
            print("DEBUG: HATA - ticket_sales_page widget'ı AdminPanel'de bulunamadı!")
            QMessageBox.critical(self, "Sayfa Hatası", "Bilet Satış Paneli sayfası yüklenemedi.")
    def init_ticket_sales_page(self):
        """Bilet satış panelinin arayüzünü oluşturur."""
        layout = QVBoxLayout(self.ticket_sales_page) # self.ticket_sales_page __init__ içinde tanımlanmıştı
        layout.setSpacing(15) # Elemanlar arası boşluk
        layout.setContentsMargins(15, 15, 15, 15) # Sayfa kenar boşlukları

        # 1. Üst Kısım: Geri Butonu ve Sayfa Başlığı
        header_area_layout = QHBoxLayout()
        
        back_button = QPushButton("← Ana Sayfa")
        back_button.setFixedSize(120, 35) # Buton boyutunu biraz artırdık
        back_button.clicked.connect(self.show_main_page)
        header_area_layout.addWidget(back_button)
        
        page_title_label = QLabel("Bilet Satış Paneli")
        page_title_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #333;")
        page_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_area_layout.addWidget(page_title_label, 1) # Başlık ortada kalan alanı doldursun
        
        # Simetri için geri butonu kadar sağa bir boşluk (veya başka bir widget) eklenebilir
        # Şimdilik sadece bir stretch ekleyelim ki başlık ortalansın eğer sağda bir şey yoksa
        # Ya da sabit genişlikte bir spacer:
        # header_area_layout.addSpacing(120) # Geri butonuyla aynı genişlikte
        header_area_layout.addStretch(0) # Eğer sağda bir şey olmayacaksa, 0 stretch de işe yarar
                                        # Veya butonu sola, başlığı ortaya, sağı boş bırakmak için
                                        # header_area_layout.addWidget(QLabel(), alignment=Qt.AlignmentFlag.AlignRight) gibi bir yapı

        layout.addLayout(header_area_layout)
        layout.addWidget(self.create_separator_line()) # Ayırıcı çizgi

        # 2. Etkinlik Seçimi Alanı
        event_selection_groupbox = QGroupBox("Etkinlik Seçimi") # Grup kutusu
        event_selection_groupbox_layout = QVBoxLayout(event_selection_groupbox)

        self.sales_event_combo = QComboBox()
        # init_ticket_sales_page metodu içinde, self.sales_event_combo oluşturulduktan sonra:
        # ...
        self.sales_event_combo.setMinimumWidth(350) 
        self.sales_event_combo.currentIndexChanged.connect(self.on_sales_event_selected) # BU SATIRI EKLEYİN/AKTİFLEŞTİRİN
        event_selection_groupbox_layout.addWidget(self.sales_event_combo)
        # ...
        self.sales_event_combo.setPlaceholderText("Lütfen satış yapılacak bir etkinlik seçin...")
        self.sales_event_combo.setMinimumHeight(30)
        self.sales_event_combo.setMinimumWidth(350) # ComboBox genişliği
        # self.sales_event_combo.currentIndexChanged.connect(self.on_sales_event_selected) # SONRA EKLENECEK
        event_selection_groupbox_layout.addWidget(self.sales_event_combo)
        layout.addWidget(event_selection_groupbox)

        # 3. Ana İçerik Alanı (Splitter ile Sol: Satış Formu, Sağ: Son Satışlar)
        # QSplitter yerine QHBoxLayout da kullanılabilir, şimdilik QHBoxLayout kullanalım
        main_content_layout = QHBoxLayout()
        main_content_layout.setSpacing(15)

        # 3.1 Sol Panel: Üye Bulma ve Bilet Formu
        left_panel_groupbox = QGroupBox("Satış İşlemi")
        left_panel_layout = QVBoxLayout(left_panel_groupbox) # Grup kutusunun kendi layout'u

        # Kart Okutma / UID Girişi
        uid_input_label = QLabel("Üye Kart UID:")
        self.sales_uid_input = QLineEdit()
        self.sales_uid_input.setPlaceholderText("Kartı okutun veya 10 haneli UID girin...")
        self.sales_uid_input.setMaxLength(10)
        self.sales_uid_input.setMinimumHeight(30)
        # self.sales_uid_input.returnPressed.connect(self.find_member_for_sale) # SONRA EKLENECEK
        
        btn_find_member = QPushButton("Üye Bul")
        btn_find_member.setMinimumHeight(30)
        # btn_find_member.clicked.connect(self.find_member_for_sale) # SONRA EKLENECEK
        # init_ticket_sales_page metodu içinde:
        # ...
        # Kart Okutma / UID Girişi
        uid_input_label = QLabel("Üye Kart UID:")
        self.sales_uid_input = QLineEdit()
        self.sales_uid_input.setPlaceholderText("Kartı okutun veya 10 haneli UID girin...")
        self.sales_uid_input.setMaxLength(10)
        self.sales_uid_input.setMinimumHeight(30)
        self.sales_uid_input.returnPressed.connect(self.find_member_for_sale) # BU SATIRI EKLEYİN/AKTİFLEŞTİRİN

        btn_find_member = QPushButton("Üye Bul")
        btn_find_member.setMinimumHeight(30)
        btn_find_member.clicked.connect(self.find_member_for_sale) # BU SATIRI EKLEYİN/AKTİFLEŞTİRİN

        uid_find_layout = QHBoxLayout() 
        uid_find_layout.addWidget(uid_input_label)
        uid_find_layout.addWidget(self.sales_uid_input, 1) 
        uid_find_layout.addWidget(btn_find_member)
        left_panel_layout.addLayout(uid_find_layout)
        # ...

        uid_find_layout = QHBoxLayout() # UID input ve butonu için
        uid_find_layout.addWidget(uid_input_label)
        uid_find_layout.addWidget(self.sales_uid_input, 1) # Input alanı genişlesin
        uid_find_layout.addWidget(btn_find_member)
        left_panel_layout.addLayout(uid_find_layout)

        # Üye Bilgi Alanı
        self.sales_member_info_label = QLabel("Lütfen bir üye seçin/bulun.")
        self.sales_member_info_label.setStyleSheet("font-style: italic; color: grey; padding: 8px; border: 1px solid #ddd; background-color: #f0f0f0; border-radius: 4px;")
        self.sales_member_info_label.setWordWrap(True)
        self.sales_member_info_label.setMinimumHeight(70) # Yüksekliği biraz artırdık
        self.sales_member_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_panel_layout.addWidget(self.sales_member_info_label)
        left_panel_layout.addWidget(self.create_separator_line(Qt.Orientation.Horizontal, 5)) # İnce bir ayırıcı

        # Bilet Bilgileri Formu
        ticket_form_grid_layout = QGridLayout() # Daha düzenli bir form için GridLayout
        ticket_form_grid_layout.setSpacing(10)

        ticket_form_grid_layout.addWidget(QLabel("Bilet Türü:"), 0, 0)
        self.sales_ticket_type_combo = QComboBox()
        self.sales_ticket_type_combo.addItems(["Standart Bilet", "İndirimli Öğrenci", "VIP Misafir", "Ücretsiz Davetli"])
        self.sales_ticket_type_combo.setMinimumHeight(30)
        ticket_form_grid_layout.addWidget(self.sales_ticket_type_combo, 0, 1)

        ticket_form_grid_layout.addWidget(QLabel("Ödenen Ücret (₺):"), 1, 0)
        self.sales_price_paid_input = QLineEdit()
        # init_ticket_sales_page metodu içinde, Bilet Bilgileri Formu kısmında:
        # ...
        ticket_form_grid_layout.addWidget(QLabel("Ödenen Ücret (₺):"), 1, 0)
        self.sales_price_paid_input = QLineEdit()
        self.sales_price_paid_input.setPlaceholderText("Örn: 250.00 veya 0")
        self.sales_price_paid_input.setMinimumHeight(30)

        # ---- YENİ SATIRLAR BAŞLANGICI (Validator Ekleme) ----
        double_validator = QDoubleValidator(0.00, 99999.99, 2) # Minimum 0.00, Maksimum 99999.99, 2 ondalık basamak
        double_validator.setNotation(QDoubleValidator.Notation.StandardNotation) # Standart sayı formatı (bilimsel değil)
        # Kullanıcının yerel ayarlarına göre virgül/nokta ayrımını doğru işlemesi için:
        # import locale
        # current_locale = locale.getlocale()
        # q_locale = QLocale(current_locale[0] if current_locale[0] else QLocale.Language.English)
        # double_validator.setLocale(q_locale) # Bu satır QLocale importu gerektirir from PyQt6.QtCore
        # Şimdilik en basit haliyle bırakalım, genellikle nokta çalışır.
        self.sales_price_paid_input.setValidator(double_validator)
        # ---- YENİ SATIRLAR BİTİŞİ ----

        ticket_form_grid_layout.addWidget(self.sales_price_paid_input, 1, 1)
        # ...
        self.sales_price_paid_input.setPlaceholderText("Örn: 250.00 veya 0")
        self.sales_price_paid_input.setMinimumHeight(30)
        # self.sales_price_paid_input.setValidator(QDoubleValidator(0, 9999.99, 2)) # Sadece sayı ve . , girişi için (opsiyonel)
        ticket_form_grid_layout.addWidget(self.sales_price_paid_input, 1, 1)
        
        ticket_form_grid_layout.addWidget(QLabel("Ödeme Yöntemi:"), 2, 0)
        self.sales_payment_method_combo = QComboBox()
        self.sales_payment_method_combo.addItems(["Nakit", "Kredi Kartı/Banka Kartı", "Online Ödeme", "Diğer"])
        self.sales_payment_method_combo.setMinimumHeight(30)
        ticket_form_grid_layout.addWidget(self.sales_payment_method_combo, 2, 1)

        ticket_form_grid_layout.addWidget(QLabel("Notlar:"), 3, 0, Qt.AlignmentFlag.AlignTop)
        self.sales_notes_input = QTextEdit()
        self.sales_notes_input.setPlaceholderText("Bu satışla ilgili özel notlarınız (opsiyonel)...")
        self.sales_notes_input.setFixedHeight(70) # Yüksekliği biraz azalttık
        ticket_form_grid_layout.addWidget(self.sales_notes_input, 3, 1)
        
        left_panel_layout.addLayout(ticket_form_grid_layout)
        left_panel_layout.addSpacing(15)

        # Satış Butonu
        self.btn_process_sale = QPushButton("BİLET SATIŞINI TAMAMLA")
        self.btn_process_sale.setIcon(QIcon.fromTheme("emblem-default")) # veya "list-add", "document-save-as"
        self.btn_process_sale.setStyleSheet("font-weight: bold; padding: 12px; font-size:14px; background-color: #28a745; color: white; border-radius: 5px;")
        self.btn_process_sale.setMinimumHeight(40)
        self.btn_process_sale.clicked.connect(self.process_ticket_sale)
        self.btn_process_sale.setEnabled(False) # Başlangıçta pasif
        # self.btn_process_sale.clicked.connect(self.process_ticket_sale) # SONRA EKLENECEK
        left_panel_layout.addWidget(self.btn_process_sale)
        
        left_panel_layout.addStretch(1) # Sol paneldeki elemanları yukarı iter
        main_content_layout.addWidget(left_panel_groupbox, 1) # Sol panel, oran 1 (genişlesin)

        # 3.2 Sağ Panel: Son Satışlar Tablosu
        right_panel_groupbox = QGroupBox("Etkinlikteki Son Satışlar")
        right_panel_layout = QVBoxLayout(right_panel_groupbox)

        self.sales_recent_sales_table = QTableWidget()
                # init_ticket_sales_page metodu içinde, self.sales_recent_sales_table oluşturulduktan sonra:
        # ... (diğer tablo ayarları: setColumnCount, setHorizontalHeaderLabels vb.)
        self.sales_recent_sales_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sales_recent_sales_table.customContextMenuRequested.connect(self.on_sales_table_context_menu) # Bu metodu birazdan oluşturacağız
        # ...
        self.sales_recent_sales_table.setColumnCount(5) 
        self.sales_recent_sales_table.setHorizontalHeaderLabels(["Üye Adı", "Bilet Türü", "Ücret", "Ödeme Ynt.", "Satış Zamanı"])
        self.sales_recent_sales_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.sales_recent_sales_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.sales_recent_sales_table.verticalHeader().setVisible(False)
        self.sales_recent_sales_table.setAlternatingRowColors(True) # Zebra deseni için
        
        sales_table_header = self.sales_recent_sales_table.horizontalHeader()
        sales_table_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch) # Üye Adı genişlesin
        sales_table_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents) # Bilet Türü içeriğe
        sales_table_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents) # Ücret içeriğe
        sales_table_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents) # Ödeme Ynt. içeriğe
        sales_table_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive) # Zamanı kullanıcı ayarlasın
        self.sales_recent_sales_table.setColumnWidth(4, 140) # Zaman için başlangıç genişliği

        right_panel_layout.addWidget(self.sales_recent_sales_table)
        main_content_layout.addWidget(right_panel_groupbox, 2) # Sağ panel, oran 2 (daha geniş olsun)

        layout.addLayout(main_content_layout) # Sol ve Sağ panelleri ana layout'a ekle

        # Sayfayı stacked widget'a ekle
        if self.stacked_widget.indexOf(self.ticket_sales_page) == -1:
             self.stacked_widget.addWidget(self.ticket_sales_page)
    # AdminPanel sınıfının içine bir yardımcı metot olarak:
    # AdminPanel sınıfının içine (diğer metodlarla birlikte):

    # AdminPanel sınıfının içinde:
    # AdminPanel sınıfının içinde:
    # AdminPanel sınıfının içine:
    # AdminPanel sınıfının içine (diğer metodlarla birlikte):
# AdminPanel sınıfının içinde:

    def load_member_points_log(self, member_id):
        """Verilen üyenin puan geçmişini profil sayfasındaki tabloya yükler."""

        if not hasattr(self, 'profile_points_log_table'):
            print("DEBUG: HATA - load_member_points_log: self.profile_points_log_table bulunamadı!")
            return

        self.profile_points_log_table.setRowCount(0) # Tabloyu temizle

        if member_id is None:
            print("DEBUG: Puan geçmişi için üye ID'si None geldi.")
            # İsteğe bağlı: Tabloya "Lütfen bir üye seçin" gibi bir mesaj eklenebilir.
            return

        print(f"DEBUG: Üye ID {member_id} için puan geçmişi yükleniyor...")
        try:
            cursor = self.get_cursor()
            cursor.execute("""
                SELECT log_timestamp, reason, points_earned 
                FROM points_log 
                WHERE member_id = %s 
                ORDER BY log_timestamp DESC -- En yeni loglar üste gelsin
            """, (member_id,))
            logs = cursor.fetchall()

            if not logs:
                print(f"DEBUG: Üye ID {member_id} için puan geçmişi bulunamadı.")
                self.profile_points_log_table.setRowCount(1)
                self.profile_points_log_table.setItem(0, 0, QTableWidgetItem("Bu üye için puan geçmişi kaydı yok."))
                self.profile_points_log_table.setSpan(0, 0, 1, 3) # Mesajı 3 sütuna yay
                return

            self.profile_points_log_table.setRowCount(len(logs))
            for row_idx, log_row in enumerate(logs):
                # --- ZAMAN DAMGASI İŞLEME KISMI (DÜZELTİLDİ) ---
                log_time_str = "Bilinmiyor"
                timestamp_value = log_row['log_timestamp']  # Veritabanından gelen zaman damgası değeri

                if timestamp_value:  # Eğer değer None veya boş değilse
                    if isinstance(timestamp_value, datetime.datetime):
                        # Eğer değer Python'un datetime.datetime objesi ise,
                        # QDateTime'e doğrudan yıl, ay, gün, saat, dk, sn ile dönüştür
                        q_dt_obj = QDateTime(timestamp_value.year, timestamp_value.month, timestamp_value.day,
                                             timestamp_value.hour, timestamp_value.minute, timestamp_value.second)
                        # Opsiyonel: Zaman dilimi bilgisini de kullanmak isterseniz (TIMESTAMPTZ için)
                        # if timestamp_value.tzinfo:
                        #     q_dt_obj.setTimeSpec(Qt.TimeSpec.OffsetFromUTC)
                        #     q_dt_obj.setOffsetFromUtc(int(timestamp_value.utcoffset().total_seconds()))
                        log_time_str = q_dt_obj.toString("dd.MM.yyyy HH:mm")
                    elif isinstance(timestamp_value, str):
                        # Eğer değer zaten bir string (metin) ise, fromString ile parse etmeyi dene
                        # Önce milisaniyeli (ISODateWithMs), sonra milisaniyesiz (ISODate) dene
                        q_dt_obj = QDateTime.fromString(timestamp_value, Qt.DateFormat.ISODateWithMs)
                        if not q_dt_obj.isValid():
                            q_dt_obj = QDateTime.fromString(timestamp_value, Qt.DateFormat.ISODate)
                        
                        if q_dt_obj.isValid():
                            log_time_str = q_dt_obj.toString("dd.MM.yyyy HH:mm")
                        else:
                            log_time_str = str(timestamp_value) # Parse edilemezse olduğu gibi göster
                    else:
                        # Beklenmedik bir tip ise
                        log_time_str = "Bilinmeyen Zaman Formatı"
                
                time_item = QTableWidgetItem(log_time_str)
                # --- ZAMAN DAMGASI İŞLEME KISMI BİTTİ ---

                # Neden (Açıklama)
                reason_item = QTableWidgetItem(str(log_row['reason'] or ''))

                # Puan Değişimi (+ veya - olarak gösterelim)
                points_earned = log_row['points_earned'] if log_row['points_earned'] is not None else 0
                points_str = f"+{points_earned}" if points_earned >= 0 else str(points_earned)
                points_item = QTableWidgetItem(points_str)
                points_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                # Puana göre renklendirme (opsiyonel)
                if points_earned > 0:
                    points_item.setForeground(QColor("blue"))
                elif points_earned < 0:
                    points_item.setForeground(QColor("red"))

                # Hücreleri tabloya ekle
                self.profile_points_log_table.setItem(row_idx, 0, time_item)
                self.profile_points_log_table.setItem(row_idx, 1, reason_item)
                self.profile_points_log_table.setItem(row_idx, 2, points_item)

            print(f"DEBUG: Üye ID {member_id} için {len(logs)} puan kaydı yüklendi.")

        except psycopg2.Error as e_db:
            print(f"HATA: Puan geçmişi yüklenirken veritabanı hatası: {e_db}")
            QMessageBox.warning(self, "Veritabanı Hatası", f"Puan geçmişi yüklenemedi: {e_db}")
            self.profile_points_log_table.setRowCount(1)
            self.profile_points_log_table.setItem(0, 0, QTableWidgetItem("Puan geçmişi yüklenirken hata oluştu."))
            self.profile_points_log_table.setSpan(0, 0, 1, 3)
            traceback.print_exc()
        except Exception as e_general:
            print(f"HATA: Puan geçmişi yüklenirken genel hata: {e_general}")
            QMessageBox.warning(self, "Beklenmedik Hata", f"Puan geçmişi yüklenirken bir sorun oluştu: {e_general}")
            self.profile_points_log_table.setRowCount(1)
            self.profile_points_log_table.setItem(0, 0, QTableWidgetItem("Puan geçmişi yüklenirken hata oluştu."))
            self.profile_points_log_table.setSpan(0, 0, 1, 3)
            traceback.print_exc()
    def confirm_delete_ticket_sale(self, sale_id, member_name, ticket_type):
        """Bilet satışını silmeden önce kullanıcıdan onay ister."""
        if sale_id is None:
            QMessageBox.warning(self, "Hata", "Silinecek satış seçilemedi (ID bulunamadı).")
            return

        reply = QMessageBox.question(self, "Satışı Silme Onayı",
                                    f"<b>'{member_name}'</b> adlı üyenin <b>'{ticket_type}'</b> bilet satışını silmek istediğinizden emin misiniz?\n\n"
                                    f"Bu işlem geri alınamaz!",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No) # Varsayılan "Hayır"

        if reply == QMessageBox.StandardButton.Yes:
            print(f"DEBUG: Satış ID {sale_id} için silme onaylandı.")
            self.delete_ticket_sale_from_db(sale_id)

    def delete_ticket_sale_from_db(self, sale_id):
        """Verilen ID'li bilet satışını veritabanından siler."""
        if sale_id is None:
            return

        try:
            cursor = self.get_cursor()
            # Silmeden önce, kapasite takibi yapıyorsak, event_id ve member_id'yi alıp
            # events tablosundaki tickets_sold'u azaltmamız gerekebilir.
            # Şimdilik bu adımı atlıyoruz, sadece satışı silelim.
            # cursor.execute("SELECT event_id FROM ticket_sales WHERE id = ?", (sale_id,))
            # sale_info = cursor.fetchone()
            # event_id_of_sale = sale_info['event_id'] if sale_info else None

            cursor.execute("DELETE FROM ticket_sales WHERE id = %s", (sale_id,))
            rowcount = cursor.rowcount
            self.db_connection.commit()

            if rowcount > 0:
                QMessageBox.information(self, "Başarılı", "Bilet satışı başarıyla silindi.")
                print(f"DEBUG: Satış ID {sale_id} veritabanından silindi.")
                # Satış silindikten sonra son satışlar listesini ve belki etkinlik istatistiklerini güncelle
                self.update_recent_sales_list()
                # Eğer tickets_sold'u azalttıysak, ana sayfa istatistiklerini de güncellemeliyiz.
                # if event_id_of_sale and hasattr(self, 'decrement_tickets_sold_for_event'):
                # self.decrement_tickets_sold_for_event(event_id_of_sale) # Böyle bir metot oluşturulabilir.
                # self.update_main_page_stats()
            else:
                QMessageBox.warning(self, "Bulunamadı", f"ID'si {sale_id} olan satış kaydı silinemedi (muhtemelen zaten silinmiş).")

        except psycopg2.Error as e_db:
            QMessageBox.critical(self, "Veritabanı Hatası", f"Bilet satışı silinirken hata oluştu: {e_db}")
            traceback.print_exc()
        except Exception as e_general:
            QMessageBox.critical(self, "Beklenmedik Hata", f"Bilet satışı silinirken bir sorun oluştu: {e_general}")
            traceback.print_exc()
    # AdminPanel sınıfının içine (diğer metodlarla birlikte):
    
    # AdminPanel sınıfının içine (diğer metodlarla birlikte):
    # AdminPanel sınıfının içine:
# AdminPanel sınıfının içine:
    def find_referrer_member(self):
        """Yeni üye ekleme formunda girilen isme göre referans üyesini arar.
        Birden fazla sonuç varsa seçim diyalogu açar."""

        if not all(hasattr(self, attr) and getattr(self, attr) is not None 
                for attr in ['referrer_search_input', 'referrer_info_label']):
            print("HATA: find_referrer_member - Gerekli widget'lar bulunamadı.")
            return

        search_term = self.referrer_search_input.text().strip()
        self.selected_referrer_id = None 
        self.referrer_info_label.setStyleSheet("font-style: italic; color: grey;") 

        if not search_term:
            self.referrer_info_label.setText("Aramak için bir isim yazın.")
            return

        print(f"DEBUG: Referans üye aranıyor: '{search_term}'")
        self.referrer_info_label.setText("Referans aranıyor...")

        try:
            cursor = self.get_cursor()
            query = "SELECT id, name, email, department FROM members WHERE LOWER(name) LIKE LOWER(%s)"
            like_term = f"%{search_term}%" 

            cursor.execute(query, (like_term,))
            found_members = cursor.fetchall() # sqlite3.Row listesi

            if not found_members:
                self.referrer_info_label.setText(f"<font color='red'>'{search_term}' ile eşleşen üye bulunamadı.</font>")
                print(f"DEBUG: Referans bulunamadı: '{search_term}'")
            elif len(found_members) == 1:
                # Tam olarak bir üye bulundu
                member = found_members[0]
                self.selected_referrer_id = member['id'] 
                info_text = (f"<font color='green'><b>Referans Seçildi:</b> "
                            f"{member['name']} (ID: {member['id']})</font>")
                self.referrer_info_label.setText(info_text)
                print(f"DEBUG: Tek referans bulundu ve seçildi: {member['name']} (ID: {self.selected_referrer_id})")
            else:
                # ---- BİRDEN FAZLA ÜYE BULUNDU -> DİYALOG AÇ ----
                print(f"DEBUG: Birden fazla referans bulundu ({len(found_members)} kişi). Seçim diyalogu açılıyor...")
                self.referrer_info_label.setText(f"<font color='orange'>'{search_term}' ile {len(found_members)} üye bulundu. Lütfen seçin:</font>")

                # Bulunan üyeleri SelectReferrerDialog'a gönder
                dialog = SelectReferrerDialog(found_members, self) # Yeni Diyalog Sınıfı (aşağıda oluşturulacak)

                # Diyalogdan bir sonuç (seçilen ID veya None) döndüğünde ne yapılacağını ayarla
                # exec() yerine open() ve finished sinyali daha modern olabilir ama exec() daha basit.
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    # Kullanıcı birini seçip "Seç" butonuna bastı
                    selected_id, selected_name = dialog.get_selected_referrer()
                    if selected_id is not None:
                        self.selected_referrer_id = selected_id
                        info_text = (f"<font color='green'><b>Referans Seçildi:</b> "
                                    f"{selected_name} (ID: {selected_id})</font>")
                        self.referrer_info_label.setText(info_text)
                        print(f"DEBUG: Diyalogdan referans seçildi: {selected_name} (ID: {self.selected_referrer_id})")
                    else: # Seçim yapılmadan kapatıldıysa veya hata olduysa
                        self.selected_referrer_id = None
                        self.referrer_info_label.setText("Referans seçilmedi.")
                        print("DEBUG: Referans seçim diyalogundan seçim yapılmadı.")
                else:
                    # Kullanıcı diyalogu kapattı veya iptal etti
                    self.selected_referrer_id = None
                    self.referrer_info_label.setText("Referans seçimi iptal edildi.")
                    print("DEBUG: Referans seçim diyalogu iptal edildi.")
                # ---- DİYALOG BİTTİ ----

        except psycopg2.Error as e_db:
            self.referrer_info_label.setText("<font color='red'>Veritabanı hatası oluştu.</font>")
            print(f"HATA: Referans aranırken DB hatası: {e_db}")
            traceback.print_exc()
        except Exception as e_general:
            self.referrer_info_label.setText("<font color='red'>Beklenmedik bir hata oluştu.</font>")
            print(f"HATA: Referans aranırken genel hata: {e_general}")
            traceback.print_exc()
    def clear_sale_form_for_new_entry(self, clear_member_info=True):
        """Bilet satış formunu yeni bir giriş için temizler ve düzenleme modunu sıfırlar."""
        print(f"DEBUG: clear_sale_form_for_new_entry çağrıldı. Üye bilgisi temizlensin mi? {clear_member_info}")

        # Üye ile ilgili alanları temizle (eğer isteniyorsa)
        if clear_member_info:
            if hasattr(self, 'sales_uid_input'):
                self.sales_uid_input.clear()
            if hasattr(self, 'sales_member_info_label'):
                self.sales_member_info_label.setText("Lütfen bir üye seçin/bulun.")
            # Üye ID'sini de sıfırla
            self.current_sale_member_id = None

        # Bilet detay form alanlarını temizle/sıfırla
        if hasattr(self, 'sales_ticket_type_combo'): 
            self.sales_ticket_type_combo.setCurrentIndex(0) # İlk seçeneğe dön
        if hasattr(self, 'sales_price_paid_input'): 
            self.sales_price_paid_input.clear()
        if hasattr(self, 'sales_payment_method_combo'): 
            self.sales_payment_method_combo.setCurrentIndex(0)
        if hasattr(self, 'sales_notes_input'): 
            self.sales_notes_input.clear()

        # Düzenleme ID'sini temizle (artık düzenleme modunda değiliz)
        if hasattr(self, 'current_editing_sale_id'):
            self.current_editing_sale_id = None 
            print("DEBUG: Düzenleme modu sıfırlandı (current_editing_sale_id = None).")

        # Satış butonunu normale çevir (eğer varsa)
        if hasattr(self, 'btn_process_sale'):
            self.btn_process_sale.setText("BİLET SATIŞINI TAMAMLA") 
            # Orijinal yeşil stilini tekrar uygula (stil kodunu buradan aldım, sizdeki farklıysa güncelleyin)
            self.btn_process_sale.setStyleSheet("font-weight: bold; padding: 12px; font-size:14px; background-color: #28a745; color: white; border-radius: 5px;") 

        # Satış butonunun aktif/pasif durumunu güncelle (üye temizlendiyse pasif olur)
        if hasattr(self, 'check_sale_button_status'): 
            self.check_sale_button_status() 

        # UID alanına odaklan (eğer üye temizlendiyse)
        if clear_member_info and hasattr(self, 'sales_uid_input'): 
            self.sales_uid_input.setFocus()
    # AdminPanel sınıfının içinde:

    def load_events_into_sales_combo(self):
        """Etkinlikleri bilet satışı sayfasındaki ComboBox'a yükler."""
        print("DEBUG: Bilet Satış Paneli: Etkinlikler ComboBox'a yükleniyor...")
        
        if not hasattr(self, 'sales_event_combo'):
            print("DEBUG: HATA - load_events_into_sales_combo: self.sales_event_combo widget'ı bulunamadı!")
            return

        try:
            # ComboBox'ı her yüklemeden önce temizle
            self.sales_event_combo.blockSignals(True)
            self.sales_event_combo.clear()
            self.sales_event_combo.blockSignals(False)

            # Kullanıcıya rehberlik edecek ilk öğeyi ekle
            self.sales_event_combo.addItem("Lütfen bir etkinlik seçin...", None) 
            
            cursor = self.get_cursor()
            
            today_iso = QDate.currentDate().toString(Qt.DateFormat.ISODate)
            # SQL sorgusunda %s kullanıldığından emin olun (önceki düzeltmelerde belirtilmişti)
            query = "SELECT id, name, event_date FROM events WHERE event_date >= %s ORDER BY event_date ASC"
            params = (today_iso,)
            
            cursor.execute(query, params)
            events = cursor.fetchall()
            
            if not events:
                print("DEBUG: ComboBox'a yüklenecek aktif veya yaklaşan etkinlik bulunamadı.")
                return

            # Bulunan her etkinliği ComboBox'a ekle
            for event_row in events:
                event_id = event_row['id']
                event_name = event_row['name']
                
                # --- TARİH İŞLEME KISMI (DÜZELTİLDİ) ---
                event_date_value = event_row['event_date']  # Veritabanından gelen tarih değeri
                display_date = str(event_date_value) if event_date_value is not None else "Tarihsiz" # Varsayılan

                if event_date_value:  # Eğer tarih değeri None değilse
                    if isinstance(event_date_value, datetime.date):
                        # Eğer değer Python'un datetime.date objesi ise,
                        # QDate'e doğrudan yıl, ay, gün bilgileriyle dönüştür
                        q_date_obj = QDate(event_date_value.year, event_date_value.month, event_date_value.day)
                        display_date = q_date_obj.toString("dd.MM.yyyy")
                    elif isinstance(event_date_value, str):
                        # Eğer değer zaten bir string (metin) ise, fromString ile parse etmeyi dene
                        q_date_obj = QDate.fromString(event_date_value, Qt.DateFormat.ISODate)
                        if q_date_obj.isValid():
                            display_date = q_date_obj.toString("dd.MM.yyyy")
                        # else: display_date zaten event_date_value (str hali) olarak ayarlı kalır
                    # else: Beklenmedik bir tip ise, display_date zaten event_date_value (str hali) olarak ayarlı kalır
                else: # event_date_value None ise
                    display_date = "Tarihsiz"
                # --- TARİH İŞLEME KISMI BİTTİ ---
                
                item_text = f"{event_name} ({display_date})"
                self.sales_event_combo.addItem(item_text, userData=event_id) 
            
            print(f"DEBUG: {len(events)} etkinlik ComboBox'a başarıyla eklendi.")

        except psycopg2.Error as e_db:
            print(f"HATA: Bilet satışı için etkinlikler yüklenirken veritabanı hatası oluştu: {e_db}")
            if hasattr(self, 'sales_event_combo'):
                 self.sales_event_combo.addItem("Etkinlikler yüklenemedi (DB Hatası)", None)
            QMessageBox.warning(self, "Veritabanı Hatası", f"Etkinlik listesi yüklenirken bir sorun oluştu:\n{e_db}")
            traceback.print_exc()
        except Exception as e_general:
            print(f"HATA: Bilet satışı için etkinlikler yüklenirken genel bir hata oluştu: {e_general}")
            if hasattr(self, 'sales_event_combo'):
                 self.sales_event_combo.addItem("Etkinlikler yüklenemedi (Genel Hata)", None)
            QMessageBox.warning(self, "Beklenmedik Hata", f"Etkinlik listesi yüklenirken beklenmedik bir sorun oluştu:\n{e_general}")
            traceback.print_exc()

# AdminPanel sınıfının içinde:
    def on_sales_event_selected(self, index):
        """Bilet satışı sayfasında bir etkinlik seçildiğinde çağrılır."""
        if index == 0 and self.sales_event_combo.itemData(index) is None: # "Lütfen bir etkinlik seçin..." seçiliyse
            print("DEBUG: Bilet Satış Paneli: 'Lütfen bir etkinlik seçin' seçildi.")
            self.current_sale_event_id = None # Seçili etkinlik ID'sini sıfırla
            if hasattr(self, 'update_recent_sales_list'): self.update_recent_sales_list() # Son satışları temizle/güncelle
            if hasattr(self, 'check_sale_button_status'): self.check_sale_button_status() # Satış butonunu pasif yap
            return

        selected_event_id = self.sales_event_combo.itemData(index) # Sakladığımız event_id'yi al
        selected_event_name = self.sales_event_combo.currentText()

        print(f"DEBUG: Bilet Satış Paneli: Etkinlik seçildi. Index: {index}, Ad: '{selected_event_name}', ID: {selected_event_id}")

        self.current_sale_event_id = selected_event_id # Seçilen etkinliğin ID'sini sakla
                                                    # Bu değişkeni __init__ içinde None olarak başlatmayı unutmayın:
                                                    # self.current_sale_event_id = None

        if hasattr(self, 'update_recent_sales_list'): self.update_recent_sales_list() # Bu etkinliğin son satışlarını yükle/güncelle
        if hasattr(self, 'check_sale_button_status'): self.check_sale_button_status() # Satış butonunun durumunu kontrol et

# AdminPanel sınıfının içinde:
    def find_member_for_sale(self):
        """Bilet satışı için girilen UID ile üyeyi bulur ve bilgileri gösterir."""
        if not hasattr(self, 'sales_uid_input') or not hasattr(self, 'sales_member_info_label'):
            print("DEBUG: HATA - find_member_for_sale: Gerekli widget'lar (sales_uid_input veya sales_member_info_label) bulunamadı.")
            return

        uid = self.sales_uid_input.text().strip()
        print(f"DEBUG: Bilet Satış Paneli: Üye aranıyor. UID: '{uid}'")
        
        self.current_sale_member_id = None # Önceki seçimi temizle (önemli)
        self.sales_member_info_label.setText("Üye bilgileri aranıyor...")
        self.check_sale_button_status() # Üye seçimi kalktığı için satış butonu pasif olmalı

        if not uid:
            self.sales_member_info_label.setText("Lütfen bir UID girin veya kart okutun.")
            return

        if len(uid) != 10: # Genellikle UID'ler 10 haneli olur, bu bir ön kontrol
            self.sales_member_info_label.setText("<font color='orange'>Girilen UID 10 haneli olmalıdır.</font>")
            return

        try:
            cursor = self.get_cursor()
            cursor.execute("SELECT id, name, role, department, email FROM members WHERE uid = %s", (uid,))
            member = cursor.fetchone() # sqlite3.Row nesnesi veya None

            if member:
                self.current_sale_member_id = member['id'] # Bulunan üyenin ID'sini sakla
                info_text = (f"<b>ÜYE BULUNDU:</b><br><br>"
                            f"<b>Ad Soyad:</b> {member['name']}<br>"
                            f"<b>Rol:</b> {member['role'] or '-'}<br>"
                            f"<b>Bölüm:</b> {member['department'] or '-'}<br>"
                            f"<b>E-posta:</b> {member['email'] or '-'}")
                self.sales_member_info_label.setText(info_text)
                print(f"DEBUG: Üye bulundu: {member['name']} (ID: {self.current_sale_member_id})")
            else:
                self.sales_member_info_label.setText(f"<font color='red'><b>HATA:</b> '{uid}' UID ile kayıtlı üye bulunamadı.</font>")
                print(f"DEBUG: '{uid}' UID ile üye bulunamadı.")
        
        except psycopg2.Error as e_db:
            self.sales_member_info_label.setText(f"<font color='red'><b>Veritabanı Hatası:</b> Üye aranırken sorun oluştu.</font>")
            print(f"HATA: Üye aranırken veritabanı hatası: {e_db}")
            traceback.print_exc()
        except Exception as e_general:
            self.sales_member_info_label.setText(f"<font color='red'><b>Beklenmedik Hata:</b> Üye aranırken sorun oluştu.</font>")
            print(f"HATA: Üye aranırken genel bir hata: {e_general}")
            traceback.print_exc()
        
        self.check_sale_button_status() # Üye bulunup bulunmadığına göre satış butonunun durumunu güncelle

# AdminPanel sınıfının içinde:
# AdminPanel sınıfının içinde:
    # AdminPanel sınıfının içinde:

    def process_ticket_sale(self):
        """Bilet satış işlemini gerçekleştirir, veritabanına kaydeder ve puan ekler/loglar."""
        print("DEBUG: Bilet Satış Paneli: Satış/Güncelleme butonuna basıldı.")
        
        if not all(hasattr(self, attr) for attr in [
            'current_sale_event_id', 'current_sale_member_id', 
            'sales_ticket_type_combo', 'sales_price_paid_input',
            'sales_payment_method_combo', 'sales_notes_input',
            'sales_uid_input', 'sales_member_info_label' 
        ]):
            QMessageBox.critical(self, "Kritik Hata", "Bilet satışı için gerekli arayüz elemanları eksik.")
            return
        if self.current_sale_event_id is None:
            QMessageBox.warning(self, "Eksik Bilgi", "Lütfen önce bir etkinlik seçin.")
            return
        if self.current_sale_member_id is None:
            QMessageBox.warning(self, "Eksik Bilgi", "Lütfen önce geçerli bir üye bulun/seçin.")
            return

        ticket_type = self.sales_ticket_type_combo.currentText()
        price_paid_str = self.sales_price_paid_input.text().strip().replace(',', '.') 
        payment_method = self.sales_payment_method_combo.currentText()
        notes = self.sales_notes_input.toPlainText().strip()
        # Satış zaman damgası, veritabanına ISO formatında string olarak kaydedilecek
        sale_timestamp_str = QDateTime.currentDateTime().toString(Qt.DateFormat.ISODate) 

        price_paid_float = 0.0
        if price_paid_str:
            try:
                price_paid_float = float(price_paid_str)
                if price_paid_float < 0:
                    QMessageBox.warning(self, "Geçersiz Giriş", "Ödenen ücret negatif olamaz.")
                    return
            except ValueError:
                QMessageBox.warning(self, "Geçersiz Giriş", "Lütfen 'Ödenen Ücret' alanına geçerli bir sayı girin (örn: 150.75).")
                return

        try:
            cursor = self.get_cursor()
            sale_id_for_log = None 
            msg_action = "" 
            points_to_award = 0 # Güncellemede puan verilmeyecekse veya yeni satışta verilmeyecekse
            points_awarded_successfully = True # Başlangıçta başarılı varsayalım
            
            if hasattr(self, 'current_editing_sale_id') and self.current_editing_sale_id is not None:
                # --- GÜNCELLEME İŞLEMİ ---
                editing_sale_id = self.current_editing_sale_id
                print(f"DEBUG: Satış ID {editing_sale_id} güncelleniyor...")
                cursor.execute("""
                    UPDATE ticket_sales 
                    SET ticket_type=%s, price_paid=%s, payment_method=%s, notes=%s, sale_timestamp=%s 
                    WHERE id=%s AND event_id=%s AND member_id=%s
                """, (ticket_type, price_paid_float, payment_method, notes if notes else None, 
                    sale_timestamp_str, editing_sale_id, self.current_sale_event_id, self.current_sale_member_id))
                self.db_connection.commit()
                sale_id_for_log = editing_sale_id
                msg_action = "güncellendi"
                # Puanlar genellikle düzenleme sırasında değişmez, bu yüzden points_to_award = 0 kalır.
            else:
                # --- YENİ SATIŞ EKLEME İŞLEMİ (DÜZELTİLMİŞ ID ALMA) ---
                print(f"DEBUG: Yeni satış ekleniyor...")
                cursor.execute("""
                    INSERT INTO ticket_sales 
                    (event_id, member_id, sale_timestamp, ticket_type, price_paid, payment_method, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id  -- ID'yi geri döndür
                """, (self.current_sale_event_id, self.current_sale_member_id, sale_timestamp_str,
                    ticket_type, price_paid_float, payment_method, notes if notes else None))
                
                inserted_sale_row = cursor.fetchone()
                if inserted_sale_row and 'id' in inserted_sale_row:
                    sale_id_for_log = inserted_sale_row['id']
                else:
                    QMessageBox.critical(self, "Kritik Hata", "Bilet satışı kaydedildi ancak satış ID'si alınamadı! İşlem geri alınıyor.")
                    if self.db_connection and not self.db_connection.closed:
                        self.db_connection.rollback()
                    return 

                self.db_connection.commit() # Satış ekleme işlemini onayla
                print(f"DEBUG: Yeni satış kaydedildi (Commit edildi). Satış ID: {sale_id_for_log}")
                msg_action = "kaydedildi"

                # ---- YENİ PUAN EKLEME VE LOGLAMA KISMI ----
                points_awarded_successfully = False # Yeni satışta puan eklemeyi deneyeceğiz
                points_to_award = TICKET_PURCHASE_POINTS

                if points_to_award > 0 and sale_id_for_log is not None:
                    try:
                        cursor.execute("SELECT name FROM events WHERE id = %s", (self.current_sale_event_id,))
                        event_row = cursor.fetchone()
                        event_name = event_row['name'] if event_row else f"ID:{self.current_sale_event_id}"
                        reason_text = f"Bilet Alımı: {event_name}"
                        # Puan logu için zaman damgası, veritabanı DEFAULT CURRENT_TIMESTAMP kullanabilir
                        # veya buradan gönderebiliriz. points_log tablosu TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        # olduğu için, bu alanı INSERT sorgusundan çıkarabiliriz veya None gönderebiliriz
                        # ya da buradan bir değer gönderebiliriz. Şimdilik buradan gönderelim.
                        log_timestamp_str = QDateTime.currentDateTime().toString(Qt.DateFormat.ISODate)

                        cursor.execute("UPDATE members SET points = points + %s WHERE id = %s", 
                                    (points_to_award, self.current_sale_member_id))
                        
                        cursor.execute("""
                            INSERT INTO points_log 
                            (member_id, points_earned, reason, related_event_id, related_sale_id, log_timestamp)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (self.current_sale_member_id, points_to_award, reason_text, 
                            self.current_sale_event_id, sale_id_for_log, log_timestamp_str))
                        
                        self.db_connection.commit() # Puan güncelleme ve loglamayı commit et
                        print(f"DEBUG: Üye {self.current_sale_member_id} için bilet alım puanı ({points_to_award}) eklendi ve loglandı.")
                        points_awarded_successfully = True
                    except psycopg2.Error as e_points_db:
                        print(f"HATA: Satış kaydedildi ancak puan eklenirken/loglanırken DB hatası: {e_points_db}")
                        # Puan ekleme başarısız olursa, bu hatayı kullanıcıya bildirebiliriz.
                        # İsteğe bağlı olarak, puan eklenemezse satışı da geri alabilirsiniz:
                        # self.db_connection.rollback()
                        # QMessageBox.warning(self, "Puan Hatası", f"Bilet satışı yapıldı ancak puan eklenirken bir sorun oluştu:\n{e_points_db}")
                    except Exception as e_points_gen:
                        print(f"HATA: Satış kaydedildi ancak puan eklenirken/loglanırken genel hata: {e_points_gen}")
                        traceback.print_exc()
                        # self.db_connection.rollback()
                elif points_to_award <= 0 : # Eğer TICKET_PURCHASE_POINTS 0 veya negatifse
                    points_awarded_successfully = True # Puan verilmedi ama işlem "başarılı"
                # ---- PUAN EKLEME BİTTİ ----
            
            member_name = "Bilinmeyen Üye"
            try: 
                cursor.execute("SELECT name FROM members WHERE id = %s", (self.current_sale_member_id,))
                member_row = cursor.fetchone()
                if member_row: member_name = member_row['name']
            except: pass # Hata olursa varsayılan isim kalsın

            success_message_text = (f"'{member_name}' adlı üyeye '{ticket_type}' bilet satışı başarıyla {msg_action}.\n"
                                f"Ödenen Ücret: {price_paid_float:.2f} ₺")
            if msg_action == "kaydedildi": # Sadece yeni satışta puan mesajı göster
                if points_awarded_successfully and points_to_award > 0:
                    success_message_text += f"\n<font color='blue'><b>+{points_to_award} puan</b> kazanıldı!</font>"
                elif not points_awarded_successfully and points_to_award > 0: # Puan verilecekti ama eklenemedi
                    success_message_text += f"\n<font color='orange'>Puan eklenirken bir sorun oluştu.</font>"
            
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle(f"Satış Başarıyla {msg_action.capitalize()}")
            msg_box.setIcon(QMessageBox.Icon.Information)
            msg_box.setTextFormat(Qt.TextFormat.RichText)
            msg_box.setText(success_message_text)
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.exec()
            
            self.clear_sale_form_for_new_entry(clear_member_info=False) 
            if hasattr(self, 'update_recent_sales_list'): self.update_recent_sales_list()
            if hasattr(self, 'check_sale_button_status'): self.check_sale_button_status() 
            if hasattr(self, 'sales_uid_input'): self.sales_uid_input.setFocus()
            if hasattr(self, 'update_leaderboard'): self.update_leaderboard() # Puanlar değiştiği için lider tablosunu güncelle


        except psycopg2.IntegrityError as e_int: 
            QMessageBox.critical(self, "Veritabanı Bütünlük Hatası", f"Satış kaydedilemedi/güncellenemedi: {e_int}")
            if self.db_connection and not self.db_connection.closed: self.db_connection.rollback()
            print(f"HATA: Satış işlenirken bütünlük hatası: {e_int}")
            traceback.print_exc()
        except psycopg2.Error as e_db:
            QMessageBox.critical(self, "Veritabanı Hatası", f"Satış kaydedilirken/güncellenirken bir sorun oluştu: {e_db}")
            if self.db_connection and not self.db_connection.closed: self.db_connection.rollback()
            print(f"HATA: Satış işlenirken veritabanı hatası: {e_db}")
            traceback.print_exc()
        except Exception as e_general:
            QMessageBox.critical(self, "Beklenmedik Hata", f"Satış işlemi sırasında beklenmedik bir sorun oluştu: {e_general}")
            if self.db_connection and not self.db_connection.closed: 
                try: self.db_connection.rollback() 
                except: pass 
            print(f"HATA: Satış işlenirken genel bir hata: {e_general}")
            traceback.print_exc()
    # AdminPanel sınıfının içinde:

    def update_recent_sales_list(self):
        """Seçili etkinlik için son satışları bilet satış panelindeki tabloya yükler."""
        print("DEBUG: Bilet Satış Paneli: Son satışlar listesi güncelleniyor...")

        if not hasattr(self, 'sales_recent_sales_table'):
            print("DEBUG: HATA - update_recent_sales_list: self.sales_recent_sales_table widget'ı bulunamadı!")
            return
        
        if not hasattr(self, 'current_sale_event_id'):
            print("DEBUG: HATA - update_recent_sales_list: self.current_sale_event_id özelliği bulunamadı!")
            if hasattr(self, 'sales_recent_sales_table'): # Tablo varsa boşalt
                self.sales_recent_sales_table.setRowCount(0)
            return
            
        self.sales_recent_sales_table.setRowCount(0) # Her güncellemeden önce tabloyu temizle

        if self.current_sale_event_id is None:
            print("DEBUG: Son satışlar için gösterilecek bir etkinlik seçilmemiş.")
            # Başlıkların görünür kalması için (eğer setRowCount(0) başlıkları siliyorsa)
            # self.sales_recent_sales_table.setHorizontalHeaderLabels(["Üye Adı", "Bilet Türü", "Ücret", "Ödeme Ynt.", "Satış Zamanı"])
            return

        try:
            cursor = self.get_cursor()
            # SQL sorgusuna ts.id (ticket_sales tablosunun ID'si) alias sale_id olarak eklendi
            # LIMIT 50 son 50 satışı gösterir, performansı artırabilir.
            cursor.execute("""
                SELECT ts.id AS sale_id, m.name, ts.ticket_type, ts.price_paid, ts.payment_method, ts.sale_timestamp
                FROM ticket_sales ts
                JOIN members m ON ts.member_id = m.id
                WHERE ts.event_id = %s
                ORDER BY ts.sale_timestamp DESC 
                LIMIT 50 
            """, (self.current_sale_event_id,))
            sales_data = cursor.fetchall()

            if not sales_data:
                print(f"DEBUG: Etkinlik ID {self.current_sale_event_id} için kayıtlı bilet satışı bulunamadı.")
                return

            self.sales_recent_sales_table.setRowCount(len(sales_data))
            
            for row_idx, sale_row in enumerate(sales_data):
                sale_id = sale_row['sale_id']

                member_name = str(sale_row['name'] or '-')
                name_item = QTableWidgetItem(member_name)
                name_item.setData(Qt.ItemDataRole.UserRole, sale_id) 
                
                ticket_type = str(sale_row['ticket_type'] or '-')
                type_item = QTableWidgetItem(ticket_type)
                
                price_paid_value = sale_row['price_paid']
                price_str = f"{float(price_paid_value):.2f} ₺" if price_paid_value is not None else "-"
                price_item = QTableWidgetItem(price_str)
                price_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                
                payment_method_str = str(sale_row['payment_method'] or '-') # Değişken adını değiştirdim
                payment_item = QTableWidgetItem(payment_method_str)
                
                # --- SATIŞ ZAMANI (TIMESTAMP) İŞLEME KISMI (DÜZELTİLDİ) ---
                sale_time_str = "Bilinmiyor"
                timestamp_value = sale_row['sale_timestamp']  # Veritabanından gelen zaman damgası değeri

                if timestamp_value:  # Eğer değer None veya boş değilse
                    if isinstance(timestamp_value, datetime.datetime):
                        # Eğer değer Python'un datetime.datetime objesi ise,
                        # QDateTime'e doğrudan yıl, ay, gün, saat, dk, sn ile dönüştür
                        q_dt_obj = QDateTime(timestamp_value.year, timestamp_value.month, timestamp_value.day,
                                             timestamp_value.hour, timestamp_value.minute, timestamp_value.second)
                        # Opsiyonel: Zaman dilimi bilgisini de kullanmak isterseniz (TIMESTAMPTZ için)
                        # if timestamp_value.tzinfo:
                        #     q_dt_obj.setTimeSpec(Qt.TimeSpec.OffsetFromUTC)
                        #     q_dt_obj.setOffsetFromUtc(int(timestamp_value.utcoffset().total_seconds()))
                        #     q_dt_obj = q_dt_obj.toLocalTime() # Yerel saate çevir
                        sale_time_str = q_dt_obj.toString("dd.MM.yyyy HH:mm:ss")
                    elif isinstance(timestamp_value, str):
                        # Eğer değer zaten bir string (metin) ise, fromString ile parse etmeyi dene
                        # Önce milisaniyeli (ISODateWithMs), sonra milisaniyesiz (ISODate) dene
                        q_dt_obj = QDateTime.fromString(timestamp_value, Qt.DateFormat.ISODateWithMs)
                        if not q_dt_obj.isValid():
                            q_dt_obj = QDateTime.fromString(timestamp_value, Qt.DateFormat.ISODate)
                        
                        if q_dt_obj.isValid():
                            sale_time_str = q_dt_obj.toString("dd.MM.yyyy HH:mm:ss")
                        else:
                            sale_time_str = str(timestamp_value) # Parse edilemezse olduğu gibi göster
                    else:
                        # Beklenmedik bir tip ise
                        sale_time_str = "Bilinmeyen Zaman Formatı"
                
                time_item = QTableWidgetItem(sale_time_str)
                # --- SATIŞ ZAMANI İŞLEME KISMI BİTTİ ---

                self.sales_recent_sales_table.setItem(row_idx, 0, name_item)
                self.sales_recent_sales_table.setItem(row_idx, 1, type_item)
                self.sales_recent_sales_table.setItem(row_idx, 2, price_item)
                self.sales_recent_sales_table.setItem(row_idx, 3, payment_item)
                self.sales_recent_sales_table.setItem(row_idx, 4, time_item)
            
            # Sütun başlıklarını tekrar ayarla (setRowCount(0) bazen başlıkları da etkileyebilir)
            # Bu satır init_ticket_sales_page içinde zaten yapılıyor olabilir,
            # eğer orada yapılıyorsa burada tekrar gerek yok.
            # self.sales_recent_sales_table.setHorizontalHeaderLabels(["Üye Adı", "Bilet Türü", "Ücret", "Ödeme Ynt.", "Satış Zamanı"])
            print(f"DEBUG: {len(sales_data)} satış kaydı 'Son Satışlar' tablosuna yüklendi.")

        except psycopg2.Error as e_db:
            print(f"HATA: Son satışlar yüklenirken veritabanı hatası: {e_db}")
            QMessageBox.warning(self, "Veritabanı Hatası", f"Son satışlar listesi yüklenemedi: {e_db}")
            traceback.print_exc()
        except Exception as e_general:
            print(f"HATA: Son satışlar yüklenirken genel bir hata: {e_general}")
            QMessageBox.warning(self, "Beklenmedik Hata", f"Son satışlar listesi yüklenirken bir sorun oluştu: {e_general}")
            traceback.print_exc()
    def check_sale_button_status(self):
        """Etkinlik seçilmişse ve üye bulunmuşsa satış butonunu aktif/pasif eder."""
        # Gerekli widget'ların varlığını kontrol et
        if not hasattr(self, 'btn_process_sale') or \
        not hasattr(self, 'current_sale_event_id') or \
        not hasattr(self, 'current_sale_member_id'):
            # print("DEBUG: check_sale_button_status: Gerekli değişkenler/widget'lar henüz tanımlanmamış.")
            if hasattr(self, 'btn_process_sale'): # Buton varsa en azından pasif yapalım
                self.btn_process_sale.setEnabled(False)
            return

        # current_sale_event_id ve current_sale_member_id'nin None olup olmadığını kontrol et
        # (None değillerse, yani bir değerleri varsa, seçilmiş/bulunmuş demektir)
        if self.current_sale_event_id is not None and self.current_sale_member_id is not None:
            self.btn_process_sale.setEnabled(True)
            print("DEBUG: Satış butonu AKTİF edildi.")
        else:
            self.btn_process_sale.setEnabled(False)
            print("DEBUG: Satış butonu PASİF edildi.")
    def create_separator_line(self, orientation=Qt.Orientation.Horizontal, thickness=1, margin_top=5, margin_bottom=5):
        line = QFrame()
        if orientation == Qt.Orientation.Horizontal:
            line.setFrameShape(QFrame.Shape.HLine)
        else:
            line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setFixedHeight(thickness) if orientation == Qt.Orientation.Horizontal else line.setFixedWidth(thickness)
        line.setStyleSheet(f"margin-top: {margin_top}px; margin-bottom: {margin_bottom}px; border: none; background-color: #ccc;")
        return line
    # AdminPanel sınıfının içinde:
    def get_cursor(self):
        """PostgreSQL veritabanı cursor'ını (DictCursor) güvenli bir şekilde alır."""
        try:
            if self.db_connection is None or self.db_connection.closed != 0:
                print("DEBUG get_cursor: Bağlantı kapalı veya yok, yeniden bağlanılıyor...")
                self.db_connection = psycopg2.connect(
                    host=PG_HOST, database=PG_DATABASE, user=PG_USER,
                    password=PG_PASSWORD, port=PG_PORT, sslmode='require' # sslmode eklendi
                )
                self.db_connection.autocommit = False
                print("DEBUG get_cursor: Veritabanı bağlantısı başarıyla yeniden kuruldu.")
            # DictCursor kullanmak için cursor_factory'yi ayarla
            return self.db_connection.cursor(cursor_factory=DictCursor)
        except psycopg2.OperationalError as e_op:
            print(f"KRİTİK HATA (get_cursor): Veritabanı bağlantısı kurulamadı/geçersiz: {e_op}")
            QMessageBox.critical(self, "Veritabanı Bağlantı Hatası", f"Veritabanı bağlantısı kullanılamıyor:\n{e_op}\nUygulama kapatılacak.")
            QApplication.instance().quit(); sys.exit(f"Kritik get_cursor Hatası: {e_op}")
        except Exception as e_gen:
            print(f"KRİTİK HATA (get_cursor): Beklenmedik hata: {e_gen}")
            QMessageBox.critical(self, "Kritik Hata", f"Veritabanı cursor alınırken hata: {e_gen}\nUygulama kapatılacak.")
            traceback.print_exc(); QApplication.instance().quit(); sys.exit(f"Kritik get_cursor Hatası: {e_gen}")
    def apply_style(self):
        """Ayarlara göre açık veya koyu temayı uygular."""
        theme = self.settings.get("theme", "light"); print(f"Tema uygulanıyor: {theme}")
        # Stil tanımları (önceki kod bloğundan alındı, değişiklik yok)
        light_theme_qss = """ QWidget { background-color: #f0f4f8; font-family: Arial; font-size: 14px; color: #333; } QLabel { color: #333; } QLineEdit, QComboBox, QDateEdit, QTextEdit, QSpinBox { background-color: white; border: 1px solid #ccc; padding: 6px; border-radius: 4px; min-height: 24px; color: #333;} QLineEdit { selection-background-color: #a8d1ff; } QPushButton { background-color: #007bff; color: white; border: none; padding: 10px 18px; border-radius: 5px; min-height: 24px; cursor: pointer; } QPushButton:hover { background-color: #0056b3; } QPushButton#btn_backup, QPushButton#btn_restore { background-color: #ff9800; } QPushButton#btn_backup:hover, QPushButton#btn_restore:hover { background-color: #f57c00; } QPushButton#btn_delete { background-color: #dc3545; } QPushButton#btn_delete:hover { background-color: #c82333; } QPushButton#btn_export, QPushButton#btn_import { background-color: #17a2b8; } QPushButton#btn_export:hover, QPushButton#btn_import:hover { background-color: #138496; } QPushButton#btn_logout, QPushButton#btn_settings { background-color: #6c757d; padding: 5px 10px; font-size: 12px; } QPushButton#btn_logout:hover, QPushButton#btn_settings:hover { background-color: #5a6268; } QPushButton.btn_details { background-color: #6c757d; color: white; padding: 2px 8px; font-size: 11px; border-radius: 3px; margin-left: 10px; max-width: 50px;} QPushButton.btn_details:hover { background-color: #5a6268; } QPushButton#btn_member_report { background-color: #fd7e14; padding: 8px 15px; font-size: 13px; } QPushButton#btn_member_report:hover { background-color: #e66a04; } QTableWidget { background-color: white; border: 1px solid #ccc; selection-background-color: #cfe2ff; selection-color: #000; gridline-color: #dee2e6; color: #333; } QHeaderView::section { background-color: #6c757d; color: white; padding: 5px; border: none; border-bottom: 1px solid #ccc; } QListWidget { border: 1px solid #ccc; background-color: white; padding: 4px; color: #333; } QTextEdit { font-size: 13px; color: #333; } #link_label { color: #007bff; text-decoration: underline; } #statsFrame { border: 1px solid #ced4da; border-radius: 5px; background-color: #e9ecef; padding: 5px; } #statsLabel { font-size: 13px; font-weight: bold; color: #495057; margin-bottom: 0px; padding-bottom: 0px;} #statsValue { font-size: 16px; font-weight: bold; color: #007bff; margin-top: 0px; padding-top: 0px;} #upcomingEventsLabel { font-size: 14px; font-weight: bold; color: #495057; margin-top: 10px; } #settingsPageTitle { font-size: 18px; font-weight: bold; margin-bottom: 10px; } #settingsSectionLabel { font-weight: bold; margin-top: 10px; margin-bottom: 3px; } """
        dark_theme_qss = """ QWidget { background-color: #2d2d2d; font-family: Arial; font-size: 14px; color: #e0e0e0; } QLabel { color: #e0e0e0; } QLineEdit, QComboBox, QDateEdit, QTextEdit, QSpinBox { background-color: #3c3c3c; border: 1px solid #555; padding: 6px; border-radius: 4px; min-height: 24px; color: #e0e0e0; } QLineEdit { selection-background-color: #005cbf; selection-color: white; } QPushButton { background-color: #005cbf; color: white; border: none; padding: 10px 18px; border-radius: 5px; min-height: 24px; cursor: pointer; } QPushButton:hover { background-color: #00418c; } QPushButton#btn_backup, QPushButton#btn_restore { background-color: #e08e0b; } QPushButton#btn_backup:hover, QPushButton#btn_restore:hover { background-color: #c87a00; } QPushButton#btn_delete { background-color: #b02a37; } QPushButton#btn_delete:hover { background-color: #91232d; } QPushButton#btn_export, QPushButton#btn_import { background-color: #138496; } QPushButton#btn_export:hover, QPushButton#btn_import:hover { background-color: #106775; } QPushButton#btn_logout, QPushButton#btn_settings { background-color: #5a6268; padding: 5px 10px; font-size: 12px; } QPushButton#btn_logout:hover, QPushButton#btn_settings:hover { background-color: #474d52; } QPushButton.btn_details { background-color: #5a6268; color: white; padding: 2px 8px; font-size: 11px; border-radius: 3px; margin-left: 10px; max-width: 50px;} QPushButton.btn_details:hover { background-color: #474d52; } QPushButton#btn_member_report { background-color: #e08e0b; padding: 8px 15px; font-size: 13px; } QPushButton#btn_member_report:hover { background-color: #c87a00; } QTableWidget { background-color: #3c3c3c; border: 1px solid #555; selection-background-color: #005cbf; selection-color: white; gridline-color: #555; color: #e0e0e0; } QHeaderView::section { background-color: #5a6268; color: white; padding: 5px; border: none; border-bottom: 1px solid #555; } QListWidget { border: 1px solid #555; background-color: #3c3c3c; padding: 4px; color: #e0e0e0; } QTextEdit { font-size: 13px; color: #e0e0e0; background-color: #3c3c3c; border: 1px solid #555;} #link_label { color: #3498db; text-decoration: underline; } #statsFrame { border: 1px solid #444; border-radius: 5px; background-color: #3c3c3c; padding: 5px; } #statsLabel { font-size: 13px; font-weight: bold; color: #adb5bd; margin-bottom: 0px; padding-bottom: 0px;} #statsValue { font-size: 16px; font-weight: bold; color: #58a6ff; margin-top: 0px; padding-top: 0px;} #upcomingEventsLabel { font-size: 14px; font-weight: bold; color: #adb5bd; margin-top: 10px; } #settingsPageTitle { font-size: 18px; font-weight: bold; margin-bottom: 10px; color: #e0e0e0;} #settingsSectionLabel { font-weight: bold; margin-top: 10px; margin-bottom: 3px; color: #e0e0e0;} QDialog { background-color: #2d2d2d; } QMessageBox { background-color: #3c3c3c; color: #e0e0e0; } QMessageBox QLabel { color: #e0e0e0; } QMessageBox QPushButton { background-color: #005cbf; color: white; min-width: 60px; } QMessageBox QPushButton:hover { background-color: #00418c; } QMenu { background-color: #3c3c3c; color: #e0e0e0; border: 1px solid #555; } QMenu::item:selected { background-color: #005cbf; } """
        if theme == "dark": self.setStyleSheet(dark_theme_qss)
        else: self.setStyleSheet(light_theme_qss)
        # Login penceresinin stilini de güncelle (varsa ve görünürse)
        try:
            if self.login_window: # and self.login_window.isVisible(): # Görünür olmasa da stil değişebilir
                self.login_window.apply_login_style(theme)
        except Exception as e:
            print(f"Login penceresi stili güncellenemedi (muhtemelen kapalı): {e}")
            pass # Login penceresi yoksa veya hata olursa devam et

    def create_shortcuts(self):
        """Uygulama genelindeki klavye kısayollarını oluşturur."""
        # Ctrl+N: Yeni üye ekleme formunu aç ve isim alanına odaklan
        self.add_member_shortcut = QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_N);
        self.add_member_action = QAction("Üye Ekle", self);
        self.add_member_action.setShortcut(self.add_member_shortcut);
        self.add_member_action.triggered.connect(self.show_member_form_and_focus);
        self.addAction(self.add_member_action)

        # Ctrl+F (veya Cmd+F): Üye arama alanına odaklan
        self.search_member_shortcut = QKeySequence.StandardKey.Find;
        self.search_member_action = QAction("Üye Ara", self);
        self.search_member_action.setShortcut(self.search_member_shortcut);
        self.search_member_action.triggered.connect(self.focus_member_search);
        self.addAction(self.search_member_action)

        # TODO: Belki başka kısayollar eklenebilir (Ctrl+E Etkinlik, Ctrl+S Kaydet vb.)

    def show_member_form_and_focus(self):
        # Üye formunu göster ve isim giriş alanına odaklan
        self.show_member_form();
        if self.name_input: # Widget oluşturulmuşsa odaklan
            self.name_input.setFocus()

    def focus_member_search(self):
        # Eğer üye formunda değilse, önce o sayfaya geç
        if self.stacked_widget.currentWidget() != self.member_form_page:
            self.show_member_form()
        # Üye arama giriş alanına odaklan
        if self.member_search_input: # Widget oluşturulmuşsa odaklan
             self.member_search_input.setFocus()

    def open_link(self, url_str):
        # Verilen URL'yi sistemin varsayılan tarayıcısında açar
        if not url_str.startswith("http"):
            url_str = "https://" + url_str # http/https yoksa ekle
        QDesktopServices.openUrl(QUrl(url_str))

    # --- init_ Sayfa Metodları (Arayüz Oluşturma - Refaktör Edilmiş) ---
    # --- Üye Profili Fonksiyonları ---

    def show_member_profile_by_id(self, member_id):
        """Verilen ID'ye sahip üyenin profilini gösterir."""
        if member_id is None:
            return
        # Widget'lar var mı kontrol et (Bu kontrol, profil sayfası widget'larının __init__ içinde
        # None olarak başlatılıp sonra init_member_profile_page içinde oluşturulduğunu varsayar)
        required_widgets = [
            self.profile_name_label, self.profile_uid_label, self.profile_role_label,
            self.profile_membership_date_label, self.profile_dep_label,
            self.profile_year_label, self.profile_email_label, self.profile_phone_label,
            self.profile_interests_label, self.profile_photo_label,
            self.profile_attendance_list
        ]
        if any(widget is None for widget in required_widgets):
            QMessageBox.critical(self, "Hata", "Üye profil sayfası elemanları henüz tam olarak yüklenmemiş.")
            # Eğer profil sayfası widget'ları __init__ içinde None olarak başlatılmıyorsa
            # ve init_member_profile_page çağrılmadan buraya gelinirse bu hata alınır.
            # Bu durumda, init_member_profile_page'in çağrıldığından emin olunmalı.
            # Ancak, normal akışta bu widget'ların __init__ içinde tanımlanmış olması gerekir.
            return

        self.current_profile_member_id = member_id # Gösterilen ID'yi sakla
        try:
            cursor = self.get_cursor()
            # Veritabanından member_id'ye göre tüm sütunları seç
            cursor.execute("SELECT * FROM members WHERE id = %s", (member_id,))
            member_data_row = cursor.fetchone() # sqlite3.Row nesnesi döndürür

            if member_data_row:
                # sqlite3.Row nesnesini bir sözlüğe çevirerek show_member_profile metoduna gönder
                member_data_dict = dict(member_data_row)
                self.show_member_profile(member_data_dict)
            else:
                QMessageBox.warning(self, "Bulunamadı", f"ID'si {member_id} olan üye bulunamadı.")
                self.current_profile_member_id = None # ID'yi sıfırla

        except psycopg2.Error as e:
            QMessageBox.critical(self, "Veritabanı Hatası", f"Üye profili yüklenirken hata: {e}")
            self.current_profile_member_id = None
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Üye profili yüklenirken beklenmedik hata: {e}")
            self.current_profile_member_id = None
            # Hatanın tam kaynağını görmek için traceback'i yazdır
            import traceback
            traceback.print_exc()
    # AdminPanel sınıfının içine (diğer metodlarla birlikte):
    # AdminPanel sınıfının içine (diğer metodlarla birlikte):
    def adjust_member_points(self):
        """Profil sayfasındaki manuel girişleri kullanarak üyenin puanını ayarlar ve loglar."""

        print("DEBUG: adjust_member_points çağrıldı.")
        # Gerekli widget'lar ve değişkenler var mı?
        if not all(hasattr(self, attr) and getattr(self, attr) is not None for attr in [
            'current_profile_member_id', 'manual_points_spinbox', 
            'manual_points_reason_input', 'profile_points_label'
        ]):
            QMessageBox.critical(self, "Hata", "Puan ayarlama için gerekli elemanlar bulunamadı veya None.")
            return

        if self.current_profile_member_id is None:
            QMessageBox.warning(self, "Üye Seçilmedi", "Puanı ayarlanacak üye profili görüntülenmiyor.")
            return

        points_to_adjust = self.manual_points_spinbox.value()
        reason = self.manual_points_reason_input.text().strip()

        if points_to_adjust == 0:
            QMessageBox.warning(self, "Geçersiz Miktar", "Lütfen eklenecek veya çıkarılacak puan miktarını (0'dan farklı) girin.")
            self.manual_points_spinbox.setFocus()
            return

        if not reason:
            QMessageBox.warning(self, "Neden Gerekli", "Lütfen puan ayarlama için bir neden girin (örn: Gönüllülük, Ödül, Düzeltme).")
            self.manual_points_reason_input.setFocus()
            return

        # Kullanıcıya onay soralım
        action_text = "eklemek" if points_to_adjust > 0 else "çıkarmak"
        # Emin olmak için üye adını da çekelim
        member_name = "Bilinmeyen üye"
        try:
            cursor = self.get_cursor()
            cursor.execute("SELECT name FROM members WHERE id = %s", (self.current_profile_member_id,))
            member_row = cursor.fetchone()
            if member_row:
                member_name = member_row['name']
        except Exception as e_name:
            print(f"Onay mesajı için üye adı alınırken hata: {e_name}")

        reply = QMessageBox.question(self, "Puan Ayarlama Onayı",
                                    f"<b>'{member_name}'</b> adlı üyeye '{reason}' nedeniyle <b>{points_to_adjust}</b> puan {action_text} istediğinizden emin misiniz?",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            try:
                cursor = self.get_cursor()
                log_timestamp = QDateTime.currentDateTime().toString(Qt.DateFormat.ISODate)
                reason_with_prefix = f"Manuel Ayarlama: {reason}" # Loga 'Manuel' ön eki ekleyelim

                # 1. Üyenin puanını güncelle
                # Önce mevcut puanı kontrol edebiliriz (negatife düşmemesi için vs.) - Opsiyonel
                cursor.execute("UPDATE members SET points = points + %s WHERE id = %s", 
                            (points_to_adjust, self.current_profile_member_id))

                # 2. Puan işlemini logla
                cursor.execute("""
                    INSERT INTO points_log 
                    (member_id, points_earned, reason, log_timestamp) 
                    VALUES (%s, %s, %s, %s)
                """, (self.current_profile_member_id, points_to_adjust, reason_with_prefix, log_timestamp))

                self.db_connection.commit()

                print(f"DEBUG: Üye {self.current_profile_member_id} için manuel olarak {points_to_adjust} puan ayarlandı. Neden: {reason}")

                # Başarı mesajı ve arayüzü güncelle
                QMessageBox.information(self, "Başarılı", f"Üyenin puanı başarıyla {points_to_adjust} olarak ayarlandı.")

                # Formu temizle
                self.manual_points_spinbox.setValue(0)
                self.manual_points_reason_input.clear()

                # Profildeki puan etiketini güncelle (yeni puanı çekerek)
                cursor.execute("SELECT points FROM members WHERE id = %s", (self.current_profile_member_id,))
                updated_points_row = cursor.fetchone()
                if updated_points_row and hasattr(self, 'profile_points_label'):
                    new_total_points = updated_points_row['points'] if updated_points_row['points'] is not None else 0
                    self.profile_points_label.setText(f"<b>Puan:</b> {new_total_points}")

                # Ana sayfadaki liderlik tablosunu da güncelle
                if hasattr(self, 'update_leaderboard'):
                    self.update_leaderboard()

            except psycopg2.Error as e_db:
                QMessageBox.critical(self, "Veritabanı Hatası", f"Puan ayarlanırken bir veritabanı hatası oluştu: {e_db}")
                traceback.print_exc()
            except Exception as e_general:
                QMessageBox.critical(self, "Beklenmedik Hata", f"Puan ayarlama sırasında beklenmedik bir sorun oluştu: {e_general}")
                traceback.print_exc()
    def convert_tr_to_eng(self, text):
        """Türkçe karakterleri İngilizce Alfabesi'ndeki karşılıklarına çevirir."""
        if text is None:
            return ""
        tr_to_eng_map = {
            'ç': 'c', 'ğ': 'g', 'ı': 'i', 'ö': 'o', 'ş': 's', 'ü': 'u',
            'Ç': 'C', 'Ğ': 'G', 'İ': 'I', 'Ö': 'O', 'Ş': 'S', 'Ü': 'U'
        }
        # Daha genel bir yaklaşım için unidecode kütüphanesi de düşünülebilir,
        # ama basit harf değişimi için bu yeterli.
        # Alternatif olarak str.maketrans ve translate kullanılabilir:
        # turkish_chars = "çğıöşüÇĞİÖŞÜ"
        # english_chars = "cgiosuCGIOSU"
        # tran_tab = str.maketrans(turkish_chars, english_chars)
        # return text.translate(tran_tab)

        new_text = ""
        for char in str(text): # Gelen metni string'e çevirdiğimizden emin olalım
            new_text += tr_to_eng_map.get(char, char)
        return new_text
    # AdminPanel sınıfı içinde:
    # AdminPanel sınıfı içinde:
    # AdminPanel sınıfı içinde:
    # AdminPanel sınıfı içinde:
# AdminPanel sınıfı içinde:
    def init_main_page(self):
        """Ana sayfanın arayüzünü oluşturur (SON DÜZELTİLMİŞ HAL)."""
        # Ana layout'u oluştur (self.main_page QWidget'ı __init__ içinde oluşturulmuş olmalı)
        layout = QVBoxLayout(self.main_page) 
        layout.setSpacing(15)
        layout.setContentsMargins(15, 15, 15, 15) # Kenar boşlukları

        # --- 1. Header Bölümü ---
        header_layout = QHBoxLayout()
        # Logo
        self.main_logo_label = QLabel("🦊") 
        self.main_logo_label.setStyleSheet("font-size: 48px; margin-right: 10px;")
        header_layout.addWidget(self.main_logo_label, alignment=Qt.AlignmentFlag.AlignTop)
        # Başlık ve Linkler Ortada
        title_layout = QVBoxLayout()
        title = QLabel(f"{CLUB_NAME} Yönetim Paneli")
        title.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 5px;")
        website_label = QLabel(f'<a href="https://{CLUB_WEBSITE}">{CLUB_WEBSITE}</a>')
        website_label.setObjectName("link_label"); website_label.setOpenExternalLinks(True)
        website_label.setStyleSheet("font-size: 12px;")
        instagram_label = QLabel(f'<a href="https://{CLUB_INSTAGRAM}">{CLUB_INSTAGRAM}</a>')
        instagram_label.setObjectName("link_label"); instagram_label.setOpenExternalLinks(True)
        instagram_label.setStyleSheet("font-size: 12px;")
        title_layout.addWidget(title); title_layout.addWidget(website_label); title_layout.addWidget(instagram_label)
        title_layout.addStretch() 
        header_layout.addLayout(title_layout, 1) 
        # Sağ Üst Butonlar
        top_right_buttons_layout = QVBoxLayout(); top_right_buttons_layout.setSpacing(5)
        settings_button = QPushButton("Ayarlar"); settings_button.setObjectName("btn_settings")
        settings_button.setFixedSize(100, 30); settings_button.clicked.connect(self.show_settings_page)
        top_right_buttons_layout.addWidget(settings_button)
        logout_button = QPushButton("Çıkış Yap"); logout_button.setObjectName("btn_logout")
        logout_button.setFixedSize(100, 30); logout_button.clicked.connect(self.logout)
        top_right_buttons_layout.addWidget(logout_button)
        top_right_buttons_layout.addStretch() 
        header_layout.addLayout(top_right_buttons_layout)
        layout.addLayout(header_layout)
        
        # Ayırıcı Çizgi (Eğer create_separator_line metodu varsa)
        if hasattr(self, 'create_separator_line') and callable(self.create_separator_line):
            try:
                layout.addWidget(self.create_separator_line())
            except Exception as e_sep:
                print(f"Ayırıcı çizgi eklenirken hata: {e_sep}") 
        
        # --- 2. İstatistik Bölümü ---
        stats_frame = QFrame(); stats_frame.setObjectName("statsFrame")
        stats_grid_layout = QGridLayout(stats_frame) # QGridLayout'u QFrame'e ata
        stats_grid_layout.setContentsMargins(15, 10, 15, 10); stats_grid_layout.setHorizontalSpacing(20); stats_grid_layout.setVerticalSpacing(10)

        # İstatistik etiketlerini oluştur ve self'e ata
        self.stats_total_members_label = QLabel("-")
        self.stats_total_events_label = QLabel("-")
        self.stats_upcoming_events_label = QLabel("-")

        # --- İstatistik satırı oluşturma yardımcısı (nested function tanımı) ---
        def create_stat_entry(parent_self, label_text, value_label_widget, detail_button_slot=None):
            # Dikkat: Nested fonksiyon dışarıdaki 'self'e doğrudan erişemez,
            # bu yüzden 'parent_self' olarak iletmemiz veya slot'ları lambda ile bağlamamız gerekir.
            # Ya da en temizi, bu fonksiyonu AdminPanel'in normal bir metodu yapmaktır.
            # Şimdilik slot'ların zaten self'e ait olduğunu varsayarak devam edelim.
            label = QLabel(label_text); label.setObjectName("statsLabel")
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            value_label_widget.setObjectName("statsValue") # self.stats_... etiketleri zaten yukarıda oluşturuldu
            value_label_widget.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            container_widget = QWidget(); hbox = QHBoxLayout(container_widget)
            hbox.setContentsMargins(0,0,0,0); hbox.setSpacing(5)
            hbox.addWidget(value_label_widget, 1) 
            if detail_button_slot: 
                detail_button = QPushButton("Detay"); detail_button.setObjectName("btn_details")
                detail_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed) 
                detail_button.setFixedWidth(60) 
                # detail_button_slot zaten self'e bağlı bir metot (örn: self.show_member_form)
                detail_button.clicked.connect(detail_button_slot) 
                hbox.addWidget(detail_button)
            else: hbox.addStretch(0) 
            return label, container_widget
        # --- Yardımcı fonksiyon tanımı bitti ---

        # --- İstatistik satırlarını oluştur ve grid'e ekle ---
        # self.show_member_form gibi metotlar zaten self'e bağlı olduğu için doğrudan kullanılabilir.
        try:
            label1, widget1 = create_stat_entry(self, "Toplam Üye:", self.stats_total_members_label, self.show_member_form)
            label3, widget3 = create_stat_entry(self, "Toplam Etkinlik:", self.stats_total_events_label, self.show_event_form)
            label4, widget4 = create_stat_entry(self, "Yaklaşan Etkinlik:", self.stats_upcoming_events_label, self.show_event_form)
            
            stats_grid_layout.addWidget(label1, 0, 0) 
            stats_grid_layout.addWidget(widget1, 0, 1) 
            stats_grid_layout.addWidget(label3, 1, 0)
            stats_grid_layout.addWidget(widget3, 1, 1)
            stats_grid_layout.addWidget(label4, 2, 0)
            stats_grid_layout.addWidget(widget4, 2, 1)
            stats_grid_layout.setColumnStretch(1, 1) 
        except Exception as e_stats:
             print(f"HATA: İstatistik bölümü oluşturulurken: {e_stats}")
             traceback.print_exc()
        # --- İstatistik grid'i bitti ---

        layout.addWidget(stats_frame) # İstatistik çerçevesini ana layout'a ekle

        # --- 3. Raporlar ve Listeler Bölümü ---
        reports_lists_layout = QHBoxLayout()
        reports_lists_layout.setSpacing(15)

        # 3.1 Sol Taraf: Rapor Butonları ve Yaklaşan Etkinlikler
        left_column_layout = QVBoxLayout()
        self.btn_member_reports = QPushButton("📊 Üye Raporları (Grafik)")
        self.btn_member_reports.setObjectName("btn_member_report")
        self.btn_member_reports.clicked.connect(self.show_member_reports_chart)
        left_column_layout.addWidget(self.btn_member_reports)
        self.upcoming_events_label_widget = QLabel("Yaklaşan Etkinlikler:")
        self.upcoming_events_label_widget.setObjectName("upcomingEventsLabel")
        left_column_layout.addWidget(self.upcoming_events_label_widget)
        self.upcoming_events_list = QListWidget()
        self.upcoming_events_list.itemDoubleClicked.connect(self.go_to_event_from_main_list)
        self.upcoming_events_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_column_layout.addWidget(self.upcoming_events_list, 1) 
        reports_lists_layout.addLayout(left_column_layout, 1)

        # 3.2 Sağ Taraf: Liderlik Tablosu
        right_column_layout = QVBoxLayout()
        leaderboard_title = QLabel("🏆 Puan Sıralaması (İlk 10)")
        leaderboard_title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 5px;")
        right_column_layout.addWidget(leaderboard_title)
        self.leaderboard_table = QTableWidget() 
        self.leaderboard_table.setColumnCount(3)
        self.leaderboard_table.setHorizontalHeaderLabels(["Sıra", "Ad Soyad", "Puan"])
        self.leaderboard_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.leaderboard_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.leaderboard_table.verticalHeader().setVisible(False)
        self.leaderboard_table.setAlternatingRowColors(True)
        leaderboard_header = self.leaderboard_table.horizontalHeader()
        leaderboard_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        leaderboard_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch) 
        leaderboard_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.leaderboard_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right_column_layout.addWidget(self.leaderboard_table, 1) 
        reports_lists_layout.addLayout(right_column_layout, 1) 
        
        # Raporlar/Listeler bölümünü ana layout'a ekle, dikeyde genişlemesini sağla (stretch=1)
        layout.addLayout(reports_lists_layout, 1) 

        # --- 4. Alt Butonlar ---
        bottom_buttons_container = QWidget() 
        bottom_buttons_layout = QHBoxLayout(bottom_buttons_container)
        bottom_buttons_layout.setContentsMargins(0, 10, 0, 0) 
        bottom_buttons_layout.setSpacing(10)
        # Ana Butonlar (Ortada)
        main_actions_layout = QHBoxLayout()
        btn_add_member = QPushButton("👥 Üyeleri Yönet"); btn_add_member.setMinimumHeight(35); btn_add_member.clicked.connect(self.show_member_form); main_actions_layout.addWidget(btn_add_member)
        btn_add_event = QPushButton("📅 Etkinlikleri Yönet"); btn_add_event.setMinimumHeight(35); btn_add_event.clicked.connect(self.show_event_form); main_actions_layout.addWidget(btn_add_event)
        btn_ticket_sales = QPushButton("🎫 Bilet Satışı"); btn_ticket_sales.setMinimumHeight(35); btn_ticket_sales.clicked.connect(self.show_ticket_sales_page); main_actions_layout.addWidget(btn_ticket_sales)
        bottom_buttons_layout.addStretch(1); bottom_buttons_layout.addLayout(main_actions_layout); bottom_buttons_layout.addStretch(1)
        # Sistem Butonları (Sağda)
        system_actions_layout = QHBoxLayout()
        btn_backup = QPushButton("💾 Yedekle"); btn_backup.setObjectName("btn_backup");  system_actions_layout.addWidget(btn_backup)
        btn_restore = QPushButton("🔄 Geri Yükle"); btn_restore.setObjectName("btn_restore");  system_actions_layout.addWidget(btn_restore)
        btn_demo_data = QPushButton("🧪 Demo Veri"); btn_demo_data.setStyleSheet("background-color: #ffc107; color: black;");  system_actions_layout.addWidget(btn_demo_data)
        bottom_buttons_layout.addLayout(system_actions_layout) 
        # Alt buton grubunu ana layout'a ekle, dikeyde genişlemesin (stretch=0)
        layout.addWidget(bottom_buttons_container, 0) 

        # --- EN SON ADIM: Sayfayı Stacked Widget'a Eklemek ---
        # Bu satırın metodun en sonunda olması kritik!
        if self.stacked_widget.indexOf(self.main_page) == -1:
             self.stacked_widget.addWidget(self.main_page)
             print("DEBUG: init_main_page tamamlandı ve self.main_page stacked widget'a eklendi.")
        else:
             print("DEBUG: init_main_page tamamlandı (self.main_page zaten stack'te vardı).")
    # --- init_main_page METODU BURADA BİTER ---
    def update_leaderboard(self, limit=10): # Varsayılan olarak ilk 10 kişiyi göster
        """Ana sayfadaki liderlik tablosunu günceller."""
        print(f"DEBUG: Liderlik tablosu güncelleniyor (İlk {limit})...")

        if not hasattr(self, 'leaderboard_table'):
            print("DEBUG: HATA - update_leaderboard: self.leaderboard_table bulunamadı!")
            return

        self.leaderboard_table.setRowCount(0) # Tabloyu temizle

        try:
            cursor = self.get_cursor()
            # En yüksek puanlı üyeleri çek (puanı 0'dan büyük olanları alalım)
            query = "SELECT name, points FROM members WHERE points > 0 ORDER BY points DESC LIMIT %s"
            cursor.execute(query, (limit,))
            top_members = cursor.fetchall()

            if not top_members:
                print("DEBUG: Liderlik tablosu için yeterli puana sahip üye bulunamadı.")
                # İsteğe bağlı: Tabloya "Henüz puan kazanan yok" gibi bir mesaj eklenebilir
                # self.leaderboard_table.setRowCount(1)
                # no_data_item = QTableWidgetItem("Henüz puan kazanan üye yok.")
                # self.leaderboard_table.setItem(0, 0, no_data_item) 
                # self.leaderboard_table.setSpan(0, 0, 1, 3) # Mesajı 3 sütuna yay
                return

            self.leaderboard_table.setRowCount(len(top_members))
            for rank, member_row in enumerate(top_members):
                rank_item = QTableWidgetItem(str(rank + 1)) # Sıra no (1'den başlar)
                rank_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter) # Ortala

                name_item = QTableWidgetItem(member_row['name'])

                points_item = QTableWidgetItem(str(member_row['points']))
                points_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter) # Sağa yasla

                self.leaderboard_table.setItem(rank, 0, rank_item)
                self.leaderboard_table.setItem(rank, 1, name_item)
                self.leaderboard_table.setItem(rank, 2, points_item)

            print(f"DEBUG: Liderlik tablosu {len(top_members)} üye ile güncellendi.")

        except psycopg2.Error as e_db:
            print(f"HATA: Liderlik tablosu verisi çekilirken DB hatası: {e_db}")
            # Hata durumunda tabloya bir mesaj yazılabilir.
        except Exception as e_general:
            print(f"HATA: Liderlik tablosu güncellenirken genel hata: {e_general}")
            traceback.print_exc()
        
        
        
    def load_member_photo_to_label(self, photo_filename, target_label_widget):
        """
        Verilen SADECE dosya adını kullanarak MEMBER_PHOTOS_DIR içindeki
        fotoğrafı bulur ve hedef QLabel widget'ına yükler.
        photo_filename yol içermemeli, sadece 'resim.jpg' gibi olmalıdır.
        """
        if not target_label_widget:
            print("DEBUG: load_member_photo_to_label - Hedef etiket widget'ı (target_label_widget) None, çıkılıyor.")
            return

        target_label_widget.setText("Fotoğraf Yok") 
        target_label_widget.setPixmap(QPixmap()) # Önceki resmi temizle (önemli)   

        if not photo_filename: # Eğer dosya adı boş veya None ise
            # print("DEBUG: load_member_photo_to_label - photo_filename boş, fotoğraf gösterilmeyecek.")
            return 

        # self.MEMBER_PHOTOS_DIR'in __init__ içinde tanımlandığından emin olun (örn: "member_photos")
        actual_photo_path = os.path.join(self.MEMBER_PHOTOS_DIR, str(photo_filename)) # str() ile tip güvenliği

        print(f"DEBUG: load_member_photo_to_label - Fotoğraf yüklenmeye çalışılıyor: '{actual_photo_path}'")

        if os.path.exists(actual_photo_path):
            pixmap = QPixmap(actual_photo_path)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(target_label_widget.size(), 
                                            Qt.AspectRatioMode.KeepAspectRatio, 
                                            Qt.TransformationMode.SmoothTransformation)
                target_label_widget.setPixmap(scaled_pixmap)
                print(f"DEBUG: load_member_photo_to_label - Fotoğraf başarıyla yüklendi: '{actual_photo_path}'")
            else:
                target_label_widget.setText("Fotoğraf\nYüklenemedi")
                print(f"Uyarı: Fotoğraf dosyası geçersiz veya QPixmap yükleyemedi ({actual_photo_path})")
        else:
            target_label_widget.setText("Fotoğraf\nBulunamadı")
            print(f"Uyarı: Fotoğraf dosyası '{self.MEMBER_PHOTOS_DIR}' klasöründe bulunamadı: '{actual_photo_path}'")
    def init_member_form(self):
            """Üye listesi ve ekleme formunun arayüzünü oluşturur (YENİDEN BAŞLANGIÇ)."""
            # Sayfa için ana widget (eğer __init__ içinde self.member_form_page = QWidget() olarak tanımlanmadıysa burada oluşturun)
            # Eğer __init__ içinde tanımlıysa bu satıra gerek yok:
            # self.member_form_page = QWidget() 

            layout = QVBoxLayout(self.member_form_page) # Layout'u sayfaya ata
            layout.setSpacing(10) # Widget'lar arası genel boşluk

            # 1. Geri Butonu ve Başlık
            header_top_layout = QHBoxLayout()
            back_button = QPushButton("← Ana Sayfa")
            back_button.setFixedSize(120, 30)
            back_button.clicked.connect(self.show_main_page)
            header_top_layout.addWidget(back_button)
            header_top_layout.addStretch() # Butonu sola yaslar
            layout.addLayout(header_top_layout)

            list_title = QLabel("Üye Listesi")
            list_title.setStyleSheet("font-size: 16px; font-weight: bold; margin-top:5px; margin-bottom: 5px;")
            layout.addWidget(list_title)

            # 2. Filtreleme Alanı
            filter_layout = QHBoxLayout()
            self.member_search_input = QLineEdit()
            self.member_search_input.setPlaceholderText("Ad, Bölüm, E-posta veya İlgi Alanına Göre Ara...")
            self.member_search_input.textChanged.connect(self.update_member_list)
            filter_layout.addWidget(self.member_search_input, 1) # Stretch faktörü 1

            self.role_filter_combo = QComboBox()
            # Rolleri basitleştirelim şimdilik, sonra ayarları eklersiniz
            roles = ["Tüm Roller", "Aktif Üye", "Normal Üye", "Yönetim Kurulu Üyesi"]
            self.role_filter_combo.addItems(roles)
            self.role_filter_combo.currentIndexChanged.connect(self.update_member_list)
            filter_layout.addWidget(self.role_filter_combo) # Stretch faktörü varsayılan (0)
            layout.addLayout(filter_layout)

            # 3. Üye Tablosu
            self.member_table = QTableWidget()
            self.member_table.setColumnCount(5)
            self.member_table.setHorizontalHeaderLabels(["Ad Soyad", "Bölüm", "Rol", "E-posta", "Üyelik Tarihi"])
            self.member_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            self.member_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            self.member_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
            self.member_table.verticalHeader().setVisible(False)
            self.member_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.member_table.customContextMenuRequested.connect(self.on_member_table_context_menu)
            self.member_table.itemDoubleClicked.connect(self.handle_member_double_click)

            # Sütun Genişlikleri (Basit Ayarlar)
            self.member_table.setColumnWidth(0, 180)  # Ad Soyad
            self.member_table.setColumnWidth(1, 200)  # Bölüm
            self.member_table.setColumnWidth(2, 120)  # Rol
            self.member_table.setColumnWidth(3, 220)  # E-posta
            self.member_table.horizontalHeader().setStretchLastSection(True) # Son sütun genişlesin
            
            # ---- TABLOYU BÜYÜTMEK İÇİN ÖNEMLİ SATIRLAR ----
            self.member_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            layout.addWidget(self.member_table, 1) # Stretch faktörü 1, tablonun dikeyde genişlemesini sağlar
            # init_member_form metodu içinde, layout.addWidget(self.member_table, 1) satırından sonra:

        # İçe/Dışa Aktarma Butonları
            exim_btn_layout = QHBoxLayout()
            exim_btn_layout.addStretch() # Butonları sağa yasla
            
            btn_import_csv = QPushButton("CSV'den İçe Aktar")
            btn_import_csv.setObjectName("btn_import") # Stil için
            btn_import_csv.setIcon(QIcon.fromTheme("document-import"))
            btn_import_csv.clicked.connect(self.import_members_from_csv) 
            exim_btn_layout.addWidget(btn_import_csv)

            btn_export_emails = QPushButton("E-posta Listesi (.csv)")
            btn_export_emails.setObjectName("btn_export") # Stil için
            btn_export_emails.clicked.connect(self.export_emails) 
            exim_btn_layout.addWidget(btn_export_emails)

            btn_export_members = QPushButton("Tüm Üye Verisi (.json)")
            btn_export_members.setObjectName("btn_export") # Stil için
            btn_export_members.clicked.connect(self.export_member_data) 
            exim_btn_layout.addWidget(btn_export_members)
            
            layout.addLayout(exim_btn_layout) # Buton layout'unu ana layout'a ekle
            # init_member_form metodu içinde, layout.addLayout(exim_btn_layout) satırından sonra:

            # Yeni Üye Ekleme Formu Başlığı
            add_title_label = QLabel("Yeni Üye Ekle")
            add_title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 20px; margin-bottom: 5px;")
            layout.addWidget(add_title_label)

            # Yeni Üye Ekleme Formu Alanları için bir QWidget ve QGridLayout kullanalım
            # Bu, formu bir bütün olarak yönetmemizi sağlar.
            form_container_widget = QWidget()
            form_fields_layout = QGridLayout(form_container_widget) # GridLayout'u QWidget'e ata
            form_fields_layout.setSpacing(10) # Alanlar arası boşluk

            # Sol Sütun Alanları (GridLayout içinde satır, sütun, satır yayılımı, sütun yayılımı)
            form_fields_layout.addWidget(QLabel("Üye Adı Soyadı:"), 0, 0)
            self.name_input = QLineEdit()
            self.name_input.setPlaceholderText("Ad Soyad")
            form_fields_layout.addWidget(self.name_input, 0, 1)

            form_fields_layout.addWidget(QLabel("Kart UID:"), 1, 0)
            self.uid_input = QLineEdit()
            self.uid_input.setPlaceholderText("Kartı okutun veya 10 haneli UID girin")
            self.uid_input.setMaxLength(10)
            form_fields_layout.addWidget(self.uid_input, 1, 1)

            form_fields_layout.addWidget(QLabel("Bölümü:"), 2, 0)
            self.department_input = QLineEdit()
            self.department_input.setPlaceholderText("Örn: Bilgisayar Mühendisliği")
            form_fields_layout.addWidget(self.department_input, 2, 1)

            form_fields_layout.addWidget(QLabel("Sınıfı/Yılı:"), 3, 0)
            self.year_input = QLineEdit()
            self.year_input.setPlaceholderText("Örn: 3")
            form_fields_layout.addWidget(self.year_input, 3, 1)
            
            form_fields_layout.addWidget(QLabel("İlgi Alanları:"), 4, 0)
            self.interests_input = QLineEdit()
            self.interests_input.setPlaceholderText("Virgülle ayırın (örn: Yapay Zeka, Pazarlama)")
            form_fields_layout.addWidget(self.interests_input, 4, 1)
            
            # Sağ Sütun Alanları (GridLayout içinde)
            form_fields_layout.addWidget(QLabel("E-posta Adresi:"), 0, 2)
            self.email_input = QLineEdit()
            self.email_input.setPlaceholderText("ornek@universite.edu.tr")
            form_fields_layout.addWidget(self.email_input, 0, 3)

            form_fields_layout.addWidget(QLabel("Telefon (Opsiyonel):"), 1, 2)
            self.phone_input = QLineEdit()
            self.phone_input.setPlaceholderText("+90 5...")
            form_fields_layout.addWidget(self.phone_input, 1, 3)

            form_fields_layout.addWidget(QLabel("Rol Seçiniz:"), 2, 2)
            self.role_combo = QComboBox()
            # Rolleri ayarlardan veya sabit listeden al
            default_member_role_setting = self.settings.get('default_member_role', 'Aktif Üye')
            add_roles = ["Aktif Üye", "Normal Üye", "Yönetim Kurulu Üyesi", "Mezun Üye", "Aday Üye"] 
            if default_member_role_setting in add_roles: 
                add_roles.remove(default_member_role_setting)
            add_roles.insert(0, default_member_role_setting)
            self.role_combo.addItems(add_roles)
            form_fields_layout.addWidget(self.role_combo, 2, 3)

            form_fields_layout.addWidget(QLabel("Üyelik Başlangıç Tarihi:"), 3, 2)
            self.membership_date_edit = QDateEdit()
            self.membership_date_edit.setDate(QDate.currentDate())
            self.membership_date_edit.setCalendarPopup(True)
            self.membership_date_edit.setDisplayFormat("dd.MM.yyyy")
            form_fields_layout.addWidget(self.membership_date_edit, 3, 3)

            form_fields_layout.addWidget(QLabel("Fotoğraf (Opsiyonel):"), 4, 2)
            photo_layout_internal = QHBoxLayout() 
            self.photo_input = QLineEdit()
            self.photo_input.setPlaceholderText("Fotoğraf dosya adı") # Artık sadece dosya adı
            self.photo_input.setReadOnly(True)
            photo_layout_internal.addWidget(self.photo_input, 1) 
            photo_button = QPushButton("Gözat")
            photo_button.clicked.connect(lambda: self.browse_photo(self.photo_input))
            photo_layout_internal.addWidget(photo_button)
            form_fields_layout.addLayout(photo_layout_internal, 4, 3) # QHBoxLayout'u GridLayout'a ekle
            # init_member_form metodu içinde, form_fields_layout'a ekleme yapılan yerde:

            # ... (Fotoğraf alanı eklendikten sonra - Örnek: form_fields_layout.addLayout(photo_layout_internal, 4, 3)) ...

            # ---- YENİ REFERANS BÖLÜMÜ ----
            # Bir ayırıcı ekleyebiliriz
            separator_ref = self.create_separator_line(margin_top=10, margin_bottom=5) if hasattr(self, 'create_separator_line') else QFrame()
            form_fields_layout.addWidget(separator_ref, 6, 0, 1, 4) # 4 sütuna yayılsın

            form_fields_layout.addWidget(QLabel("Referans Olan Üye (Opsiyonel):"), 7, 0, 1, 4) # Başlık 4 sütuna yayılsın

            form_fields_layout.addWidget(QLabel("Ara (Ad):"), 8, 0)
            self.referrer_search_input = QLineEdit()
            self.referrer_search_input.setPlaceholderText("Referans olan üyenin adını yazıp 'Bul'a basın...")
            # self.referrer_search_input.textChanged.connect(self.clear_referrer_selection_if_text_changed) # Otomatik temizleme (opsiyonel)
            form_fields_layout.addWidget(self.referrer_search_input, 8, 1, 1, 2) # 2 sütunluk yer

            btn_find_referrer = QPushButton("Bul/Doğrula")
            btn_find_referrer.clicked.connect(self.find_referrer_member) # Bu metodu sonra oluşturacağız
            form_fields_layout.addWidget(btn_find_referrer, 8, 3)

            # Bulunan/Seçilen referans bilgisini göstermek için etiket
            self.referrer_info_label = QLabel("Referans seçilmedi.")
            self.referrer_info_label.setStyleSheet("font-style: italic; color: grey;")
            form_fields_layout.addWidget(self.referrer_info_label, 9, 1, 1, 3) # 3 sütuna yayılsın
            # ---- REFERANS BÖLÜMÜ BİTTİ ----

            # form_main_layout.addLayout(form_fields_layout) # Bu satır zaten daha önce olmalı
            # layout.addWidget(form_container_widget)      # Bu satır zaten daha önce olmalı
            
            # GridLayout'un sağ tarafındaki sütunların sola yaslanması için boşlukları genişletelim
            form_fields_layout.setColumnStretch(1, 1) # Sol giriş alanları için stretch
            form_fields_layout.setColumnStretch(3, 1) # Sağ giriş alanları için stretch
            
            layout.addWidget(form_container_widget) # Form alanlarını içeren QWidget'ı ana layout'a ekle

            # Yeni Üye Kaydet Butonu
            btn_add = QPushButton("Yeni Üyeyi Kaydet")
            btn_add.setIcon(QIcon.fromTheme("list-add"))
            btn_add.clicked.connect(self.add_member_to_db)
            
            # Butonu ortalamak için bir QHBoxLayout kullanalım
            add_button_layout = QHBoxLayout()
            add_button_layout.addStretch()
            add_button_layout.addWidget(btn_add)
            add_button_layout.addStretch()
            layout.addLayout(add_button_layout)

            # Sayfanın en altına bir esneme payı ekleyerek, eğer form ve tablo tüm alanı doldurmuyorsa,
            # elemanların yukarı yığılmasını sağlar. Tabloya stretch verdiğimiz için bu çok etkili olmayabilir
            # veya formun küçülmesine neden olabilir. Deneyerek görebiliriz.
            # layout.addStretch(0) # Şimdilik bunu eklemeyelim, tablonun esnemesine öncelik verelim.
            # ---- BİTTİ ----

            # ---- ŞİMDİLİK FORM KISMINI EKLEMEYELİM ----
            # Önce tablonun doğru büyüdüğünden emin olalım.
            # Eğer tablo doğru büyürse, formu adım adım ekleriz.

            # Sayfayı stacked widget'a ekle (Bu satırın metodun en sonunda olması gerekir)
            # Eğer self.member_form_page __init__ içinde oluşturuluyorsa, bu satır burada kalabilir.
            # Eğer yukarıda bu metod içinde oluşturduysak (yorumdaki gibi), o zaman da burada kalabilir.
            if self.stacked_widget.indexOf(self.member_form_page) == -1: # Eğer daha önce eklenmediyse ekle
                self.stacked_widget.addWidget(self.member_form_page)

    def init_event_form(self):
        """Etkinlik listesi ve ekleme/düzenleme formunun arayüzünü oluşturur (Refaktör Edilmiş)."""
        layout = QVBoxLayout(self.event_form_page) # Layout'u sayfaya ata

        # Geri Butonu
        header_layout = QHBoxLayout()
        back_button = QPushButton("← Ana Sayfa")
        back_button.setFixedSize(120, 30)
        back_button.clicked.connect(self.show_main_page)
        header_layout.addWidget(back_button, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Form Başlığı ve Gizli ID Etiketi
        add_title_label = QLabel("Yeni Etkinlik Ekle / Düzenle")
        add_title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-top:10px; margin-bottom: 5px;")
        layout.addWidget(add_title_label)
        self.edit_event_id_label = QLabel("") # Düzenleme modunda ID'yi tutmak için
        self.edit_event_id_label.hide() # Görünmez yap
        layout.addWidget(self.edit_event_id_label) # Layout'a ekle ama görünmeyecek

        # Etkinlik Ekleme/Düzenleme Formu Alanları (İki sütunlu)
        form_layout = QHBoxLayout()
        form_left = QVBoxLayout()
        form_right = QVBoxLayout()
        form_layout.addLayout(form_left)
        form_layout.addLayout(form_right)

        # Sol Sütun
        form_left.addWidget(QLabel("Etkinlik Adı:"))
        self.event_name_input = QLineEdit()
        self.event_name_input.setPlaceholderText("Etkinlik Adı")
        form_left.addWidget(self.event_name_input)

        form_left.addWidget(QLabel("Tarih:"))
        self.event_date_edit = QDateEdit()
        self.event_date_edit.setDate(QDate.currentDate())
        self.event_date_edit.setCalendarPopup(True)
        self.event_date_edit.setDisplayFormat("dd.MM.yyyy")
        form_left.addWidget(self.event_date_edit)

        form_left.addWidget(QLabel("Yer:"))
        self.event_location_input = QLineEdit()
        self.event_location_input.setPlaceholderText("Örn: Konferans Salonu A")
        form_left.addWidget(self.event_location_input)

        form_left.addWidget(QLabel("Kategori:"))
        self.event_category_combo = QComboBox()
        # Kategorileri sabit veya dinamik olarak belirleyebiliriz
        self.event_category_combo.addItems(["", "Workshop", "Seminer", "Networking", "Yarışma", "Sosyal", "Diğer"])
        form_left.addWidget(self.event_category_combo)
        form_left.addStretch()

        # Sağ Sütun
        form_right.addWidget(QLabel("Açıklama:"))
        self.event_description_input = QTextEdit()
        self.event_description_input.setPlaceholderText("Etkinlik hakkında kısa bilgi...")
        self.event_description_input.setFixedHeight(120) # Yüksekliği sabitleyelim
        form_right.addWidget(self.event_description_input)
        form_right.addStretch()

        layout.addLayout(form_layout)

        # Etkinlik Ekle/Güncelle/Temizle Butonları
        event_button_layout = QHBoxLayout()
        self.event_add_update_button = QPushButton("Etkinlik Ekle") # Başlangıçta Ekle modunda
        self.event_add_update_button.setIcon(QIcon.fromTheme("list-add"))
        self.event_add_update_button.clicked.connect(self.add_or_update_event) # Sonraki bölümde implemente edilecek

        btn_clear_event_form = QPushButton("Formu Temizle")
        btn_clear_event_form.setIcon(QIcon.fromTheme("edit-clear"))
        btn_clear_event_form.clicked.connect(self.clear_event_form) # Sonraki bölümde implemente edilecek

        event_button_layout.addWidget(self.event_add_update_button)
        event_button_layout.addWidget(btn_clear_event_form)
        event_button_layout.addStretch()
        layout.addLayout(event_button_layout)

        # Etkinlik Listesi Başlığı
        list_title = QLabel("Etkinlik Listesi")
        list_title.setStyleSheet("font-size: 16px; font-weight: bold; margin-top:20px; margin-bottom: 5px;")
        layout.addWidget(list_title)

        # Etkinlik Listesi Tablosu
        self.event_list_widget = QTableWidget() # Adı table olmalı widget değil ama orijinali koruyalım
        self.event_list_widget.setColumnCount(4)
        self.event_list_widget.setHorizontalHeaderLabels(["Ad", "Tarih", "Kategori", "Yer"])
        self.event_list_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.event_list_widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.event_list_widget.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.event_list_widget.verticalHeader().setVisible(False)
        self.event_list_widget.horizontalHeader().setStretchLastSection(True) # Son sütun (Yer) genişlesin
        # Bağlantılar
        self.event_list_widget.itemDoubleClicked.connect(self.handle_event_double_click) # Çift tıklama -> Detay (Sonraki bölüm)
        self.event_list_widget.clicked.connect(self.load_event_to_form_for_edit) # Tek tıklama -> Forma yükle (Sonraki bölüm)
        self.event_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.event_list_widget.customContextMenuRequested.connect(self.on_event_table_context_menu) # Sağ tık menüsü (Sonraki bölüm)
        # Sütun genişlikleri
        self.event_list_widget.setColumnWidth(0, 250) # Ad
        self.event_list_widget.setColumnWidth(1, 100) # Tarih
        self.event_list_widget.setColumnWidth(2, 120) # Kategori
        layout.addWidget(self.event_list_widget)

        # Sayfayı stacked widget'a ekle
        self.stacked_widget.addWidget(self.event_form_page)

    def init_edit_member_form(self):
        """Üye düzenleme formunun arayüzünü oluşturur (Refaktör Edilmiş)."""
        layout = QVBoxLayout(self.edit_member_page) # Layout'u sayfaya ata

        # Geri Butonu
        header_layout = QHBoxLayout()
        back_button = QPushButton("← Üye Listesi")
        back_button.setFixedSize(120, 30)
        back_button.clicked.connect(self.show_member_form) # Üye listesine dön
        header_layout.addWidget(back_button, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Başlık
        title_label = QLabel("Üyeyi Düzenle")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-top:10px; margin-bottom: 10px;")
        layout.addWidget(title_label)

        # Fotoğraf Alanı
        self.edit_photo_label = QLabel("Fotoğraf Yok")
        self.edit_photo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit_photo_label.setMinimumSize(150, 150) # Minimum boyut
        self.edit_photo_label.setFrameShape(QFrame.Shape.Box) # Çerçeve
        self.edit_photo_label.setLineWidth(1)
        # Stil sayfasından da ayarlanabilir ama burada kalsın şimdilik
        self.edit_photo_label.setStyleSheet("border: 1px solid #ccc; background-color: white;")
        layout.addWidget(self.edit_photo_label, alignment=Qt.AlignmentFlag.AlignCenter) # Ortala

        # Form Alanları (İki Sütunlu)
        edit_form_layout = QHBoxLayout()
        edit_left = QVBoxLayout()
        edit_right = QVBoxLayout()
        edit_form_layout.addLayout(edit_left, 1)
        edit_form_layout.addLayout(edit_right, 1)

        # Sol Sütun
        edit_left.addWidget(QLabel("Üye Adı Soyadı:"))
        self.edit_name_input = QLineEdit()
        edit_left.addWidget(self.edit_name_input)

        edit_left.addWidget(QLabel("Kart UID:"))
        self.edit_uid_input = QLineEdit()
        self.edit_uid_input.setMaxLength(10)
        edit_left.addWidget(self.edit_uid_input)

        edit_left.addWidget(QLabel("Bölümü:"))
        self.edit_department_input = QLineEdit()
        edit_left.addWidget(self.edit_department_input)

        edit_left.addWidget(QLabel("Sınıfı/Yılı:"))
        self.edit_year_input = QLineEdit() # Veya QSpinBox
        edit_left.addWidget(self.edit_year_input)

        edit_left.addWidget(QLabel("İlgi Alanları (Virgülle):"))
        self.edit_interests_input = QLineEdit()
        edit_left.addWidget(self.edit_interests_input)
        edit_left.addStretch()

        # Sağ Sütun
        edit_right.addWidget(QLabel("E-posta Adresi:"))
        self.edit_email_input = QLineEdit()
        edit_right.addWidget(self.edit_email_input)

        edit_right.addWidget(QLabel("Telefon (Opsiyonel):"))
        self.edit_phone_input = QLineEdit()
        edit_right.addWidget(self.edit_phone_input)

        edit_right.addWidget(QLabel("Rol Seçiniz:"))
        self.edit_role_combo = QComboBox()
        # Rolleri ekle (yeni üye formundaki gibi)
        default_role = self.settings.get('default_member_role', 'Aktif Üye')
        edit_roles = ["Aktif Üye", "Normal Üye", "Yönetim Kurulu Üyesi"]
        if default_role not in edit_roles: edit_roles.insert(0, default_role)
        self.edit_role_combo.addItems(edit_roles)
        edit_right.addWidget(self.edit_role_combo)

        edit_right.addWidget(QLabel("Fotoğraf Yolu:"))
        edit_photo_layout = QHBoxLayout()
        self.edit_photo_input = QLineEdit()
        self.edit_photo_input.setReadOnly(True) # Gözat ile seçilsin
        edit_photo_layout.addWidget(self.edit_photo_input)
        edit_photo_button = QPushButton("Gözat")
        edit_photo_button.clicked.connect(lambda: self.browse_photo(self.edit_photo_input))
        edit_photo_layout.addWidget(edit_photo_button)
        edit_right.addLayout(edit_photo_layout)

        edit_right.addWidget(QLabel("Üyelik Başlangıç Tarihi:"))
        self.edit_membership_date_edit = QDateEdit()
        self.edit_membership_date_edit.setCalendarPopup(True)
        self.edit_membership_date_edit.setDisplayFormat("dd.MM.yyyy")
        edit_right.addWidget(self.edit_membership_date_edit)
        edit_right.addStretch()

        layout.addLayout(edit_form_layout)

        # Kaydet Butonu
        btn_update = QPushButton("Değişiklikleri Kaydet")
        btn_update.setIcon(QIcon.fromTheme("document-save"))
        btn_update.clicked.connect(self.update_member) # Güncelleme fonksiyonuna bağla
        layout.addWidget(btn_update, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addStretch() # Butonu biraz yukarıda tutmak için

        # Sayfayı stacked widget'a ekle
        self.stacked_widget.addWidget(self.edit_member_page)

    # --- Sayfa Gösterme Fonksiyonları ---
    def show_main_page(self):
        """Ana sayfayı gösterir ve istatistikleri günceller."""
        # Widget'lar oluşturulmuş mu kontrol et (ilk açılışta hata vermemesi için)
        if hasattr(self, 'stats_total_members_label') and self.stats_total_members_label:
            self.update_main_page_stats() # Sonraki bölümde implemente edilecek
            self.update_main_page_logo()  # Sonraki bölümde implemente edilecek
            self.update_leaderboard()
        self.stacked_widget.setCurrentWidget(self.main_page)

    def show_member_form(self):
        """Üye yönetimi sayfasını gösterir ve listeyi günceller."""
        if hasattr(self, 'member_table') and self.member_table: # Tablo var mı kontrol et
            self.update_member_list() # Üye listesini güncelleyerek aç
        self.stacked_widget.setCurrentWidget(self.member_form_page)
        # Formu temizle (isteğe bağlı, belki yeni üye eklemeye hazır olmalı)
        # self.name_input.clear(); self.uid_input.clear(); ...

    def show_event_form(self):
        """Etkinlik yönetimi sayfasını gösterir, formu temizler ve listeyi günceller."""
        if hasattr(self, 'event_list_widget') and self.event_list_widget: # Liste var mı kontrol et
            self.clear_event_form() # Formu temizleyerek aç (Sonraki bölüm)
            self.update_event_list() # Etkinlik listesini güncelleyerek aç (Sonraki bölüm)
        self.stacked_widget.setCurrentWidget(self.event_form_page)

    def show_settings_page(self):
        """Ayarlar sayfasını gösterir ve mevcut ayarları yükler."""
        # Bu metodun implementasyonu bir sonraki bölümde olacak (init_settings_page ile birlikte)
        print("DEBUG: show_settings_page çağrıldı - İçi doldurulmalı!")
        self.settings = load_settings() # En güncel ayarları yükle
        # TODO: Ayarları ilgili UI elemanlarına yükle (sonraki bölümde)
        # self.settings_logo_path_input.setText(...)
        self.stacked_widget.setCurrentWidget(self.settings_page)

    # --- Üyelik Fonksiyonları (Implementasyonlar) ---

    # AdminPanel içinde
    def update_member_list(self):
        """Üye listesi tablosunu filtreleri dikkate alarak günceller (PostgreSQL uyumlu)."""
        if not self.member_table: 
            print("Uyarı: update_member_list - member_table henüz yok.")
            return
        try:
            filter_text = self.member_search_input.text().strip() if self.member_search_input else ""
            filter_role = self.role_filter_combo.currentText() if self.role_filter_combo else "Tüm Roller"

            # Sorguyu oluşturmaya başla (PostgreSQL için %s kullanılacak)
            query = "SELECT id, name, department, role, email, membership_date, points FROM members WHERE 1=1" # points sütunu da eklendi
            params = []

            if filter_text:
                # PostgreSQL'de LIKE genellikle case-sensitive'dir, ILIKE case-insensitive'dir.
                # Veya LOWER() kullanmaya devam edebiliriz. LOWER() daha standarttır.
                query += " AND (LOWER(name) LIKE LOWER(%s) OR LOWER(department) LIKE LOWER(%s) OR LOWER(interests) LIKE LOWER(%s))"
                term = f"%{filter_text}%"
                params.extend([term, term, term])

            if filter_role != "Tüm Roller":
                query += " AND role = %s"
                params.append(filter_role)

            query += " ORDER BY name ASC"

            cursor = self.get_cursor()
            cursor.execute(query, params) # psycopg2 params'ı tuple veya list olarak alır
            members = cursor.fetchall() # DictCursor sayesinde sözlük listesi döner

            self.member_table.setRowCount(0)
            self.member_table.setSortingEnabled(False)

            for row_idx, member in enumerate(members):
                self.member_table.insertRow(row_idx)

                name_item = QTableWidgetItem(member['name'])
                name_item.setData(Qt.ItemDataRole.UserRole, member['id']) # ID'yi sakla
                dept_item = QTableWidgetItem(member['department'] or "-")
                role_item = QTableWidgetItem(member['role'] or "-")
                email_item = QTableWidgetItem(member['email'] or "-")
                date_str = member["membership_date"] or ""
                # PostgreSQL DATE tipini QDate.fromString ile parse etme (doğrudan str yapabiliriz veya type check)
                # psycopg2 DATE tipini Python datetime.date olarak döndürebilir.
                if isinstance(date_str, datetime.date): # Eğer date objesi ise
                    formatted_date = date_str.strftime("%d.%m.%Y")
                else: # Değilse, string parse etmeyi dene
                    qdate = QDate.fromString(str(date_str), Qt.DateFormat.ISODate) # Önce ISODate dene
                    if not qdate.isValid(): # Başarısız olursa başka formatları dene (örn: veritabanı formatı)
                        # Veya doğrudan string olarak göster
                        formatted_date = str(date_str) if date_str else "-"
                    else:
                        formatted_date = qdate.toString("dd.MM.yyyy")

                date_item = QTableWidgetItem(formatted_date)

                # Puan sütununu ekleyelim (bu Adım 1'de eklenmişti init_member_form'a)
                points_value = member.get('points', 0) # DictCursor olduğu için get kullanılabilir
                points_item = QTableWidgetItem(str(points_value))
                points_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

                # Hücreleri yerleştir
                self.member_table.setItem(row_idx, 0, name_item)
                self.member_table.setItem(row_idx, 1, dept_item)
                self.member_table.setItem(row_idx, 2, role_item)
                self.member_table.setItem(row_idx, 3, email_item)
                self.member_table.setItem(row_idx, 4, date_item)
                # Puan sütunu (Eğer init_member_form'da sütun sayısı 6 yapıldıysa)
                if self.member_table.columnCount() > 5:
                    self.member_table.setItem(row_idx, 5, points_item)

            self.member_table.setSortingEnabled(True)

        except psycopg2.Error as e_db: # Hata tipi psycopg2 olarak güncellendi
            print(f"Üye listesi güncellenirken DB hatası: {e_db}")
            QMessageBox.warning(self, "Veritabanı Hatası", f"Üye listesi güncellenemedi: {e_db}")
            traceback.print_exc()
        except Exception as e_general:
            print(f"Üye listesi güncellenirken genel hata: {e_general}")
            QMessageBox.warning(self, "Hata", f"Üye listesi güncellenirken beklenmedik bir hata oluştu: {e_general}")
            traceback.print_exc()

    def handle_member_double_click(self, item):
        """Üye tablosunda bir satıra çift tıklandığında üye profilini gösterir."""
        if not item: return
        row = item.row()
        # ID'yi ilk sütundaki item'dan al (UserRole olarak saklamıştık)
        id_item = self.member_table.item(row, 0)
        if id_item:
            member_id = id_item.data(Qt.ItemDataRole.UserRole)
            if member_id:
                print(f"Üye çift tıklama: ID={member_id}")
                self.show_member_profile_by_id(member_id) # Profil gösterme fonksiyonu (sonraki bölüm)
            else:
                print("Uyarı: Çift tıklanan satırda üye ID bulunamadı.")
        else:
            print("Uyarı: Çift tıklanan satırda ilk hücre (ID hücresi) bulunamadı.")


    # AdminPanel sınıfının içine:
    def on_sales_table_context_menu(self, pos: QPoint):
        """Bilet satışları tablosunda sağ tıklama menüsünü gösterir."""
        if not hasattr(self, 'sales_recent_sales_table'):
            return

        item = self.sales_recent_sales_table.itemAt(pos) # Tıklanan pozisyondaki item
        if not item:  # Boş bir yere tıklandıysa çık
            return

        row = item.row()
        # Satış ID'sini bir şekilde almamız gerekiyor.
        # update_recent_sales_list metodunda her satırın ilk hücresine (veya görünmez bir hücreye)
        # satış ID'sini UserRole olarak saklamamız gerekecek. Şimdilik bu adımı atlayıp,
        # sadece menüyü gösterelim ve ID'yi nasıl alacağımızı sonra düşünelim.
        # Veya, doğrudan satır numarasını kullanabiliriz ama bu ID kadar güvenli değil.

        # Şimdilik, seçili satırın bilgilerini alalım (eğer ID'yi userData'ya koyduysak)
        # update_recent_sales_list metodunu güncelleyerek her satırın ilk hücresine
        # 'sale_id'yi Qt.ItemDataRole.UserRole olarak eklememiz gerekecek.
        # Şimdilik varsayalım ki ilk hücrede Üye Adı var ve onun UserRole'unda sale_id var.
        # BU KISIM GÜNCELLENECEK olan update_recent_sales_list'e BAĞLI!

        # ÖNEMLİ: Satış ID'sini almak için update_recent_sales_list metodunu güncellememiz gerekecek.
        # O güncelleme yapılana kadar bu kısım tam çalışmayabilir.
        # Şimdilik, sadece menüyü oluşturalım.

        # Satış ID'sini al (Bu, update_recent_sales_list'te sale_id'nin UserRole olarak saklandığını varsayar)
        try:
            # Varsayalım ki satış ID'sini ilk hücrenin (Üye Adı) UserRole'una saklayacağız.
            id_item = self.sales_recent_sales_table.item(row, 0) 
            if not id_item or id_item.data(Qt.ItemDataRole.UserRole) is None:
                print("DEBUG: Sağ tık menüsü için satış ID'si bulunamadı.")
                # Belki kullanıcıya sadece bir uyarı verip çıkabiliriz.
                # Veya menüdeki silme/düzenleme seçeneklerini pasif yapabiliriz.
                # Şimdilik devam edelim, bu ID'yi update_recent_sales_list'te ekleyeceğiz.
                sale_id_to_process = None 
            else:
                sale_id_to_process = id_item.data(Qt.ItemDataRole.UserRole)

            # Menü için tıklanan satışın bazı bilgilerini alalım (kullanıcıya göstermek için)
            member_name_text = self.sales_recent_sales_table.item(row, 0).text() if self.sales_recent_sales_table.item(row, 0) else "Bilinmeyen"
            ticket_type_text = self.sales_recent_sales_table.item(row, 1).text() if self.sales_recent_sales_table.item(row, 1) else "-"

        except Exception as e:
            print(f"Sağ tık menüsü için veri alınırken hata: {e}")
            return

        menu = QMenu(self)

        # Düzenle Eylemi (Şimdilik pasif bırakalım veya sadece print yapsın)
        edit_action = QAction(QIcon.fromTheme("document-edit"), f"Satışı Düzenle ({member_name_text} - {ticket_type_text})", self)
        # edit_action.triggered.connect(lambda checked, sid=sale_id_to_process: self.edit_ticket_sale_form(sid)) # Sonraki adımda
        edit_action.setEnabled(False) # ŞİMDİLİK DÜZENLEME PASİF

        # Sil Eylemi
        delete_action = QAction(QIcon.fromTheme("edit-delete"), f"Satışı Sil ({member_name_text} - {ticket_type_text})", self)
        if sale_id_to_process is not None: # Sadece geçerli bir ID varsa silme aktif olsun
            delete_action.triggered.connect(lambda checked, sid=sale_id_to_process, m_name=member_name_text, t_type=ticket_type_text: self.confirm_delete_ticket_sale(sid, m_name, t_type))
        else:
            delete_action.setEnabled(False)

        # menu.addAction(edit_action) # Düzenleme aktif olunca eklenecek
        menu.addAction(delete_action)

        # Menüyü global pozisyonda göster
        action = menu.exec(self.sales_recent_sales_table.mapToGlobal(pos))
        # Seçilen eylem (action) burada kullanılabilir ama triggered sinyalleriyle işi hallettik.
    def on_member_table_context_menu(self, pos: QPoint):
        """Üye tablosunda sağ tıklama menüsünü gösterir."""
        item = self.member_table.itemAt(pos) # Tıklanan pozisyondaki item
        if not item: return # Boş bir yere tıklandıysa çık

        row = item.row()
        # ID'yi yine ilk sütundan alalım
        id_item = self.member_table.item(row, 0)
        if not id_item: return

        member_id = id_item.data(Qt.ItemDataRole.UserRole)
        member_name = id_item.text() # İsim ilk sütunda olduğu için direkt alabiliriz
        if not member_id: return # ID yoksa menü gösterme

        menu = QMenu(self) # Menüyü oluştur

        # Menü Eylemleri
        profile_action = QAction(QIcon.fromTheme("user-identity"), f"'{member_name}' Profilini Görüntüle", self)
        edit_action = QAction(QIcon.fromTheme("document-edit"), "Düzenle", self)
        delete_action = QAction(QIcon.fromTheme("edit-delete"), "Sil", self)

        # Eylemleri menüye ekle
        menu.addAction(profile_action)
        menu.addAction(edit_action)
        menu.addSeparator() # Ayraç
        menu.addAction(delete_action)

        # Tıklanan eyleme göre işlem yap
        # menu.exec() metodu seçilen eylemi döndürür
        action = menu.exec(self.member_table.mapToGlobal(pos)) # Menüyü global pozisyonda göster

        if action == profile_action:
            self.show_member_profile_by_id(member_id) # Profil gösterme (sonraki bölüm)
        elif action == edit_action:
            self.show_edit_member_form(member_id) # Düzenleme formunu göster (bu bölümde implemente edildi)
        elif action == delete_action:
            self.delete_member(member_id, member_name) # Silme fonksiyonu (bu bölümde implemente edildi)


    # AdminPanel sınıfının içinde:
    # AdminPanel içinde
    def add_member_to_db(self):
        """Yeni üye formundaki bilgileri veritabanına ekler (PostgreSQL uyumlu)."""
        # ... (widget kontrolü ve formdan veri alma kısımları aynı kalır) ...
        name = self.name_input.text().strip()
        uid = self.uid_input.text().strip()
        # ... (diğer değişkenler: department, year, interests, email, phone, role, photo_filename, membership_date_str)
        referrer_member_id = self.selected_referrer_id

        if not name or not uid: # ... (zorunlu alan kontrolü) ...
            return
        try: # ... (yıl çevirme) ...
                # AdminPanel.add_member_to_db() fonksiyonu içinde:

            # ... (diğer bilgileri aldığınız satırlar, örneğin department, interests vb. sonra) ...

            name = self.name_input.text().strip()
            uid = self.uid_input.text().strip()
            department = self.department_input.text().strip()
            
            # --- EKLENECEK SATIR BAŞLIYOR ---
            year_str = self.year_input.text().strip() # Yıl bilgisini formdan al
            # --- EKLENECEK SATIR BİTİYOR ---
            
            interests = self.interests_input.text().strip()
            email = self.email_input.text().strip()
            phone = self.phone_input.text().strip()
            role = self.role_combo.currentText()
            photo_filename = self.photo_input.text().strip()
            membership_date_str = self.membership_date_edit.date().toString(Qt.DateFormat.ISODate)
            
            referrer_member_id = self.selected_referrer_id

            if not name or not uid:
                QMessageBox.warning(self, "Eksik Bilgi", "Üye adı ve Kart UID zorunludur.")
                return
            
            try:
                # Artık year_str burada tanımlı olacak
                year = int(year_str) if year_str else None 
            except ValueError:
                QMessageBox.warning(self, "Geçersiz Giriş", "Sınıf/Yıl alanı sayısal olmalıdır.")
                return
            
            # ... (fonksiyonun geri kalanı) ...
            year = int(year_str) if year_str else None
        except ValueError: # ...
            QMessageBox.warning(self, "Geçersiz Giriş", "Sınıf/Yıl alanı sayısal olmalıdır.")
            return

        new_member_id = None
        try:
            cursor = self.get_cursor()
            
            # PostgreSQL için INSERT ... RETURNING id ve %s kullanımı
            sql = """
                INSERT INTO members (name, uid, role, photo_path, membership_date, 
                                department, year, email, phone, interests, 
                                points, referred_by_member_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s) 
                RETURNING id 
            """
            params = (name, uid, role, 
                    photo_filename if photo_filename else None, 
                    membership_date_str if membership_date_str else None, 
                    department or None, year, email or None, phone or None, interests or None,
                    referrer_member_id) 
            
            cursor.execute(sql, params)
            new_member_id_row = cursor.fetchone() # Dönen ID'yi al
            if new_member_id_row:
                new_member_id = new_member_id_row['id'] # DictCursor ile 'id' anahtarını kullan
            else:
                print("HATA: Yeni üye ID'si INSERT sonrası alınamadı!")
                self.db_connection.rollback() # İşlemi geri al
                QMessageBox.critical(self, "Veritabanı Hatası", "Yeni üye kaydedildi ancak ID'si alınamadı. İşlem geri alındı.")
                return

            self.db_connection.commit() # Üye ekleme işlemini onayla
            print(f"DEBUG: Yeni üye eklendi (Commit edildi). ID: {new_member_id}, Referans ID: {referrer_member_id}")

            # ---- REFERANS PUANLARINI EKLEME BÖLÜMÜ ----
            if referrer_member_id is not None and new_member_id is not None:
                points_to_award = REFERRAL_POINTS 
                if points_to_award > 0:
                    log_timestamp = QDateTime.currentDateTime().toString(Qt.DateFormat.ISODate)
                    try:
                        reason_new = "Referans ile katilim bonusu"
                        cursor.execute("UPDATE members SET points = points + %s WHERE id = %s", (points_to_award, new_member_id)) # %s kullanıldı
                        cursor.execute("""INSERT INTO points_log (member_id, points_earned, reason, log_timestamp) VALUES (%s, %s, %s, %s)""", 
                                    (new_member_id, points_to_award, reason_new, log_timestamp)) # %s kullanıldı
                        
                        cursor.execute("SELECT name FROM members WHERE id = %s", (new_member_id,)) # %s kullanıldı
                        new_member_name_row = cursor.fetchone()
                        new_member_name = new_member_name_row['name'] if new_member_name_row else f"ID:{new_member_id}"
                        reason_referrer = f"Yeni uye referansi: {new_member_name}"
                        
                        cursor.execute("UPDATE members SET points = points + %s WHERE id = %s", (points_to_award, referrer_member_id)) # %s kullanıldı
                        cursor.execute("""INSERT INTO points_log (member_id, points_earned, reason, log_timestamp) VALUES (%s, %s, %s, %s)""", 
                                    (referrer_member_id, points_to_award, reason_referrer, log_timestamp)) # %s kullanıldı
                        
                        self.db_connection.commit() 
                        print(f"DEBUG: Referans puanları başarıyla eklendi ve loglandı.")
                        QMessageBox.information(self, "Puan Eklendi", 
                                            f"Referans nedeniyle {points_to_award} puan eklendi.")
                    
                    except psycopg2.Error as e_ref_points_db: # psycopg2 hatası
                        print(f"HATA: Referans puanları eklenirken DB hatası: {e_ref_points_db}")
                        QMessageBox.warning(self, "Puan Hatası", f"Üye eklendi ancak puan eklenirken sorun oluştu:\n{e_ref_points_db}")
                        self.db_connection.rollback() 
                    except Exception as e_ref_points_gen:
                        print(f"HATA: Referans puanları eklenirken genel hata: {e_ref_points_gen}")
                        QMessageBox.warning(self, "Puan Hatası", f"Üye eklendi ancak puan eklenirken sorun oluştu:\n{e_ref_points_gen}")
                        traceback.print_exc()
                        self.db_connection.rollback()
            # ---- REFERANS PUANLARI BÖLÜMÜ BİTTİ ----

            QMessageBox.information(self, "Başarılı", f"'{name}' adlı üye başarıyla eklendi.")
            if hasattr(self, 'clear_member_form_fields'): self.clear_member_form_fields() 
            else: print("Hata: clear_member_form_fields metodu bulunamadı!") # Eğer bu yardımcı fonksiyon yoksa
            
            self.update_member_list() 
            self.update_main_page_stats() 
            if hasattr(self, 'update_leaderboard'): self.update_leaderboard() 

        except psycopg2.IntegrityError as e_int: # psycopg2 hatası
            self.db_connection.rollback() 
            # PostgreSQL hata mesajları farklı olabilir, daha genel kontrol yapalım
            if "members_uid_key" in str(e_int).lower() or ("unique constraint" in str(e_int).lower() and "uid" in str(e_int).lower()):
                QMessageBox.critical(self, "Hata", f"Bu Kart UID ({uid}) zaten kayıtlı!")
                if hasattr(self, 'uid_input'): self.uid_input.selectAll(); self.uid_input.setFocus()
            elif "members_email_key" in str(e_int).lower() or ("unique constraint" in str(e_int).lower() and "email" in str(e_int).lower()):
                QMessageBox.critical(self, "Hata", f"Bu E-posta adresi ({email}) zaten kayıtlı!")
                if hasattr(self, 'email_input'): self.email_input.selectAll(); self.email_input.setFocus()
            else:
                QMessageBox.critical(self, "Veritabanı Bütünlük Hatası", f"Üye eklenirken kısıtlama hatası: {e_int}")
                traceback.print_exc()
        except psycopg2.Error as e_db: # psycopg2 hatası
            self.db_connection.rollback()
            QMessageBox.critical(self, "Veritabanı Hatası", f"Üye eklenirken veritabanı hatası oluştu: {e_db}")
            traceback.print_exc()
        except Exception as e_general:
            if self.db_connection and not self.db_connection.closed: 
                try: self.db_connection.rollback() 
                except: pass 
            QMessageBox.critical(self, "Beklenmedik Hata", f"Üye eklenirken beklenmedik bir hata oluştu: {e_general}")
            traceback.print_exc()

# AdminPanel sınıfının içinde:

    def show_edit_member_form(self, member_id):
        """Verilen ID'li üyenin bilgilerini düzenleme formuna yükler ve formu gösterir."""
        # Gerekli widget'lar oluşturulmuş mu ve None değil mi kontrol et
        # Bu widget'lar __init__ içinde veya init_edit_member_form içinde tanımlanmış olmalı.
        required_widget_names = [
            "edit_name_input", "edit_uid_input", "edit_department_input",
            "edit_year_input", "edit_interests_input", "edit_email_input",
            "edit_phone_input", "edit_role_combo", "edit_photo_input",
            "edit_membership_date_edit", "edit_photo_label"
        ]
        for widget_name in required_widget_names:
            if not hasattr(self, widget_name) or getattr(self, widget_name) is None:
                QMessageBox.critical(self, "Kritik Hata",
                                     f"Düzenleme formu elemanı '{widget_name}' bulunamadı veya başlatılmamış.\n"
                                     f"Lütfen init_edit_member_form metodunu kontrol edin.")
                return

        self.edit_member_id = member_id # Düzenlenecek üyenin ID'sini sakla
        try:
            cursor = self.get_cursor()
            # Veritabanından üye bilgilerini çek (DictCursor sayesinde sözlük gibi erişim)
            cursor.execute("SELECT * FROM members WHERE id = %s", (member_id,))
            member = cursor.fetchone()

            if member:
                # Form alanlarını veritabanından gelen bilgilerle doldur
                # .get(key, default_value) kullanımı, anahtar yoksa hata vermek yerine varsayılan değer döndürür.
                self.edit_name_input.setText(member.get('name', ''))
                self.edit_uid_input.setText(member.get('uid', ''))
                self.edit_department_input.setText(member.get('department', ''))

                # Yıl (year) alanı integer olabilir, string'e çevirerek setText'e ver
                year_value = member.get('year')
                self.edit_year_input.setText(str(year_value) if year_value is not None else "")

                self.edit_interests_input.setText(member.get('interests', ''))
                self.edit_email_input.setText(member.get('email', ''))
                self.edit_phone_input.setText(member.get('phone', ''))
                self.edit_photo_input.setText(member.get('photo_path', '')) # Sadece dosya adını gösterir

                # Rol ComboBox'ını ayarla
                role_from_db = member.get('role', "") # Veritabanındaki rol
                # ComboBox'ta bu rolü bul ve seçili yap
                role_index = self.edit_role_combo.findText(role_from_db, Qt.MatchFlag.MatchFixedString)
                if role_index >= 0:
                    self.edit_role_combo.setCurrentIndex(role_index)
                else:
                    # Eğer rol ComboBox'ta yoksa, ilk sıradakini seç veya boş bırak (uygulama mantığınıza göre)
                    print(f"Uyarı: '{role_from_db}' rolü düzenleme formundaki ComboBox'ta bulunamadı.")
                    self.edit_role_combo.setCurrentIndex(0) # Veya -1 eğer boş olmasını istiyorsanız

                # --- DÜZELTİLMİŞ TARİH İŞLEME KISMI ---
                membership_date_value = member.get("membership_date")
                final_q_date = QDate.currentDate() # Varsayılan: bugünün tarihi

                if membership_date_value:
                    if isinstance(membership_date_value, datetime.date):
                        # Eğer Python'un datetime.date objesi ise, QDate'e doğrudan dönüştür
                        final_q_date = QDate(membership_date_value.year,
                                             membership_date_value.month,
                                             membership_date_value.day)
                    elif isinstance(membership_date_value, str):
                        # Eğer string ise, ISODate formatında parse etmeyi dene
                        parsed_q_date = QDate.fromString(membership_date_value, Qt.DateFormat.ISODate)
                        if parsed_q_date.isValid():
                            final_q_date = parsed_q_date
                        else:
                            print(f"Uyarı: '{membership_date_value}' string tarihi ISODate formatında parse edilemedi. Varsayılan tarih kullanılıyor.")
                    else:
                        # Beklenmedik bir tip ise (ne datetime.date ne de string)
                        print(f"Uyarı: Beklenmedik tarih tipi ({type(membership_date_value)}) veritabanından geldi. Varsayılan tarih kullanılıyor.")

                self.edit_membership_date_edit.setDate(final_q_date)
                # --- TARİH İŞLEME KISMI BİTTİ ---

                # Üye fotoğrafını yükle (load_member_photo_to_label metodu sadece dosya adını almalı)
                photo_filename_from_db = member.get('photo_path') # Bu sadece 'resim.jpg' gibi bir dosya adı olmalı
                self.load_member_photo_to_label(photo_filename_from_db, self.edit_photo_label)

                # Düzenleme sayfasını göster
                self.stacked_widget.setCurrentWidget(self.edit_member_page)
            else:
                QMessageBox.warning(self, "Üye Bulunamadı", f"ID'si {member_id} olan üye veritabanında bulunamadı.")
                self.edit_member_id = None # ID'yi sıfırla ki yanlışlıkla işlem yapılmasın

        except psycopg2.Error as db_err:
            QMessageBox.critical(self, "Veritabanı Hatası",
                                 f"Üye bilgileri yüklenirken bir veritabanı hatası oluştu:\n{db_err}")
            self.edit_member_id = None # Hata durumunda ID'yi sıfırla
            print(f"Veritabanı Hatası (show_edit_member_form): {db_err}")
            traceback.print_exc() # Konsola detaylı hata dökümü için
        except Exception as e:
            QMessageBox.critical(self, "Beklenmedik Hata",
                                 f"Üye bilgileri yüklenirken beklenmedik bir hata oluştu:\n{e}")
            self.edit_member_id = None # Hata durumunda ID'yi sıfırla
            print(f"Beklenmedik Hata (show_edit_member_form): {e}")
            traceback.print_exc() # Konsola detaylı hata dökümü için


    # AdminPanel sınıfının içine (diğer metodlarla birlikte):
    def go_to_event_from_main_list(self, item):
        """
        Ana sayfadaki yaklaşan etkinlikler listesinden bir öğeye çift tıklandığında
        ilgili etkinliğin detay sayfasını açar.
        """
        if not item:  # Tıklanan bir öğe yoksa bir şey yapma
            return
        try:
            event_id = item.data(Qt.ItemDataRole.UserRole) # Saklanan etkinlik ID'sini al
            if event_id is not None:
                print(f"Ana listeden etkinlik detayı açılıyor: ID={event_id}")
                self.show_event_details_page(event_id) # Etkinlik detay sayfasını göster
            else:
                # Bu durumun normalde oluşmaması gerekir, çünkü ID'leri atıyoruz.
                print("Uyarı: Ana listeden tıklanan etkinlik item'ında ID bulunamadı.")
                QMessageBox.warning(self, "Hata", "Seçilen etkinliğin ID'si alınamadı.")
        except Exception as e:
            print(f"Ana listeden etkinlik detayına gidilirken hata: {e}")
            # Kullanıcıya bir hata mesajı göstermek iyi olur.
            QMessageBox.warning(self, "Hata", f"Etkinlik detayı açılamadı:\n{e}")
            # Hatanın tam izini konsola yazdıralım, bu geliştirme aşamasında yardımcı olur.
            import traceback
            traceback.print_exc()
    def load_member_photo_to_edit_label(self, photo_path):
        """Düzenleme formundaki fotoğraf etiketine üyenin fotoğrafını yükler."""
        label = self.edit_photo_label # Düzenleme formundaki label
        if not label: return # Label yoksa çık

        label.setText("Fotoğraf Yok") # Varsayılan metin
        label.setPixmap(QPixmap()) # Önceki resmi temizle

        if photo_path and os.path.exists(photo_path):
            pixmap = QPixmap(photo_path)
            if not pixmap.isNull():
                # Etikete sığdırarak göster (oranı koruyarak)
                scaled_pixmap = pixmap.scaled(label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                label.setPixmap(scaled_pixmap)
            else:
                label.setText("Fotoğraf\nYüklenemedi")
                print(f"Uyarı: Fotoğraf dosyası geçersiz veya yüklenemedi ({photo_path})")
        # else: # Fotoğraf yolu yoksa veya dosya mevcut değilse zaten "Fotoğraf Yok" yazıyor


    # AdminPanel içinde
    def update_member(self):
        """Düzenleme formundaki bilgileri kullanarak üye kaydını günceller (PostgreSQL uyumlu)."""
        if self.edit_member_id is None: # ... (Kontrol) ...
            return
        # ... (widget kontrolü) ...
        # ... (Formdan verileri alma) ...
        name = self.edit_name_input.text().strip()
        uid = self.edit_uid_input.text().strip()
        # ... (diğerleri) ...
        membership_date_str = self.edit_membership_date_edit.date().toString(Qt.DateFormat.ISODate)
        if not name or not uid: # ... (zorunlu alan kontrolü) ...
            return
        try: # ... (yıl çevirme) ...
            year = int(year_str) if year_str else None
        except ValueError: # ...
            return

        try:
            cursor = self.get_cursor()
            # UPDATE sorgusunda ? yerine %s kullanıldı
            cursor.execute("""
                UPDATE members SET
                name=%s, uid=%s, role=%s, photo_path=%s, membership_date=%s, department=%s,
                year=%s, email=%s, phone=%s, interests=%s
                WHERE id=%s
            """, (name, uid, role, 
                photo_filename if photo_filename else None, # photo_filename burada tanımlı mıydı? 
                                                            # Muhtemelen self.edit_photo_input.text().strip() olmalı.
                membership_date_str if membership_date_str else None, 
                department or None, year, email or None, phone or None, interests or None, 
                self.edit_member_id))
            self.db_connection.commit()
            QMessageBox.information(self, "Başarılı", f"'{name}' adlı üyenin bilgileri güncellendi.")
            self.show_member_form() 

        except psycopg2.IntegrityError as e_int: # psycopg2 hatası
            self.db_connection.rollback()
            if "members_uid_key" in str(e_int).lower() or ("unique constraint" in str(e_int).lower() and "uid" in str(e_int).lower()):
                QMessageBox.critical(self, "Hata", f"Güncelleme hatası: Bu Kart UID ({uid}) zaten BAŞKA bir üyeye kayıtlı!")
                if hasattr(self, 'edit_uid_input'): self.edit_uid_input.setFocus()
            elif "members_email_key" in str(e_int).lower() or ("unique constraint" in str(e_int).lower() and "email" in str(e_int).lower()):
                QMessageBox.critical(self, "Hata", f"Güncelleme hatası: Bu E-posta ({email}) zaten BAŞKA bir üyeye kayıtlı!")
                if hasattr(self, 'edit_email_input'): self.edit_email_input.setFocus()
            else:
                QMessageBox.critical(self, "Veritabanı Bütünlük Hatası", f"Güncelleme sırasında kısıtlama hatası: {e_int}")
                traceback.print_exc()
        except psycopg2.Error as e_db: # psycopg2 hatası
            self.db_connection.rollback()
            QMessageBox.critical(self, "Veritabanı Hatası", f"Üye güncellenirken veritabanı hatası oluştu: {e_db}")
            traceback.print_exc()
        except Exception as e_general:
            if self.db_connection and not self.db_connection.closed: 
                try: self.db_connection.rollback() 
                except: pass 
            QMessageBox.critical(self, "Beklenmedik Hata", f"Üye güncellenirken beklenmedik bir hata oluştu: {e_general}")
            traceback.print_exc()


    def delete_member(self, member_id, member_name="Bilinmeyen Üye"):
        """Verilen ID'li üyeyi ve ilişkili katılım kayıtlarını siler (onay alarak)."""
        if member_id is None: return

        reply = QMessageBox.question(self, "Üyeyi Sil",
                                     f"'{member_name}' adlı üyeyi ve tüm katılım kayıtlarını silmek istediğinizden emin misiniz?\n\n"
                                     f"BU İŞLEM GERİ ALINAMAZ!",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, # Butonlar
                                     QMessageBox.StandardButton.Cancel) # Varsayılan buton

        if reply == QMessageBox.StandardButton.Yes:
            try:
                cursor = self.get_cursor()
                # Foreign Key ON DELETE CASCADE olduğu için ilişkili katılım kayıtları otomatik silinmeli.
                # Yine de önce katılımı silmek isterseniz:
                # cursor.execute("DELETE FROM attendance WHERE member_id = ?", (member_id,))
                cursor.execute("DELETE FROM members WHERE id = %s", (member_id,))
                rowcount = cursor.rowcount # Silinen satır sayısını kontrol et
                self.db_connection.commit()

                if rowcount > 0:
                    QMessageBox.information(self, "Başarılı", f"'{member_name}' adlı üye başarıyla silindi.")
                    self.update_member_list() # Listeyi yenile
                    self.update_main_page_stats() # Ana sayfa istatistiklerini güncelle (sonraki bölüm)

                    # Eğer profil veya düzenleme sayfası açıksa ve silinen üye gösteriliyorsa, üye listesine dön
                    current_widget = self.stacked_widget.currentWidget()
                    if current_widget == self.member_profile_page and self.current_profile_member_id == member_id:
                        self.show_member_form()
                    elif current_widget == self.edit_member_page and self.edit_member_id == member_id:
                        self.show_member_form()
                else:
                     QMessageBox.warning(self, "Bulunamadı", f"ID'si {member_id} olan üye silinemedi (muhtemelen zaten silinmiş).")

            except psycopg2.Error as e:
                QMessageBox.critical(self, "Veritabanı Hatası", f"Üye silinirken veritabanı hatası oluştu: {e}")
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Üye silinirken beklenmedik bir hata oluştu: {e}")
                import traceback
                traceback.print_exc()

    # AdminPanel sınıfının içinde:
    def browse_photo(self, line_edit_widget):
        """
        Fotoğraf dosyası seçmek için diyalog açar, seçilen fotoğrafı
        MEMBER_PHOTOS_DIR klasörüne kopyalar ve sadece dosya adını ilgili QLineEdit'a yazar.
        """
        # Önce MEMBER_PHOTOS_DIR'in var olduğundan emin olalım (normalde __init__ bunu yapar)
        if not os.path.exists(self.MEMBER_PHOTOS_DIR):
            try:
                os.makedirs(self.MEMBER_PHOTOS_DIR)
            except OSError as e:
                QMessageBox.critical(self, "Klasör Hatası",
                                     f"'{self.MEMBER_PHOTOS_DIR}' klasörü bulunamadı ve oluşturulamadı: {e}")
                return # Klasör yoksa veya oluşturulamazsa devam etme

        file_path, _ = QFileDialog.getOpenFileName(self,
                                                   "Fotoğraf Seç",
                                                   "", # Başlangıç dizini
                                                   "Resim Dosyaları (*.png *.jpg *.jpeg *.bmp)")
        
        if file_path: # Kullanıcı bir dosya seçtiyse
            try:
                # Benzersiz bir dosya adı oluşturmaya çalışalım (örn: uyeID_zamanDamgasi.uzanti)
                # Ancak üye ID'si bu aşamada henüz belli olmayabilir (yeni üye eklerken).
                # Bu yüzden şimdilik orijinal dosya adını kullanalım, ama hedef klasöre kopyalayalım.
                # Daha iyisi, rastgele bir string veya zaman damgası ile yeni bir ad oluşturmak olabilir
                # ki aynı isimde dosyalar çakışmasın.
                
                original_filename = os.path.basename(file_path)
                # Dosya adını ve uzantısını ayır
                filename_root, filename_ext = os.path.splitext(original_filename)
    
                current_time_str = QDateTime.currentDateTime().toString("yyyyMMddHHmmsszzz")
                # Orijinal dosya adındaki geçersiz karakterleri temizleyelim (isteğe bağlı)
                safe_original_filename = "".join(c if c.isalnum() or c in ['.', '_', '-'] else '_' for c in original_filename)
                target_filename = original_filename 
                destination_path = os.path.join(self.MEMBER_PHOTOS_DIR, target_filename)
                
             
                shutil.copy2(file_path, destination_path) # copy2 metadata'yı da korur
                print(f"Fotoğraf '{file_path}' adresinden '{destination_path}' adresine kopyalandı.")
                
                # QLineEdit'a sadece dosya adını (yolunu değil) yaz
                line_edit_widget.setText(target_filename) 
                
                # Eğer düzenleme formundaysak ve edit_photo_label varsa fotoğrafı orada da gösterelim
                if hasattr(self, 'edit_photo_label') and self.edit_photo_label and \
                   self.stacked_widget.currentWidget() == self.edit_member_page:
                    self.load_member_photo_to_label(destination_path, self.edit_photo_label) # Yeni yardımcı fonksiyon
                elif hasattr(self, 'profile_photo_label') and self.profile_photo_label and \
                     self.stacked_widget.currentWidget() == self.member_profile_page and \
                     line_edit_widget == getattr(self, 'edit_photo_input', None): # Bu biraz dolaylı oldu, belki gerek yok.
                     # Profil sayfasında doğrudan fotoğraf yükleme butonu yok, bu daha çok düzenleme için.
                     pass


            except FileNotFoundError:
                QMessageBox.critical(self, "Hata", f"Kaynak fotoğraf dosyası bulunamadı: {file_path}")
                line_edit_widget.clear()
            except PermissionError:
                QMessageBox.critical(self, "Hata", f"Fotoğraf kopyalamak için izin yok: {destination_path}")
                line_edit_widget.clear()
            except Exception as e:
                QMessageBox.critical(self, "Fotoğraf Kopyalama Hatası", f"Fotoğraf kopyalanırken bir hata oluştu: {e}")
                line_edit_widget.clear()
                traceback.print_exc()
        # Kullanıcı dosya seçmezse bir şey yapma (file_path boş olur)

# --- Kapatma Olayı (AdminPanel içinde) ---
    def closeEvent(self, event):
        """Admin paneli kapatılırken veritabanı bağlantısını güvenli kapatır."""
        print("Admin paneli kapatılıyor...")
        if self.db_connection:
            try:
                self.db_connection.close()
                self.db_connection = None # Referansı temizle
                print("Veritabanı bağlantısı kapatıldı.")
            except psycopg2.Error as e:
                print(f"Veritabanı kapatılırken hata: {e}")
            except Exception as e:
                print(f"Kapatma sırasında beklenmedik hata: {e}")
        # Login penceresini gizlemek yerine uygulamayı tamamen kapatmak daha mantıklı olabilir
        # Eğer login penceresi açıksa, o zaten uygulamayı kapatacaktır (closeEvent'i var)
        # Eğer login penceresi gizliyse, biz burada kapatmalıyız.
        if self.login_window and not self.login_window.isVisible():
             QApplication.instance().quit()
        event.accept() # Pencerenin kapanmasına izin ver

# --- Uygulama Ana Çalıştırma Bloğu (Sonraki bölümde gelecek) ---
# if __name__ == "__main__":
#     app = QApplication(sys.argv)
#     # ... (LoginWindow oluşturma ve gösterme)
#     sys.exit(app.exec())
# AdminPanel sınıfının devamı... (Önceki bölümdeki kodun devamıdır)

    # --- init_ Sayfa Metodları (Devamı - Refaktör Edilmiş) ---

    def init_event_details_page(self):
        """Etkinlik detayları ve katılım yönetimi sayfasının arayüzünü oluşturur (Refaktör Edilmiş)."""
        layout = QVBoxLayout(self.event_details_page) # Layout'u sayfaya ata

        # Geri Butonu
        header_layout = QHBoxLayout()
        back_button = QPushButton("← Etkinlik Listesi")
        back_button.setFixedSize(150, 30)
        # Lambda ile doğrudan etkinlik listesi sayfasına dön
        back_button.clicked.connect(lambda: self.stacked_widget.setCurrentWidget(self.event_form_page))
        header_layout.addWidget(back_button, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Etkinlik Bilgileri Alanı
        self.event_details_layout = QVBoxLayout() # Ayrı bir layout grubu
        self.event_details_name_label = QLabel("Etkinlik: -")
        self.event_details_name_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.event_details_layout.addWidget(self.event_details_name_label)

        self.event_details_date_loc_label = QLabel("Tarih/Yer: - / -")
        self.event_details_date_loc_label.setStyleSheet("font-size: 14px; color: #555;") # Stil dosyasından alabilir
        self.event_details_layout.addWidget(self.event_details_date_loc_label)

        self.event_details_cat_label = QLabel("Kategori: -")
        self.event_details_cat_label.setStyleSheet("font-size: 14px; color: #555;")
        self.event_details_layout.addWidget(self.event_details_cat_label)

        self.event_details_desc_label = QLabel("Açıklama:")
        self.event_details_desc_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        self.event_details_layout.addWidget(self.event_details_desc_label)

        self.event_details_desc_text = QTextEdit()
        self.event_details_desc_text.setReadOnly(True) # Sadece okunabilir
        self.event_details_desc_text.setMaximumHeight(100) # Yüksekliği sınırla
        self.event_details_layout.addWidget(self.event_details_desc_text)

        layout.addLayout(self.event_details_layout) # Etkinlik bilgilerini ana layout'a ekle
        layout.addSpacing(15)

        # Katılımcı Yönetimi Alanı (İki Sütunlu)
        participants_layout = QHBoxLayout()
        participants_left = QVBoxLayout() # Sol: Butonlar
        participants_right = QVBoxLayout() # Sağ: Liste

        # Sol Butonlar
        self.start_uid_check_button = QPushButton("✅ Üye Kart Kontrolü Başlat")
        self.start_uid_check_button.clicked.connect(self.show_uid_check_dialog) # Sonraki bölümde implemente edilecek
        self.start_uid_check_button.setStyleSheet("background-color: #28a745; padding: 12px; font-weight: bold;")
        participants_left.addWidget(self.start_uid_check_button)

        self.export_participants_pdf_button = QPushButton("📄 Katılımcıları PDF Aktar")
        self.export_participants_pdf_button.setObjectName("btn_export") # Stil için
        self.export_participants_pdf_button.setIcon(QIcon.fromTheme("document-export"))
        self.export_participants_pdf_button.clicked.connect(self.export_event_participants_pdf) # Sonraki bölümde implemente edilecek
        participants_left.addWidget(self.export_participants_pdf_button)

        self.export_participants_csv_button = QPushButton("📊 Katılımcıları CSV Aktar")
        self.export_participants_csv_button.setObjectName("btn_export") # Stil için
        self.export_participants_csv_button.setIcon(QIcon.fromTheme("document-export"))
        self.export_participants_csv_button.clicked.connect(self.export_event_participants) # Sonraki bölümde implemente edilecek
        participants_left.addWidget(self.export_participants_csv_button)
        participants_left.addStretch() # Butonları yukarı yasla

        # Sağ Katılımcı Listesi
        participant_label = QLabel("Katılımcılar:")
        participant_label.setStyleSheet("font-weight: bold;")
        self.participants_list_widget = QListWidget()
        # TODO: Katılımcı listesine sağ tık menüsü eklenebilir (örn: Üye profilini aç, katılımı sil)
        # self.participants_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # self.participants_list_widget.customContextMenuRequested.connect(self.on_participant_list_context_menu)
        participants_right.addWidget(participant_label)
        participants_right.addWidget(self.participants_list_widget) # Listeyi ekle

        participants_layout.addLayout(participants_left, 1) # Sol sütun (oran 1)
        participants_layout.addLayout(participants_right, 2) # Sağ sütun (oran 2, daha geniş)
        layout.addLayout(participants_layout) # Katılımcı alanını ana layout'a ekle

        # Sayfayı stacked widget'a ekle
        self.stacked_widget.addWidget(self.event_details_page)

    def init_member_profile_page(self):
        """Üye profil sayfasının arayüzünü oluşturur (Refaktör Edilmiş)."""
        layout = QVBoxLayout(self.member_profile_page) # Layout'u sayfaya ata

        # Geri Butonu
        header_layout = QHBoxLayout()
        back_button = QPushButton("← Üye Listesi")
        back_button.setFixedSize(120, 30)
        back_button.clicked.connect(self.show_member_form) # Üye listesi sayfasına dön
        header_layout.addWidget(back_button, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Profil Başlığı
        profile_title = QLabel("Üye Profili")
        profile_title.setStyleSheet("font-size: 18px; font-weight: bold; margin-bottom: 10px;")
        profile_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(profile_title)

        # Profil İçeriği (İki Sütunlu)
        profile_content_layout = QHBoxLayout()
        profile_left = QVBoxLayout() # Sol: Fotoğraf ve Temel Bilgiler
        profile_right = QVBoxLayout() # Sağ: Diğer Bilgiler ve Etkinlikler
        profile_content_layout.addLayout(profile_left, 1) # Oran 1
        profile_content_layout.addLayout(profile_right, 2) # Oran 2 (daha geniş)

        # Sol Sütun: Fotoğraf ve Temel Bilgiler
        self.profile_photo_label = QLabel("Fotoğraf Yok")
        self.profile_photo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.profile_photo_label.setFixedSize(200, 200) # Sabit boyut
        self.profile_photo_label.setFrameShape(QFrame.Shape.Box)
        self.profile_photo_label.setLineWidth(1)
        self.profile_photo_label.setStyleSheet("border: 1px solid #ccc; background-color: white;")
        profile_left.addWidget(self.profile_photo_label)

        # Etiket stili (tekrarı önlemek için)
        info_style = "font-size: 14px; margin-bottom: 6px;"

        self.profile_name_label = QLabel("Ad:")
        self.profile_name_label.setStyleSheet(info_style)
        profile_left.addWidget(self.profile_name_label)

        self.profile_uid_label = QLabel("UID:")
        self.profile_uid_label.setStyleSheet(info_style)
        profile_left.addWidget(self.profile_uid_label)

        self.profile_role_label = QLabel("Rol:")
        self.profile_role_label.setStyleSheet(info_style)
        profile_left.addWidget(self.profile_role_label)

        self.profile_membership_date_label = QLabel("Üyelik Tarihi:")
        self.profile_membership_date_label.setStyleSheet(info_style)
        profile_left.addWidget(self.profile_membership_date_label)
        self.profile_points_label = QLabel("Puan:") 
        self.profile_points_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #1a73e8; margin-bottom: 6px;") # Biraz farklı bir stil verelim
        profile_left.addWidget(self.profile_points_label)
        # init_member_profile_page metodu içinde, profile_left.addWidget(self.profile_points_label) satırından sonra:

        # ---- YENİ MANUEL PUAN AYARLAMA BÖLÜMÜ ----
        # Ayırıcı çizgi ekleyelim (isteğe bağlı, create_separator_line metodu sizde olmalı)
        if hasattr(self, 'create_separator_line') and callable(self.create_separator_line):
             profile_left.addWidget(self.create_separator_line(margin_top=10, margin_bottom=10))

        manual_points_label = QLabel("Manuel Puan Ekle/Çıkar:")
        manual_points_label.setStyleSheet("font-weight:bold; margin-top: 5px;")
        profile_left.addWidget(manual_points_label)

        manual_points_layout = QGridLayout() # Daha düzenli hizalama için Grid
        manual_points_layout.setSpacing(5)

        manual_points_layout.addWidget(QLabel("Miktar (+/-):"), 0, 0)
        # Bu spinbox'ı self'e atamayı unutmayın!
        self.manual_points_spinbox = QSpinBox() 
        self.manual_points_spinbox.setRange(-9999, 9999) # Geniş bir aralık
        self.manual_points_spinbox.setSingleStep(5)     
        self.manual_points_spinbox.setFixedWidth(100)    
        self.manual_points_spinbox.setValue(0)         
        manual_points_layout.addWidget(self.manual_points_spinbox, 0, 1)

        manual_points_layout.addWidget(QLabel("Neden:"), 1, 0)
        # Bu input'u self'e atamayı unutmayın!
        self.manual_points_reason_input = QLineEdit() 
        self.manual_points_reason_input.setPlaceholderText("Puan ekleme/çıkarma nedeni...")
        manual_points_layout.addWidget(self.manual_points_reason_input, 1, 1)

        btn_adjust_points = QPushButton("Puanı Ayarla")
        # Bu butona bir ikon ekleyebilirsiniz (isteğe bağlı)
        # btn_adjust_points.setIcon(QIcon.fromTheme("list-add")) 
        # Bu metodu bir sonraki adımda oluşturacağız:
        btn_adjust_points.clicked.connect(self.adjust_member_points) 
        manual_points_layout.addWidget(btn_adjust_points, 2, 0, 1, 2) # Buton iki sütuna yayılsın

        # GridLayout'u ana sol sütun layout'una ekle
        profile_left.addLayout(manual_points_layout)
        # ---- MANUEL PUAN AYARLAMA BÖLÜMÜ BİTTİ ----

        # profile_left.addStretch() # Bu satır zaten metodun sonunda olmalı
        profile_left.addStretch() # Bilgileri yukarı yasla

        

        # Sağ Sütun: Diğer Bilgiler ve Etkinlik Listesi
        self.profile_dep_label = QLabel("Bölüm:")
        self.profile_dep_label.setStyleSheet(info_style)
        profile_right.addWidget(self.profile_dep_label)

        self.profile_year_label = QLabel("Sınıf/Yıl:")
        self.profile_year_label.setStyleSheet(info_style)
        profile_right.addWidget(self.profile_year_label)

        self.profile_email_label = QLabel("E-posta:")
        self.profile_email_label.setStyleSheet(info_style)
        # E-postayı tıklanabilir yap (mailto linki)
        # self.profile_email_label.setOpenExternalLinks(True) # QLabel'da doğrudan çalışmaz, QLineEdit veya başka yöntem gerekebilir.
        profile_right.addWidget(self.profile_email_label)

        self.profile_phone_label = QLabel("Telefon:")
        self.profile_phone_label.setStyleSheet(info_style)
        profile_right.addWidget(self.profile_phone_label)

        self.profile_interests_label = QLabel("İlgi Alanları:")
        self.profile_interests_label.setStyleSheet(info_style)
        profile_right.addWidget(self.profile_interests_label)

        profile_right.addSpacing(20) # Boşluk

        # Katıldığı Etkinlikler
        attendance_label = QLabel("Katıldığı Etkinlikler:")
        attendance_label.setStyleSheet("font-weight: bold;")
        self.profile_attendance_list = QListWidget()
        # TODO: Buradaki etkinliklere çift tıklayınca ilgili etkinlik detayına gitme eklenebilir.
        # self.profile_attendance_list.itemDoubleClicked.connect(self.go_to_event_from_profile)
        profile_right.addWidget(attendance_label)
        profile_right.addWidget(self.profile_attendance_list, 1) # Liste widget'ını ekle
        profile_right.addSpacing(15) # Önceki listeyle araya biraz boşluk koyalım

        points_log_label = QLabel("Puan Geçmişi:")
        points_log_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        profile_right.addWidget(points_log_label)

        self.profile_points_log_table = QTableWidget()
        self.profile_points_log_table.setColumnCount(3) # Sütunlar: Tarih/Saat, Neden, Kazanılan/Kaybedilen Puan
        self.profile_points_log_table.setHorizontalHeaderLabels(["Zaman", "Açıklama (Neden)", "Puan Değişimi"])
        self.profile_points_log_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.profile_points_log_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.profile_points_log_table.verticalHeader().setVisible(False)
        self.profile_points_log_table.setAlternatingRowColors(True)

        # Sütun genişlikleri ve davranışları
        points_log_header = self.profile_points_log_table.horizontalHeader()
        points_log_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) # Zaman içeriğe göre
        points_log_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch) # Açıklama genişlesin
        points_log_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents) # Puan içeriğe göre
        self.profile_points_log_table.setColumnWidth(0, 140) # Zaman için başlangıç genişliği

        # Tablonun dikeyde genişlemesini sağlayalım
        self.profile_points_log_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Bu tablonun da dikeyde yer kaplamasını istediğimiz için stretch faktörü ekleyebiliriz.
        # profile_right layout'u içindeki profile_attendance_list ve profile_points_log_table
        # alanı nasıl paylaşacak? İkisine de stretch=1 verelim.
        # Önce profile_attendance_list'i eklerken stretch ekleyelim:
        # profile_right.addWidget(self.profile_attendance_list, 1) # Stretch 1 ekle
        # Sonra puan log tablosunu ekleyelim:
        profile_right.addWidget(self.profile_points_log_table, 1) # Stretch 1 ekle
        # ---- PUAN GEÇMİŞİ BÖLÜMÜ BİTTİ ----
        layout.addLayout(profile_content_layout) # İçerik layout'unu ana layout'a ekle

        # Sayfayı stacked widget'a ekle
        self.stacked_widget.addWidget(self.member_profile_page)

    def init_settings_page(self):
        """Uygulama ayarları sayfasının arayüzünü oluşturur (Refaktör Edilmiş)."""
        layout = QVBoxLayout(self.settings_page) # Layout'u sayfaya ata
        layout.setSpacing(15)

        # Geri Butonu
        header_layout = QHBoxLayout()
        back_button = QPushButton("← Ana Sayfa")
        back_button.setFixedSize(120, 30)
        back_button.clicked.connect(self.show_main_page)
        header_layout.addWidget(back_button, alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Başlık
        title_label = QLabel("Uygulama Ayarları")
        title_label.setObjectName("settingsPageTitle") # Stil için
        layout.addWidget(title_label)

        # Ayar Alanları (Grid Layout ile)
        settings_grid = QGridLayout()
        settings_grid.setSpacing(10)
        settings_grid.setColumnStretch(1, 1) # İkinci sütun (giriş alanları) genişlesin

        # Satır 0: Logo Yolu
        settings_grid.addWidget(QLabel("Logo Dosya Yolu:", objectName="settingsSectionLabel"), 0, 0)
        logo_path_layout = QHBoxLayout()
        self.settings_logo_path_input = QLineEdit()
        self.settings_logo_path_input.setPlaceholderText("Logo için resim dosyası...")
        self.settings_logo_path_input.setReadOnly(True)
        logo_browse_button = QPushButton("Gözat")
        logo_browse_button.clicked.connect(self.browse_logo_for_settings) # Sonraki bölümde implemente edilecek
        logo_path_layout.addWidget(self.settings_logo_path_input)
        logo_path_layout.addWidget(logo_browse_button)
        settings_grid.addLayout(logo_path_layout, 0, 1)

        # Satır 1: PDF Font Yolu
        settings_grid.addWidget(QLabel("PDF Font Yolu:", objectName="settingsSectionLabel"), 1, 0)
        pdf_font_layout = QHBoxLayout()
        self.settings_pdf_font_input = QLineEdit()
        self.settings_pdf_font_input.setPlaceholderText("PDF için .ttf font (örn: DejaVuSans.ttf)")
        self.settings_pdf_font_input.setReadOnly(True)
        pdf_font_browse_button = QPushButton("Gözat")
        pdf_font_browse_button.clicked.connect(self.browse_pdf_font_for_settings) # Sonraki bölümde implemente edilecek
        pdf_font_layout.addWidget(self.settings_pdf_font_input)
        pdf_font_layout.addWidget(pdf_font_browse_button)
        settings_grid.addLayout(pdf_font_layout, 1, 1)

        # Satır 2: Varsayılan Yedekleme Konumu
        settings_grid.addWidget(QLabel("Vars. Yedekleme Konumu:", objectName="settingsSectionLabel"), 2, 0)
        backup_path_layout = QHBoxLayout()
        self.settings_backup_path_input = QLineEdit()
        self.settings_backup_path_input.setPlaceholderText("Yedeklerin kaydedileceği klasör...")
        self.settings_backup_path_input.setReadOnly(True)
        backup_browse_button = QPushButton("Klasör Seç")
        backup_browse_button.clicked.connect(self.browse_backup_path) # Sonraki bölümde implemente edilecek
        backup_path_layout.addWidget(self.settings_backup_path_input)
        backup_path_layout.addWidget(backup_browse_button)
        settings_grid.addLayout(backup_path_layout, 2, 1)

        # Satır 3: Varsayılan Dışa Aktarma Konumu
        settings_grid.addWidget(QLabel("Vars. Dışa Aktarma Konumu:", objectName="settingsSectionLabel"), 3, 0)
        export_path_layout = QHBoxLayout()
        self.settings_export_path_input = QLineEdit()
        self.settings_export_path_input.setPlaceholderText("Dışa aktarılan dosyaların konumu...")
        self.settings_export_path_input.setReadOnly(True)
        export_browse_button = QPushButton("Klasör Seç")
        export_browse_button.clicked.connect(self.browse_export_path) # Sonraki bölümde implemente edilecek
        export_path_layout.addWidget(self.settings_export_path_input)
        export_path_layout.addWidget(export_browse_button)
        settings_grid.addLayout(export_path_layout, 3, 1)

        # Satır 4: Varsayılan Üye Rolü
        settings_grid.addWidget(QLabel("Varsayılan Üye Rolü:", objectName="settingsSectionLabel"), 4, 0)
        self.settings_default_role_combo = QComboBox()
        # Kullanılabilir rolleri ekle (düzenleme/ekleme formlarındaki gibi)
        settings_roles = ["Aktif Üye", "Normal Üye", "Yönetim Kurulu Üyesi"]
        self.settings_default_role_combo.addItems(settings_roles)
        settings_grid.addWidget(self.settings_default_role_combo, 4, 1)

        # Satır 5: Ana Sayfa Etkinlik Limiti
        settings_grid.addWidget(QLabel("Ana Sayfa Etkinlik Limiti:", objectName="settingsSectionLabel"), 5, 0)
        self.settings_upcoming_limit_spinbox = QSpinBox()
        self.settings_upcoming_limit_spinbox.setRange(1, 20) # Min 1, Max 20 etkinlik
        self.settings_upcoming_limit_spinbox.setSuffix(" etkinlik")
        self.settings_upcoming_limit_spinbox.setToolTip("Ana sayfada gösterilecek yaklaşan etkinlik sayısı")
        settings_grid.addWidget(self.settings_upcoming_limit_spinbox, 5, 1)

        # Satır 6: Uygulama Teması
        settings_grid.addWidget(QLabel("Uygulama Teması:", objectName="settingsSectionLabel"), 6, 0)
        self.settings_theme_combo = QComboBox()
        self.settings_theme_combo.addItems(["Açık Tema", "Koyu Tema"])
        settings_grid.addWidget(self.settings_theme_combo, 6, 1)

        layout.addLayout(settings_grid) # Grid'i ana layout'a ekle
        layout.addStretch() # Ayarları yukarı yasla

        # Kaydet Butonu
        save_button = QPushButton("Ayarları Kaydet")
        save_button.setIcon(QIcon.fromTheme("document-save"))
        save_button.clicked.connect(self.save_settings_from_ui) # Sonraki bölümde implemente edilecek
        layout.addWidget(save_button, alignment=Qt.AlignmentFlag.AlignCenter)

        # Sayfayı stacked widget'a ekle
        self.stacked_widget.addWidget(self.settings_page)


    # --- İstatistik ve Ana Sayfa Güncelleme ---
    def update_main_page_stats(self):
        """Ana sayfadaki istatistikleri ve yaklaşan etkinlik listesini günceller."""
        # Widget'lar var mı kontrol et
        required = [self.stats_total_members_label, self.stats_total_events_label,
                    self.stats_upcoming_events_label, self.upcoming_events_list,
                    self.upcoming_events_label_widget]
        if any(w is None for w in required):
             print("Uyarı: Ana sayfa istatistik widget'ları henüz hazır değil.")
             return

        total_members, total_events, upcoming_events_count = 0, 0, 0;
        upcoming_events_data = []
        limit = self.settings.get('upcoming_events_limit', 5) # Ayarlardan limiti al

        try:
            cursor = self.get_cursor()
            # Toplam üye sayısı
            cursor.execute("SELECT COUNT(id) FROM members")
            result = cursor.fetchone(); total_members = result[0] if result else 0
            # Toplam etkinlik sayısı
            cursor.execute("SELECT COUNT(id) FROM events")
            result = cursor.fetchone(); total_events = result[0] if result else 0

            # Yaklaşan etkinlikler (bugünden itibaren)
            today_iso = QDate.currentDate().toString(Qt.DateFormat.ISODate)
            # Limitli sayıda etkinlik adı ve tarihi al (geçmiş olmayanları)
            # Not: event_date NULL ise veya formatı bozuksa sorgu hatasına neden olabilir.
            # Bu yüzden WHERE event_date IS NOT NULL eklemek daha güvenli olabilir.
            # Veya Python tarafında kontrol edilebilir. Şimdilik basit tutalım.
            query_upcoming = f"""
                SELECT id, name, event_date
                FROM events
                WHERE event_date >= %s
                ORDER BY event_date ASC
                LIMIT %s """
            cursor.execute(query_upcoming, (today_iso, limit))
            upcoming_events_data = cursor.fetchall() # Limitli liste

            # Yaklaşan etkinliklerin toplam sayısını al (limitsiz)
            cursor.execute("SELECT COUNT(id) FROM events WHERE event_date >= %s", (today_iso,))
            result = cursor.fetchone(); upcoming_events_count = result[0] if result else 0

        except psycopg2.Error as e:
            print(f"Ana sayfa istatistikleri alınırken veritabanı hatası: {e}")
            self.stats_total_members_label.setText("Hata")
            self.stats_total_events_label.setText("Hata")
            self.stats_upcoming_events_label.setText("Hata")
            self.upcoming_events_list.clear()
            self.upcoming_events_list.addItem("Veri alınamadı.")
            return
        except Exception as e:
            print(f"Ana sayfa istatistikleri alınırken genel hata: {e}")
            # Hata durumunda da etiketleri sıfırlayabilir veya hata mesajı gösterebiliriz
            self.stats_total_members_label.setText("Hata")
            self.stats_total_events_label.setText("Hata")
            self.stats_upcoming_events_label.setText("Hata")
            self.upcoming_events_list.clear()
            self.upcoming_events_list.addItem(f"Hata: {e}")
            return

        # Etiketleri güncelle
        self.stats_total_members_label.setText(str(total_members))
        self.stats_total_events_label.setText(str(total_events))
        self.stats_upcoming_events_label.setText(str(upcoming_events_count))

        # Yaklaşan etkinlik listesini güncelle
        self.upcoming_events_list.clear();
        # Liste başlığını güncelle (limit bilgisini ekleyerek)
        self.upcoming_events_label_widget.setText(f"Yaklaşan Etkinlikler (İlk {limit}):")

        if upcoming_events_data:
            for event in upcoming_events_data:
                event_date_value = event["event_date"]  # Veritabanından gelen tarih değeri
                formatted_date = "Tarihsiz"  # Varsayılan değer

                if event_date_value:  # Eğer tarih değeri None veya boş değilse
                    if isinstance(event_date_value, datetime.date):
                        # Eğer değer Python'un datetime.date objesi ise,
                        # QDate'e doğrudan yıl, ay, gün bilgileriyle dönüştür
                        q_date_obj = QDate(event_date_value.year, event_date_value.month, event_date_value.day)
                        formatted_date = q_date_obj.toString("dd.MM.yyyy")
                    elif isinstance(event_date_value, str):
                        # Eğer değer zaten bir string (metin) ise, fromString ile parse etmeyi dene
                        q_date_obj = QDate.fromString(event_date_value, Qt.DateFormat.ISODate)
                        if q_date_obj.isValid():
                            formatted_date = q_date_obj.toString("dd.MM.yyyy")
                        else:
                            formatted_date = "Hatalı T." # Veya event_date_value'yu olduğu gibi göster
                    else:
                        # Beklenmedik bir tip ise
                        formatted_date = "Bilinmeyen T. Formatı"
                item_text = f"{event['name']} ({formatted_date})"
                list_item = QListWidgetItem(item_text)
                list_item.setData(Qt.ItemDataRole.UserRole, event['id']) # Etkinlik ID'sini sakla (çift tıklama için)
                self.upcoming_events_list.addItem(list_item)
        else:
            self.upcoming_events_list.addItem("Yaklaşan etkinlik bulunmuyor.")


    def update_main_page_logo(self):
        """Ayarlara göre ana sayfadaki logoyu günceller."""
        if not self.main_logo_label: return # Logo etiketi henüz yoksa çık

        logo_path = self.settings.get('logo_path', ''); # Ayarlardan logo yolunu al
        logo_loaded = False
        if logo_path and os.path.exists(logo_path):
            try:
                pixmap = QPixmap(logo_path) # Resmi yüklemeyi dene
                if pixmap and not pixmap.isNull():
                    # Logoyu etiket boyutuna sığdır (yüksekliği 50px)
                    self.main_logo_label.setPixmap(pixmap.scaledToHeight(50, Qt.TransformationMode.SmoothTransformation))
                    logo_loaded = True
                else:
                    print(f"Uyarı: Logo dosyası geçersiz veya yüklenemedi ({logo_path})")
            except Exception as e:
                print(f"Logo yüklenirken hata (QPixmap): {e}")

        # Eğer logo yüklenemediyse varsayılan emoji logoyu göster
        if not logo_loaded:
            self.main_logo_label.setText("🦊") # Varsayılan logo
            self.main_logo_label.setStyleSheet("font-size: 48px;"); # Emoji için stil


    # --- Placeholder/Rapor Metodları ---
    # AdminPanel sınıfının içinde:
    def show_member_report_placeholder(self):
        """Ana sayfadaki 'Toplam Üye' istatistiğinin yanındaki 'Detay' butonuna basıldığında
        Üye Yönetimi sayfasını gösterir."""
        print("DEBUG: 'Toplam Üye -> Detay' butonuna basıldı. Üye formu gösteriliyor.")
        self.show_member_form() # Üye yönetimi sayfasını açan metot

    # AdminPanel sınıfının içinde:
    def show_event_report_placeholder(self):
        """Ana sayfadaki 'Toplam Etkinlik' istatistiğinin yanındaki 'Detay' butonuna basıldığında
        Etkinlik Yönetimi sayfasını gösterir."""
        print("DEBUG: 'Toplam Etkinlik -> Detay' butonuna basıldı. Etkinlik formu gösteriliyor.")
        self.show_event_form() # Etkinlik yönetimi sayfasını açan metot

    def show_upcoming_event_report_placeholder(self):
        # Yaklaşan etkinlik detayı istendiğinde doğrudan etkinlik yönetimi sayfasını aç
        self.show_event_form()

    def show_member_reports_chart(self):
        """Üyelerin bölümlere göre dağılımını gösteren pasta grafik oluşturur."""
        if not MATPLOTLIB_AVAILABLE:
            QMessageBox.critical(self,"Kütüphane Eksik","Grafik oluşturmak için 'matplotlib' kütüphanesi kurulu olmalıdır.\nKurmak için: pip install matplotlib")
            return
        try:
            cursor = self.get_cursor()
            # Boş olmayan ve null olmayan bölümleri say, sayıya göre sırala
            cursor.execute("""
                SELECT department, COUNT(*) as count
                FROM members
                WHERE department IS NOT NULL AND department != ''
                GROUP BY department
                HAVING COUNT(*) > 0
                ORDER BY count DESC
            """)
            data = cursor.fetchall()

            # Veri yoksa mesaj göster
            if not data:
                QMessageBox.information(self, "Yetersiz Veri", "Grafik oluşturmak için yeterli üye bölüm verisi bulunamadı.")
                return

            # Verileri etiketlere ve boyutlara ayır
            labels = [row['department'] for row in data]
            sizes = [row['count'] for row in data]

            # Grafik diyalogunu oluştur ve göster
            # ChartDialog sınıfı önceki kod bölümünde tanımlanmıştı.
            chart_dialog = ChartDialog(self) # Parent olarak AdminPanel'i ver
            chart_dialog.plot_pie(labels, sizes, "Üye Dağılımı (Bölüme Göre)")
            chart_dialog.exec() # Modsal olarak göster (kapatılana kadar bekle)

        except psycopg2.Error as e:
            QMessageBox.critical(self, "Veritabanı Hatası", f"Üye rapor verisi alınırken hata oluştu: {e}")
        except ImportError:
             QMessageBox.critical(self,"Kütüphane Eksik","Grafik oluşturmak için 'matplotlib' kütüphanesi kurulu olmalıdır.")
        except Exception as ex:
            QMessageBox.critical(self, "Grafik Hatası", f"Grafik oluşturulurken beklenmedik bir hata oluştu: {ex}")
            traceback.print_exc() # Detaylı hata için konsola yazdır

    # --- Etkinlik Yönetimi Fonksiyonları (Devamı) ---

    def clear_event_form(self):
        """Etkinlik ekleme/düzenleme formunu temizler."""
        if not self.event_name_input: return # Form widgetları yoksa çık
        self.edit_event_id_label.setText("") # Gizli ID label'ını temizle (yeni ekleme modu)
        self.event_name_input.clear()
        self.event_date_edit.setDate(QDate.currentDate()) # Tarihi bugüne ayarla
        self.event_location_input.clear()
        self.event_category_combo.setCurrentIndex(0) # İlk (boş) seçeneği seç
        self.event_description_input.clear()
        # Buton metnini ve ikonunu "Ekle" moduna getir
        self.event_add_update_button.setText("Etkinlik Ekle")
        self.event_add_update_button.setIcon(QIcon.fromTheme("list-add"))
        # Etkinlik listesindeki seçimi kaldır
        self.event_list_widget.clearSelection()


    # AdminPanel sınıfının içinde:
# AdminPanel sınıfının içinde:
    def load_event_to_form_for_edit(self, index):
        """Etkinlik listesinden tıklanan etkinliğin bilgilerini forma yükler (düzenleme için - KAPASİTE ÖZELLİĞİ YOK)."""

        # Gerekli widget'ların var olup olmadığını kontrol edelim (kapasite hariç)
        required_widget_names = [
            "event_name_input", "event_date_edit", "event_location_input",
            "event_category_combo", "event_description_input", 
            "edit_event_id_label", "event_add_update_button", "event_list_widget"
        ]
        # hasattr ve getattr kullanarak daha güvenli kontrol
        missing_widget = None
        for name in required_widget_names:
            if not hasattr(self, name) or getattr(self, name) is None:
                missing_widget = name
                break
        if missing_widget:
            QMessageBox.critical(self, "Hata", f"Etkinlik formu elemanı '{missing_widget}' yüklenemedi (load_event_to_form_for_edit).")
            return

        # QModelIndex'ten satırdaki ilk öğeyi al
        item = self.event_list_widget.item(index.row(), 0) 
        if not item: 
            print("DEBUG: load_event_to_form_for_edit - Tıklanan satırda geçerli bir item bulunamadı.")
            return 

        # Item'ın userData'sından etkinlik ID'sini al
        event_id = item.data(Qt.ItemDataRole.UserRole) 
        if event_id is None:
            print("Uyarı: Tıklanan etkinlik item'ında saklı bir ID bulunamadı (load_event_to_form_for_edit).")
            self.clear_event_form() # Hata durumunda formu temizle
            return

        print(f"DEBUG: Düzenleme için etkinlik forma yükleniyor. ID: {event_id}")

        try:
            cursor = self.get_cursor()
            # Veritabanından etkinlik bilgilerini çekerken 'capacity' SÜTUNU YOK.
            cursor.execute("""
                SELECT name, event_date, location, category, description 
                FROM events 
                WHERE id = %s
            """, (event_id,))
            event_data = cursor.fetchone() # sqlite3.Row nesnesi veya None

        except psycopg2.Error as e_db:
            QMessageBox.warning(self, "Veritabanı Hatası", f"Etkinlik verisi alınamadı: {e_db}")
            traceback.print_exc()
            self.clear_event_form()
            return
        except Exception as e_general:
            QMessageBox.warning(self, "Beklenmedik Hata", f"Etkinlik verisi alınırken bir sorun oluştu: {e_general}")
            traceback.print_exc()
            self.clear_event_form()
            return

        if event_data: # Veri başarıyla alındıysa
            self.edit_event_id_label.setText(str(event_id)) 
            self.event_name_input.setText(event_data["name"] or "")

            # Tarihi yükle
            event_date_value = event_data["event_date"]  # Veritabanından gelen tarih değeri
            final_q_date = QDate.currentDate() # Varsayılan olarak bugünün tarihi

            if event_date_value:  # Eğer tarih değeri None veya boş değilse
                # Dosyanızın başında "import datetime" olduğundan emin olun
                if isinstance(event_date_value, datetime.date):
                    # Eğer değer Python'un datetime.date objesi ise,
                    # QDate'e doğrudan yıl, ay, gün bilgileriyle dönüştür
                    final_q_date = QDate(event_date_value.year, event_date_value.month, event_date_value.day)
                elif isinstance(event_date_value, str):
                    # Eğer değer zaten bir string (metin) ise, fromString ile parse etmeyi dene
                    parsed_q_date = QDate.fromString(event_date_value, Qt.DateFormat.ISODate)
                    if parsed_q_date.isValid():
                        final_q_date = parsed_q_date
                    # else: final_q_date zaten QDate.currentDate() olarak ayarlı,
                    # ya da isterseniz burada "Hatalı T." için bir uyarı verebilirsiniz.
                # else: Beklenmedik bir tip ise, final_q_date zaten QDate.currentDate()
            
            self.event_date_edit.setDate(final_q_date)

            self.event_location_input.setText(event_data["location"] or "")

            # Kategoriyi seç
            category_from_db = event_data["category"] or ""
            cat_index = self.event_category_combo.findText(category_from_db, Qt.MatchFlag.MatchFixedString)
            self.event_category_combo.setCurrentIndex(cat_index if cat_index >= 0 else 0) 

            self.event_description_input.setText(event_data["description"] or "")

            # --- Kapasite ile ilgili satırlar buradan tamamen kaldırıldı ---

            # Butonu "Güncelle" moduna getir
            self.event_add_update_button.setText("Etkinliği Güncelle")
            self.event_add_update_button.setIcon(QIcon.fromTheme("document-save"))
        else:
            # Etkinlik ID'si geçerli ama veritabanında bulunamadıysa
            QMessageBox.warning(self, "Bulunamadı", f"ID'si {event_id} olan etkinlik veritabanında bulunamadı.")
            self.clear_event_form()
    def add_or_update_event(self):
        """Etkinlik formundaki bilgilere göre yeni etkinlik ekler veya mevcut etkinliği günceller."""
        
        # Form widget'larının varlığını kontrol et (önlem olarak)
        # Kapasite spinbox'ı artık listede olmamalı.
        required_widget_names = [
            "event_name_input", "event_date_edit", "event_location_input",
            "event_category_combo", "event_description_input", 
            "edit_event_id_label", "event_add_update_button"
        ]
        # hasattr ile kontrol edelim, çünkü widget'lar __init__ içinde None olarak başlatılmış olabilir
        # ve init_event_form henüz çağrılmamışsa None olabilirler.
        for widget_name_str in required_widget_names:
            if not hasattr(self, widget_name_str) or getattr(self, widget_name_str) is None:
                QMessageBox.critical(self, "Hata", f"Etkinlik formu elemanı '{widget_name_str}' henüz yüklenmemiş.")
                return

        # Düzenleme modunda mıyız kontrol et (gizli label'dan ID al)
        event_id_str = self.edit_event_id_label.text()
        try:
            event_id = int(event_id_str) if event_id_str else None
        except ValueError:
            print(f"Uyarı: Geçersiz etkinlik ID'si '{event_id_str}'. Ekleme moduna geçiliyor.")
            event_id = None

        # Formdan verileri al
        name = self.event_name_input.text().strip()
        event_date_str = self.event_date_edit.date().toString(Qt.DateFormat.ISODate) # YYYY-MM-DD
        location = self.event_location_input.text().strip()
        category = self.event_category_combo.currentText()
        description = self.event_description_input.toPlainText().strip()
        
        # Kapasite ile ilgili satırlar kaldırıldı.

        # Zorunlu alan kontrolü
        if not name:
            QMessageBox.warning(self, "Eksik Bilgi", "Etkinlik adı zorunludur.")
            self.event_name_input.setFocus()
            return

        try:
            cursor = self.get_cursor()
            
            if event_id is None: # --- YENİ ETKİNLİK EKLE ---
                print(f"DEBUG: Yeni etkinlik ekleniyor: {name}")
                # capacity ve tickets_sold sütunları INSERT sorgusundan çıkarıldı.
                cursor.execute("""
                    INSERT INTO events (name, event_date, location, category, description)
                    VALUES (%s, %s, %s, %s, %s) 
                """, (name, event_date_str, location or None, category or None, description or None))
                msg = f"'{name}' etkinliği başarıyla eklendi."
            
            else: # --- MEVCUT ETKİNLİĞİ GÜNCELLE ---
                print(f"DEBUG: Etkinlik güncelleniyor ID: {event_id}, Ad: {name}")
                # capacity sütunu UPDATE sorgusundan çıkarıldı.
                cursor.execute("""
                    UPDATE events SET name=%s, event_date=%s, location=%s, category=%s, description=%s
                    WHERE id=%s
                """, (name, event_date_str, location or None, category or None, description or None, event_id))
                msg = f"'{name}' etkinliği başarıyla güncellendi."

            self.db_connection.commit() # Değişiklikleri kaydet
            QMessageBox.information(self, "Başarılı", msg)
            
            self.clear_event_form() # Formu temizle
            self.update_event_list() # Etkinlik listesini güncelle
            if hasattr(self, 'update_main_page_stats'): 
                self.update_main_page_stats()

        except psycopg2.Error as e_integrity:
            if "UNIQUE constraint failed: events.name" in str(e_integrity):
                QMessageBox.critical(self, "Hata", f"Bu isimde ('{name}') başka bir etkinlik zaten mevcut!")
                self.event_name_input.setFocus()
            else:
                QMessageBox.critical(self, "Veritabanı Bütünlük Hatası", f"İşlem sırasında benzersizlik veya kısıtlama hatası: {e_integrity}")
                traceback.print_exc()
        except psycopg2.Error as e_db:
            QMessageBox.critical(self, "Veritabanı Hatası", f"Etkinlik kaydedilirken bir veritabanı hatası oluştu: {e_db}")
            traceback.print_exc()
        except Exception as e_general:
            QMessageBox.critical(self, "Beklenmedik Hata", f"Etkinlik kaydedilirken beklenmedik bir hata oluştu: {e_general}")
            traceback.print_exc()

    # AdminPanel sınıfının içinde:

    def update_event_list(self):
        """Etkinlik listesi tablosunu veritabanından günceller."""
        if not self.event_list_widget:  # Liste widget'ı yoksa veya None ise çık
            print("DEBUG: update_event_list - self.event_list_widget bulunamadı veya None.")
            return
        
        try:
            cursor = self.get_cursor()
            # Tüm etkinlikleri tarihe göre (yeni->eski), aynı tarihtekileri ada göre sıralı al
            cursor.execute("SELECT id, name, event_date, category, location FROM events ORDER BY event_date DESC, name ASC")
            events = cursor.fetchall()

            self.event_list_widget.setRowCount(0)  # Tabloyu temizle
            self.event_list_widget.setSortingEnabled(False) # Sıralamayı geçici olarak kapat

            for row_idx, event_row in enumerate(events): # event yerine event_row kullanalım (daha net)
                self.event_list_widget.insertRow(row_idx)
                
                # Ad sütunu (ID'yi UserRole olarak sakla)
                name_item = QTableWidgetItem(event_row['name'])
                name_item.setData(Qt.ItemDataRole.UserRole, event_row['id'])
                
                # --- TARİH SÜTUNU İÇİN DÜZELTİLMİŞ KOD BAŞLIYOR ---
                event_date_value = event_row["event_date"]  # Veritabanından gelen tarih değeri
                formatted_date = "Tarihsiz"  # Varsayılan değer

                if event_date_value:  # Eğer tarih değeri None veya boş değilse
                    if isinstance(event_date_value, datetime.date):
                        # Eğer değer Python'un datetime.date objesi ise,
                        # QDate'e doğrudan yıl, ay, gün bilgileriyle dönüştür
                        q_date_obj = QDate(event_date_value.year, event_date_value.month, event_date_value.day)
                        formatted_date = q_date_obj.toString("dd.MM.yyyy")
                    elif isinstance(event_date_value, str):
                        # Eğer değer zaten bir string (metin) ise, fromString ile parse etmeyi dene
                        q_date_obj = QDate.fromString(event_date_value, Qt.DateFormat.ISODate)
                        if q_date_obj.isValid():
                            formatted_date = q_date_obj.toString("dd.MM.yyyy")
                        else:
                            formatted_date = "Hatalı T." # Veya event_date_value'yu olduğu gibi göster
                    else:
                        # Beklenmedik bir tip ise
                        formatted_date = "Bilinmeyen T. Formatı"
                
                date_item = QTableWidgetItem(formatted_date)
                # --- TARİH SÜTUNU İÇİN DÜZELTİLMİŞ KOD BİTİYOR ---
                
                # Kategori ve Yer sütunları
                cat_item = QTableWidgetItem(event_row['category'] or "-")
                loc_item = QTableWidgetItem(event_row['location'] or "-")

                # Hücreleri yerleştir
                self.event_list_widget.setItem(row_idx, 0, name_item)
                self.event_list_widget.setItem(row_idx, 1, date_item)
                self.event_list_widget.setItem(row_idx, 2, cat_item)
                self.event_list_widget.setItem(row_idx, 3, loc_item)

            self.event_list_widget.setSortingEnabled(True) # Sıralamayı tekrar aktif et
            # self.event_list_widget.resizeColumnsToContents() # İçeriğe göre boyutlandır (isteğe bağlı)

        except psycopg2.Error as e:
            print(f"Etkinlik listesi güncellenirken DB hatası: {e}")
            QMessageBox.warning(self, "Veritabanı Hatası", f"Etkinlik listesi güncellenemedi: {e}")
            traceback.print_exc() # Hatanın detayını konsola yazdır
        except Exception as e:
            print(f"Etkinlik listesi güncellenirken genel hata: {e}")
            QMessageBox.warning(self, "Hata", f"Etkinlik listesi güncellenirken beklenmedik bir hata oluştu: {e}")
            traceback.print_exc() # Hatanın detayını konsola yazdır

    def handle_event_double_click(self, item):
        """Etkinlik tablosunda bir satıra çift tıklandığında etkinlik detay sayfasını açar."""
        if not item: return
        row = item.row()
        id_item = self.event_list_widget.item(row, 0) # Ad sütunundaki item
        if id_item:
            event_id = id_item.data(Qt.ItemDataRole.UserRole) # Saklanan ID'yi al
            if event_id:
                print(f"Etkinlik çift tıklama: ID={event_id}")
                self.show_event_details_page(event_id)
            else:
                print("Uyarı: Çift tıklanan etkinlik item'ında ID bulunamadı.")

    def on_event_table_context_menu(self, pos: QPoint):
        """Etkinlik tablosunda sağ tıklama menüsünü gösterir."""
        item = self.event_list_widget.itemAt(pos)
        if not item: return

        row = item.row()
        id_item = self.event_list_widget.item(row, 0)
        if not id_item: return

        event_id = id_item.data(Qt.ItemDataRole.UserRole)
        event_name = id_item.text()
        if not event_id: return

        menu = QMenu(self)
        details_action = QAction(QIcon.fromTheme("document-properties"), "Detayları Görüntüle / Katılım", self)
        edit_action = QAction(QIcon.fromTheme("document-edit"), "Düzenle", self)
        delete_action = QAction(QIcon.fromTheme("edit-delete"), "Sil", self)

        menu.addAction(details_action)
        menu.addAction(edit_action)
        menu.addSeparator()
        menu.addAction(delete_action)

        action = menu.exec(self.event_list_widget.mapToGlobal(pos))

        if action == details_action:
            self.show_event_details_page(event_id)
        elif action == edit_action:
            # Forma yükle (tıklama olayını tekrar tetiklemiş gibi)
            index = self.event_list_widget.indexFromItem(item)
            self.load_event_to_form_for_edit(index)
            # Etkinlik formu sayfasında değilsek oraya geçmeye gerek yok, zaten oradayız.
        elif action == delete_action:
            self.delete_event(event_id, event_name)

    def delete_event(self, event_id, event_name="Bilinmeyen Etkinlik"):
        """Verilen ID'li etkinliği ve ilişkili katılım kayıtlarını siler (onay alarak)."""
        if event_id is None: return

        reply = QMessageBox.question(self, "Etkinliği Sil",
                                     f"'{event_name}' adlı etkinliği ve tüm katılım kayıtlarını silmek istediğinizden emin misiniz?\n\n"
                                     f"BU İŞLEM GERİ ALINAMAZ!",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                     QMessageBox.StandardButton.Cancel)

        if reply == QMessageBox.StandardButton.Yes:
            try:
                cursor = self.get_cursor()
                # Foreign Key ON DELETE CASCADE etkinse katılım kayıtları otomatik silinir.
                cursor.execute("DELETE FROM events WHERE id = %s", (event_id,))
                rowcount = cursor.rowcount
                self.db_connection.commit()

                if rowcount > 0:
                    QMessageBox.information(self, "Başarılı", f"'{event_name}' etkinliği başarıyla silindi.")
                    self.update_event_list() # Listeyi yenile
                    self.update_main_page_stats() # Ana sayfa istatistiklerini güncelle

                    # Eğer detay sayfası açıksa ve silinen etkinlik gösteriliyorsa, etkinlik listesine dön
                    if self.stacked_widget.currentWidget() == self.event_details_page and self.current_event_id == event_id:
                        self.show_event_form() # Etkinlik listesi ve formunun olduğu sayfaya dön

                    # Eğer formda bu etkinlik yüklü ise formu temizle
                    if self.edit_event_id_label.text() == str(event_id):
                        self.clear_event_form()
                else:
                     QMessageBox.warning(self, "Bulunamadı", f"ID'si {event_id} olan etkinlik silinemedi.")

            except psycopg2.Error as e:
                QMessageBox.critical(self, "Veritabanı Hatası", f"Etkinlik silinirken veritabanı hatası oluştu: {e}")
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Etkinlik silinirken beklenmedik bir hata oluştu: {e}")
                traceback.print_exc()

    def show_event_details_page(self, event_id):
        """Verilen ID'li etkinliğin detaylarını ve katılımcılarını gösteren sayfayı açar."""
         # Widget'lar var mı kontrol et
        required = [self.event_details_name_label, self.event_details_date_loc_label,
                    self.event_details_cat_label, self.event_details_desc_text,
                    self.participants_list_widget]
        if any(w is None for w in required):
             QMessageBox.critical(self, "Hata", "Etkinlik detay sayfası elemanları henüz yüklenmemiş.")
             return

        self.current_event_id = event_id # Mevcut etkinlik ID'sini sakla
        try:
            cursor = self.get_cursor()
            cursor.execute("SELECT name, event_date, location, category, description FROM events WHERE id = %s", (event_id,))
            event = cursor.fetchone()

            if event:
                # Etkinlik bilgilerini etiketlere yaz
                # Etkinlik bilgilerini etiketlere yaz
                self.event_details_name_label.setText(f"Etkinlik: {event['name']}")

                # --- TARİH İŞLEME KISMI BAŞLIYOR ---
                event_date_value = event["event_date"]  # Veritabanından gelen tarih değeri
                formatted_date = "Tarihsiz"  # Varsayılan değer

                if event_date_value:  # Eğer tarih değeri None veya boş değilse
                    # Dosyanızın başında "import datetime" olduğundan emin olun
                    if isinstance(event_date_value, datetime.date):
                        # Eğer değer Python'un datetime.date objesi ise,
                        # QDate'e doğrudan yıl, ay, gün bilgileriyle dönüştür
                        q_date_obj = QDate(event_date_value.year, event_date_value.month, event_date_value.day)
                        formatted_date = q_date_obj.toString("dd.MM.yyyy")
                    elif isinstance(event_date_value, str):
                        # Eğer değer zaten bir string (metin) ise, fromString ile parse etmeyi dene
                        q_date_obj = QDate.fromString(event_date_value, Qt.DateFormat.ISODate)
                        if q_date_obj.isValid():
                            formatted_date = q_date_obj.toString("dd.MM.yyyy")
                        else:
                            formatted_date = "Hatalı T." # Veya event_date_value'yu olduğu gibi göster
                    else:
                        # Beklenmedik bir tip ise
                        formatted_date = "Bilinmeyen T. Formatı"
                # --- TARİH İŞLEME KISMI BİTİYOR ---
                
                location = event['location'] or "Bilinmiyor"
                self.event_details_date_loc_label.setText(f"Tarih / Yer: {formatted_date} / {location}")
                self.event_details_cat_label.setText(f"Kategori: {event['category'] or 'Belirtilmemiş'}")
                self.event_details_desc_text.setText(event['description'] or "Açıklama yok.")

                # Katılımcıları yükle
                self.load_participants(event_id)

                # Sayfayı göster
                self.stacked_widget.setCurrentWidget(self.event_details_page)

                self.event_details_cat_label.setText(f"Kategori: {event['category'] or 'Belirtilmemiş'}")
                self.event_details_desc_text.setText(event['description'] or "Açıklama yok.")

                # Katılımcıları yükle
                self.load_participants(event_id)

                # Sayfayı göster
                self.stacked_widget.setCurrentWidget(self.event_details_page)
            else:
                QMessageBox.warning(self, "Bulunamadı", f"ID'si {event_id} olan etkinlik bulunamadı.")
                self.current_event_id = None # ID'yi sıfırla

        except psycopg2.Error as e:
            QMessageBox.critical(self, "Veritabanı Hatası", f"Etkinlik detayları yüklenirken hata: {e}")
            self.current_event_id = None
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Etkinlik detayları yüklenirken beklenmedik hata: {e}")
            self.current_event_id = None
            traceback.print_exc()

    def load_participants(self, event_id):
            """Verilen etkinlik ID'sine ait katılımcıları detay sayfasındaki listeye yükler."""
            
            # --- YENİ DETAYLI DEBUG BLOĞU BAŞLANGICI ---
            print(f"DEBUG load_participants BAŞLANGICI: Fonksiyon çağrıldı. Etkinlik ID: {event_id}")
            
            widget_obj = self.participants_list_widget
            widget_type = type(widget_obj)
            is_none = widget_obj is None
            evaluates_as_false = not widget_obj # Bu, 'if not widget_obj:' koşulunun sonucudur

            print(f"    DEBUG-Detay: self.participants_list_widget Değeri: {widget_obj}")
            print(f"    DEBUG-Detay: self.participants_list_widget Tipi: {widget_type}")
            print(f"    DEBUG-Detay: Kontrol (widget_obj is None) sonucu: {is_none}")
            print(f"    DEBUG-Detay: Kontrol (not widget_obj) sonucu: {evaluates_as_false}")
            # --- YENİ DETAYLI DEBUG BLOĞU BİTİŞİ ---

            # Şimdi asıl kontrol
            if is_none: # Eğer widget gerçekten None ise
                print("DEBUG: HATA - self.participants_list_widget GERÇEKTEN None. Fonksiyondan çıkılıyor.")
                return
            elif evaluates_as_false: # Eğer widget None değil ama 'if not widget:' yine de True oluyorsa
                print("DEBUG: UYARI - self.participants_list_widget None değil ama 'if not' koşulunda False gibi değerlendiriliyor. Bu beklenmedik bir durum!")
                # Bu durumda bile widget'ı kullanmayı deneyebiliriz, ama normalde buraya girmemeli.
                # Şimdilik yine de fonksiyondan çıkalım ki durumu analiz edebilelim.
                # Eğer bu satıra düşersek, Qt widget'larının 'truthiness' davranışı ile ilgili bir tuhaflık olabilir.
                # return # <-- Bu satırı geçici olarak yorumda bırakıp akışa devam etmesini sağlayabiliriz, ama önce logları görelim.
            else:
                print("DEBUG: self.participants_list_widget geçerli bir nesne gibi görünüyor. İşleme devam ediliyor.")

            # Eğer buraya kadar geldiysek, self.participants_list_widget dolu bir nesne olmalı.
            # Ancak bir önceki logda evaluates_as_false True ise ve return'ü yorumladıysak,
            # aşağıdaki .clear() hataya neden olabilir.
            try:
                self.participants_list_widget.clear() 
            except Exception as e_clear:
                print(f"DEBUG: HATA - self.participants_list_widget.clear() çağrılırken hata: {e_clear}")
                print(f"DEBUG: Bu hata anında self.participants_list_widget: {self.participants_list_widget}")
                return # clear başarısız olursa devam etme

            try:
                cursor = self.get_cursor()
                cursor.execute("""
                    SELECT m.id, m.name, m.department, a.timestamp
                    FROM attendance a
                    JOIN members m ON a.member_id = m.id
                    WHERE a.event_id = %s
                    ORDER BY a.timestamp ASC
                """, (event_id,))
                participants = cursor.fetchall()
                print(f"DEBUG: Veritabanından {len(participants)} katılımcı çekildi. Etkinlik ID: {event_id}")

                if participants:
                    for i, p in enumerate(participants): 
                        time_str = "Zaman?" 
                        try:
                            dt = QDateTime.fromString(p['timestamp'], Qt.DateFormat.ISODateWithMs)
                            if not dt.isValid():
                                dt = QDateTime.fromString(p['timestamp'], Qt.DateFormat.ISODate)
                            if dt.isValid():
                                time_str = dt.toString("dd.MM.yyyy HH:mm")
                            else:
                                time_str = p['timestamp'] 
                        except Exception as time_e:
                            print(f"DEBUG: Zaman formatlama hatası: {time_e} - Veri: {p['timestamp']}")
                            time_str = p['timestamp'] 

                        item_text = f"{p['name']} ({p['department'] or 'Bölüm?'} ) - {time_str}"
                        print(f"DEBUG: ({i+1}) Listeye ekleniyor: {item_text}")
                        list_item = QListWidgetItem(item_text)
                        list_item.setData(Qt.ItemDataRole.UserRole, p['id']) 
                        self.participants_list_widget.addItem(list_item)
                    print(f"DEBUG: Listeye {len(participants)} öğe eklendi.")
                else:
                    print(f"DEBUG: Etkinlik ID {event_id} için veritabanında katılımcı bulunamadı. 'Katılım yok' mesajı ekleniyor.")
                    self.participants_list_widget.addItem("Bu etkinliğe henüz katılım kaydedilmemiş.")

            except psycopg2.Error as e:
                print(f"Katılımcılar yüklenirken DB hatası: {e}")
                if self.participants_list_widget: # Hala geçerliyse hata mesajını ekle
                    self.participants_list_widget.addItem(f"Katılımcılar yüklenemedi: DB Hatası")
            except Exception as e:
                print(f"Katılımcılar yüklenirken genel hata: {e}")
                if self.participants_list_widget: # Hala geçerliyse hata mesajını ekle
                    self.participants_list_widget.addItem(f"Katılımcılar yüklenemedi: Genel Hata")
                traceback.print_exc()

    # AdminPanel sınıfının içinde:

    def show_member_profile(self, member_data):
        """Verilen üye verilerini (dict) kullanarak profil sayfasını doldurur ve gösterir."""
        if not member_data:
            return

        # Profil sayfasındaki etiketleri doldur (HTML benzeri formatlama ile)
        self.profile_name_label.setText(f"<b>Ad Soyad:</b> {member_data.get('name', '-')}")
        self.profile_uid_label.setText(f"<b>Kart UID:</b> {member_data.get('uid', '-')}")
        self.profile_role_label.setText(f"<b>Rol:</b> {member_data.get('role', 'Belirtilmemiş')}")

        # --- ÜYELİK TARİHİNİ İŞLEME KISMI (DÜZELTİLDİ) ---
        membership_date_value = member_data.get("membership_date")  # Veritabanından gelen tarih değeri
        formatted_membership_date = "Bilinmiyor"  # Varsayılan değer

        if membership_date_value:  # Eğer tarih değeri None veya boş değilse
            if isinstance(membership_date_value, datetime.date):
                # Eğer değer Python'un datetime.date objesi ise,
                # QDate'e doğrudan yıl, ay, gün bilgileriyle dönüştür
                q_date_obj = QDate(membership_date_value.year, membership_date_value.month, membership_date_value.day)
                formatted_membership_date = q_date_obj.toString("dd.MM.yyyy")
            elif isinstance(membership_date_value, str):
                # Eğer değer zaten bir string (metin) ise, fromString ile parse etmeyi dene
                q_date_obj = QDate.fromString(membership_date_value, Qt.DateFormat.ISODate)
                if q_date_obj.isValid():
                    formatted_membership_date = q_date_obj.toString("dd.MM.yyyy")
                else:
                    formatted_membership_date = "Hatalı Tarih"
            else:
                # Beklenmedik bir tip ise
                formatted_membership_date = "Bilinmeyen Tarih Formatı"
        
        self.profile_membership_date_label.setText(f"<b>Üyelik Tarihi:</b> {formatted_membership_date}")
        # --- ÜYELİK TARİHİNİ İŞLEME KISMI BİTTİ ---

        self.profile_dep_label.setText(f"<b>Bölüm:</b> {member_data.get('department', 'Belirtilmemiş')}")
        self.profile_year_label.setText(f"<b>Sınıf/Yıl:</b> {str(member_data.get('year', '-'))}") # Yıl integer olabileceği için str() eklendi
        self.profile_email_label.setText(f"<b>E-posta:</b> {member_data.get('email', '-')}")
        self.profile_phone_label.setText(f"<b>Telefon:</b> {member_data.get('phone', '-')}")
        self.profile_interests_label.setText(f"<b>İlgi Alanları:</b> {member_data.get('interests', '-')}")

        member_points = member_data.get('points', 0)
        self.profile_points_label.setText(f"<b>Puan:</b> {member_points}")
        
        # Fotoğrafı yükle
        photo_db_filename = member_data.get('photo_path')
        self.load_member_photo_to_label(photo_db_filename, self.profile_photo_label)

        # Katıldığı etkinlikleri yükle
        member_id_for_lists = member_data.get('id')
        if member_id_for_lists is not None:
            self.load_member_attendance(member_id_for_lists)
            
            # Puan geçmişini yükle
            if hasattr(self, 'load_member_points_log'):
                self.load_member_points_log(member_id_for_lists)
        else:
            # Eğer ID yoksa listeleri temizle veya "Veri yok" mesajı göster
            if hasattr(self, 'profile_attendance_list') and self.profile_attendance_list:
                self.profile_attendance_list.clear()
                self.profile_attendance_list.addItem("Üye ID bulunamadığı için katılım yüklenemedi.")
            if hasattr(self, 'profile_points_log_table') and self.profile_points_log_table:
                self.profile_points_log_table.setRowCount(0)
                # İsteğe bağlı olarak puan geçmişi tablosuna da bir mesaj eklenebilir.

        # Profil sayfasını göster
        self.stacked_widget.setCurrentWidget(self.member_profile_page)

    def load_member_attendance(self, member_id):
        """Verilen üyenin katıldığı etkinlikleri profil sayfasındaki listeye yükler."""
        if member_id is None or not self.profile_attendance_list: return
        self.profile_attendance_list.clear()
        try:
            cursor = self.get_cursor()
            cursor.execute("""
                SELECT e.id, e.name, e.event_date, a.timestamp
                FROM attendance a
                JOIN events e ON a.event_id = e.id
                WHERE a.member_id = %s
                ORDER BY e.event_date DESC, a.timestamp DESC -- En yeni etkinlik/katılım üste
            """, (member_id,))
            attendances = cursor.fetchall()

            if attendances:
                for att in attendances:
                    date_str = att["event_date"] or ""
                    formatted_date = QDate.fromString(date_str, Qt.DateFormat.ISODate).toString("dd.MM.yyyy") if date_str else "Tarihsiz"
                    item_text = f"{att['name']} ({formatted_date})"
                    list_item = QListWidgetItem(item_text)
                    list_item.setData(Qt.ItemDataRole.UserRole, att['id']) # Etkinlik ID'sini sakla
                    self.profile_attendance_list.addItem(list_item)
            else:
                self.profile_attendance_list.addItem("Bu üyenin katıldığı etkinlik kaydı bulunmuyor.")

        except psycopg2.Error as e:
            print(f"Üye katılım geçmişi yüklenirken DB hatası: {e}")
            self.profile_attendance_list.addItem(f"Katılım geçmişi yüklenemedi: DB Hatası")
        except Exception as e:
            print(f"Üye katılım geçmişi yüklenirken genel hata: {e}")
            self.profile_attendance_list.addItem(f"Katılım geçmişi yüklenemedi: Genel Hata")
            traceback.print_exc()

    # --- Kalan Fonksiyonlar (Sonraki Bölümde) ---
    # logout, browse_*, save_settings_from_ui, UID check, data import/export, backup/restore, demo data...
    # AdminPanel sınıfının devamı... (Önceki bölümlerdeki kodun devamıdır)

    # --- Ayarlar Yönetimi Fonksiyonları ---

    def browse_logo_for_settings(self):
        """Ayarlar sayfasındaki logo için resim dosyası seçme."""
        if not self.settings_logo_path_input: return
        file_path, _ = QFileDialog.getOpenFileName(self, "Logo Seç", "", "Resim Dosyaları (*.png *.jpg *.jpeg *.bmp)")
        if file_path:
            self.settings_logo_path_input.setText(file_path)

    def browse_pdf_font_for_settings(self):
        """Ayarlar sayfasındaki PDF fontu için .ttf dosyası seçme."""
        if not self.settings_pdf_font_input: return
        file_path, _ = QFileDialog.getOpenFileName(self, "PDF Font Seç (.ttf)", "", "TrueType Font (*.ttf)")
        if file_path:
            self.settings_pdf_font_input.setText(file_path)

    def browse_backup_path(self):
        """Ayarlar sayfasındaki yedekleme konumu için klasör seçme."""
        if not self.settings_backup_path_input: return
        dir_path = QFileDialog.getExistingDirectory(self, "Yedekleme Klasörü Seç", self.settings_backup_path_input.text() or "")
        if dir_path:
            self.settings_backup_path_input.setText(dir_path)

    def browse_export_path(self):
        """Ayarlar sayfasındaki dışa aktarma konumu için klasör seçme."""
        if not self.settings_export_path_input: return
        dir_path = QFileDialog.getExistingDirectory(self, "Dışa Aktarma Klasörü Seç", self.settings_export_path_input.text() or "")
        if dir_path:
            self.settings_export_path_input.setText(dir_path)

    def save_settings_from_ui(self):
        """Ayarlar sayfasındaki değerleri alır ve JSON dosyasına kaydeder."""
        # Gerekli widget'lar var mı kontrol et
        required = [self.settings_logo_path_input, self.settings_pdf_font_input, self.settings_backup_path_input,
                    self.settings_export_path_input, self.settings_default_role_combo,
                    self.settings_upcoming_limit_spinbox, self.settings_theme_combo]
        if any(w is None for w in required):
             QMessageBox.critical(self, "Hata", "Ayarlar sayfası elemanları henüz yüklenmemiş.")
             return

        # Mevcut ayarları temel alarak yeni ayar sözlüğü oluştur
        current_settings = load_settings() # Önce diskten en güncelini oku
        # UI elemanlarındaki değerleri al ve güncelle
        current_settings['logo_path'] = self.settings_logo_path_input.text().strip()
        current_settings['pdf_font_path'] = self.settings_pdf_font_input.text().strip()
        current_settings['default_backup_path'] = self.settings_backup_path_input.text().strip()
        current_settings['default_export_path'] = self.settings_export_path_input.text().strip()
        current_settings['default_member_role'] = self.settings_default_role_combo.currentText()
        current_settings['upcoming_events_limit'] = self.settings_upcoming_limit_spinbox.value()
        selected_theme_text = self.settings_theme_combo.currentText()
        current_settings['theme'] = "dark" if selected_theme_text == "Koyu Tema" else "light"

        # Ayarları kaydetmeyi dene (global save_settings fonksiyonu ile)
        if save_settings(current_settings):
            self.settings = current_settings # AdminPanel'in kendi ayarlarını güncelle
            QMessageBox.information(self, "Başarılı", "Ayarlar başarıyla kaydedildi.\nBazı değişikliklerin (tema gibi) tam etkili olması için yeniden başlatma gerekebilir.")
            # Değişiklikleri anında uygula (tema, logo, istatistik limiti vb.)
            self.apply_style()
            self.update_main_page_logo()
            # Login penceresinin ayarlarını ve görünümünü de güncelle (varsa)
            if self.login_window:
                self.login_window.settings = current_settings
                self.login_window.apply_login_style(self.settings.get("theme", "light"))
                self.login_window.load_logo()
            self.update_main_page_stats() # Limit değişmiş olabilir, istatistikleri yenile
        else:
            # Kaydetme başarısız olduysa (save_settings içinde zaten mesaj gösterilmiş olmalı)
            # QMessageBox.warning(self, "Hata", "Ayarlar kaydedilirken bir sorun oluştu.") # Tekrara gerek yok
            pass

    def show_settings_page(self): # Önceki bölümde eksik kalan implementasyon
        """Ayarlar sayfasını gösterir ve mevcut ayarları UI elemanlarına yükler."""
        # Gerekli widget'lar var mı kontrol et (init_settings_page çağrıldıktan sonra çalışmalı)
        required = [self.settings_logo_path_input, self.settings_pdf_font_input, self.settings_backup_path_input,
                    self.settings_export_path_input, self.settings_default_role_combo,
                    self.settings_upcoming_limit_spinbox, self.settings_theme_combo]
        if any(w is None for w in required):
             QMessageBox.critical(self, "Hata", "Ayarlar sayfası elemanları henüz yüklenmemiş.")
             # Belki init_settings_page'i burada çağırmak bir çözüm olabilir ama __init__ içinde çağrılması daha doğru.
             # self.init_settings_page() # Eğer __init__ içinde çağrılmadıysa diye? Riskli.
             return

        self.settings = load_settings() # En güncel ayarları yükle

        # Ayarları ilgili inputlara/widget'lara yükle
        self.settings_logo_path_input.setText(self.settings.get('logo_path',''))
        self.settings_pdf_font_input.setText(self.settings.get('pdf_font_path', DEFAULT_FONT_PATH))
        self.settings_backup_path_input.setText(self.settings.get('default_backup_path',''))
        self.settings_export_path_input.setText(self.settings.get('default_export_path',''))

        # ComboBox için: Kayıtlı metni bul ve seç
        role_text = self.settings.get('default_member_role','Aktif Üye')
        role_index = self.settings_default_role_combo.findText(role_text)
        self.settings_default_role_combo.setCurrentIndex(role_index if role_index >=0 else 0) # Bulamazsa ilkini seç

        # SpinBox için: Değeri ayarla
        self.settings_upcoming_limit_spinbox.setValue(self.settings.get('upcoming_events_limit',5))

        # Tema ComboBox için:
        theme_text = "Açık Tema" if self.settings.get('theme','light')=='light' else "Koyu Tema"
        theme_index = self.settings_theme_combo.findText(theme_text)
        self.settings_theme_combo.setCurrentIndex(theme_index if theme_index >=0 else 0) # Bulamazsa ilkini seç

        # Ayarlar sayfasını göster
        self.stacked_widget.setCurrentWidget(self.settings_page)


    # --- UID Kontrol ve Katılım Kaydı ---

    def show_uid_check_dialog(self):
        """Katılım kaydı için UID (kart) okutma diyalogunu gösterir."""
        if self.current_event_id is None:
            QMessageBox.warning(self, "Etkinlik Seçilmedi", "Önce katılım alınacak etkinliğin detay sayfasına girmelisiniz.")
            return

        # Eğer zaten açıksa tekrar açma, öne getir
        if self.uid_check_dialog and self.uid_check_dialog.isVisible():
            self.uid_check_dialog.activateWindow()
            self.uid_check_dialog.raise_()
            return

        # Yeni diyalog oluştur
        self.uid_check_dialog = QDialog(self) # Parent olarak AdminPanel
        self.uid_check_dialog.setWindowTitle("Kart Okutma / Katılım Kaydı")
        self.uid_check_dialog.setMinimumWidth(350)
        # Kapatıldığında referansı temizle (tekrar açılabilmesi için)
        self.uid_check_dialog.finished.connect(lambda: setattr(self, 'uid_check_dialog', None))

        layout = QVBoxLayout(self.uid_check_dialog)

        # Etkinlik adını göster
        event_name = "Bilinmiyor"
        try:
             cursor=self.get_cursor();
             cursor.execute("SELECT name FROM events WHERE id=%s", (self.current_event_id,))
             result = cursor.fetchone()
             if result: event_name = result['name'];
        except Exception as e: print(f"Etkinlik adı alınırken hata: {e}")
        layout.addWidget(QLabel(f"<b>Etkinlik:</b> {event_name}"))

        layout.addWidget(QLabel("Lütfen üye kartını okutun veya UID girin:"))
        # UID giriş alanı (kendi sınıf değişkeni yapmaya gerek yok, diyalog içinde kalabilir)
        uid_input = QLineEdit(self.uid_check_dialog) # Parent olarak diyalog
        uid_input.setPlaceholderText("10 Haneli UID...")
        uid_input.setMaxLength(10)
        layout.addWidget(uid_input)

        # Durum etiketi (kendi sınıf değişkeni yapmaya gerek yok)
        status_label = QLabel("<i>Kart bekleniyor...</i>", self.uid_check_dialog)
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_label.setWordWrap(True) # Uzun mesajlar için kelime kaydırma
        layout.addWidget(status_label)

        # Otomatik kontrol için sinyal (opsiyonel, 10 karaktere ulaşınca)
        # uid_input.textChanged.connect(lambda text: self.auto_check_uid_dialog(text, uid_input, status_label))

        # Manuel kontrol/kaydet butonu
        check_button = QPushButton("Kontrol Et / Kaydet")
        check_button.clicked.connect(lambda: self.check_uid_dialog(uid_input, status_label))
        # Enter tuşu ile de kontrol et
        uid_input.returnPressed.connect(check_button.click)
        # Otomatik kontrol için sinyal (10 karaktere ulaşınca)
    # Lambda içindeki current_input ve current_label, lambda oluşturulduğu andaki
    # uid_input ve status_label değişkenlerinin o anki değerlerini yakalar. Bu,
    # diyalogun her açılışında doğru referanslarla çalışmasını sağlar.
        uid_input.textChanged.connect(
            lambda text, input_field=uid_input, label_field=status_label: \
            self.auto_check_uid_dialog(text, input_field, label_field)
        )
        layout.addWidget(check_button)

        close_button = QPushButton("Kapat")
        close_button.clicked.connect(self.uid_check_dialog.close)
        layout.addWidget(close_button)

        self.uid_check_dialog.show()
        uid_input.setFocus() # Diyalog açılınca UID alanına odaklan

    def auto_check_uid_dialog(self, text, input_field, status_label):
        """(Opsiyonel) UID girişi 10 haneye ulaşınca otomatik kontrol eder."""
        if len(text) == 10: # UID uzunluğu 10 ise
            self.check_uid_dialog(input_field, status_label)

    def check_uid_dialog(self, input_field, status_label):
            uid = input_field.text().strip()
            if not uid:
                status_label.setText("<font color='orange'>Lütfen UID girin veya kart okutun.</font>")
                return
            if self.current_event_id is None:
                status_label.setText("<font color='red'>Hata: Geçerli bir etkinlik seçilmemiş.</font>")
                return

            try:
                cursor = self.get_cursor()
                cursor.execute("SELECT id, name FROM members WHERE uid = %s", (uid,))
                member = cursor.fetchone()

                if member:
                    member_id = member['id']
                    member_name = member['name']
                    if self.record_attendance(member_id, self.current_event_id, status_label):
                        print(f"DEBUG: record_attendance başarılı. Üye ID: {member_id}, Etkinlik ID: {self.current_event_id}")
                        # input_field.clear() # İsterseniz bu satırı aktif edip bir alt satırı yorum yapabilirsiniz.
                        input_field.selectAll() # Yeni giriş için alanı seçili bırakmak daha iyi olabilir
                        input_field.setFocus() 
                        self.load_participants(self.current_event_id) 
                    else:
                        print(f"DEBUG: record_attendance false döndü. Üye ID: {member_id}, Etkinlik ID: {self.current_event_id}")
                        input_field.selectAll() # Hatalı girişi seçili bırak
                        input_field.setFocus()
                else:
                    status_label.setText(f"<font color='red'><b>Hata:</b> Bu UID ({uid}) ile kayıtlı üye bulunamadı.</font>")
                    input_field.selectAll()
                    input_field.setFocus()

            except psycopg2.Error as e:
                status_label.setText(f"<font color='red'><b>Veritabanı Hatası:</b> {e}</font>")
                print(f"UID kontrol DB hatası: {e}")
            except Exception as e:
                status_label.setText(f"<font color='red'><b>Beklenmedik Hata:</b> {e}</font>")
                print(f"UID kontrol genel hatası: {e}")
                traceback.print_exc()

# AdminPanel sınıfının içinde:
    # AdminPanel sınıfının içinde:
    def record_attendance(self, member_id, event_id, status_label_ref):
        try:
            cursor = self.get_cursor()
            timestamp = QDateTime.currentDateTime().toString(Qt.DateFormat.ISODate)

            # --- DEĞİŞİKLİK 1: Tüm işlemler tek bir transaction (işlem) olarak ele alınacak ---
            # Bu, ya tüm sorguların başarılı olup COMMIT edileceği ya da herhangi bir hata durumunda
            # tümünün ROLLBACK edileceği anlamına gelir.

            # 1. Katılımı kaydet (HENÜZ COMMIT ETME)
            cursor.execute("INSERT INTO attendance (member_id, event_id, timestamp) VALUES (%s, %s, %s)",
                        (member_id, event_id, timestamp))
            print(f"DEBUG: Katılım (attendance) INSERT sorgusu çalıştırıldı. Üye ID: {member_id}, Etkinlik ID: {event_id}")

            # 2. Puan eklemeyi ve loglamayı dene (HENÜZ COMMIT ETME)
            points_awarded_successfully = False # Puanın başarılı bir şekilde eklendiğini takip etmek için
            points_to_award = ATTENDANCE_POINTS # Sabit değeriniz (örn: 10)

            if points_to_award > 0: # Sadece puan verilecekse (ATTENDANCE_POINTS > 0 ise) işlemleri yap
                # Puan logu için etkinlik adını alalım
                cursor.execute("SELECT name FROM events WHERE id = %s", (event_id,))
                event_row = cursor.fetchone()
                # Etkinlik bulunamazsa veya silinmişse bile hata vermemesi için kontrol
                event_name = event_row['name'] if event_row and event_row['name'] else f"Etkinlik ID:{event_id}"
                reason_text = f"Etkinlik Katılımı: {event_name}"
                log_timestamp = QDateTime.currentDateTime().toString(Qt.DateFormat.ISODate)

                # Üyenin puanını güncelle
                cursor.execute("UPDATE members SET points = points + %s WHERE id = %s",
                            (points_to_award, member_id))
                print(f"DEBUG: Üye puanı UPDATE sorgusu çalıştırıldı. Üye ID: {member_id}, Puan: +{points_to_award}")

                # Puan işlemini logla
                cursor.execute("""
                    INSERT INTO points_log
                    (member_id, points_earned, reason, related_event_id, log_timestamp)
                    VALUES (%s, %s, %s, %s, %s)
                """, (member_id, points_to_award, reason_text, event_id, log_timestamp))
                print(f"DEBUG: Puan log INSERT sorgusu çalıştırıldı. Üye ID: {member_id}")
                points_awarded_successfully = True
            else: # Eğer ATTENDANCE_POINTS <= 0 ise, puanlama kısmı atlanır ama işlem "başarılı" sayılır.
                points_awarded_successfully = True # Puan verilmedi ama puanlama adımı "sorunsuz" geçti.

            # --- DEĞİŞİKLİK 2: TEK COMMIT ---
            # Tüm veritabanı sorguları (INSERT attendance, UPDATE members, INSERT points_log)
            # bu noktaya kadar hatasız çalıştıysa, şimdi tüm değişiklikleri veritabanına kalıcı yap.
            self.db_connection.commit()
            print(f"DEBUG: Tüm katılım ve puan işlemleri başarıyla COMMIT edildi. Üye ID: {member_id}, Etkinlik ID: {event_id}")

            # Başarı mesajını ayarla
            # Üye adını almak için yeni bir sorgu yapmaya gerek yok, mevcut cursor hala kullanılabilir.
            # Ancak commit sonrası cursor'un durumu hakkında emin değilseniz veya garanti olsun isterseniz,
            # cursor'u kapatıp yeniden açarak sorgu yapabilirsiniz. Şimdilik mevcut cursor ile devam edelim.
            cursor.execute("SELECT name FROM members WHERE id=%s", (member_id,))
            mem_name_row = cursor.fetchone()
            mem_name = mem_name_row['name'] if mem_name_row else 'Bilinmeyen Üye'

            success_message = f"<font color='green'><b>Başarılı:</b> '{mem_name}' katılımı kaydedildi ({QDateTime.currentDateTime().toString('HH:mm:ss')}).</font>"
            if points_to_award > 0 and points_awarded_successfully:
                success_message += f"<br><font color='blue'><b>+{points_to_award} puan</b> kazanıldı!</font>"
            # Puan ekleme başarısızsa (yukarıdaki try-except puan bloğunda yakalanıp rollback yapılmış ve False dönülmüş olmalıydı)
            # Bu senaryo artık buraya ulaşmamalı. Eğer puanlama kısmında bir sorun olursa, tüm işlem geri alınacak.

            status_label_ref.setText(success_message)

            # Liderlik tablosunu ve diğer UI elemanlarını güncelle
            if hasattr(self, 'update_leaderboard'):
                self.update_leaderboard()
            # check_uid_dialog içindeki self.load_participants(self.current_event_id) zaten katılımcı listesini güncelleyecektir.

            return True # Tüm işlem başarılı

        # --- DEĞİŞİKLİK 3: HATA YÖNETİMİNDE ROLLBACK ---
        except psycopg2.IntegrityError as e_integrity:
            # Bu blok, genellikle UNIQUE kısıtlaması ihlali (örn: aynı üye aynı etkinliğe tekrar katılamaz)
            # veya FOREIGN KEY kısıtlaması ihlali (örn: var olmayan bir üye ID'si) gibi durumlarda çalışır.
            print(f"DEBUG record_attendance: psycopg2.IntegrityError yakalandı: {str(e_integrity)}")
            # ÖNEMLİ: İşlemde bir hata oluştu, bu yüzden yapılan tüm değişiklikleri geri al.
            if self.db_connection and not self.db_connection.closed:
                self.db_connection.rollback()
                print(f"DEBUG record_attendance: IntegrityError sonrası ROLLBACK yapıldı.")

            # PostgreSQL'de unique constraint hatası (örn: attendance_member_id_event_id_key)
            # "duplicate key value violates unique constraint" mesajını içerir.
            error_str_lower = str(e_integrity).lower()
            if "attendance_member_id_event_id_key" in error_str_lower or \
               ("duplicate key value violates unique constraint" in error_str_lower and "attendance" in error_str_lower):
                member_name_for_msg = 'Bu üye'
                try:
                    # Hata sonrası cursor'un durumu belirsiz olabilir, bu yüzden yeni bir cursor ile üye adını almayı deneyebiliriz.
                    # Ancak bu, bağlantının hala iyi durumda olmasına bağlı. Genellikle rollback sonrası temizlenir.
                    # Emin olmak için, eğer cursor'u tekrar kullanacaksak, rollback'ten sonra yeni bir cursor almalıyız.
                    # Ya da, bu blok içinde yeni bir cursor alıp, onunla sorgu yapıp, sonra onu kapatabiliriz.
                    # Şimdilik basit tutalım ve mevcut cursor'u (ya da yeni alınmış bir cursor'u) kullanmaya çalışalım.
                    # Daha güvenli bir yol, bu blok içinde ayrı bir cursor açmaktır.
                    name_cursor = self.db_connection.cursor(cursor_factory=DictCursor)
                    name_cursor.execute("SELECT name FROM members WHERE id=%s", (member_id,))
                    mem_name_row = name_cursor.fetchone()
                    if mem_name_row: member_name_for_msg = mem_name_row['name']
                    name_cursor.close() # Aldığımız cursor'u kapatalım.
                except Exception as name_exc:
                    print(f"DEBUG: Katılım tekrarı mesajı için üye adı alınırken hata: {name_exc}")
                status_label_ref.setText(f"<font color='blue'>'{member_name_for_msg}' bu etkinliğe zaten katılmış.</font>")
                print(f"Üye {member_id} zaten etkinlik {event_id}'ye katılmış (IntegrityError nedeniyle tespit edildi).")
            else: # Başka bir IntegrityError
                status_label_ref.setText(f"<font color='red'><b>Veritabanı Kısıtlama Hatası:</b> Veri kaydedilemedi. ({e_integrity.pgcode})</font>")
                print(f"Katılım kaydedilirken başka bir IntegrityError: {e_integrity}")
                traceback.print_exc() # Detaylı hata logu için
            return False # İşlem başarısız

        except psycopg2.Error as e_db_main: # Diğer tüm psycopg2 (veritabanı) hataları
            print(f"DEBUG record_attendance: psycopg2.Error (e_db_main) yakalandı: {str(e_db_main)}")
            if self.db_connection and not self.db_connection.closed:
                self.db_connection.rollback()
                print(f"DEBUG record_attendance: e_db_main sonrası ROLLBACK yapıldı.")
            status_label_ref.setText(f"<font color='red'><b>Veritabanı Hatası:</b> İşlem yapılamadı. ({e_db_main.pgcode})</font>")
            print(f"Katılım kaydedilirken genel veritabanı hatası: {e_db_main}")
            traceback.print_exc()
            return False # İşlem başarısız

        except Exception as e_gen_main: # Diğer tüm beklenmedik Python hataları
            print(f"DEBUG record_attendance: Genel Exception (e_gen_main) yakalandı: {str(e_gen_main)}")
            if self.db_connection and not self.db_connection.closed:
                self.db_connection.rollback()
                print(f"DEBUG record_attendance: e_gen_main sonrası ROLLBACK yapıldı.")
            status_label_ref.setText(f"<font color='red'><b>Beklenmedik Bir Hata Oluştu:</b> Lütfen tekrar deneyin.</font>")
            print(f"Katılım kaydedilirken beklenmedik genel hata: {e_gen_main}")
            traceback.print_exc()
            return False # İşlem başarısız

    


    def export_member_data(self):
        """Tüm üyelerin detaylı bilgilerini JSON formatında dışa aktarır."""
        default_path = self.settings.get('default_export_path', '')
        timestamp = QDateTime.currentDateTime().toString("yyyyMMdd")
        default_filename = os.path.join(default_path, f"uye_verileri_{timestamp}.json")

        save_path, _ = QFileDialog.getSaveFileName(self, "Tüm Üye Verisini Dışa Aktar (JSON)", default_filename, "JSON Dosyası (*.json)")

        if save_path:
            try:
                cursor = self.get_cursor()
                cursor.execute("SELECT * FROM members ORDER BY name ASC")
                members_raw = cursor.fetchall() # sqlite3.Row listesi
                # sqlite3.Row nesnelerini dict listesine çevir
                member_list = [dict(row) for row in members_raw]

                with open(save_path, 'w', encoding='utf-8') as f:
                    json.dump(member_list, f, ensure_ascii=False, indent=4) # Güzel formatlı JSON

                QMessageBox.information(self, "Dışa Aktarma Başarılı", f"Tüm üye verileri ({len(member_list)} üye) başarıyla '{os.path.basename(save_path)}' dosyasına aktarıldı.")
            except psycopg2.Error as e:
                QMessageBox.critical(self, "Veritabanı Hatası", f"Üye verileri alınırken hata oluştu: {e}")
            except IOError as e:
                 QMessageBox.critical(self, "Dosya Hatası", f"JSON dosyası yazılırken hata oluştu: {e}")
            except Exception as e:
                QMessageBox.critical(self, "Dışa Aktarma Hatası", f"Üye verileri (JSON) dışa aktarılırken beklenmedik hata oluştu: {e}")
                traceback.print_exc()


    def logout(self):
        """Oturumu kapatır ve login ekranına döner."""
        reply = QMessageBox.question(self,
                                    "Çıkış Yap",
                                    "Oturumu kapatmak istediğinizden emin misiniz?",
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                    QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.Yes:
            print("DEBUG: Çıkış yapılıyor...");
            self.hide() # Admin panelini gizle

            # Veritabanı bağlantısını kapat (PostgreSQL için de geçerli)
            if self.db_connection and self.db_connection.closed == 0: # Bağlantı varsa ve açıksa
                try:
                    self.db_connection.close()
                    self.db_connection = None # Referansı temizle
                    print("Veritabanı bağlantısı çıkışta kapatıldı.")
                except psycopg2.Error as e_db_close: # psycopg2 hatası
                    print(f"Veritabanı kapatılırken hata oluştu: {e_db_close}")
                except Exception as e_close:
                    print(f"Veritabanı kapatılırken genel hata: {e_close}")

            # Login penceresindeki alanları temizle ve göster
            if self.login_window: # login_window referansı __init__ içinde atanmış olmalı
                try:
                    self.login_window.clear_login_fields()
                    self.login_window.show()
                    print("DEBUG: Login penceresi tekrar gösterildi.")
                except Exception as e_show_login:
                    print(f"Hata: Login penceresi gösterilemedi: {e_show_login}")
                    QApplication.instance().quit() # Login gösterilemezse uygulamayı kapat
            else:
                print("HATA: Login penceresi referansı bulunamadı! Uygulama kapatılıyor.")
                QApplication.instance().quit()


# === AdminPanel Sınıfının Sonu ===

    
    def export_emails(self):
        """Tüm üyelerin adını ve e-posta adreslerini CSV formatında dışa aktarır."""
        default_path = self.settings.get('default_export_path', '')
        timestamp = QDateTime.currentDateTime().toString("yyyyMMdd")
        default_filename = os.path.join(default_path, f"eposta_listesi_{timestamp}.csv")

        save_path, _ = QFileDialog.getSaveFileName(self, "E-posta Listesini Dışa Aktar (CSV)", default_filename, "CSV Dosyası (*.csv)")

        if save_path:
            try:
                cursor = self.get_cursor()
                # E-postası boş olmayanları al
                cursor.execute("SELECT name, email FROM members WHERE email IS NOT NULL AND email != '' ORDER BY name ASC")
                emails = cursor.fetchall() # sqlite3.Row listesi

                with open(save_path, 'w', newline='', encoding='utf-8-sig') as f: # utf-8-sig Excel uyumu için önemli
                    writer = csv.writer(f)
                    writer.writerow(['Ad Soyad', 'E-posta']) # Başlık satırı
                    for member in emails:
                        writer.writerow([member['name'], member['email']])

                QMessageBox.information(self, "Dışa Aktarma Başarılı", f"E-posta listesi ({len(emails)} adres) başarıyla '{os.path.basename(save_path)}' dosyasına aktarıldı.")
            except psycopg2.Error as e:
                QMessageBox.critical(self, "Veritabanı Hatası", f"E-posta verileri alınırken hata oluştu: {e}")
            except IOError as e:
                 QMessageBox.critical(self, "Dosya Hatası", f"CSV dosyası yazılırken hata oluştu: {e}")
            except Exception as e:
                QMessageBox.critical(self, "Dışa Aktarma Hatası", f"E-posta listesi (CSV) dışa aktarılırken beklenmedik hata oluştu: {e}")
                traceback.print_exc()


    def export_event_participants(self):
        """Mevcut etkinlik detay sayfasındaki katılımcı listesini CSV olarak dışa aktarır."""
        if self.current_event_id is None:
            QMessageBox.warning(self, "Etkinlik Seçilmedi", "Önce katılımcılarını dışa aktarmak istediğiniz etkinliğin detay sayfasına girmelisiniz.")
            return

        # Etkinlik adını al (dosya adı için)
        event_name = "bilinmeyen_etkinlik"
        try:
             cursor=self.get_cursor();
             cursor.execute("SELECT name FROM events WHERE id=%s", (self.current_event_id,))
             result = cursor.fetchone()
             if result:
                  # Dosya adı için geçersiz karakterleri temizle
                  event_name_raw = result['name']
                  event_name = "".join(c if c.isalnum() or c in (' ', '-') else "_" for c in event_name_raw).rstrip()
        except Exception as e: print(f"Etkinlik adı alınamadı: {e}")

        default_path = self.settings.get('default_export_path', '')
        timestamp = QDateTime.currentDateTime().toString("yyyyMMdd")
        default_filename = os.path.join(default_path, f"{event_name}_katilimcilar_{timestamp}.csv")

        save_path, _ = QFileDialog.getSaveFileName(self, "Katılımcı Listesini Dışa Aktar (CSV)", default_filename, "CSV Dosyası (*.csv)")

        if save_path:
            try:
                cursor = self.get_cursor()
                cursor.execute("""
                    SELECT m.name, m.department, m.email, m.year, m.role, a.timestamp
                    FROM attendance a
                    JOIN members m ON a.member_id = m.id
                    WHERE a.event_id = %s
                    ORDER BY a.timestamp ASC
                """, (self.current_event_id,))
                participants = cursor.fetchall() # sqlite3.Row listesi

                with open(save_path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    # Başlık satırı
                    writer.writerow(['Ad Soyad', 'Bölüm', 'E-posta', 'Sınıf/Yıl', 'Rol', 'Katılım Zamanı'])
                    for p in participants:
                        # Zaman damgasını formatla
                        time_str = "Zaman?"
                        try:
                             dt = QDateTime.fromString(p['timestamp'], Qt.DateFormat.ISODateWithMs)
                             if not dt.isValid(): dt = QDateTime.fromString(p['timestamp'], Qt.DateFormat.ISODate)
                             if dt.isValid(): time_str = dt.toString("dd.MM.yyyy HH:mm:ss")
                             else: time_str = p['timestamp']
                        except: time_str = p['timestamp']

                        writer.writerow([
                            p['name'],
                            p['department'] or '-',
                            p['email'] or '-',
                            p['year'] if p['year'] is not None else '-',
                            p['role'] or '-',
                            time_str
                        ])
                QMessageBox.information(self, "Dışa Aktarma Başarılı", f"Katılımcı listesi ({len(participants)} kişi) başarıyla '{os.path.basename(save_path)}' dosyasına aktarıldı.")
            except psycopg2.Error as e:
                QMessageBox.critical(self, "Veritabanı Hatası", f"Katılımcı verileri alınırken hata oluştu: {e}")
            except IOError as e:
                 QMessageBox.critical(self, "Dosya Hatası", f"CSV dosyası yazılırken hata oluştu: {e}")
            except Exception as e:
                QMessageBox.critical(self, "Dışa Aktarma Hatası", f"Katılımcı listesi (CSV) dışa aktarılırken beklenmedik hata oluştu: {e}")
                traceback.print_exc()


# AdminPanel sınıfındaki export_event_participants_pdf metodunun GÜNCELLENMİŞ HALİ:
# AdminPanel sınıfının içinde:

    def export_event_participants_pdf(self):
        # FPDF_AVAILABLE kontrolü dosyanızın başında global olarak tanımlı olmalı
        # try:
        #     from fpdf import FPDF, FPDFException
        #     FPDF_AVAILABLE = True
        # except ImportError:
        #     FPDF_AVAILABLE = False
        #     FPDF, FPDFException = object, Exception # Sahte sınıflar

        if not FPDF_AVAILABLE: 
            QMessageBox.critical(self, "Kütüphane Eksik", "PDF oluşturmak için 'fpdf2' kütüphanesi kurulu olmalıdır.\nKurmak için: pip install fpdf2")
            return
        if self.current_event_id is None:
            QMessageBox.warning(self, "Etkinlik Seçilmedi", "Önce katılımcılarını PDF'e aktarmak istediğiniz etkinliğin detay sayfasına girmelisiniz.")
            return

        event_info = None
        event_name_original = 'Bilinmeyen Etkinlik'
        # event_date_str_original yerine event_date_value kullanacağız
        event_date_value = None # Başlangıç değeri
        participants_rows = []

        try:
            cursor = self.get_cursor()
            # Etkinlik bilgilerini al
            cursor.execute("SELECT name, event_date FROM events WHERE id=%s", (self.current_event_id,))
            event_info = cursor.fetchone()

            if event_info:
                event_name_original = event_info['name'] if event_info['name'] is not None else 'İsimsiz Etkinlik'
                event_date_value = event_info['event_date'] # Bu datetime.date objesi olabilir
            
            # Katılımcı verilerini çek (timestamp PostgreSQL'den datetime.datetime olarak gelebilir)
            cursor.execute("""
                SELECT m.name, m.department, m.email, a.timestamp
                FROM attendance a
                JOIN members m ON a.member_id = m.id
                WHERE a.event_id = %s
                ORDER BY a.timestamp ASC
            """, (self.current_event_id,))
            participants_rows = cursor.fetchall()

        except psycopg2.Error as e_db_fetch:
            QMessageBox.critical(self, "Veritabanı Hatası", f"PDF için veri alınırken hata oluştu: {e_db_fetch}")
            traceback.print_exc()
            return
        except Exception as e_fetch:
            QMessageBox.critical(self, "Genel Hata", f"PDF için veri hazırlanırken beklenmedik bir hata oluştu: {e_fetch}")
            traceback.print_exc()
            return

        # --- ETKİNLİK TARİHİNİ FORMATLAMA (DÜZELTİLDİ) ---
        formatted_event_date_original = "Tarihsiz" # Varsayılan değer
        if event_date_value:
            if isinstance(event_date_value, datetime.date):
                q_date_obj = QDate(event_date_value.year, event_date_value.month, event_date_value.day)
                formatted_event_date_original = q_date_obj.toString("dd.MM.yyyy")
            elif isinstance(event_date_value, str):
                q_date_obj = QDate.fromString(event_date_value, Qt.DateFormat.ISODate)
                if q_date_obj.isValid():
                    formatted_event_date_original = q_date_obj.toString("dd.MM.yyyy")
                else:
                    formatted_event_date_original = "Hatalı Tarih Formatı"
            else:
                formatted_event_date_original = "Bilinmeyen Tarih Tipi"
        # --- ETKİNLİK TARİHİNİ FORMATLAMA BİTTİ ---
        
        event_name_for_filename = self.convert_tr_to_eng(event_name_original)
        clean_event_name = "".join(c if c.isalnum() or c in (' ', '-') else "_" for c in event_name_for_filename).rstrip().replace(" ", "_")

        default_path = self.settings.get('default_export_path', '')
        timestamp_filename = QDateTime.currentDateTime().toString("yyyyMMdd") # Dosya adı için zaman damgası
        default_filename = os.path.join(default_path, f"{clean_event_name}_katilimcilar_{timestamp_filename}.pdf")

        save_path, _ = QFileDialog.getSaveFileName(self, "Katılımcı Listesini PDF Olarak Kaydet", default_filename, "PDF Dosyası (*.pdf)")

        if save_path:
            try:
                pdf = PDF('P', 'mm', 'A4') # PDF sınıfınız (font ayarları __init__ içinde olmalı)
                pdf.setup_font() # Gerekirse veya __init__'te değilse
                pdf.set_auto_page_break(auto=True, margin=15)
                pdf.add_page()
                pdf.alias_nb_pages()

                pdf.chapter_title(self.convert_tr_to_eng("Etkinlik Katilimci Listesi"))
                pdf.cell(0, 7, self.convert_tr_to_eng(f"Etkinlik Adi: {event_name_original}"), 0, 1, 'L')
                pdf.cell(0, 7, self.convert_tr_to_eng(f"Etkinlik Tarihi: {formatted_event_date_original}"), 0, 1, 'L') # Düzeltilmiş tarih kullanılıyor
                pdf.cell(0, 7, self.convert_tr_to_eng(f"Toplam Katilimci: {len(participants_rows)}"), 0, 1, 'L')
                pdf.ln(5)

                headers_tr = ['#', 'Ad Soyad', 'Bölüm', 'E-posta', 'Katılım Zamanı']
                headers_converted = [self.convert_tr_to_eng(h) for h in headers_tr]
                col_widths = [10, 55, 45, 45, 35] # Sütun genişlikleri

                table_data_converted = []
                for i, p_row in enumerate(participants_rows):
                    # --- KATILIM ZAMANINI (TIMESTAMP) FORMATLAMA (DÜZELTİLDİ) ---
                    time_str = "Zaman?"
                    timestamp_value = p_row['timestamp'] # Bu datetime.datetime objesi olabilir
                    if timestamp_value:
                        if isinstance(timestamp_value, datetime.datetime):
                            # datetime.datetime objesini QDateTime'e çevir
                            q_dt_obj = QDateTime(timestamp_value.year, timestamp_value.month, timestamp_value.day,
                                                 timestamp_value.hour, timestamp_value.minute, timestamp_value.second)
                            time_str = q_dt_obj.toString("dd.MM HH:mm:ss")
                        elif isinstance(timestamp_value, str):
                            # Eğer string ise, fromString ile parse etmeyi dene
                            # Önce milisaniyeli (ISODateWithMs), sonra milisaniyesiz (ISODate) dene
                            q_dt_obj = QDateTime.fromString(timestamp_value, Qt.DateFormat.ISODateWithMs)
                            if not q_dt_obj.isValid():
                                q_dt_obj = QDateTime.fromString(timestamp_value, Qt.DateFormat.ISODate)
                            
                            if q_dt_obj.isValid():
                                time_str = q_dt_obj.toString("dd.MM HH:mm:ss")
                            else:
                                time_str = str(timestamp_value) # Parse edilemezse olduğu gibi göster
                        else:
                            time_str = "Bilinmeyen Zaman Tipi"
                    else:
                        time_str = "Belirtilmemiş"
                    # --- KATILIM ZAMANINI FORMATLAMA BİTTİ ---
                    
                    table_data_converted.append([
                        str(i + 1),
                        self.convert_tr_to_eng(p_row['name'] if p_row['name'] is not None else '-'),
                        self.convert_tr_to_eng(p_row['department'] if p_row['department'] is not None else '-'),
                        p_row['email'] if p_row['email'] is not None else '-',
                        time_str 
                    ])
                
                pdf.create_table(table_data_converted, headers_converted, col_widths)
                
                pdf.output(save_path)
                QMessageBox.information(self, "PDF Dışa Aktarma Başarılı", 
                                        self.convert_tr_to_eng(f"Katılımcı listesi ({len(participants_rows)} kişi) başarıyla '{os.path.basename(save_path)}' dosyasına aktarıldı."))

            except FPDFException as fe: 
                QMessageBox.critical(self, "PDF Oluşturma Hatası", f"FPDF hatası oluştu: {fe}")
                traceback.print_exc()
            except IOError as e_io:
                QMessageBox.critical(self, "Dosya Hatası", f"PDF dosyası yazılırken hata oluştu: {e_io}")
                traceback.print_exc()
            except Exception as e_gen:
                QMessageBox.critical(self, "Dışa Aktarma Hatası", f"Katılımcı listesi (PDF) dışa aktarılırken beklenmedik hata oluştu: {e_gen}")
                traceback.print_exc()


    def import_members_from_csv(self):
        """CSV dosyasından üye verilerini içe aktarır."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Üyeleri CSV'den İçe Aktar", "", "CSV Dosyası (*.csv)")
        if not file_path: return

        # Hangi sütunların hangi DB alanına karşılık geldiğini belirle (varsayılanlar)
        # TODO: Kullanıcıya sütun eşleştirme arayüzü sunmak daha esnek olurdu.
        # Küçük harfe çevirerek eşleştirmeyi kolaylaştırabiliriz.
        column_map = {
            'ad soyad': 'name', 'isim': 'name', 'ad': 'name', # Olası isimler
            'uid': 'uid', 'kart': 'uid', 'kart no': 'uid',
            'eposta': 'email', 'mail': 'email', 'e-posta': 'email',
            'bölüm': 'department', 'bolum': 'department',
            'sınıf': 'year', 'sinif': 'year', 'yıl': 'year',
            'telefon': 'phone', 'tel': 'phone',
            'ilgi alanları': 'interests', 'ilgi alanlari': 'interests',
            'rol': 'role',
            'üyelik tarihi': 'membership_date', 'uyelik tarihi': 'membership_date', 'kayıt tarihi': 'membership_date'
        }
        default_role = self.settings.get('default_member_role', 'Aktif Üye')
        default_date = QDate.currentDate().toString(Qt.DateFormat.ISODate)

        imported_count = 0
        skipped_count = 0
        error_list = []

        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f: # utf-8-sig BOM'u handle eder
                reader = csv.reader(f)
                # Başlık satırını oku ve küçük harfe çevir
                try:
                    header = [h.strip().lower() for h in next(reader)]
                except StopIteration:
                    raise ValueError("CSV dosyası boş veya sadece başlık satırı var.")

                if not header:
                     raise ValueError("CSV dosyasında başlık satırı bulunamadı veya boş.")

                # Başlıkların veritabanı alanlarına haritasını oluştur
                db_field_indices = {}
                for csv_header, db_field in column_map.items():
                     if csv_header in header:
                         db_field_indices[db_field] = header.index(csv_header)

                # Gerekli alanlar (name, uid) başlıkta var mı?
                if 'name' not in db_field_indices or 'uid' not in db_field_indices:
                     raise ValueError("CSV başlıklarında 'Ad Soyad/İsim' ve 'UID/Kart' sütunları bulunamadı.")

                cursor = self.get_cursor()
                for row_num, row in enumerate(reader, start=2): # Satır 2'den başla
                    if not row or all(not cell for cell in row): continue # Boş satırları atla

                    member_data = {}
                    try:
                         # Verileri index'e göre al
                         for db_field, index in db_field_indices.items():
                              if index < len(row): # Index satır sınırları içindeyse
                                   member_data[db_field] = row[index].strip()
                              else:
                                   member_data[db_field] = '' # Index dışarıdaysa boş ata
                    except IndexError:
                         error_list.append(f"Satır {row_num}: Sütun sayısı başlıkla uyuşmuyor, atlandı.")
                         skipped_count += 1
                         continue

                    # Zorunlu alanlar (name, uid) dolu mu?
                    if not member_data.get('name') or not member_data.get('uid'):
                        error_list.append(f"Satır {row_num}: Ad Soyad veya UID boş, atlandı.")
                        skipped_count += 1
                        continue

                    # Varsayılanları ata (eğer CSV'de yoksa)
                    member_data.setdefault('role', default_role)
                    member_data.setdefault('membership_date', default_date)
                    # Fotoğraf yolu CSV'de olmaz genelde, NULL ata
                    member_data['photo_path'] = None

                    # Yıl bilgisini integer'a çevir
                    year_str = member_data.get('year')
                    try:
                         member_data['year'] = int(year_str) if year_str else None
                    except ValueError:
                         error_list.append(f"Satır {row_num} ({member_data.get('name')}): Geçersiz yıl değeri '{year_str}', boş bırakıldı.")
                         member_data['year'] = None # Hatalıysa None ata

                    # Veritabanına eklemeyi dene
                    try:
                        # NULL olabilecek alanları kontrol et
                        email_val = member_data.get('email') or None
                        dept_val = member_data.get('department') or None
                        phone_val = member_data.get('phone') or None
                        interests_val = member_data.get('interests') or None
                        role_val = member_data.get('role') or None
                        mem_date_val = member_data.get('membership_date') or None
                        # Tarih formatını kontrol et (YYYY-MM-DD olmalı)
                        try:
                             QDate.fromString(mem_date_val, Qt.DateFormat.ISODate)
                        except:
                             error_list.append(f"Satır {row_num} ({member_data.get('name')}): Geçersiz tarih formatı '{mem_date_val}', varsayılan ({default_date}) kullanıldı.")
                             mem_date_val = default_date


                        cursor.execute("""
                             INSERT INTO members (name, uid, email, department, year, phone, interests, role, membership_date, photo_path)
                             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                         """, (member_data.get('name'), member_data.get('uid'), email_val, dept_val, member_data.get('year'),
                               phone_val, interests_val, role_val, mem_date_val, member_data.get('photo_path') ))
                        imported_count += 1
                    except psycopg2.Error as ie:
                        error_list.append(f"Satır {row_num} ({member_data.get('name')}): UID veya E-posta zaten kayıtlı, atlandı.")
                        skipped_count += 1
                    except Exception as row_e:
                        error_list.append(f"Satır {row_num} ({member_data.get('name')}): Ekleme hatası - {row_e}, atlandı.")
                        skipped_count += 1

            self.db_connection.commit() # Tüm başarılı eklemeleri onayla

            # Sonuç mesajını oluştur
            result_message = f"{imported_count} üye başarıyla içe aktarıldı.\n{skipped_count} üye atlandı.\n\n"
            if error_list:
                result_message += "Atlanan Satırlar/Hatalar (ilk 10):\n" + "\n".join(error_list[:10])
                if len(error_list) > 10:
                    result_message += f"\n... ve {len(error_list) - 10} hata daha."
            QMessageBox.information(self, "İçe Aktarma Tamamlandı", result_message)
            self.update_member_list() # Listeyi güncelle
            self.update_main_page_stats() # İstatistikleri güncelle

        except FileNotFoundError:
            QMessageBox.critical(self, "Hata", f"Dosya bulunamadı: {file_path}")
        except ValueError as ve: # Başlık veya format hatası
            QMessageBox.critical(self, "CSV Format Hatası", f"{ve}")
        except Exception as e:
            QMessageBox.critical(self, "İçe Aktarma Hatası", f"CSV dosyası okunurken veya işlenirken hata oluştu: {e}")
            traceback.print_exc()


    def add_demo_data(self):
     QMessageBox.information(self, "Demo Veri", "PostgreSQL için demo veri ekleme fonksiyonu güncellenmelidir.")
     pass # İçeriği geçici olarak devre dışı bırak
    # --- Çıkış Yapma ---
    # AdminPanel sınıfının içine:
    

# --- Ana Çalıştırma Bloğu ---
if __name__ == "__main__":
    # Yüksek DPI ölçeklemesini etkinleştir (isteğe bağlı, bazı ekranlarda görünümü iyileştirir)
    # QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    # QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    print("DEBUG: Uygulama başlatılıyor...")
    app = QApplication(sys.argv)

    # Önemli: Uygulama kapanmadan önce veritabanı bağlantılarının kapatıldığından emin olalım
    # AdminPanel'in closeEvent'i ve LoginWindow'un closeEvent'i bunu halletmeli.
    # Yine de app.aboutToQuit sinyaline bağlanabiliriz.
    def cleanup():
        print("Uygulama kapanıyor...")
        # Gerekirse burada ek temizlik yapılabilir (açık dosyalar vb.)
        # Bağlantıların closeEvent'lerde kapatıldığını varsayıyoruz.
    app.aboutToQuit.connect(cleanup)

    # Stil için global ayarlar (isteğe bağlı)
    # app.setStyle("Fusion") # Farklı bir görünüm için

    # Login penceresini oluştur ve göster
    login_window = LoginWindow()
    login_window.show()

    # Olay döngüsünü başlat ve çıkış kodunu al
    exit_code = app.exec()
    print(f"Uygulama çıkış kodu: {exit_code}")
    sys.exit(exit_code) # Uygulama kapanınca çıkış koduyla çık