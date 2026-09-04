# YOMAMA INVESTMENTS — İş Tanımı

## Proje tek cümlede

30 kişilik bir grubun aynı pazarı paylaşarak, 3 ay boyunca kesintisiz oynadığı
bir tarayıcı oyunu: fabrika kur, ürün üret, ortak pazarda sat, kazancı borsada
değerlendir.

Oyun **şu an çalışıyor.** Girip oynayabilirsiniz. Üç eksik iş var.

---

# YAPILMASINI İSTEDİĞİM 3 İŞ

## İş 1 — Çalışmayan 4 binayı çalışır hale getir

Oyunda 6 tane "gelişmiş bina" var. **4'ü hiçbir işe yaramıyor.** Oyuncu para
veriyor, inşaat süresini bekliyor, bina ekranda görünüyor — ama hiçbir etkisi
olmuyor.

| Bina | Durum |
|---|---|
| Müteahhit Ofisi | ✅ Çalışıyor (aynı anda daha çok inşaat yapılmasını sağlıyor) |
| Otomasyon | ✅ Çalışıyor (oyuncu yokken üretimin devam etme süresini uzatıyor) |
| Merkez Bina (HQ) | ❌ Hiçbir şey yapmıyor |
| Depo | ❌ Hiçbir şey yapmıyor (depo limiti diye bir şey yok) |
| Lojistik | ❌ Hiçbir şey yapmıyor |
| Pazar Binası | ❌ Hiçbir şey yapmıyor |

**Yapılacak:** Bu 4 binanın ne işe yarayacağını tasarla ve kodla. Sonra
fiyatlarını dengele (fiyatlama yöntemi aşağıda "Dikkat 1"de anlatılıyor).

**Not:** Bu üç işin en büyüğü. Tasarım kararı da içeriyor, sadece kodlama değil.

## İş 2 — Sınıfla test edilebilir hale getir

İki parçası var:

**a) Sunucuya al.** Oyun şu an sadece benim bilgisayarımda, aynı wifi'daki
cihazlar bağlanabiliyor. İnternete açılması lazım: HTTPS, sunucunun sürekli
ayakta kalması, veritabanının her gece yedeklenmesi.

**b) Öğretmen ekranını gerçek veriye bağla.** `teach.html` sayfasının arayüzü
hazır ve güzel görünüyor — ama gösterdiği öğrenciler **uydurma**. Kodun içine
yazılmış 54 sahte isim var. Gerçek oyuncu verisine bağlanması gerekiyor.
(Veriyi veren API zaten yazılmış durumda.)

## İş 3 — Borsayı gerçek fiyatlara bağla

Oyunda hisse alıp satılabiliyor ama fiyatlar sahte, rastgele üretiliyor.
Gerçek fiyatlara bağlanacak.

**Bu iş kolay olmalı:** Gerekli veri kaynağı projede zaten var ve çalışıyor
(döviz kuru için kullanılıyor). Aynı kaynak hisse fiyatı da veriyor, test
ettim:

```
AAPL  328.21      NVDA  228.45      SPY  773.17
```

**Yapılacak:** Sahte fiyat üretimini bu kaynakla değiştir. Her istekte dış
servise gitmemek için önbellek koy. İnternet kesilirse veya borsa kapalıysa ne
olacağını çöz.

---

## KAPSAM DIŞI

**Yetenek ağacı (`focus-tree.html`) — dokunulmayacak.** Boş bir sayfa, 85
düğüm var ama hiçbiri çalışmıyor. Şimdilik böyle kalacak.

---

# ŞU AN NELER HAZIR

Bunlara dokunmanıza gerek yok, çalışıyor ve test edildi:

- Oyuncu girişi (sınıf kodu + isim + PIN), tekrar giriş, aynı isim çakışması
- 30 kişinin aynı anda alışveriş yaptığı ortak pazar — biri çok satınca fiyat
  düşüyor, sonra toparlanıyor
- Sıralama tablosu, canlı oyuncu listesi
- Öğretmen kontrolleri: sınıfı durdur/başlat, piyasaya şok ver, oyuncu sıfırla
- **Cihaz değiştirince ilerlemenin kaybolmaması** (telefonda oyna, bilgisayarda
  devam et)
- Bina inşası, yükseltme, üretim, satış — yani oyunun ana döngüsü
- Sunucu güvenliği: dosya sızıntısı kapatıldı

---

# PROJEYİ ÇALIŞTIRMA

```bash
python3 server.py 3000
```

