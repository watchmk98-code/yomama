> **Durum (2026-09-12):** Bu belgeden sonra çok şey değişti: ekonomi v4'e geçti (`ECONOMY_README.md`),
> sınıflar artık `class.html`'den değil geliştiricinin `admin.py` komutuyla açılıyor, hiçbir sayfa
> oturum açmadan sunulmuyor ve sunucu Render'da çalışıyor (`DEPLOY.md`). Önce `AGENTS.md`'yi okuyun;
> aşağıdaki v1 ekonomisi ve `class.html` anlatımı tarihseldir.

# YOMAMA INVESTMENTS — Ne arıyoruz

## Proje

30 kişilik bir grubun aynı pazarı paylaşarak, bir dönem boyunca (~3 ay)
oynadığı bir tarayıcı oyunu. Fabrika kur, üret, ortak pazarda sat, kazancını
değerlendir. Hem oyun hem finans dersi aracı.

Oyunun temel döngüsü **çalışıyor**. Girip oynayabilirsiniz. Ama oyunun yarısı
eksik ve diğer yarısı da yeniden düşünülmeye muhtaç.

## Aradığımız kişi

Sadece verilen listeyi kodlayacak biri değil. **Oyunun kendisi hakkında
düşünebilecek** biri. Aşağıdaki üç alanın ikisi tasarım sorusu; kod bunun
sonrasında geliyor.

---

# ÜZERİNDE ÇALIŞILACAK 3 ALAN

## 1. Yatırım tarafı hiç yok

Oyunun adı **INVESTMENTS**. Ama oyuncu kazandığı parayla şu an sadece bina
yükseltebiliyor. Hisse alıp satamıyor.

Altyapının bir kısmı hazır: sunucuda alım-satım ve portföy mantığı yazılmış ve
çalışıyor. Eksik olan, oyuncunun bunu kullanabileceği ekran ve bu kısmın oyuna
nasıl bağlanacağı.

Cevaplanması gereken sorular kodlamadan önce geliyor:

- Yatırım oyunun neresinde duruyor? Fabrikadan kazanılan para borsaya mı
  gidiyor, yoksa ikisi ayrı yarış mı?
- Gerçek hisse fiyatları mı kullanılsın, simülasyon mu? (Gerçek fiyat verisi
  projede mevcut ve çalışıyor — teknik engel yok, tercih meselesi.)
- Oyunun eğitim amacı burada: oyuncu ne öğrenmeli? Riski mi, sabrı mı,
  çeşitlendirmeyi mi?

**Bu, üç işin en kritik olanı.** Oyunun adını taşıyan kısım eksik.

## 2. Bina ve ekonomi sistemi (v1 ile değiştirildi)

Bu madde büyük ölçüde kapandı. Prototipin ekonomisi — 4 üretim binası,
reçeteler, kaynaklar, ortak sipariş defteri — tamamen kaldırıldı ve yerine
**v1 ekonomisi** kuruldu:

- Aynı anda tek bina. Seviye atlatırsınız, Auto Control alırsınız, sonra bir üst
  binaya **mezun olursunuz** (18 saatlik inşaat, 2 kişilik kuyruk).
- 15 binalık merdiven, artan üretim ve artan maliyet.
- Depo dolunca taşan mal kendiliğinden %10 iskontoyla satılır.
- Gelir arttıkça dilimli vergi devreye girer.
- Fiyatlar sınıf başına tek akıştır: herkes aynı çarpanı görür.
- Dördüncü binaya gelen, seviye 25'e çıkan, Auto Control alan, 10 iyi satış
  yapan ve sınavı geçen oyuncuya **yatırım lisansı** açılır — Part 2'nin kapısı.

Bütün para sunucuda hesaplanıyor, bütün sayılar `config/economy.v1.json`
içinde. Ayrıntı: `ECONOMY_README.md`, teknik tuzaklar: `TEKNIK-NOTLAR.md`.

Geriye kalan tasarım soruları:

- Lisanstan sonra oyuncu 3 ay boyunca neyle meşgul olacak? Merdiven tek başına
  yetmez; asıl cevap Part 2 (yatırım) olmalı.
- `config/quiz.json` içindeki 5 soru **yer tutucu**. Gerçek sorular yazılmalı.
- Sınıfın fiyatı birlikte hareket ettirmesi (prototipin en sağlam parçasıydı)
  v1'de yok. Geri gelecekse bilinçli bir ekleme olarak gelmeli.

## 3. Gerçek bir grupla oynanabilir hale gelmeli

Oyun şu an sadece tek bir bilgisayarda, aynı wifi üzerinden çalışıyor.
İnternete taşınması gerekiyor: sürekli ayakta kalan bir sunucu, HTTPS, veri
yedeği.

Bir de öğretmen ekranı var (`teach.html`): tasarımı hazır ve iyi görünüyor,
ama gösterdiği öğrenciler uydurma. Gerçek oyuncu verisine bağlanması lazım.

Bu üç alanın en net tanımlı ve en öngörülebilir olanı.

---

## KAPSAM DIŞI

**Yetenek ağacı** (`focus-tree.html`) — boş bir sayfa, şimdilik öyle kalacak.

---

# ŞU AN ÇALIŞAN KISIMLAR

Bunlar bitti ve test edildi, üzerine inşa edilebilir:

- Oyuncu girişi: sınıf kodu + isim + PIN, cihaz değiştirince aynı hesaba dönüş
- **v1 ekonomisi**: bina, seviye, Auto Control, mezuniyet, depo, vergi, lisans —
  tamamı sunucuda, testleriyle birlikte
- **Ortak fiyat akışı**: sınıftaki herkes aynı çarpanı görür, dönem birebir
  tekrar oynatılabilir
- **Cihazlar arası oyun**: durum sunucuda olduğu için telefonda oyna,
  bilgisayarda devam et
- Öğretmen kontrolleri: sınıfı durdur (ekonomi de durur), oyuncu sıfırla
- Canlı sıralama, öğrenci başına lisans ilerlemesi (`class.html`)
- Sunucu güvenliği

# ÇALIŞTIRMA

```bash
python3 server.py 3000
```

Kurulum yok, build yok, framework yok. Sadece Python 3.9.

`/class.html` sınıf açar, `/join.html` oyuncu girişi, oyun sayfaları
`/buildings.html`, `/warehouse.html`, `/marketplace.html`, `/advanced-hq.html`,
`/license.html`.

Ekonomi testleri (kurulum gerektirmez):

```bash
python3 tests/run_tests.py
```

# İŞE BAŞLAMADAN ÖNCE

İki dosya var, ikisi de kısa:

- `ECONOMY_README.md` — ekonomi nasıl çalışıyor, tik döngüsü, config nerede,
  testler nasıl çalıştırılır.
- `TEKNIK-NOTLAR.md` — kodun içinde sizi yanıltacak yerler.

Kısaca: ekonomi sayılarının tamamı `config/economy.v1.json` içinde ve hiçbiri
koda yazılmaz. Kuralları değiştirirken referans motor (`engine/`) ile testler
son sözü söyler; testi kırmadan sayı oynatmak **hata mesajı vermez.**

# TASARIMDA KORUNMASI GEREKENLER

- **Build sistemi yok, olmayacak.** React/webpack yok; düz HTML dosyaları.
- **Görsel dil bitmiş durumda**: siyah zemin, amber sarısı, terminal yazı tipi,
  keskin köşeler. Yuvarlak köşeli modern arayüze çevirmeyin.
