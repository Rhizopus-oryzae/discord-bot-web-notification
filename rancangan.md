# Rancangan Proyek: Discord Blog Notification Bot

## 1. Ringkasan Proyek

Bot Discord otomatis yang memantau pembaruan artikel dari satu atau beberapa
situs web. Setiap situs dikonfigurasi secara modular melalui `config.yaml`,
feed-nya diambil menggunakan RSSHub (*self-hosted* via Docker), lalu artikel
baru dikirimkan ke channel Discord yang sesuai.

Situs yang dipantau tidak boleh dikunci di dalam kode. Menambah, menghapus,
atau menonaktifkan situs cukup dilakukan melalui konfigurasi.

---

## 2. Tujuan dan Prinsip Utama

- Mendukung banyak situs tanpa mengubah kode utama bot.
- Mencegah artikel yang sama dikirim lebih dari sekali.
- Tidak kehilangan artikel ketika beberapa artikel baru muncul di antara dua
  siklus polling.
- Error pada satu situs tidak boleh menghentikan pemrosesan situs lain.
- Menyimpan state secara permanen dan aman.
- Menyimpan rahasia hanya di `.env` dan tidak memasukkannya ke repository.

---

## 3. Tech Stack & Tools

- **Bahasa:** Python 3.x
- **Bot Discord:** `discord.py`
- **Parser RSS:** `feedparser`
- **Konfigurasi:** `python-dotenv` untuk `.env` dan library YAML untuk
  `config.yaml`
- **Penyimpanan state:** SQLite melalui modul `sqlite3`
- **Feed generator:** RSSHub
- **Cache RSSHub:** Redis
- **Orkestrasi:** Docker Compose

SQLite dipilih sebagai penyimpanan utama karena transactional, tidak
memerlukan service database tambahan, dan lebih aman untuk deduplikasi
daripada file JSON.

---

## 4. Konfigurasi

### 4.1 `.env`

`.env` hanya berisi rahasia dan konfigurasi runtime umum:

```env
DISCORD_TOKEN=token-discord
DEFAULT_CHANNEL_ID=123456789012345678
POLL_INTERVAL_MINUTES=20
DATABASE_PATH=data/bot.sqlite3
RSSHUB_BASE_URL=http://rsshub:1200
```

File `.env` harus masuk `.gitignore` dan permission-nya dibatasi agar tidak
dapat dibaca user lain.

### 4.2 `config.example.yaml` dan `config.yaml`

Template daftar situs dan pengaturan non-rahasia disimpan di
`config.example.yaml` dan boleh di-commit karena hanya menggunakan domain
placeholder. Salin template tersebut menjadi `config.yaml` untuk penggunaan
lokal:

```bash
cp config.example.yaml config.yaml
```

`config.yaml` dapat berisi target website lokal/private dan harus masuk
`.gitignore`.

```yaml
initial_sync: skip_existing

sites:
  - id: blog-contoh
    name: Blog Contoh
    enabled: true
    rss_url: http://rsshub:1200/wordpress/https%3A%2F%2Fblog.example.com
    channel_id: null

  - id: contoh
    name: Contoh Website
    enabled: false
    rss_url: http://rsshub:1200/wordpress/https%3A%2F%2Fcontoh.com
    channel_id: null
```

Aturan konfigurasi:

- `id` harus stabil dan unik; digunakan sebagai identitas situs di database.
- `name` adalah nama yang ditampilkan di log atau pesan jika diperlukan.
- `enabled: false` menonaktifkan situs tanpa menghapus konfigurasinya.
- `rss_url` adalah endpoint RSS untuk situs tersebut.
- `channel_id` dapat menentukan channel khusus; jika `null`, gunakan
  `DEFAULT_CHANNEL_ID` dari `.env`.
- `initial_sync: skip_existing` berarti artikel lama yang sudah ada saat
  pertama kali sinkronisasi tidak langsung membanjiri channel Discord.

---

## 5. Penyimpanan dan Deduplikasi

Database utama:

```text
data/bot.sqlite3
```

Tabel minimal yang direncanakan:

```sql
CREATE TABLE sent_posts (
    site_id TEXT NOT NULL,
    post_id TEXT NOT NULL,
    article_url TEXT,
                title TEXT,
                sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                discord_message_id TEXT,
                status TEXT NOT NULL DEFAULT 'sent',
                PRIMARY KEY (site_id, post_id)
            );
```

Deduplikasi menggunakan kombinasi `site_id + post_id`, sehingga artikel dari
dua situs berbeda tidak akan bentrok walaupun memiliki ID yang sama.

Artikel yang berhasil dikirim disimpan dengan status `sent` setelah
`channel.send()` berhasil. Pada `initial_sync: skip_existing`, artikel yang
sudah ada di feed dicatat dengan status `skipped` sebagai baseline tanpa
dikirim ke Discord. Jika pengiriman gagal, artikel tidak ditandai terkirim dan
akan dicoba kembali pada siklus polling berikutnya.

---

## 6. Workflow Sistem

