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

## 2. Bina ve ekonomi sistemi yeniden düşünülmeli

Somut durum: 4 üretim binası çalışıyor. 6 "gelişmiş bina"nın 4'ü hiçbir işe
yaramıyor — oyuncu para veriyor, inşaatı bekliyor, bina ekranda duruyor, ama
hiçbir etkisi yok.

Ama asıl sorun bu değil. **Asıl soru şu: bu sistem 3 ay boyunca ilgi çekici
mi?**

Şu an oyuncunun verdiği tek karar "hangi binayı yükselteyim". Ekonomi bu karar
gerçekten anlamlı olsun diye hesaplanarak dengelendi — her bina kendini aynı
sürede geri ödüyor. Ama tek çeşit karar, 3 ay boyunca tekrar ediyor.

Beklentimiz, gelen kişinin şunu değerlendirmesi:

- Mevcut sistem üzerine mi inşa etmeli, yoksa bina mantığı baştan mı
  kurgulanmalı?
- 4 boş bina neyle doldurulmalı — yoksa silinip yerine başka bir mekanik mi
  gelmeli?
- Oyuncuyu 3 ay boyunca tutacak olan ne? Şu an cevabı yok.

**Bu bir denge ayarı işi değil, tasarım işi.** Kod tarafı ikinci aşama.

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
- **Ortak pazar**: 30 kişi aynı deftere satıyor. Biri çok satınca fiyat
  düşüyor, zamanla toparlanıyor. Oyunun en sağlam parçası bu.
- Bina inşası, yükseltme, üretim, satış — ana döngü
- **Cihazlar arası kayıt**: telefonda oyna, bilgisayarda devam et
- Öğretmen kontrolleri: sınıfı durdur, piyasaya şok ver, oyuncu sıfırla
- Canlı sıralama ve oyuncu listesi (`class.html`)
- Sunucu güvenliği

# ÇALIŞTIRMA

```bash
python3 server.py 3000
```

Kurulum yok, build yok, framework yok. Sadece Python 3.9.

`/class.html` sınıf açar, `/join.html` oyuncu girişi, oyun sayfaları
`/collect.html`, `/produce.html`, `/marketplace.html`.

# İŞE BAŞLAMADAN ÖNCE

Kod tarafında bilinmesi gereken üç kritik konu var — özellikle **ekonomi
sayılarını değiştirmeden önce** okunmalı. Ayrı dosyada: `TEKNIK-NOTLAR.md`

Kısaca: ekonomi sayıları elle ayarlanmadı, hesaplandı. Tek bir sayıyı
değiştirmek dengeyi bozar ve **hata mesajı vermez.**

# TASARIMDA KORUNMASI GEREKENLER

- **Build sistemi yok, olmayacak.** React/webpack yok; düz HTML dosyaları.
- **Görsel dil bitmiş durumda**: siyah zemin, amber sarısı, terminal yazı tipi,
  keskin köşeler. Yuvarlak köşeli modern arayüze çevirmeyin.
