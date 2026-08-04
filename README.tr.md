# cc-telegram-bridge (Türkçe)

**Claude Code Desktop** session'larını Telegram'dan yönet.

- Claude bir cevabı bitirdiğinde, soru sorduğunda ya da seni beklediğinde telefonuna mesaj gelir.
- Telefondan cevap yazarsın — cevabın doğru session'a girer, Claude devam eder.
- PC başındayken telefon susar: bildirimler birkaç dakika bekletilir, app'te bir şey yazarsan iptal olur.

Her şey resmi Claude Code mekanizmalarıyla çalışır (plugin + hook'lar + uygulamanın kendi araçları).

---

## Nasıl davranır

| Durum | Ne olur |
|---|---|
| PC başındasın | Bildirim 3 dk bekler (`NOTIFY_GRACE_SECONDS`). Bu sürede app'te bir şey yazarsan iptal olur — telefon hiç titremez. |
| Uzaktasın | Süre dolunca bildirim düşer: `[session başlığı #id]` + Claude'un söylediğinin özeti. |
| Telefondan cevap yazdın | "Canlı mod" açılır. Cevabın session'a doğrudan enjekte edilir; sonraki cevaplar beklemesiz telefonuna gelir. Session'lar turn sonunda bir sonraki mesajını yakalamak için kısa süre bekler (`HOLD_SECONDS`, varsayılan 10 dk). |
| Telefondayken Claude çoktan seçmeli soru sordu | Soru her seçenek için bir **butonla** gelir (+ serbest metin için "✍️ Type an answer"; çoklu seçim destekli). Butona bas, session devam etsin. PC'deysen soru normal şekilde app'te açılır, hiçbir şey beklemez. |
| PC'ye döndün | App'te bir şey yazdığın an canlı mod biter, her şey normale döner. Telefonda bekleyen soru iptal olup app'te açılır. |
| Uzun süredir boşta bir session'a yazdın | Mesaj kuyruklanır; o session uyanınca (içine yazınca veya app yeniden açılınca) otomatik iletilir. Anında iletim istersen: [Opsiyonel köprü](#opsiyonel-köprü-sessionı). |

Bildirim ikonları: `✅` cevap bitti · `🔄(N bg)` arka planda iş sürüyor · `⏳` input bekliyor · `❓` çoktan seçmeli soru · `📋` plan onayı bekliyor.

---

## Gereksinimler

- Windows 10/11
- [Claude Code Desktop](https://claude.com/claude-code) (giriş yapılmış)
- Telegram hesabı
- Python 3.10+ (yalnızca bir kez, exe'leri derlemek için)

---

## Kurulum — adım adım

**1. Kodu al ve kur:**

```powershell
git clone https://github.com/ozaneski13/cc-telegram-bridge.git
cd cc-telegram-bridge
powershell -ExecutionPolicy Bypass -File setup.ps1
```

`setup.ps1` her şeyi yapar: exe'leri derler (ilk seferde), Claude Code plugin'ini kurar, autostart'ı ayarlar, arka plan daemon'ını başlatır. İstediğin zaman tekrar çalıştırabilirsin, güvenlidir.

**2. Telegram botunu oluştur:**

1. Telegram'da [@BotFather](https://t.me/BotFather)'a `/newbot` yaz.
2. Bir isim, sonra `bot` ile biten bir kullanıcı adı ver (örn. `my_claude_bot`).
3. BotFather sana `123456789:AAH...` gibi bir **token** verir — kopyala.

**3. Numeric Telegram id'ni öğren:**

1. [@userinfobot](https://t.me/userinfobot)'u aç, Start'a bas.
2. Sana id'ni söyler, örn. `412587349`.

**4. İkisini proje klasöründeki `.env` dosyasına yaz:**

```
BOT_TOKEN=123456789:AAH...
TELEGRAM_OWNER_ID=412587349
```

Bu dosya sadece senin makinende kalır — gitignore'dadır, hiçbir yere gitmez.

**5. Daemon'ı yeniden başlat** (token'ı okusun):

```powershell
taskkill /IM cc-telegram-bridge.exe /F
.\cc-telegram-bridge.exe
```

**6. Botuna bir DM at** ("selam" yeterli). Chat böyle bağlanır. Sadece senin id'inden gelen mesajlar kabul edilir; başka herkes sessizce yok sayılır.

**7. Claude Code Desktop uygulamasını bir kez kapatıp aç.** Plugin session açılırken yüklenir; kurulumdan önce açık olan chat'ler yeniden açılana kadar sessiz kalır. Tek app restart'ı hepsini birden düzeltir.

**8. Test:** bir chat aç, bir şey sor, app'e dokunma. Grace süresi (3 dk) dolunca cevap telefonuna düşmeli. Bildirime swipe-reply at — Claude cevabınla devam etmeli.

Kurulum bu kadar. Bundan sonrası otomatik: daemon logon'da kendi başlar, durursa herhangi bir Claude aktivitesi onu yeniden ayağa kaldırır.

---

## Günlük kullanım

| Telegram'dan gönderdiğin | Ne olur |
|---|---|
| Bildirime swipe-reply | Metnin tam o session'a gider |
| Düz mesaj | En son bildirim atan session'a gider |
| `/sessions` | Son session'ları numaralı listeler (`*` = aktif hedef) |
| `/use 2` veya `/use a1b2` | Düz mesajların hedefini değiştirir |
| `/usage` | Plan limitlerin: 5 saatlik ve haftalık pencereler + sıfırlanma saatleri |
| `/status` | Mevcut varsayılanlar + hedef chat + kullanım, tek mesajda |
| `/model opus\|sonnet\|fable\|haiku [#chat\|N\|global]` | Modeli değiştirir (1M context için sonuna `[1m]`) |
| `/effort low\|medium\|high\|xhigh [#chat\|N\|global]` | Düşünme eforunu değiştirir |
| `/fast on\|off` | Fast mode açar/kapatır |
| `/help` | Komut listesi |

**Kapsam kuralı.** `/model` ve `/effort` tek bir chat'i değiştirir. Chat'i satır içinde belirt — `/model fable #a1b2c3d4`, `/model fable 6` (`/sessions`'daki numara) veya başlığıyla — ya da hiç yazma, aktif hedef chat kullanılır. Sonuna `global` eklersen — `/model fable global` — bunun yerine **yeni** chat'lerin varsayılanı değişir. `/fast` yalnızca globaldir.

Chat bazlı değişiklik o chat'in kayıtlı durumuna yazılır, yani chat bir dahaki açılışında geçerli olur. Uygulama, aktif kullandığın chat'in durumunu her turda kendisi yeniden yazdığı için **şu an açık olan** bir chat değişikliği ezer — önce o chat'i kapat, ya da `global` kullan. Halihazırda içinde yazdığın chat'in modelini uzaktan değiştirmek mümkün değil; app'teki model seçiciyi kullan.

`/usage` makinendeki mevcut Claude oturumunu kullanır, ek kurulum gerekmez.

Dönen onaylar: `⚡ →` canlı iletildi · `→ ... (session idle)` kuyruklandı, session uyanınca iletilecek.

---

## Opsiyonel: köprü session'ı

Canlı mod aktif konuşmaları karşılar. Uzun süredir boşta olan session'lara da **anında** iletim istersen bir aktarıcı session aç:

1. Claude Code'da `cc-telegram-bridge` klasöründe yeni bir session aç (kendi kendini bildirmemesi için).
2. İçine `/cc-telegram-bridge` yaz, açık bırak.

Kapalı olması bir şey bozmaz — kuyruktakiler yine hedef session uyanınca iletilir.

---

## Daemon yönetimi

| İşlem | Komut |
|---|---|
| Çalışıyor mu? | `curl.exe http://127.0.0.1:8765/health` → `ok` |
| Durdur | `curl.exe -X POST http://127.0.0.1:8765/shutdown -H "X-Bridge-Token: <.env'deki BRIDGE_SECRET>"` |
| Başlat | `cc-telegram-bridge.exe` (ya da hiçbir şey yapma — hook'lar kendisi başlatır) |
| Kod değişince derle | `powershell -ExecutionPolicy Bypass -File build.ps1` sonra `setup.ps1` |
| Plugin'i kapat | `claude plugin disable cc-telegram-bridge@skills-dir` |

---

## Ayarlar (`.env`)

| Anahtar | Anlamı | Varsayılan |
|---|---|---|
| `BOT_TOKEN` | BotFather'dan aldığın token | — |
| `TELEGRAM_OWNER_ID` | Numeric Telegram id'in; sadece bu kabul edilir | — |
| `BRIDGE_SECRET` | Hook↔daemon ortak sırrı (otomatik üretilir) | — |
| `PORT` | Lokal port, sadece 127.0.0.1 | `8765` |
| `NOTIFY_GRACE_SECONDS` | PC'deyken bildirimlerin bekleme süresi; `0` = anında | `180` |
| `HOLD_SECONDS` | Canlı modda session'ın sonraki cevabını bekleme süresi | `600` |
| `ASK_WAIT_SECONDS` | Çoktan seçmeli sorunun buton cevabını bekleme süresi (yalnız canlı modda) | `300` |
| `ASK_ANSWER_MODE` | `input` cevabı tool'a doldurur; `deny` cevabı geri-bildirim metni olarak verir | `input` |
| `IGNORE_CWD_SUBSTRINGS` | Bildirim atmayacak klasör adı parçaları (virgülle) | `cc-telegram-bridge` |

`.env` değişince daemon'ı yeniden başlat.

---

## Başka PC'ye taşıma (aynı Claude hesabı)

1. **Eski** PC'de: `taskkill /IM cc-telegram-bridge.exe /F` + `shell:startup` içindeki `cc-telegram-bridge.lnk`'i sil. (İki PC aynı token'ı dinlerse çakışma ve çift bildirim olur.)
2. Proje klasörünü yeni PC'ye kopyala — veya `git clone` yapıp sadece `.env`'ini taşı (`state.json`'ı da taşırsan chat bağı korunur).
3. **Yeni** PC'de `setup.ps1` çalıştır, Claude uygulamasını bir kez yeniden başlat. Bitti — kullanıcı adına veya klasör konumuna bağlı hiçbir şey yok.

---

## Güvenlik ve gizlilik

- Daemon sadece **127.0.0.1** dinler; hook çağrıları ortak sırla doğrulanır.
- Sadece senin Telegram id'in kabul edilir — botunu bulan bir yabancının yapabileceği hiçbir şey yok.
- Bot token'ın yalnızca lokal `.env`'de yaşar (gitignore'da). Başka hiçbir yerde saklanmaz.
- **Claude cevaplarının özetleri Telegram sunucularından geçer.** Hassas projeler için klasör adını `IGNORE_CWD_SUBSTRINGS`'e ekle.
- Repoda binary yok; iki exe'yi de okunabilir, bağımlılıksız Python kaynağından kendin derliyorsun.

## Sınırlar

- Çoktan seçmeli sorular Telegram'dan cevaplanabilir (inline butonlar). Plan onayı ve izin dialogları cevaplanamaz — sadece bildirim düşer, cevabın normal mesaj olarak gider.
- Butona bastığın halde soru app'te yine açılıyorsa `.env`'de `ASK_ANSWER_MODE=deny` yapıp daemon'ı yeniden başlat.
- Cevap enjeksiyonu Claude Code Desktop gerektirir; yalnız-bildirim tarafı hook çalıştıran her Claude Code'da işler.
- Şu haliyle Windows-only (PowerShell script'leri, Startup kısayolu); daemon'ın kendisi taşınabilir Python.

## Lisans

[MIT](LICENSE) — © 2026 Ozan Eşki.