```text
Startup
  ↓
Load .env dan config.yaml
  ↓
Validasi token, channel, interval, situs, dan database
  ↓
Buka atau buat SQLite
  ↓
Login ke Discord
  ↓
Mulai satu polling task
  ↓
Untuk setiap situs yang enabled:
  ↓
Ambil RSS dengan timeout
  ↓
Parse semua entry dan validasi field penting
  ↓
Urutkan artikel dari yang paling lama ke terbaru
  ↓
Cek kombinasi site_id + post_id di SQLite
  ↓
Format dan kirim setiap artikel yang belum terkirim
  ↓
Simpan artikel ke SQLite setelah pengiriman berhasil
  ↓
Jika situs gagal, catat error lalu lanjutkan ke situs berikutnya
  ↓
Tunggu interval berikutnya
```

Ketentuan workflow:

1. Semua artikel baru diproses, bukan hanya entry paling terbaru.
2. Artikel diproses dari lama ke baru agar urutan notifikasi tetap benar.
3. Error RSSHub, jaringan, atau Discord pada satu situs tidak menghentikan
   situs lainnya.
4. RSS request harus memiliki timeout dan error harus dicatat dengan jelas.
5. Task polling tidak boleh dibuat ulang ketika Discord melakukan reconnect.
6. Jika satu pengiriman gagal, artikel tersebut tidak ditandai terkirim.
7. Jika RSSHub sedang tidak tersedia, situs dilewati dan dicoba lagi pada
   siklus berikutnya.

---

## 7. Struktur Modul yang Direncanakan

```text
bot.py              # Lifecycle Discord dan polling task
config.py           # Pembacaan serta validasi .env dan config.yaml
storage.py          # Inisialisasi dan operasi SQLite
feed.py             # Pengambilan serta parsing RSS
formatter.py        # Pembersihan summary dan format pesan Discord
config.example.yaml # Template daftar situs generik
config.yaml         # Konfigurasi lokal, tidak di-commit
data/
  bot.sqlite3       # Database runtime, tidak di-commit
```

Pembagian ini membuat penambahan situs atau perubahan format pesan tidak
memerlukan perubahan pada seluruh alur bot.

---

## 8. Spesifikasi Output Pesan Discord

Setiap artikel baru dikirim dengan format:

```text
**[Judul Artikel]**

[Hook atau ringkasan singkat]

[URL artikel]
```

Ketentuan format:

- Tag HTML pada summary dibersihkan dengan parser yang sesuai.
- Summary dipotong menjadi hook singkat.
- Total pesan harus berada di bawah batas maksimum Discord, yaitu 2.000
  karakter.
- Jika summary atau title tidak tersedia, gunakan fallback yang aman tanpa
  menghentikan polling.

---

## 9. Infrastruktur Docker

Docker Compose direncanakan menjalankan:

- `bot`
- `rsshub`
- `redis`

Ketentuan deployment:

- Bot dalam Compose mengakses RSSHub melalui hostname `rsshub`, bukan
  `localhost`.
- Database SQLite disimpan pada volume permanen.
- RSSHub dan Redis menggunakan image dengan versi yang dipin, bukan `latest`.
- RSSHub dan Redis memiliki healthcheck.
- `.env` tidak disalin ke image dan tidak di-commit.

---

## 10. Struktur Direktori Target

```text
notif/
├── bot.py
├── config.py
├── feed.py
├── formatter.py
├── storage.py
├── config.example.yaml
├── config.yaml              # Lokal, tidak di-commit
├── docker-compose.yaml
├── requirements.txt
├── rancangan.md
├── README.md
├── .env                    # Lokal/rahasia, tidak di-commit
├── .gitignore
└── data/
    └── bot.sqlite3         # Runtime state, tidak di-commit
```

---

## 11. Pengujian yang Diperlukan

- Beberapa artikel baru muncul dalam satu siklus polling.
- Dua situs memiliki `post_id` yang sama.
- Entry RSS tidak memiliki `id`, `title`, atau `summary`.
- RSSHub tidak tersedia atau mengalami timeout.
- Discord mengembalikan error saat pengiriman.
- Bot melakukan reconnect Discord.
- Artikel yang sama tidak dikirim dua kali.
- Pesan tetap berada di bawah batas karakter Discord.
- Situs nonaktif tidak diproses.
- Database tetap tersedia setelah restart bot.

---

## 12. Cara Menjalankan

### Lokal

1. Salin `.env.example` menjadi `.env` dan isi token serta channel Discord.
2. Salin `config.example.yaml` menjadi `config.yaml`, lalu sesuaikan daftar
   situs lokal.
3. Buat virtual environment dan install dependency:

   ```bash
   python -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

4. Jalankan bot:

   ```bash
   .venv/bin/python bot.py
   ```

RSSHub dan Redis harus sudah berjalan jika bot dijalankan langsung dari host.

### Docker Compose

```bash
docker compose up -d --build
docker compose logs -f bot
```

Di dalam Compose, bot mengakses RSSHub melalui `http://rsshub:1200`.

---

## 13. Urutan Implementasi

1. Membuat konfigurasi `.env` dan `config.yaml` yang tervalidasi dari template
   generik.
2. Membuat layer SQLite dan migrasi state dari `sent_posts.json` bila
   diperlukan.
3. Memisahkan pengambilan serta parsing RSS dari `bot.py`.
4. Mengimplementasikan polling semua situs dan seluruh artikel baru.
5. Menambahkan format pesan, timeout, logging, dan error handling.
6. Memperbaiki lifecycle task Discord saat reconnect.
7. Menambahkan service bot, volume, healthcheck, dan versi image di Docker
   Compose.
8. Menjalankan pengujian workflow dan dokumentasi penggunaan.
