# Girişimcilik Kulübü Yönetim Sistemi

Bu proje, PyQt6 tabanlı masaüstü uygulamasını Flask web uygulamasına dönüştürülmüş halidir. Neon PostgreSQL veritabanı kullanarak üye yönetimi, etkinlik takibi ve puan sistemi sağlar.

## Özellikler

### 🏠 Ana Sayfa
- Dashboard istatistikleri
- Yaklaşan etkinlikler
- Liderlik tablosu
- Hızlı işlem butonları

### 👥 Üye Yönetimi
- Üye ekleme, düzenleme, silme
- Fotoğraf yükleme
- UID tabanlı üye tanımlama
- Puan sistemi
- Katılım geçmişi

### 📅 Etkinlik Yönetimi
- Etkinlik oluşturma ve düzenleme
- Kategori sistemi
- Tarih ve konum takibi
- Katılımcı sayısı

### ✅ Katılım Sistemi
- UID ile hızlı katılım kaydı
- Otomatik puan ekleme (+10 puan)
- Tekrar katılım engelleme

### 🎫 Bilet Satışları
- Bilet türü seçimi
- Ödeme yöntemi
- Fiyat takibi
- Otomatik puan ekleme (+5 puan)

### 📊 Raporlar
- Detaylı istatistikler
- Katılım oranları
- Puan dağılımı
- Analiz raporları

## Kurulum

### Gereksinimler
- Python 3.8+
- PostgreSQL (Neon veritabanı)
- pip

### Adımlar

1. **Projeyi klonlayın:**
```bash
git clone <repository-url>
cd cursordeneme
```

2. **Sanal ortam oluşturun:**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# veya
venv\Scripts\activate  # Windows
```

3. **Bağımlılıkları yükleyin:**
```bash
pip install -r requirements.txt
```

4. **Veritabanı ayarlarını yapılandırın:**
`app.py` dosyasındaki veritabanı bağlantı bilgilerini güncelleyin:
```python
PG_HOST = "your-neon-host"
PG_DATABASE = "your-database-name"
PG_USER = "your-username"
PG_PASSWORD = "your-password"
PG_PORT = "5432"
```

5. **Uygulamayı çalıştırın:**
```bash
python app.py
```

6. **Tarayıcıda açın:**
```
http://localhost:5000
```

## Varsayılan Giriş Bilgileri

- **Kullanıcı Adı:** admin
- **Şifre:** admin123

## Veritabanı Yapısı

### Tablolar
- `members` - Üye bilgileri
- `events` - Etkinlik bilgileri
- `attendance` - Katılım kayıtları
- `ticket_sales` - Bilet satışları
- `points_log` - Puan geçmişi
- `admin_users` - Yönetici kullanıcılar

### Puan Sistemi
- Etkinlik katılımı: +10 puan
- Bilet satın alma: +5 puan
- Referans: +15 puan

## API Endpoints

### Üyeler
- `GET /api/members` - Tüm üyeleri listele
- `POST /members/add` - Yeni üye ekle
- `GET /members/<id>/edit` - Üye düzenleme sayfası
- `POST /members/<id>/edit` - Üye güncelle
- `POST /members/<id>/delete` - Üye sil

### Etkinlikler
- `GET /api/events` - Tüm etkinlikleri listele
- `POST /events/add` - Yeni etkinlik ekle
- `GET /events/<id>/edit` - Etkinlik düzenleme sayfası
- `POST /events/<id>/edit` - Etkinlik güncelle
- `POST /events/<id>/delete` - Etkinlik sil

### Katılım ve Satışlar
- `POST /attendance` - Katılım kaydet
- `POST /ticket_sales` - Bilet satışı kaydet

## Güvenlik

- Flask-Login ile oturum yönetimi
- Şifre hashleme (Werkzeug)
- CSRF koruması
- Input validasyonu

## Teknolojiler

- **Backend:** Flask, Python
- **Frontend:** HTML5, CSS3, JavaScript, Bootstrap 5
- **Veritabanı:** PostgreSQL (Neon)
- **ORM:** psycopg2
- **Authentication:** Flask-Login
- **Icons:** Font Awesome

## Geliştirme

### Proje Yapısı
```
cursordeneme/
├── app.py                 # Ana Flask uygulaması
├── requirements.txt       # Python bağımlılıkları
├── templates/            # HTML template'leri
│   ├── base.html
│   ├── login.html
│   ├── index.html
│   ├── members.html
│   ├── events.html
│   └── ...
├── static/               # Statik dosyalar
├── uploads/              # Yüklenen dosyalar
└── README.md
```

### Özelleştirme

1. **Tema Değişikliği:** `templates/base.html` dosyasındaki CSS'i düzenleyin
2. **Puan Sistemi:** `app.py` dosyasındaki sabitleri değiştirin
3. **Veritabanı:** Neon veritabanı ayarlarını güncelleyin
4. **Logo:** `static/` klasörüne logo ekleyin

## Sorun Giderme

### Yaygın Sorunlar

1. **Veritabanı Bağlantı Hatası:**
   - Neon veritabanı bilgilerini kontrol edin
   - SSL ayarlarını doğrulayın
   - Ağ bağlantısını kontrol edin

2. **Modül Bulunamadı:**
   - Sanal ortamın aktif olduğundan emin olun
   - `pip install -r requirements.txt` komutunu çalıştırın

3. **Port Hatası:**
   - 5000 portunun kullanılabilir olduğunu kontrol edin
   - `app.py` dosyasında port değiştirin

## Katkıda Bulunma

1. Fork yapın
2. Feature branch oluşturun (`git checkout -b feature/amazing-feature`)
3. Commit yapın (`git commit -m 'Add amazing feature'`)
4. Push yapın (`git push origin feature/amazing-feature`)
5. Pull Request oluşturun

## Lisans

Bu proje MIT lisansı altında lisanslanmıştır.

## İletişim

- **Proje Sahibi:** Girişimcilik Kulübü
- **E-posta:** [e-posta adresi]
- **Website:** girisimcilikkulubu.com

## Teşekkürler

- Flask framework'ü
- Bootstrap CSS framework'ü
- Font Awesome ikonları
- Neon PostgreSQL hosting 