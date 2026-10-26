# Discord Blog Web Notification Bot

Bot Discord untuk memantau artikel baru dari beberapa website melalui RSSHub
dan mengirim notifikasi ke channel Discord.

## Fitur

- Daftar website modular melalui `config.yaml`.
- Satu channel default atau channel berbeda untuk setiap website.
- Deduplikasi permanen menggunakan SQLite.
- Memproses seluruh artikel baru dari satu siklus polling.
- Error satu website tidak menghentikan website lain.
- RSS request memiliki timeout dan polling aman saat Discord reconnect.
- Mode sinkronisasi awal untuk melewati artikel lama.

## Prasyarat

Pilih salah satu cara menjalankan bot:

- **Docker Compose:** Docker Engine dan Docker Compose Plugin.
- **Lokal:** Python 3.12 atau lebih baru, serta RSSHub dan Redis yang sudah
  berjalan.

Selain itu, siapkan:

- Discord bot token.
- ID channel Discord tujuan.
- URL website dan route RSSHub untuk website tersebut.

## Quick Start dengan Docker Compose

### 1. Clone repository

```bash
git clone https://github.com/Rhizopus-oryzae/discord-bot-web-notification.git
cd discord-bot-web-notification
```

### 2. Buat konfigurasi environment

```bash
cp .env.example .env
```

Isi `DISCORD_TOKEN` dan `DEFAULT_CHANNEL_ID` di `.env`. File ini bersifat
rahasia dan tidak boleh di-commit.

### 3. Konfigurasi website

Tambahkan atau ubah website di `config.yaml`. Contoh berikut memakai domain
placeholder; ganti `blog.example.com` dengan website yang ingin dipantau:

```yaml
initial_sync: skip_existing

sites:
  - id: blog-contoh
    name: Blog Contoh
    enabled: true
    rss_url: ${RSSHUB_BASE_URL}/wordpress/https%3A%2F%2Fblog.example.com
    channel_id: null
```

`channel_id: null` memakai `DEFAULT_CHANNEL_ID`. Gunakan `enabled: false`
untuk menonaktifkan website tanpa menghapus konfigurasinya.

### 4. Jalankan service

```bash
docker compose up -d --build
docker compose logs -f bot
```

Compose menjalankan bot, RSSHub, dan Redis. Database disimpan pada volume
`bot-data` agar state tetap ada setelah container dibuat ulang.

## Instalasi dan Menjalankan secara Lokal

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python bot.py
```

Untuk mode lokal, RSSHub harus tersedia di `http://localhost:1200` atau
`RSSHUB_BASE_URL` diubah di `.env`.

## Perintah Operasional Docker

```bash
docker compose ps
docker compose logs -f bot
docker compose restart bot
docker compose down
```

## Pengujian

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Dokumen arsitektur dan workflow lengkap tersedia di [`rancangan.md`](rancangan.md).
