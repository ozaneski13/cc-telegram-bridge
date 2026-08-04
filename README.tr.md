# cc-telegram-bridge (Türkçe)

**Claude Code Desktop** (Windows) için iki yönlü Telegram köprüsü: koşan *bütün* session'ların kullanıcıya-dönük olaylarını (cevap bitti, soru, plan onayı, input bekleme) Telegram'a bildirir; telefondan yazdığın cevabı doğru session'a user mesajı olarak geri iletir.

Ayrıntılı dokümantasyon İngilizce [README.md](README.md)'de; burada hızlı kurulum ve günlük kullanım var.

## Kurulum

```powershell
git clone https://github.com/ozaneski13/cc-telegram-bridge.git
cd cc-telegram-bridge
powershell -ExecutionPolicy Bypass -File setup.ps1
```

`setup.ps1`: exe'ler yoksa derler (`build.ps1`), plugin'i `~/.claude/skills/cc-telegram-bridge`'e kurar (yeni session'larda otomatik yüklenir), uygulama konumunu `home.txt`'ye yazar, Startup kısayolunu oluşturur, `BRIDGE_SECRET` üretir, daemon'ı başlatıp health-check yapar. Tekrar tekrar çalıştırılabilir.

## Telegram'ı aktive etme

1. @BotFather → `/newbot` → token'ı al.
2. @userinfobot → numeric ID'ni al.
3. İkisini `.env`'e yaz: `BOT_TOKEN=...`, `TELEGRAM_OWNER_ID=...`
4. Daemon'ı yeniden başlat.
5. Botuna bir DM at (chat bağlanır; sadece senin ID'in kabul edilir).
6. Cevap kanalı için herhangi bir session'da `/cc-telegram-bridge` çalıştır ve o session'ı açık bırak. Kapalıysa bildirimler akmaya devam eder, cevaplar kuyruklanır.

## Günlük kullanım

- İkonlar: `✅` cevap bitti · `🔄(N bg)` arka planda iş sürüyor · `⏳` input bekliyor · `❓` çoktan seçmeli soru · `📋` plan onayı.
- Bildirime **swipe-reply** → cevap o session'a; düz mesaj → en son bildirim atan session'a.
- `/sessions` → numaralı liste (`*` = aktif hedef); `/use 2` veya `/use a1b2` → hedef değiştir.

## Daemon işlemleri

| İşlem | Komut |
|---|---|
| Durum | `curl.exe http://127.0.0.1:8765/health` → `ok` |
| Durdur | `curl.exe -X POST http://127.0.0.1:8765/shutdown -H "X-Bridge-Token: <BRIDGE_SECRET>"` |
| Başlat | `cc-telegram-bridge.exe` (veya hiçbir şey yapma — hook kapalıysa kendisi başlatır) |
| Derle | `powershell -ExecutionPolicy Bypass -File build.ps1` |

## Başka PC'ye taşıma (aynı Claude hesabı)

1. **Eski PC'de:** daemon'ı kapat (`taskkill /IM cc-telegram-bridge.exe /F`) ve `shell:startup` içindeki `cc-telegram-bridge.lnk`'i sil — iki PC aynı bot token'ıyla aynı anda çalışırsa Telegram getUpdates çakışır (409) ve çift bildirim düşer.
2. Klasörü kopyala (`.env` ve istersen `state.json` ile) veya `git clone` + `.env`'i taşı.
3. Yeni PC'de `setup.ps1` çalıştır. Konum ve kullanıcı adı bağımsızdır.

## Güvenlik

- Daemon sadece `127.0.0.1` dinler; hook istekleri `X-Bridge-Token` ile doğrulanır; sadece `TELEGRAM_OWNER_ID` kabul edilir.
- Bot token'ı yalnızca lokal `.env`'de durur; `.env` gitignore'dadır, asla commit etme.
- **Konuşma özetleri Telegram sunucularından geçer** — hassas projeleri `IGNORE_CWD_SUBSTRINGS` ile sustur.

## Lisans

[MIT](LICENSE) — © 2026 Ozan Eşki.