Kurulum yok, `npm install` yok, build yok. Sadece Python 3.9 gerekiyor.
Komut çalışınca ekrana adres yazar.

Sayfalar: `/class.html` (sınıf aç), `/join.html` (oyuncu girişi),
`/collect.html` (üs), `/produce.html` (üretim), `/marketplace.html` (pazar).

---

# DİKKAT — 3 TUZAK

Bunları bilmeden kod değiştirirseniz oyunu bozarsınız ve **hata mesajı
almazsınız.**

## Dikkat 1 — Ekonomi rastgele ayarlanmış sayılardan ibaret değil

`config/economy.v0.1.json` içindeki fiyatlar elle yazılmadı, hesaplandı.
Formül şu:

> Bir yükseltmenin fiyatı = o yükseltmenin kazandırdığı günlük gelir × 40 gün

Yani her bina kendini aynı sürede geri ödüyor. Oyuncunun "hangi binayı
yükseltsem" diye gerçekten düşünmesi bu yüzden. Üssün tam olarak dönem sonunda
(91. gün) bitmesi de bu yüzden.

**"Şu bina pahalı, biraz ucuzlatayım" derseniz bu denge bozulur.** Hata vermez,
oyun çalışmaya devam eder, ama aylar sonra oyun anlamsız hale gelir.

Bağlı olan üç şey: bina üretim miktarları, ürün satış fiyatları, üretim döngü
süreleri. Birini değiştirirseniz diğerlerini yeniden hesaplamanız gerekir.

## Dikkat 2 — Cihaz değiştirince ilerleme kaybolmaması hassas bir mekanizma

Oyuncunun binaları ve kaynakları tarayıcıda tutuluyor, sonra sunucuya
gönderiliyor. Bu senkronizasyonun 4 kuralı var ve **dördü de daha önce gerçekten
bozuldu.** `yomama-net.js` dosyasında bu kısma dokunacaksanız:

1. Sunucudan veri gelmeden sunucuya veri gönderme. Yeni açılan ikinci bir cihaz
   boş verisini gerçek kaydın üzerine yazar.
2. Sunucudan gelen kaydı uygulamak için sayfayı yenileme (`location.reload`).
   Çalışmıyor — oyun kendi eski verisini geri yazıyor. Bunun yerine
   `await YomamaNet.ready()` beklenmeli.
3. `getPlayerSave()` sonucu hafızada tutuyor. Sunucudan yeni kayıt gelince bu
   hafızayı temizlemezseniz gelen veri hiç okunmaz.
4. Zaman damgası "kaydı ne zaman gönderdim" değil, "veri ne zaman değişti"
   olmalı. Yoksa eski bir cihazda oyunu açmak bile diğer cihazdaki ilerlemeyi
   siler.

## Dikkat 3 — Sunucu neyin doğru olduğuna karar verir

Puanlamaya giren her şey (para, envanter, hisseler, sıralama) sunucuda tutulur
ve orada hesaplanır. Tarayıcıya güvenilmez, çünkü oyuncu tarayıcıdaki değerleri
değiştirebilir.

Yeni bir özellik eklerken puanı etkiliyorsa sunucuda hesaplayın.

---

# DOKUNMAYIN

- **Build sistemi eklemeyin.** React, Vue, webpack yok ve olmayacak. Düz HTML
  dosyaları, çift tıklayınca açılıyor. Projenin çalışma mantığı bu.
- **Görsel tasarımı değiştirmeyin.** Siyah zemin, amber sarısı, terminal yazı
  tipi, köşeleri keskin kutular. Bilinçli bir tercih ve bitmiş durumda.
  Yuvarlak köşeli modern arayüze çevirmeyin.
- **`server.py` içindeki dosya izin listesini gevşetmeyin.** O liste var, çünkü
  sunucu daha önce oyuncu isimlerinin ve şifrelerinin olduğu veritabanı
  dosyasını isteyen herkese veriyordu.

---

# BİLİNEN EKSİKLER (kapsam dışı, bilginiz olsun)

| Ne | Durum |
|---|---|
| `memos.html` sıralama sayfası | Sahte animasyon. Gerçek sıralama `class.html`'de. |
| `port_trading.html` | Arayüz hazır, fiyat kaynağı yok |
| PIN'ler | Veritabanında açık yazıyor. Tanıdık grup için sorun değil. |
| Üretim doğrulaması | Üretim tarayıcıda hesaplanıyor, sınırlı da olsa hile mümkün |
| Otomatik test | Yok. Test için gerçek tarayıcı sürüldü (Playwright). |
