> **Durum (2026-09-12):** Bu belgeden sonra çok şey değişti: ekonomi v4'e geçti (`ECONOMY_README.md`),
> sınıflar artık `class.html`'den değil geliştiricinin `admin.py` komutuyla açılıyor, hiçbir sayfa
> oturum açmadan sunulmuyor ve sunucu Render'da çalışıyor (`DEPLOY.md`). Önce `AGENTS.md`'yi okuyun;
> aşağıdaki v1 ekonomisi ve `class.html` anlatımı tarihseldir.

# Teknik Notlar

İşe başlayan geliştirici için. `HANDOVER.md` işin ne olduğunu anlatır; bu dosya
kodun içinde sizi yanıltacak yerleri anlatır.

Buradaki konuların ortak özelliği: **yanlış yaparsanız hata mesajı almazsınız.**

Ekonominin nasıl çalıştığı ayrı bir dosyada: `ECONOMY_README.md`.

---

## 1. Ekonomi sunucuda ve tek bir config dosyasından geliyor

| Dosya | Rolü |
|---|---|
| `config/economy.v1.json` | Bütün sayılar. Binalar, maliyetler, vergi dilimleri, süreler. |
| `economy.py` | Kurallar. Referans motorun satır satır Python çevirisi. |
| `engine/economy-engine.reference.js` | Referans motor. Yuvarlama ve işlem sırasında son söz bunundur. |
| `game_api.py` | Saklama, sınıf saati, uç noktalar. Kendi başına hiçbir kural içermez. |
| `econ.js` | Tarayıcı. Niyet gönderir, geleni gösterir, para hesaplamaz. |

**Kural:** hiçbir ekonomi sayısı `.py` veya `.js` içine yazılmaz. Yeni bina
eklemek ya da vergi dilimini değiştirmek sadece config düzenlemesidir.

**Sınıf başlarken config'in kopyasını alır** (`sessions.econ_config`). Dosyayı
sonradan değiştirmek yalnızca yeni sınıfları etkiler, devam eden sınıfı asla.
Bu bilinçli: kuralları ortasında değişen bir dönem adil değerlendirilemez.

Eski `config/economy.v0.1.json` silindi. Sayıları geçersiz; hiçbir yerden
okunmamalı.

---

## 2. Tik döngüsü: 15 saniye, tek tek oynatılır

Tik 0, öğretmenin sınıfı açtığı andır. Sınıf duraklatılınca sınıf saati de
durur, yani duraklatma gerçekten her öğrencinin üretimini dondurur.

Oyuncunun durumu, en son hesaplandığı tikle birlikte saklanır. İstek geldiğinde
şimdiye kadar **tik tik** oynatılır.

**Kapalı form kısayolu yazmayın.** Her tikte tam sayıya yuvarlama var; ekonomi
tam olarak o yuvarlamadır. Bir günü oynatmak ~40 ms sürüyor, otuz kişilik bir
sınıfın sabah aynı anda girmesi toplam ~1 saniye.

İstek başına en fazla 30 gün oynatılır (`MAX_CATCHUP_DAYS`). Daha uzun süre
girmemiş oyuncu sonraki isteklerde yetişir; bu sırada cevapta `behind: true`
döner.

**Fiyatlar** sınıf başına tek akıştır, sınıf tohumundan üretilir: bütün
öğrenciler aynı piyasayı görür ve dönem birebir tekrar oynatılabilir. Akışlar
günlük bloklar hâlinde, ihtiyaç oldukça üretilir (`economy.PriceBook`).

**Bir tik kayma var ve kasıtlı:** `state.tick` anındaki çarpan, akışın
`tick - 1` indeksidir. Önce saat ilerler, sonra ticaret az önce terk edilen
tikin fiyatından yapılır.

---

## 3. JS motorunu Python'a çevirirken dikkat edilenler

Hepsi sessizce yanlış sonuç üretir:

- **`Math.round` ≠ Python `round()`.** JavaScript yarımları yukarı yuvarlar,
  Python çifte yuvarlar (`round(2.5) == 2`). Her yerde `economy.jsround`
  kullanılır.
- **JSON'dan dönen anahtarlar metindir.** `pend` ve `unlock` sözlüklerinde
  anahtarlar `"0"`, `"1"` şeklindedir. `int` ile `str` karıştırmak, dolu bir
  deponun boş görünmesi demektir.
