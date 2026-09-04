# YOMAMA INVESTMENTS — Geliştirici Devir Belgesi

Bu belge, projeyi devralacak geliştirici için yazıldı. Kısa tutuldu; sizi
yanıltabilecek yerler ⚠️ ile işaretlendi. Kod değiştirmeden önce okuyun.

---

## Proje nedir

Yaklaşık 30 kişilik bir grubun **aynı piyasayı paylaşarak** oynadığı, bir dönem
(~3 ay) boyunca kesintisiz çalışacak şekilde tasarlanmış bir tarayıcı oyunu.

Oyuncu küçük bir üretim üssü işletir (binalar → kaynaklar → ürünler), ürünleri
**ortak pazara** satar — fiyatlar herkesin arzına göre hareket eder — ve
kazandığı parayı yatırıma yönlendirir.

Yarı finans terminali, yarı tycoon oyunu. Görsel dil bilinçli olarak seçildi ve
tamamlanmış durumda; "Bozulmaması gerekenler" bölümüne bakın.

## Nasıl çalıştırılır

```bash
python3 server.py 3000
```

Build adımı yok, paket kurulumu yok, framework yok. Yalnızca Python 3.9+
standart kütüphanesi. Komut, diğer cihazların bağlanacağı yerel ağ adresini
ekrana yazar.

| Sayfa | İşlev |
|---|---|
| `/class.html` | Sınıf açma konsolu: kod üretir, canlı liste gösterir |
| `/join.html` | Oyuncu girişi: sınıf kodu + isim + 4 haneli PIN |
| `/collect.html` | Üs ve binalar |
| `/produce.html` | Üretim reçeteleri |
| `/marketplace.html` | Ortak pazar |

## Mimari

Düz HTML sayfaları + tek bir paylaşılan `app.js` (335KB, elle yazılmış) +
`styles.css`. Bundler yok. Sayfalar birbirinden bağımsız; ortak durum sunucu
üzerinden akar.

| Dosya | Rolü |
|---|---|
| `server.py` | Statik dosya sunumu (izin listeli), haber/döviz proxy'leri, API yönlendirme |
| `game_api.py` | Otoriter olması gereken tüm oyun mantığı. SQLite. |
| `yomama-net.js` | Oyun API'siyle konuşan **tek** dosya |
| `app.js` | Bina/ekonomi simülasyonu ve arayüzün büyük kısmı |
| `marketplace.js`, `produce.js` | Sayfaya özel mantık |
| `config/economy.v0.1.json` | Tüm ekonomi ayarları |

**Kritik ayrım:**

- **Sunucu sahibi** (`game.db` içinde): nakit, ürün envanteri, hisse
  pozisyonları, pazar fiyatları ve stok, sıralama tablosu, oyuncu listesi.
  Bunlar puanlamaya girdiği için tarayıcıdan değiştirilebilir olmamalı.
- **İstemci sahibi**: bina seviyeleri, inşaat süreleri, kaynaklar. Tarayıcıda
  simüle edilir, sonra sunucuya tek parça halinde senkronlanır.

Oturum yoksa veya sunucuya ulaşılamıyorsa her sayfa eski localStorage
davranışına düşer; oyun çalışmaya devam eder.

---

# İSTENEN İŞ

Üç başlık. Yetenek ağacı (`focus-tree.html`) **kapsam dışıdır**, dokunulmayacak.

## 1. Bina mantıklarının tamamlanması

Altı gelişmiş binanın **dördü hiçbir şey yapmıyor.** Kaynak ve nakit
harcatıyor, inşa süresi işletiyor, arayüzde yer kaplıyor — ama hiçbir etkileri
yok.

| Bina | Durum |
|---|---|
| `contractor_office` | ✅ Seviye başına +1 inşaat ekibi |
| `automation` | ✅ Çevrimdışı üretim süresini uzatıyor |
| `hq` | ❌ Etkisi yok |
| `warehouse` | ❌ **Depo limiti hiçbir yerde uygulanmıyor** |
| `logistics` | ❌ Etkisi yok |
| `marketplace` | ❌ Etkisi yok |

