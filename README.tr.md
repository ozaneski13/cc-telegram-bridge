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
- `PATH`'te Python 3.10+ — daemon da hook da doğrudan `.py` kaynağından çalışır; hiçbir şey derlenmez/paketlenmez

---

## Kurulum — adım adım

**1. Kodu al ve kur:**

```powershell
git clone https://github.com/ozaneski13/cc-telegram-bridge.git
cd cc-telegram-bridge
powershell -ExecutionPolicy Bypass -File setup.ps1
```

`setup.ps1` her şeyi yapar: Python'unu bulur, Claude Code plugin'ini kurar (yorumlayıcının yolunu hook ayarına yazarak), autostart'ı ayarlar, daemon'ı `pythonw` ile başlatır. İstediğin zaman tekrar çalıştırabilirsin, güvenlidir.

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
powershell -ExecutionPolicy Bypass -File setup.ps1
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
| `/sessions` | App'teki sohbetlerini numaralı listeler; model ve effort'larıyla (`*` = aktif hedef) |
| `/use 2`, `/use a1b2`, `/use drift` | Düz mesajların hedefini değiştirir (numara, id veya başlık) |
| `/usage` | Plan limitlerin: 5 saatlik ve haftalık pencereler + sıfırlanma saatleri |
| `/status` | Mevcut varsayılanlar + hedef chat + kullanım, tek mesajda |
| `/model opus\|sonnet\|fable\|haiku [#chat\|N\|global]` | Modeli değiştirir (1M context için sonuna `[1m]`) |
| `/effort low\|medium\|high\|xhigh [#chat\|N\|global]` | Düşünme eforunu değiştirir |
| `/fast on\|off` | Fast mode açar/kapatır |
| `/help` | Komut listesi |