- **Fiyatlar float32.** Referans `Float32Array` kullanıyor; Python tarafında
  `array('f')`. float64 saklamak satış tutarlarını kaydırır.
- **RNG bit düzeyinde aynı.** xorshift32, 32 bitlik maskelerle.
- **`autoContinue` açık olduğu için `bot_buy` sunucuda.** Görev tanımı onu
  testlerde tutmayı söylüyordu, ama `_finish_build` onu çağırıyor: sunucuda
  olmasaydı referans motorla arası açılırdı. Yalnızca oyuncu yokken biten
  inşaatta çalışır.

Doğrulama: `python3 tests/run_tests.py` (kurulum gerektirmez).

---

## 4. Sunucu otoritesi

Puanlamaya giren her şey sunucuda tutulur ve orada hesaplanır: para, depo,
üretim, fiyatlar, vergi, sıralama.

Sebep basit: tarayıcıdaki hiçbir değere güvenilemez. Oyuncu geliştirici
araçlarını açıp parasını değiştirebilir.

Prototipteki açık kapandı: üretim artık tarayıcıda hesaplanmıyor, saatlik
depozito sınırına da gerek kalmadı.

**Yeni özellik eklerken:** sıralamayı etkiliyorsa sunucuda hesaplayın.

---

## 5. Cihazlar arası kayıt (artık sadece görünüm verisi)

Ekonomi sunucuda olduğu için para açısından bu mekanizma devre dışı. Ama
karakter seçimi gibi görünüm verileri hâlâ `yomama-net.js` üzerinden tek parça
gidiyor. Oraya dokunacaksanız aşağıdaki dördü **daha önce gerçekten bozuldu**:

**a) Sunucudan veri gelmeden sunucuya veri göndermeyin.** Yeni açılan ikinci bir
cihaz, boş başlangıç durumunu gerçek kaydın üzerine yazar.

**b) Gelen kaydı uygulamak için sayfayı yenilemeyin.** Doğrusu:
`await YomamaNet.ready()` beklemek.

**c) `getPlayerSave()` sonucu bellekte tutuyor.** Sunucudan yeni kayıt
geldiğinde temizlenmezse ekranda hiçbir şey değişmez, hata da vermez.

**d) Zaman damgası "veri ne zaman değişti" olmalı**, "ne zaman gönderdim"
değil.

---

## 6. Dosya düzeni

| Dosya | Rolü |
|---|---|
| `server.py` | Statik dosya sunumu, dış servis proxy'leri, API yönlendirme |
| `game_api.py` | Sunucu tarafı oyun mantığı, SQLite (`game.db`) |
| `economy.py` | Ekonomi motoru (Part 1) |
| `config/economy.v1.json` | Bütün ekonomi sayıları |
| `config/quiz.json` | Lisans sınavı — **sorular şu an yer tutucu** |
| `econ.js` | Ekonomi ekranlarının tamamı |
| `yomama-net.js` | Oturum, Part 2 hisse işlemleri, görünüm blobu |
| `app.js` | Arayüzün geri kalanı: şerit, saat, haber masası, memo, karakter |
| `tests/` | Ekonomi testleri ve altın dosyalar |

Oyun sayfaları: `/buildings.html`, `/warehouse.html`, `/marketplace.html`,
`/advanced-hq.html`, `/license.html`. `/collect.html`, `/produce.html` ve
`/focus-tree.html` emekliye ayrıldı: dosyalar duruyor ama menüde yoklar.

Sunucu veya oturum yoksa ekonomi ekranları "bir sınıfa katıl" der; oyunun geri
kalanı çalışmaya devam eder.

---

## 7. Güvenlik

`server.py` içinde statik dosya **izin listesi** var. Bu liste olmadan sunucu,
`game.db` (oyuncu isimleri, oturum anahtarları, öğretmen anahtarı), `.git/`
klasörü ve yedek arşivleri dahil klasördeki her şeyi isteyen herkese veriyordu.

Bilinçli olarak izin listesi: yasak listesi olsaydı klasöre eklenen her yeni
dosya otomatik yayına çıkardı.

---

## 8. Test

Ekonominin testi var ve kurulum gerektirmez:

```bash
python3 tests/run_tests.py
```

Arayüz tarafında otomatik test yok; doğrulama Playwright ile gerçek tarayıcı
sürülerek yapıldı. En çok ihtiyaç duyulan: giriş akışı ve ekonomi ekranları için
tarayıcı testi.