`logistics` ve `marketplace` 335KB'lık `app.js` içinde **birer kez** geçiyor.
Depo mekaniği tamamen dekoratif: kaynaklar hiçbir üst sınıra takılmıyor.

Yapılacak: bu dört binanın ne yapacağının **tasarlanması**, uygulanması ve
maliyetlerinin yeniden türetilmesi. Not: mevcut maliyet modeli yalnızca dört
üretim binası için türetildi; gelişmiş binalara sabit bir çarpan uygulandı.

## 2. Sınıfla test edilebilir hale getirme

Giriş akışı, oyuncu listesi, ortak pazar, öğretmen kontrolleri ve cihazlar
arası kayıt **çalışıyor ve test edildi**. Eksik olanlar:

- **Yayına alma**: HTTPS, `ThreadingHTTPServer` önüne gerçek bir web sunucusu
  (Caddy önerilir), `game.db` için gecelik yedek, servis yöneticisi (systemd).
- **`teach.html`**: 815 satır, 52 handler — arayüz hazır, ama verisi sahte.
  Tohumlanmış bir PRNG'den üretilen 54 uydurma öğrenci gösteriyor. Gerçek API'ye
  bağlanması gerekiyor.

## 3. Gerçek hisse fiyatları

Şu an hisse fiyatları sunucuda tohumlanmış rastgele yürüyüşle üretiliyor
(`game_api.py` içindeki `equity_price`). Gerçek fiyatlarla değiştirilecek.

**Kaynak hazır ve çalışıyor.** `server.py` içinde döviz için kullanılan
TradingView uç noktası hisseler için de veri dönüyor:

```
NASDAQ:AAPL   close=328.21
NASDAQ:NVDA   close=228.45
AMEX:SPY      close=773.17
```

`fetch_fx_quote` fonksiyonundaki kalıp aynen kullanılabilir. Gereken:
önbellekleme (her istekte dış servise gidilmemeli), internet kesildiğinde
yedek davranış, ve tatil/kapanış saatlerinin ele alınması.

---

## ⚠️ Ekonomi türetilmiş bir sistemdir — tek bir sayıyı elle değiştirmeyin

`config/economy.v0.1.json` içindeki maliyetler elle seçilmedi, **hesaplandı**:

```
bir yükseltmenin nakit maliyeti = getirdiği ek gelir × 40 gün
```

Her binanın kendini aynı sürede amorti etmesi, dört binanın da dönem boyunca
yaklaşık eşit sayıda yükseltilmesi ve üssün ~91. günde tamamlanması bu yüzden.
Girdilerden birini değiştirmek diğerlerini sessizce bozar:

- **Bina üretimleri, reçetelerin tükettiği orana göre ayarlandı.** Bir üretim
  merdivenini değiştirirseniz kaynaklar yeniden israf olmaya başlar.
- **Ürün fiyatları, her kaynağın değerini belirler.** Bunlar beş reçeteli bir
  doğrusal programın gölge fiyatları; arz bu değeri değiştirmez. Hydro Lettuce
  fiyatı 11,88 → 21,18 olarak güncellendi, çünkü aksi halde gıdanın birim
  değeri 0,04 dolarda kalıyor ve çiftlik işlevsiz bir binaya dönüşüyordu.
- **Döngü süreleri ile nakit maliyetler birbirine bağlı.** Gelir döngü hızıyla
  doğru orantılı; `cycleMinutes` yarıya inerse gelir ikiye katlanır ve tüm
  maliyetlerin buna göre kayması gerekir.

Denge değişikliği gerekiyorsa beş reçete üzerinden doğrusal programı yeniden
çözün; sezgiyle sayı oynatmayın. Hedeflenen his: üs dönemin sonuna doğru
tamamlanır, her gün oynayan bitirir, haftada bir oynayan yarı yola gelir.

## ⚠️ Cihazlar arası kaydın dört kuralı

Binalar ve kaynaklar `/api/game/buildings` üzerinden senkronlanır. Kırılması
kolaydır; aşağıdakilerin her biri gerçekten yaşanmış birer hatadır:

1. **Senkron tamamlanmadan sunucuya yazmayın.** Yeni açılan ikinci bir cihaz,
   boş başlangıç durumunu gerçek kaydın üzerine yazar. `pushBuildings` bu yüzden
   senkron bitene kadar hiçbir şey göndermez.
