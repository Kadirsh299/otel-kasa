from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from openpyxl import Workbook
import io, os
# Kalıcı disk klasörü yoksa otomatik oluştur (502 hatasını çözer)
os.makedirs("/var/data", exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "otel-kasa-2025-gizli-anahtar-degistir")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:////var/data/yeni_kasa.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ============ VERİTABANI MODELLERİ ============
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), default="")
    role = db.Column(db.String(20), default="resepsiyon")
    active = db.Column(db.Boolean, default=True)

class Oda(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    no = db.Column(db.String(10), unique=True, nullable=False)

class Kayit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    oda_no = db.Column(db.String(10), nullable=False)
    musteri_adi = db.Column(db.String(120), default="")
    toplam_tutar = db.Column(db.Float, nullable=False)
    odenen = db.Column(db.Float, default=0)
    tip = db.Column(db.String(30), nullable=False)
    tarih = db.Column(db.DateTime, default=datetime.now)
    personel = db.Column(db.String(80))
    kilitli = db.Column(db.Boolean, default=True)
    notlar = db.Column(db.Text, default="")

    @property
    def kalan(self):
        return round(self.toplam_tutar - self.odenen, 2)

class Gider(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    aciklama = db.Column(db.String(255), nullable=False)
    tutar = db.Column(db.Float, nullable=False)
    tarih = db.Column(db.DateTime, default=datetime.now)
    personel = db.Column(db.String(80))

class Personel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ad_soyad = db.Column(db.String(120), nullable=False)
    gorev = db.Column(db.String(50), default="Genel")
    maas = db.Column(db.Float, default=0)
    ise_giris = db.Column(db.DateTime, default=datetime.now)
    avanslar = db.relationship('Avans', backref='personel', lazy=True)

class Avans(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    personel_id = db.Column(db.Integer, db.ForeignKey('personel.id'), nullable=False)
    tutar = db.Column(db.Float, nullable=False)
    tarih = db.Column(db.DateTime, default=datetime.now)
    aciklama = db.Column(db.String(255), default="")

class Talep(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kayit_id = db.Column(db.Integer, nullable=True)
    talep_tipi = db.Column(db.String(20), default="tutar_degisikligi")
    oda_no = db.Column(db.String(10))
    musteri_adi = db.Column(db.String(120))
    toplam_tutar = db.Column(db.Float)
    odenen = db.Column(db.Float)
    tip = db.Column(db.String(30))
    notlar = db.Column(db.Text)
    tarih_str = db.Column(db.String(20))
    eski_tutar = db.Column(db.Float)
    yeni_tutar = db.Column(db.Float)
    sebep = db.Column(db.Text, nullable=False)
    durum = db.Column(db.String(20), default="Bekliyor")
    tarih = db.Column(db.DateTime, default=datetime.now)
    personel = db.Column(db.String(80))

class Odeme(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kayit_id = db.Column(db.Integer, db.ForeignKey("kayit.id"))
    tutar = db.Column(db.Float, nullable=False)
    tip = db.Column(db.String(30), default="Nakit")
    tarih = db.Column(db.DateTime, default=datetime.now)
    personel = db.Column(db.String(80))
    aciklama = db.Column(db.String(255), default="")

class Log(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tarih = db.Column(db.DateTime, default=datetime.now)
    kullanici = db.Column(db.String(80))
    islem = db.Column(db.String(255))
    detay = db.Column(db.Text, default="")

class Kur(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ay = db.Column(db.String(7), unique=True)
    usd = db.Column(db.Float, default=34.0)
    eur = db.Column(db.Float, default=37.0)

# ============ YARDIMCILAR ============
def giris_yapmis(): return "user_id" in session
def admin_mi(): return session.get("role") == "admin"
def giris_gerek(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*a, **kw):
        if not giris_yapmis(): return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper
def log_yaz(islem, detay=""):
    db.session.add(Log(kullanici=session.get("username","sistem"), islem=islem, detay=detay))
    db.session.commit()

@app.context_processor
def inject_user():
    return dict(current_user={"username":session.get("username",""), "full_name":session.get("full_name",""), "role":session.get("role","")}, giris=giris_yapmis())

# ============ ROTALAR ============
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = User.query.filter_by(username=request.form["username"]).first()
        if u and u.active and check_password_hash(u.password_hash, request.form["password"]):
            session["user_id"] = u.id; session["username"] = u.username; session["full_name"] = u.full_name; session["role"] = u.role
            log_yaz("GİRİŞ", u.username); return redirect(url_for("odalar"))
        flash("Kullanıcı adı veya şifre yanlış!", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    log_yaz("ÇIKIŞ", session.get("username","")); session.clear(); return redirect(url_for("login"))

@app.route("/")
@giris_gerek
def index(): return redirect(url_for("odalar"))

# TAKVİM MANTIĞI EKLENDİ
@app.route("/odalar")
@giris_gerek
def odalar():
    secili_tarih = request.args.get("tarih", datetime.now().strftime("%Y-%m-%d"))
    kayitlar = Kayit.query.filter(Kayit.tarih.like(f"{secili_tarih}%")).order_by(Kayit.oda_no).all()
    odalar_list = Oda.query.all()
    return render_template("odalar.html", kayitlar=kayitlar, odalar=odalar_list, admin=admin_mi(), secili_tarih=secili_tarih)

@app.route("/kayit_ekle", methods=["POST"])
@giris_gerek
def kayit_ekle():
    try:
        toplam = float(request.form["toplam_tutar"].replace(",", ".")); odenen = float(request.form.get("odenen", "0").replace(",", ".") or 0)
    except:
        flash("Geçerli tutar girin!", "danger"); return redirect(url_for("odalar"))
    if odenen > toplam:
        flash("Ödenen tutar toplamdan büyük olamaz!", "danger"); return redirect(url_for("odalar"))
    
    kayit_tarihi = datetime.now()
    secilen_tarih = request.form.get("kayit_tarihi")
    if admin_mi() and secilen_tarih:
        try: kayit_tarihi = datetime.strptime(secilen_tarih, "%Y-%m-%d")
        except: pass

    k = Kayit(oda_no=request.form["oda"], musteri_adi=request.form.get("musteri_adi", ""), 
              toplam_tutar=toplam, odenen=odenen, tip=request.form["tip"], 
              personel=session.get("username"), kilitli=True, notlar=request.form.get("notlar", ""),
              tarih=kayit_tarihi)
    db.session.add(k); db.session.commit()
    log_yaz("KAYIT EKLE", f"{k.oda_no} - {toplam} (Tarih: {kayit_tarihi.strftime('%Y-%m-%d')})")
    flash(f"✅ {k.oda_no} → {toplam} TL kaydedildi. Tarih: {kayit_tarihi.strftime('%d.%m.%Y')}", "success")
    return redirect(url_for("odalar", tarih=secilen_tarih or datetime.now().strftime("%Y-%m-%d")))

@app.route("/kayit_sil/<int:kid>")
@giris_gerek
def kayit_sil(kid):
    if not admin_mi(): flash("Yetkiniz yok!", "danger"); return redirect(url_for("odalar"))
    k = Kayit.query.get_or_404(kid); tarih = k.tarih.strftime("%Y-%m-%d"); db.session.delete(k); db.session.commit()
    log_yaz("KAYIT SIL", f"ID {kid}"); flash("Kayıt silindi.", "success"); return redirect(url_for("odalar", tarih=tarih))

@app.route("/gecmis_kayit_talebi", methods=["POST"])
@giris_gerek
def gecmis_kayit_talebi():
    try:
        toplam = float(request.form["toplam_tutar"].replace(",", ".")); odenen = float(request.form.get("odenen", "0").replace(",", ".") or 0)
    except:
        flash("Geçerli tutar girin!", "danger"); return redirect(url_for("odalar"))
    tarih_str = request.form.get("tarih")
    if not tarih_str: flash("Lütfen bir tarih seçin!", "danger"); return redirect(url_for("odalar"))
    t = Talep(talep_tipi="yeni_kayit", oda_no=request.form["oda"], musteri_adi=request.form.get("musteri_adi", ""), toplam_tutar=toplam, odenen=odenen, tip=request.form["tip"], notlar=request.form.get("notlar", ""), tarih_str=tarih_str, sebep=request.form.get("sebep", "Geçmiş tarihli kayıt"), personel=session.get("username"))
    db.session.add(t); db.session.commit()
    log_yaz("GECMIS KAYIT TALEBI", f"{t.oda_no} - {toplam} TL - Tarih: {tarih_str}")
    flash("✅ Talep ana kullanıcıya gönderildi.", "success"); return redirect(url_for("odalar"))

@app.route("/talep_gonder/<int:kid>", methods=["POST"])
@giris_gerek
def talep_gonder(kid):
    k = Kayit.query.get_or_404(kid)
    try: yeni = float(request.form["yeni_tutar"].replace(",", "."))
    except: flash("Geçerli tutar!", "danger"); return redirect(url_for("odalar"))
    sebep = request.form["sebep"].strip()
    if not sebep: flash("Sebep zorunlu!", "danger"); return redirect(url_for("odalar"))
    t = Talep(kayit_id=kid, oda_no=k.oda_no, eski_tutar=k.toplam_tutar, yeni_tutar=yeni, sebep=sebep, personel=session.get("username"))
    db.session.add(t); db.session.commit()
    log_yaz("TALEP", f"{k.oda_no} {k.toplam_tutar}->{yeni}"); flash("✅ Talep gönderildi.", "success"); return redirect(url_for("odalar"))

@app.route("/giderler")
@giris_gerek
def giderler(): return render_template("giderler.html", giderler=Gider.query.order_by(Gider.tarih.desc()).all())

@app.route("/gider_ekle", methods=["POST"])
@giris_gerek
def gider_ekle():
    try: t = float(request.form["tutar"].replace(",", "."))
    except: flash("Geçerli tutar!", "danger"); return redirect(url_for("giderler"))
    db.session.add(Gider(aciklama=request.form["aciklama"], tutar=t, personel=session.get("username")))
    db.session.commit(); log_yaz("GIDER", f"{request.form['aciklama']} - {t} TL"); flash("Gider eklendi.", "success"); return redirect(url_for("giderler"))

@app.route("/borclular")
@giris_gerek
def borclular():
    borclular = Kayit.query.filter(Kayit.odenen < Kayit.toplam_tutar).order_by(Kayit.oda_no).all()
    return render_template("borclular.html", borclular=borclular, toplam_borc=sum(k.kalan for k in borclular), admin=admin_mi())

@app.route("/odeme_al/<int:kid>", methods=["POST"])
@giris_gerek
def odeme_al(kid):
    k = Kayit.query.get_or_404(kid)
    try: tutar = float(request.form["tutar"].replace(",", "."))
    except: flash("Geçerli tutar girin!", "danger"); return redirect(url_for("borclular"))
    if tutar <= 0 or tutar > k.kalan + 0.01: flash("Tutar geçersiz veya kalan borçtan büyük!", "danger"); return redirect(url_for("borclular"))
    odeme = Odeme(kayit_id=k.id, tutar=tutar, tip=request.form.get("tip", "Nakit"), personel=session.get("username"), aciklama=request.form.get("aciklama", ""))
    k.odenen += tutar; db.session.add(odeme); db.session.commit()
    log_yaz("ODEME AL", f"{k.oda_no} - {tutar} TL (kalan: {k.kalan} TL)"); flash(f"✅ {k.oda_no} → {tutar} TL ödeme alındı.", "success"); return redirect(url_for("borclular"))

@app.route("/odeme_gecmisi/<int:kid>")
@giris_gerek
def odeme_gecmisi(kid): return render_template("odeme_gecmisi.html", kayit=Kayit.query.get_or_404(kid), odemeler=Odeme.query.filter_by(kayit_id=kid).order_by(Odeme.tarih.desc()).all())

@app.route("/personel", methods=["GET", "POST"])
@giris_gerek
def personel():
    if not admin_mi(): flash("Yetkiniz yok!", "danger"); return redirect(url_for("odalar"))
    if request.method == "POST":
        try: maas = float(request.form["maas"].replace(",", "."))
        except: maas = 0
        db.session.add(Personel(ad_soyad=request.form["ad_soyad"], gorev=request.form["gorev"], maas=maas)); db.session.commit(); flash("Personel eklendi.", "success"); return redirect(url_for("personel"))
    return render_template("personel.html", personeller=Personel.query.all())

@app.route("/avans_ver/<int:pid>", methods=["POST"])
@giris_gerek
def avans_ver(pid):
    if not admin_mi(): return redirect(url_for("odalar"))
    p = Personel.query.get_or_404(pid)
    try: tutar = float(request.form["tutar"].replace(",", "."))
    except: flash("Geçerli tutar girin!", "danger"); return redirect(url_for("personel"))
    db.session.add(Avans(personel_id=p.id, tutar=tutar, aciklama=request.form.get("aciklama", ""))); db.session.commit()
    log_yaz("AVANS", f"{p.ad_soyad} - {tutar} TL"); flash(f"✅ {tutar} TL avans verildi.", "success"); return redirect(url_for("personel"))

@app.route("/maas_ode/<int:pid>")
@giris_gerek
def maas_ode(pid):
    if not admin_mi(): return redirect(url_for("odalar"))
    p = Personel.query.get_or_404(pid); kalan = p.maas - sum(a.tutar for a in p.avanslar)
    if kalan > 0:
        db.session.add(Gider(aciklama=f"{p.ad_soyad} Maaş Ödemesi", tutar=kalan, personel="admin")); log_yaz("MAAS ODEME", f"{p.ad_soyad} - {kalan} TL")
        for a in p.avanslar: db.session.delete(a)
        db.session.commit(); flash(f"✅ {kalan} TL maaş ödendi ve gidere işlendi.", "success")
    else: flash("Ödenecek maaş kalmamış.", "danger")
    return redirect(url_for("personel"))

@app.route("/personel_sil/<int:pid>")
@giris_gerek
def personel_sil(pid):
    if not admin_mi(): return redirect(url_for("odalar"))
    p = Personel.query.get_or_404(pid); Avans.query.filter_by(personel_id=p.id).delete(); db.session.delete(p); db.session.commit(); log_yaz("PERSONEL SIL", p.ad_soyad); return redirect(url_for("personel"))

@app.route("/talepler")
@giris_gerek
def talepler():
    if not admin_mi(): return redirect(url_for("odalar"))
    return render_template("talepler.html", talepler=Talep.query.order_by(Talep.tarih.desc()).all())

@app.route("/talep_karar/<int:tid>/<karar>")
@giris_gerek
def talep_karar(tid, karar):
    if not admin_mi(): return redirect(url_for("odalar"))
    t = Talep.query.get_or_404(tid)
    if t.durum == "Bekliyor":
        t.durum = "Onaylandı" if karar == "onay" else "Reddedildi"
        if karar == "onay":
            if t.talep_tipi == "yeni_kayit":
                yeni_tarih = datetime.now()
                try: yeni_tarih = datetime.strptime(t.tarih_str, "%Y-%m-%d")
                except: pass
                db.session.add(Kayit(oda_no=t.oda_no, musteri_adi=t.musteri_adi, toplam_tutar=t.toplam_tutar, odenen=t.odenen, tip=t.tip, personel=t.personel, kilitli=True, notlar=t.notlar, tarih=yeni_tarih))
            else:
                k = Kayit.query.get(t.kayit_id)
                if k: k.toplam_tutar = t.yeni_tutar; k.kilitli = False
        db.session.commit(); log_yaz("TALEP KARAR", f"#{tid} {t.durum}")
    return redirect(url_for("talepler"))

@app.route("/kasa", methods=["GET","POST"])
@giris_gerek
def kasa():
    if not admin_mi(): return redirect(url_for("odalar"))
    ay = request.values.get("ay", datetime.now().strftime("%Y-%m"))
    if request.method == "POST":
        try:
            usd = float(request.form["usd"].replace(",", ".")); eur = float(request.form["eur"].replace(",", "."))
            kur = Kur.query.filter_by(ay=ay).first()
            if kur: kur.usd = usd; kur.eur = eur
            else: db.session.add(Kur(ay=ay, usd=usd, eur=eur))
            db.session.commit()
        except: flash("Kurları sayı olarak girin (Örn: 34.50)", "danger"); return redirect(url_for("kasa"))
    kur = Kur.query.filter_by(ay=ay).first(); usd = kur.usd if kur else 34.0; eur = kur.eur if kur else 37.0
    toplam = {"Nakit":0, "Kredi Kartı":0, "Havale":0, "USD":0, "EUR":0, "ETS":0, "Tatilbudur":0, "Joly":0, "Otelfiyat":0}; adet = {k:0 for k in toplam}
    for k in Kayit.query.filter(Kayit.tarih.like(f"{ay}%")).all():
        if k.tip in toplam: toplam[k.tip] += k.odenen; adet[k.tip] += 1
    toplam_tl = sum(toplam[k] for k in ["Nakit","Kredi Kartı","Havale","ETS","Tatilbudur","Joly","Otelfiyat"]) + toplam["USD"]*usd + toplam["EUR"]*eur
    gider_tl = sum(g.tutar for g in Gider.query.filter(Gider.tarih.like(f"{ay}%")).all())
    borc_tl = sum(k.kalan for k in Kayit.query.filter(Kayit.tarih.like(f"{ay}%")).all())
    return render_template("kasa.html", ay=ay, toplam=toplam, adet=adet, usd=usd, eur=eur, toplam_tl=toplam_tl, gider_tl=gider_tl, net=toplam_tl-gider_tl, borc_tl=borc_tl)

@app.route("/kasa/excel/<ay>")
@giris_gerek
def kasa_excel(ay):
    if not admin_mi(): return "Yetki yok", 403
    wb = Workbook(); ws = wb.active; ws.title = f"Kasa {ay}"; ws.append([f"{ay} KASA RAPORU"]); ws.append([]); ws.append(["Ödeme Tipi", "Adet", "Tahsil Edilen (TL)"])
    kur = Kur.query.filter_by(ay=ay).first(); usd = kur.usd if kur else 34.0; eur = kur.eur if kur else 37.0
    for tip in ["Nakit","Kredi Kartı","Havale","USD","EUR","ETS","Tatilbudur","Joly","Otelfiyat"]:
        kayitlar = Kayit.query.filter(Kayit.tarih.like(f"{ay}%"), Kayit.tip==tip).all(); top = sum(k.odenen for k in kayitlar); tl = top*usd if tip=="USD" else (top*eur if tip=="EUR" else top); ws.append([tip, len(kayitlar), f"{tl:.2f}"])
    ws.append([]); ws.append(["GIDERLER"])
    for g in Gider.query.filter(Gider.tarih.like(f"{ay}%")).all(): ws.append([g.aciklama, g.tarih.strftime("%d.%m.%Y"), f"{g.tutar:.2f}"])
    bio = io.BytesIO(); wb.save(bio); bio.seek(0); return send_file(bio, as_attachment=True, download_name=f"kasa_{ay}.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/sifre_degistir", methods=["GET", "POST"])
@giris_gerek
def sifre_degistir():
    if request.method == "POST":
        u = User.query.get(session["user_id"])
        if not check_password_hash(u.password_hash, request.form["eski_sifre"]): flash("Mevcut şifre yanlış!", "danger")
        elif request.form["yeni_sifre"] != request.form["yeni_sifre_tekrar"]: flash("Şifreler uyuşmuyor!", "danger")
        elif len(request.form["yeni_sifre"]) < 4: flash("En az 4 karakter olmalı!", "danger")
        else:
            u.password_hash = generate_password_hash(request.form["yeni_sifre"]); db.session.commit(); log_yaz("SIFRE DEGISTI", u.username); flash("✅ Şifre güncellendi!", "success"); return redirect(url_for("odalar"))
    return render_template("sifre_degistir.html")

@app.route("/kullanicilar")
@giris_gerek
def kullanicilar():
    if not admin_mi(): return redirect(url_for("odalar"))
    return render_template("kullanicilar.html", kullanicilar=User.query.all())

@app.route("/personel_ekle", methods=["POST"])
@giris_gerek
def personel_ekle():
    if not admin_mi(): return redirect(url_for("odalar"))
    if User.query.filter_by(username=request.form["username"]).first(): flash("Kullanıcı adı alınmış!", "danger")
    else:
        db.session.add(User(username=request.form["username"], password_hash=generate_password_hash(request.form["password"]), full_name=request.form["full_name"], role="resepsiyon")); db.session.commit(); log_yaz("PERSONEL EKLE", request.form["username"]); flash("✅ Personel eklendi.", "success")
    return redirect(url_for("kullanicilar"))

@app.route("/loglar")
@giris_gerek
def loglar():
    if not admin_mi(): return redirect(url_for("odalar"))
    return render_template("loglar.html", loglar=Log.query.order_by(Log.tarih.desc()).limit(300).all())

def init_db():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username="admin").first():
            db.session.add(User(username="admin", password_hash=generate_password_hash("1234"), full_name="Otel Yöneticisi", role="admin"))
            db.session.add(User(username="resepsiyon", password_hash=generate_password_hash("1234"), full_name="Resepsiyon", role="resepsiyon"))
            for kat in [1,2,3]:
                for no in range(1,11): db.session.add(Oda(no=f"{kat}{no:02d}"))
            db.session.commit(); print("✅ İlk kurulum tamam")

init_db()
if __name__ == "__main__": app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
