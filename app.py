from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from openpyxl import Workbook
import io, os

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "otel-kasa-2025-gizli-anahtar-degistir")
db_url = os.environ.get("DATABASE_URL", "sqlite:///otel_kasa.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

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
    tip = db.Column(db.String(20), nullable=False)
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

class Talep(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kayit_id = db.Column(db.Integer)
    oda_no = db.Column(db.String(10))
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
    tip = db.Column(db.String(20), default="Nakit")
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

def giris_yapmis():
    return "user_id" in session

def admin_mi():
    return session.get("role") == "admin"

def giris_gerek(f):
    from functools import wraps
    @wraps(f)
    def wrapper(*a, **kw):
        if not giris_yapmis():
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper

def log_yaz(islem, detay=""):
    db.session.add(Log(kullanici=session.get("username","sistem"), islem=islem, detay=detay))
    db.session.commit()

@app.context_processor
def inject_user():
    return dict(current_user={"username":session.get("username",""),
                              "full_name":session.get("full_name",""),
                              "role":session.get("role","")},
                giris=giris_yapmis())

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = User.query.filter_by(username=request.form["username"]).first()
        if u and u.active and check_password_hash(u.password_hash, request.form["password"]):
            session["user_id"] = u.id
            session["username"] = u.username
            session["full_name"] = u.full_name
            session["role"] = u.role
            log_yaz("GİRİŞ", u.username)
            return redirect(url_for("odalar"))
        flash("Kullanıcı adı veya şifre yanlış!", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    log_yaz("ÇIKIŞ", session.get("username",""))
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@giris_gerek
def index():
    return redirect(url_for("odalar"))

@app.route("/odalar")
@giris_gerek
def odalar():
    kayitlar = Kayit.query.order_by(Kayit.tarih.desc()).all()
    odalar_list = Oda.query.all()
    return render_template("odalar.html", kayitlar=kayitlar, odalar=odalar_list, admin=admin_mi())

@app.route("/kayit_ekle", methods=["POST"])
@giris_gerek
def kayit_ekle():
    try:
        toplam = float(request.form["toplam_tutar"].replace(",", "."))
        odenen = float(request.form.get("odenen", "0").replace(",", ".") or 0)
    except:
        flash("Geçerli tutar girin!", "danger")
        return redirect(url_for("odalar"))
    if odenen > toplam:
        flash("Ödenen tutar toplamdan büyük olamaz!", "danger")
        return redirect(url_for("odalar"))
    k = Kayit(oda_no=request.form["oda"],
              musteri_adi=request.form.get("musteri_adi", ""),
              toplam_tutar=toplam, odenen=odenen,
              tip=request.form["tip"], personel=session.get("username"),
              kilitli=True, notlar=request.form.get("notlar", ""))
    db.session.add(k); db.session.commit()
    log_yaz("KAYIT EKLE", f"{k.oda_no} - {toplam} (odenen: {odenen}, kalan: {toplam-odenen})")
    flash(f"✅ {k.oda_no} → Toplam {toplam} TL, Ödenen {odenen} TL, Kalan {toplam-odenen} TL", "success")
    return redirect(url_for("odalar"))

@app.route("/kayit_sil/<int:kid>")
@giris_gerek
def kayit_sil(kid):
    if not admin_mi():
        flash("Yetkiniz yok!", "danger"); return redirect(url_for("odalar"))
    k = Kayit.query.get_or_404(kid)
    db.session.delete(k); db.session.commit()
    log_yaz("KAYIT SIL", f"ID {kid}")
    flash("Kayıt silindi.", "success")
    return redirect(url_for("odalar"))

@app.route("/talep_gonder/<int:kid>", methods=["POST"])
@giris_gerek
def talep_gonder(kid):
    k = Kayit.query.get_or_404(kid)
    try:
        yeni = float(request.form["yeni_tutar"].replace(",", "."))
    except:
        flash("Geçerli tutar!", "danger"); return redirect(url_for("odalar"))
    sebep = request.form["sebep"].strip()
    if not sebep:
        flash("Sebep zorunlu!", "danger"); return redirect(url_for("odalar"))
    t = Talep(kayit_id=kid, oda_no=k.oda_no, eski_tutar=k.toplam_tutar,
              yeni_tutar=yeni, sebep=sebep, personel=session.get("username"))
    db.session.add(t); db.session.commit()
    log_yaz("TALEP", f"{k.oda_no} {k.toplam_tutar}->{yeni}")
    flash("✅ Talep ana kullanıcıya gönderildi.", "success")
    return redirect(url_for("odalar"))

@app.route("/giderler")
@giris_gerek
def giderler():
    g = Gider.query.order_by(Gider.tarih.desc()).all()
    return render_template("giderler.html", giderler=g)

@app.route("/gider_ekle", methods=["POST"])
@giris_gerek
def gider_ekle():
    try:
        t = float(request.form["tutar"].replace(",", "."))
    except:
        flash("Geçerli tutar!", "danger"); return redirect(url_for("giderler"))
    db.session.add(Gider(aciklama=request.form["aciklama"], tutar=t,
                         personel=session.get("username")))
    db.session.commit()
    log_yaz("GIDER", f"{request.form['aciklama']} - {t} TL")
    flash("Gider eklendi.", "success")
    return redirect(url_for("giderler"))

@app.route("/borclular")
@giris_gerek
def borclular():
    borclular = Kayit.query.filter(Kayit.odenen < Kayit.toplam_tutar).order_by(Kayit.oda_no).all()
    toplam_borc = sum(k.kalan for k in borclular)
    return render_template("borclular.html", borclular=borclular,
                           toplam_borc=toplam_borc, admin=admin_mi())

@app.route("/odeme_al/<int:kid>", methods=["POST"])
@giris_gerek
def odeme_al(kid):
    k = Kayit.query.get_or_404(kid)
    try:
        tutar = float(request.form["tutar"].replace(",", "."))
    except:
        flash("Geçerli tutar girin!", "danger")
        return redirect(request.referrer or url_for("borclular"))
    if tutar <= 0:
        flash("Tutar 0'dan büyük olmalı!", "danger")
        return redirect(request.referrer or url_for("borclular"))
    if tutar > k.kalan + 0.01:
        flash(f"Ödeme kalan borçtan ({k.kalan} TL) büyük olamaz!", "danger")
        return redirect(request.referrer or url_for("borclular"))
    odeme = Odeme(kayit_id=k.id, tutar=tutar,
                  tip=request.form.get("tip", "Nakit"),
                  personel=session.get("username"),
                  aciklama=request.form.get("aciklama", ""))
    k.odenen += tutar
    db.session.add(odeme); db.session.commit()
    log_yaz("ODEME AL", f"{k.oda_no} - {tutar} TL (kalan: {k.kalan} TL)")
    if k.kalan <= 0.01:
        flash(f"🎉 {k.oda_no} odasının borcu TAMAMEN kapandı!", "success")
    else:
        flash(f"✅ {k.oda_no} → {tutar} TL ödeme alındı. Kalan: {k.kalan} TL", "success")
    return redirect(request.referrer or url_for("borclular"))

@app.route("/odeme_gecmisi/<int:kid>")
@giris_gerek
def odeme_gecmisi(kid):
    k = Kayit.query.get_or_404(kid)
    odemeler = Odeme.query.filter_by(kayit_id=kid).order_by(Odeme.tarih.desc()).all()
    return render_template("odeme_gecmisi.html", kayit=k, odemeler=odemeler)

@app.route("/talepler")
@giris_gerek
def talepler():
    if not admin_mi():
        flash("Yetkiniz yok!", "danger"); return redirect(url_for("odalar"))
    t = Talep.query.order_by(Talep.tarih.desc()).all()
    return render_template("talepler.html", talepler=t)

@app.route("/talep_karar/<int:tid>/<karar>")
@giris_gerek
def talep_karar(tid, karar):
    if not admin_mi(): return redirect(url_for("odalar"))
    t = Talep.query.get_or_404(tid)
    if t.durum == "Bekliyor":
        t.durum = "Onaylandı" if karar == "onay" else "Reddedildi"
        if karar == "onay":
            k = Kayit.query.get(t.kayit_id)
            if k: k.toplam_tutar = t.yeni_tutar; k.kilitli = False
        db.session.commit()
        log_yaz("TALEP KARAR", f"#{tid} {t.durum}")
    return redirect(url_for("talepler"))

@app.route("/kasa", methods=["GET","POST"])
@giris_gerek
def kasa():
    if not admin_mi():
        flash("Yetkiniz yok!", "danger"); return redirect(url_for("odalar"))
    ay = request.values.get("ay", datetime.now().strftime("%Y-%m"))
    if request.method == "POST":
        usd = float(request.form["usd"]); eur = float(request.form["eur"])
        kur = Kur.query.filter_by(ay=ay).first()
        if kur: kur.usd = usd; kur.eur = eur
        else: db.session.add(Kur(ay=ay, usd=usd, eur=eur))
        db.session.commit()
    kur = Kur.query.filter_by(ay=ay).first()
    usd = kur.usd if kur else 34.0
    eur = kur.eur if kur else 37.0
    toplam = {"Nakit":0, "Kredi Kartı":0, "Havale":0, "USD":0, "EUR":0}
    adet = {k:0 for k in toplam}
    for k in Kayit.query.filter(Kayit.tarih.like(f"{ay}%")).all():
        toplam[k.tip] += k.odenen
        adet[k.tip] += 1
    toplam_tl = (toplam["Nakit"] + toplam["Kredi Kartı"] + toplam["Havale"]
                 + toplam["USD"]*usd + toplam["EUR"]*eur)
    gider_tl = sum(g.tutar for g in Gider.query.filter(Gider.tarih.like(f"{ay}%")).all())
    net = toplam_tl - gider_tl
    borc_tl = sum(k.kalan for k in Kayit.query.filter(Kayit.tarih.like(f"{ay}%")).all())
    return render_template("kasa.html", ay=ay, toplam=toplam, adet=adet,
                           usd=usd, eur=eur, toplam_tl=toplam_tl,
                           gider_tl=gider_tl, net=net, borc_tl=borc_tl)

@app.route("/kasa/excel/<ay>")
@giris_gerek
def kasa_excel(ay):
    if not admin_mi(): return "Yetki yok", 403
    wb = Workbook(); ws = wb.active; ws.title = f"Kasa {ay}"
    ws.append([f"{ay} KASA RAPORU"]); ws.append([])
    ws.append(["Ödeme Tipi", "Adet", "Tahsil Edilen (TL)"])
    kur = Kur.query.filter_by(ay=ay).first()
    usd = kur.usd if kur else 34.0; eur = kur.eur if kur else 37.0
    for tip in ["Nakit","Kredi Kartı","Havale","USD","EUR"]:
        kayitlar = Kayit.query.filter(Kayit.tarih.like(f"{ay}%"), Kayit.tip==tip).all()
        top = sum(k.odenen for k in kayitlar)
        tl = top*usd if tip=="USD" else (top*eur if tip=="EUR" else top)
        ws.append([tip, len(kayitlar), f"{tl:.2f}"])
    ws.append([]); ws.append(["GIDERLER"])
    for g in Gider.query.filter(Gider.tarih.like(f"{ay}%")).all():
        ws.append([g.aciklama, g.tarih.strftime("%d.%m.%Y"), f"{g.tutar:.2f}"])
    ws.append([]); ws.append(["BORCLAR"])
    for k in Kayit.query.filter(Kayit.tarih.like(f"{ay}%")).all():
        if k.kalan > 0:
            ws.append([f"Oda {k.oda_no} - {k.musteri_adi}", f"Kalan: {k.kalan:.2f} TL"])
    bio = io.BytesIO(); wb.save(bio); bio.seek(0)
    return send_file(bio, as_attachment=True, download_name=f"kasa_{ay}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/loglar")
@giris_gerek
def loglar():
    if not admin_mi(): return redirect(url_for("odalar"))
    return render_template("loglar.html", loglar=Log.query.order_by(Log.tarih.desc()).limit(300).all())

def init_db():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username="admin").first():
            db.session.add(User(username="admin", password_hash=generate_password_hash("1234"),
                                full_name="Ana Kullanıcı", role="admin"))
            db.session.add(User(username="resepsiyon", password_hash=generate_password_hash("1234"),
                                full_name="Resepsiyon", role="resepsiyon"))
            for kat in [1,2,3]:
                for no in range(1,11):
                    db.session.add(Oda(no=f"{kat}{no:02d}"))
            db.session.commit()
            print("✅ İlk kurulum tamam")

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