2. **Sunucudan gelen kaydı uygulamak için `location.reload()` kullanmayın.**
   `app.js` kendi asenkron başlatmasını tamamlayıp bellekteki varsayılanları
   yeni alınan kaydın üzerine yazar; sayfa yenilendiğinde varsayılanlar okunur.
   Bunun yerine sayfalar `await YomamaNet.ready()` beklemeli.
3. **`getPlayerSave()` sonucu bellekte tutar.** Sunucudan kayıt alındığında
   `playerSaveState` temizlenmezse, gelen veri localStorage'da durur ama hiç
   okunmaz.
4. **Zaman damgası, gönderim anına değil değişim anına ait olmalı.** Aksi halde
   eski bir cihazda oyunu açmak bile o cihazı "daha yeni" gösterir ve diğer
   cihazdaki gerçek ilerlemeyi sessizce geri alır.

`produce.js` kaynaklarını `ready()` beklemeden okuyor. Normal akış güvenli
(girişten sonra önce `collect.html` açılıyor ve senkron orada tamamlanıyor),
ama temiz bir tarayıcıda doğrudan `produce.html` açılırsa kısa süreli eski veri
görünebilir. Kapatılması iyi olur.

## Şu an çalışmayan kısımlar

| Alan | Durum |
|---|---|
| `teach.html` | Sahte veri (bkz. İstenen İş #2) |
| `memos.html` | Sıralama tablosu, kurgusal karakterlerin rastgele oynatıldığı bir animasyon. Gerçek sıralama API'de ve `class.html` içinde. |
| `focus-tree.html` | Statik HTML. 85 düğüm, durum yok, maliyet yok. **Kapsam dışı.** |
| `port_trading.html` | 2646 satır, arayüz hazır; fiyat kaynağı yok, pozisyon değerleri oyuncunun elle girdiği sayıdan geliyor. |
| Üretim doğrulaması | Üretim istemcide simüle ediliyor. `/api/game/produce` sınır koyuyor (400 birim + saatte 120) ama bu sınır içinde şişirme mümkün. |
| PIN'ler | Veritabanında açık metin. Tanıdık bir grup için sorun değil, halka açık kullanım için zayıf. |

## Bozulmaması gerekenler

- **Build adımı yok.** Düz dosyalar, doğrudan açılabiliyor. Böyle kalsın; React
  veya bundler eklemek bu projenin çalışma modelini bozar.
- **Görsel dil tamamlanmış durumda**: siyaha yakın zemin, amber vurgu, kazanç
  için yeşil / kayıp için kırmızı, VT323 terminal yazı tipi, sıfır köşe
  yuvarlaklığı, yoğun yerleşim. Yuvarlak kartlı "modern fintech" görünümüne
  çevirmeyin, gradient eklemeyin.
- **`server.py` içindeki statik dosya izin listesi.** Bu liste var, çünkü sunucu
  daha önce `game.db` (oyuncu isimleri, oturum anahtarları, öğretmen anahtarı),
  `.git/` klasörünü ve yedek arşivlerini isteyen herkese veriyordu. Bilinçli
  olarak *izin listesi* (whitelist); yasak listesi olsaydı klasöre eklenen her
  yeni dosya otomatik olarak yayına çıkardı.
- **Sunucu otoritesi.** Sıralama tablosuna giren her değer sunucuda
  hesaplanmalı.

## Test

Otomatik test paketi yok. Davranış, Playwright ile gerçek tarayıcılar
sürülerek doğrulandı: giriş akışları, cihazlar arası kayıt, alım-satım
döngüsü, yük altında fiyat hareketi ve statik dosya izin listesi.

Yazılması gereken: özellikle kayıt senkronizasyonu için regresyon testi —
yukarıdaki dört kuralın hiçbirini koruyan bir test şu an mevcut değil.

Ekonomi değişikliklerinde faydalı kontrol: config üzerinden 91 günlük oyun
simüle edip üssün hâlâ 85–91. gün civarında, dört bina da yaklaşık eşit
yükseltilmiş halde tamamlandığını doğrulayın.
