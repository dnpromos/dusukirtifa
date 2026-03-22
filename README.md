# ✈️ TeleFlight — Telegram Uçuş Fiyat Takip Botu

Aviasales API kullanarak uçak bileti fiyatlarını takip eden ve günlük bildirim gönderen Telegram botu.

## Özellikler

- **Uçuş Takibi** — En fazla 3 uçuş aynı anda takip edilebilir
- **Günlük Fiyat Bildirimleri** — Her gün belirlenen saatte fiyat güncellenmesi
- **Fiyat Değişim Takibi** — Fiyat düşüşleri ve artışları gösterilir
- **Aylık İstatistikler** — En düşük, en yüksek ve ortalama fiyatlar
- **Aviasales Linki** — Doğrudan arama sonuçlarına yönlendirme

## Kurulum

### 1. Gereksinimleri yükleyin

```bash
pip install -r requirements.txt
```

### 2. Ortam değişkenlerini ayarlayın

```bash
cp .env.example .env
```

`.env` dosyasını düzenleyin:

- **TELEGRAM_BOT_TOKEN** — [BotFather](https://t.me/BotFather) üzerinden alın
- **AVIASALES_API_TOKEN** — [Travelpayouts](https://www.travelpayouts.com/programs/100/tools/api) üzerinden alın

### 3. Botu çalıştırın

```bash
python -m bot.main
```

## Proje Yapısı

```
bot/
├── main.py              # Giriş noktası
├── config.py            # Yapılandırma
├── handlers/
│   ├── start.py         # /start komutu ve ana menü
│   ├── track.py         # Uçuş takip konuşma akışı
│   ├── list_flights.py  # Takip listesi
│   ├── remove.py        # Takipten kaldırma
│   └── stats.py         # Fiyat istatistikleri
├── services/
│   ├── aviasales.py     # Aviasales API istemcisi
│   ├── database.py      # SQLite veritabanı işlemleri
│   └── scheduler.py     # Günlük bildirim zamanlayıcı
└── utils/
    ├── formatters.py    # Mesaj biçimlendirme
    └── keyboards.py     # Inline klavyeler
```

## Railway ile Deploy

1. Projeyi GitHub'a pushla
2. [railway.app](https://railway.app) adresine git ve GitHub ile giriş yap
3. **New Project → Deploy from GitHub Repo** seç
4. Repoyu seç ve şu ortam değişkenlerini ekle:
   - `TELEGRAM_BOT_TOKEN`
   - `AVIASALES_API_TOKEN`
5. Railway otomatik olarak `Procfile`'ı algılayıp botu başlatır
6. **Settings → Networking** kısmında "worker" servis tipini doğrula (web değil)

> ⚠️ Railway ücretsiz planda aylık 500 saat çalışma süresi verir. Bot 7/24 çalışması için yeterlidir (~720 saat/ay gerekir), limit aşılırsa $5/ay Hobby planına geçin.

## Kullanım

1. Telegram'da botunuzu açın ve `/start` gönderin
2. **➕ Uçuş Takip Et** ile yeni uçuş ekleyin
3. Kalkış ve varış havalimanı IATA kodlarını girin (örn: `IST`, `AYT`)
4. Gidiş ve dönüş tarihlerini girin
5. Bot günlük olarak fiyat bildirimleri gönderecektir