**Kapsam kuralı.** `/model` ve `/effort` tek bir chat'i değiştirir. Chat'i satır içinde belirt — `/model fable #a1b2c3d4`, `/model fable 6` (`/sessions`'daki numara) veya başlığıyla — ya da hiç yazma, aktif hedef chat kullanılır. Sonuna `global` eklersen — `/model fable global` — bunun yerine **yeni** chat'lerin varsayılanı değişir. `/fast` yalnızca globaldir.

Chat bazlı değişiklik o chat'in kayıtlı durumuna yazılır, yani chat bir dahaki açılışında geçerli olur. Uygulama, aktif kullandığın chat'in durumunu her turda kendisi yeniden yazdığı için **şu an açık olan** bir chat değişikliği ezer — önce o chat'i kapat, ya da `global` kullan.

**Çalışan bir chat'in modelini buradan anlık değiştirmek mümkün değil.** Durum dosyasına yazılan değeri app eziyor; enjekte edilen mesajlar da session'a düz metin olarak ulaşıp istemcinin slash-komut işleyicisine girmediği için `/model` uzaktan tetiklenemiyor. Canlı bir session'ı telefondan yönetmek istiyorsan Anthropic'in kendi Remote Control'ünü kullan (claude.ai/code veya Claude mobil uygulaması).

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
| Başlat | `pythonw daemon.py` (ya da hiçbir şey yapma — hook kendisi başlatır) |
| Kod değişince | `setup.ps1`'i tekrar çalıştır (daemon'ı yeniden başlatır, plugin'i yeniden kurar) |
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

## Başka PC'ye taşıma / Windows'u yeniden kurma

**Yedeklemen gereken tam olarak iki dosya** — gerisi ya bu repoda ya da `setup.ps1` tarafından yeniden üretiliyor:

| Dosya | Neden | Kaybedersen |
|---|---|---|
| `.env` | bot token'ın, Telegram id'in, ortak sır | @BotFather'dan yeni bot alıp `.env`'i doldurursun; sır otomatik yeniden üretilir |
| `state.json` *(opsiyonel)* | bağlı Telegram chat'i ve son hedefler | Hiçbir şey bozulmaz — bota bir DM at, yeniden bağlanır |

Saklamaya değmez: `logs/`, `inbox.jsonl`, `inbox.cursor`, `spike/`. Botun kendisi Telegram sunucularında yaşar, formatı atlatır.

**Yeni makinede:**

1. **Eski** PC hâlâ duruyorsa: daemon'ı durdur (shutdown komutu veya `pythonw` sürecini sonlandır) + `shell:startup` içindeki `cc-telegram-bridge.lnk`'i sil. İki makine aynı token'ı yoklarsa çakışır ve çift bildirim gelir.
2. Repoyu `git clone` et, `.env`'ini `daemon.py`'nin yanına koy.
3. `setup.ps1` çalıştır, Claude Code Desktop'ı bir kez yeniden başlat. Kullanıcı adına veya klasör konumuna bağlı hiçbir şey yok.

---

## Çalıştırmak güvenli mi?

Bu araç kod asistanınla bir sohbet uygulaması arasında duruyor, dolayısıyla sorgulanmayı hak ediyor. Aşağıdakilerin hepsi kaynak koddan bir dakikada doğrulanabilir — bana güvenmek yerine kontrol et.

**Kendin doğrula:**

```bash
grep -hE "^import |^from " daemon.py plugin/hooks/notify_event.py | sort -u   # bagimliliklar
grep -ohE "https?://[a-zA-Z0-9./_-]+" daemon.py plugin/hooks/notify_event.py  # disari giden tum adresler
grep -nE "subprocess|os.system|eval\(|exec\(|shell=True" daemon.py plugin/hooks/notify_event.py
grep -nE "open\(.*['\"]w|write_text|os.replace" daemon.py                     # yazdigi tum dosyalar
```

Bu komutların gösterdiği ve anlamı:

- **Sıfır bağımlılık.** Yalnızca Python standart kütüphanesi — çalışma anında PyPI'dan hiçbir şey çekilmiyor, yani güvenmen gereken bir tedarik zinciri yok. Toplam ~1.300 satır; baştan sona okunabilecek kadar küçük.
- **Hiçbir yerde binary yok.** Hiçbir şey derlenmiyor/paketlenmiyor: az önce okuduğun `.py` dosyalarını kendi Python yorumlayıcın çalıştırıyor, yani çalışan şey birebir denetleyebildiğin şey. (Windows Defender'ın memnun olmasının sebebi de bu — bkz. [Sorun giderme](#sorun-giderme).)
- **Toplam üç dış adres:** `127.0.0.1` (hook → daemon), `api.telegram.org` (kendi botun) ve `api.anthropic.com/api/oauth/usage` (yalnızca `/usage` için). Telemetri, analitik, üçüncü taraf uç noktası yok.
- **Gönderdiğin hiçbir şeyi çalıştırmıyor.** Başlattığı tek süreç kendi daemon'ı (`pythonw daemon.py`) — shell yok, `eval` yok, mesajdan komut üretimi yok. Telegram metni metin olarak taşınıyor.
- **Sabit bir dosya kümesine yazıyor:** kendi klasörü (durum, kuyruk, log), hedeflenen sohbetin `model`/`effort` alanı ve — yalnızca `global`/`/fast` ile — `~/.claude/settings.json` içindeki `model`, `effortLevel`, `fastMode` anahtarları (`.bridge-bak` yedeği alınarak ve dosya doğrulanarak). Geçersiz değer reddediliyor.
- **Sadece senin numeric Telegram id'in kabul ediliyor;** gerisi sessizce düşüyor, yani botunu bulan yabancının eline hiçbir şey geçmiyor. Lokal HTTP ucu yalnızca loopback dinliyor ve ortak sır istiyor.
- **Bot token'ın `.env`'den hiç çıkmıyor** (gitignore'da). Daemon başka bir kimlik bilgisi tutmuyor; `/usage`, Claude Code'un makinende zaten sakladığı OAuth token'ını okuyup yalnızca Anthropic'e gönderiyor.

**Gerçekten neyi açığa çıkarıyor — kabul edip etmediğine sen karar ver:**

- Claude cevaplarının özetleri Telegram'a gidiyor; yani Telegram sunucularından geçiyor ve sohbet geçmişinde saklanıyor. Telegram bot mesajları uçtan uca şifreli değildir. Hassas projeleri `IGNORE_CWD_SUBSTRINGS` ile sustur.
- Telegram'dan yazdığın cevap, senin izinlerinle çalışan bir session'a kullanıcı mesajı olarak düşer. Claude Code'u izin sormayan bir modda kullanıyorsan bu mesaj dosya değişikliğine yol açabilir — dolayısıyla kilidi açık Telegram hesabına erişen biri de bu erişime sahiptir. Bot token'ı da aynı ölçüde hassastır: elinde tutan, bota yazdıklarını okuyabilir.
- Daemon, ortak sırrı bilen yerel süreçlere güvenir. Zaten senin kullanıcınla çalışan herhangi bir şey `.env`'i okuyabilirdi, yani bu yeni bir sınır değil — ama ele geçirilmiş bir makineye karşı da bir savunma değil.

## Sınırlar

- Çoktan seçmeli sorular Telegram'dan cevaplanabilir (inline butonlar). Plan onayı ve izin dialogları cevaplanamaz — sadece bildirim düşer, cevabın normal mesaj olarak gider.
- Butona bastığın halde soru app'te yine açılıyorsa `.env`'de `ASK_ANSWER_MODE=deny` yapıp daemon'ı yeniden başlat.
- Cevap enjeksiyonu Claude Code Desktop gerektirir; yalnız-bildirim tarafı hook çalıştıran her Claude Code'da işler.
- Şu haliyle Windows-only (PowerShell script'leri, Startup kısayolu); daemon'ın kendisi taşınabilir Python.

## Sorun giderme

**Windows Defender köprüyü işaretledi.** Önceki sürümler PyInstaller ile paketlenmiş bir `.exe` içeriyordu ve Defender'ın makine öğrenmesi sezgiseli bunu trojan olarak puanladı: kendini kuran, soket açan, uzak sunucu yoklayan ve süreç başlatan tek dosyalık bir binary dışarıdan bakınca birebir uzaktan erişim aracına benziyor. Bu, kendi derlememiz üzerinde bir false positive'di — ama senden antivirüs istisnası eklemeni istemek yerine paketlemeyi tamamen kaldırdık. Daemon ve hook artık düz `.py` dosyaları olarak, imzalı ve güvenilen kendi Python yorumlayıcın altında çalışıyor; sezgiselin puanlayacağı bir şey kalmıyor. `cc-telegram-bridge.exe` içeren bir sürümden geliyorsan: o dosyayı ve `Startup\cc-telegram-bridge.lnk`'i sil, `setup.ps1`'i tekrar çalıştır.

**Güncellemeden sonra bildirimler kesildi.** Plugin'ler session açılırken yüklenir. Claude Code Desktop'ı bir kez yeniden başlat ki açık her sohbet güncel hook'ları alsın.

**Bir sohbet hiç bildirim atmıyor.** Klasör adının `IGNORE_CWD_SUBSTRINGS` ile eşleşmediğini kontrol et, sonra yukarıdaki health komutuyla daemon'ın ayakta olduğunu doğrula.

## Platform notları

[docs/platform-notes.md](docs/platform-notes.md), bu köprüyü inşa ederken Claude Code Desktop hakkında **ölçülen** şeyleri kaydediyor: hook/plugin yükleme farkı, iki ayrı session-id uzayı, iletilen mesajın ne olup ne olmadığı ve imkânsız çıkan birkaç yol. Köprüyü genişletmeden veya benzer bir şey yazmadan önce okumaya değer.

## Güvenlik bildirimi

Bir açık bulursan: [SECURITY.md](SECURITY.md) — hassas bildirimler GitHub'ın özel güvenlik bildirim kanalından iletilir.

## Lisans

[MIT](LICENSE) — © 2026 Ozan Eşki.
