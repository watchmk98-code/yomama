# Teknik Notlar

İşe başlayan geliştirici için. `HANDOVER.md` işin ne olduğunu anlatır; bu dosya
kodun içinde sizi yanıltacak yerleri anlatır.

Buradaki üç konunun ortak özelliği: **yanlış yaparsanız hata mesajı almazsınız.**

---

## 1. Ekonomi sayıları hesaplandı, elle yazılmadı

`config/economy.v0.1.json` içindeki nakit fiyatlar şu formülden üretildi:

> Bir yükseltmenin fiyatı = kazandırdığı günlük gelir × 40 gün

Sonucu: her bina kendini aynı sürede geri ödüyor, dört bina da dönem boyunca
yaklaşık eşit sayıda yükseltiliyor, üs 91. gün civarında tamamlanıyor.

Birbirine bağlı üç girdi var:

| Girdi | Değiştirirseniz |
|---|---|
| Bina üretim miktarları | Kaynaklar israf olmaya başlar; bazı binalar anlamsızlaşır |
| Ürün satış fiyatları | Kaynakların değeri değişir; bir bina ölü hale gelebilir |
| Üretim döngü süreleri | Gelir doğru orantılı değişir, tüm fiyatların kayması gerekir |

Örnek: Hydro Lettuce fiyatı 11,88'den 21,18'e çıkarıldı. Sebep, gıdanın birim
değerinin 0,04 dolarda kalması ve çiftliğin yükseltilmesinin hiçbir kazanç
sağlamamasıydı. Tek bir ürün fiyatı, bir binanın işe yarayıp yaramamasını
belirliyor.

**Denge değiştirecekseniz:** beş reçete üzerinden hangi kaynağın ne kadar
değerli olduğunu yeniden hesaplayın, sonra fiyatları o değerden türetin.
Sezgiyle sayı oynatmayın.

**Doğrulama yöntemi:** config üzerinden 91 günlük oyunu simüle edin. Üs 85-91.
gün civarında bitiyorsa ve dört bina da yaklaşık eşit yükseltilmişse denge
korunmuştur.

---

## 2. Cihazlar arası kayıt senkronizasyonu

Oyuncunun binaları ve kaynakları tarayıcıda tutulur, sunucuya tek parça
gönderilir (`/api/game/buildings`). `yomama-net.js` içindeki bu mekanizmaya
dokunacaksanız, aşağıdaki dördü de **daha önce gerçekten bozuldu**:

**a) Sunucudan veri gelmeden sunucuya veri göndermeyin.**
Yeni açılan ikinci bir cihaz, boş başlangıç durumunu gerçek kaydın üzerine
yazar. `pushBuildings` bu yüzden senkron tamamlanana kadar hiçbir şey
göndermez.

**b) Gelen kaydı uygulamak için sayfayı yenilemeyin.**
`location.reload()` işe yaramıyor: `app.js` kendi başlatmasını tamamlayıp
bellekteki eski veriyi yeni gelenin üzerine yazıyor, sayfa yenilenince eski
veri okunuyor. Doğrusu: sayfa `await YomamaNet.ready()` beklemeli.

**c) `getPlayerSave()` sonucu bellekte tutuyor.**
Sunucudan yeni kayıt geldiğinde `playerSaveState` temizlenmezse, gelen veri
localStorage'a yazılır ama hiç okunmaz. Ekranda hiçbir şey değişmez, hata da
vermez.

**d) Zaman damgası "veri ne zaman değişti" olmalı, "ne zaman gönderdim"
değil.**
Aksi halde eski bir cihazda oyunu açmak bile o cihazı daha yeni gösterir ve
diğer cihazdaki gerçek ilerlemeyi sessizce siler.

**Bilinen açık:** `produce.js` kaynaklarını `ready()` beklemeden okuyor. Normal
akışta sorun çıkmıyor (girişten sonra önce `collect.html` açılıyor ve senkron
orada tamamlanıyor), ama temiz bir tarayıcıda doğrudan `produce.html`
açılırsa kısa süre eski veri görünebilir.

---

## 3. Sunucu otoritesi

Puanlamaya giren her şey sunucuda tutulur ve orada hesaplanır: para, ürün
envanteri, hisse pozisyonları, pazar fiyatları, sıralama.

Sebep basit: tarayıcıdaki hiçbir değere güvenilemez. Oyuncu geliştirici
araçlarını açıp parasını değiştirebilir.

Tarayıcıda tutulanlar: bina seviyeleri, inşaat süreleri, kaynaklar. Bunlar
puanlamaya doğrudan girmediği için kabul edilmiş bir risk.

**Yeni özellik eklerken:** sıralamayı etkiliyorsa sunucuda hesaplayın.

**Bilinen açık:** üretim tarayıcıda hesaplanıyor. `/api/game/produce` saatlik
bir üst sınır koyuyor (400 birim + saatte 120) ama bu sınırın içinde şişirme
mümkün. Tam çözüm üretimin sunucuya taşınması.

---

## Dosya düzeni

| Dosya | Rolü |
|---|---|
| `server.py` | Statik dosya sunumu, dış servis proxy'leri, API yönlendirme |
| `game_api.py` | Sunucu tarafı oyun mantığı. SQLite (`game.db`). |
| `yomama-net.js` | Oyun API'siyle konuşan **tek** dosya |
| `app.js` | Bina/ekonomi simülasyonu, arayüzün çoğu (335KB, elle yazılmış) |
| `marketplace.js`, `produce.js` | Sayfaya özel mantık |
| `config/economy.v0.1.json` | Tüm ekonomi ayarları |

Sunucu veya oturum yoksa her sayfa eski localStorage davranışına düşer, oyun
çalışmaya devam eder.

## Güvenlik

`server.py` içinde statik dosya **izin listesi** var. Bu liste olmadan sunucu,
`game.db` (oyuncu isimleri, oturum anahtarları, öğretmen anahtarı), `.git/`
klasörü ve yedek arşivleri dahil klasördeki her şeyi isteyen herkese veriyordu.

Bilinçli olarak izin listesi: yasak listesi olsaydı klasöre eklenen her yeni
dosya otomatik yayına çıkardı.

## Test

Otomatik test yok. Doğrulama, Playwright ile gerçek tarayıcı sürülerek yapıldı:
giriş akışları, cihazlar arası kayıt, alım-satım döngüsü, 30 kişilik yük
altında fiyat hareketi, dosya izin listesi.

En çok ihtiyaç duyulan: kayıt senkronizasyonu için regresyon testi. Yukarıdaki
dört kuralı koruyan hiçbir test şu an mevcut değil.
