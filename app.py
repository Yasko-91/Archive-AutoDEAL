from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import sqlite3
import hashlib
import secrets
import os
from datetime import date
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.secret_key = "concession_secret_key_2024"

DB_NAME = "concession.db"
SCHEMA_FILE = "schema.sql"
UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"


# ---------------------------
# DB
# ---------------------------
def get_db():
    conn = sqlite3.connect(DB_NAME, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    if not os.path.exists(SCHEMA_FILE):
        print("schema.sql introuvable.")
        return
    conn = get_db()
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        conn.executescript(f.read())

    # Créer le compte admin en DB si il n'existe pas
    existing = conn.execute("SELECT 1 FROM client WHERE username='admin'").fetchone()
    if not existing:
        salt = secrets.token_hex(16)
        pw_hash = hash_password("admin123", salt)
        conn.execute("""
            INSERT INTO client (username, nom, prenom, password_salt, password_hash, role)
            VALUES ('admin', 'Admin', 'Admin', ?, ?, 'admin')
        """, (salt, pw_hash))
        conn.commit()
        admin = conn.execute("SELECT id_client FROM client WHERE username='admin'").fetchone()
        print(f"Compte admin créé avec id={admin['id_client']}")

    conn.close()

# ---------------------------
# OUTILS
# ---------------------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def hash_password(password: str, salt_hex: str) -> str:
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return dk.hex()


def today_iso():
    return datetime.now().isoformat()


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("role") != "admin":
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated


# ---------------------------
# ROUTES PRINCIPALES
# ---------------------------
@app.route("/")
def index():
    conn = get_db()
    # 5 véhicules les plus likés
    vehicules = conn.execute("""
        SELECT v.*, COUNT(l.id_client) as nb_likes,
               (SELECT chemin FROM photo WHERE id_vehicule = v.id_vehicule ORDER BY ordre LIMIT 1) as photo
        FROM vehicule v
        LEFT JOIN like_vehicule l ON v.id_vehicule = l.id_vehicule
        WHERE v.statut = 'en_stock'
        GROUP BY v.id_vehicule
        ORDER BY nb_likes DESC
        LIMIT 4
    """).fetchall()
    conn.close()
    return render_template("index.html", vehicules=vehicules)


@app.route("/catalogue")
def catalogue():
    conn = get_db()

    # Filtres
    marque = request.args.get("marque", "")
    carburant = request.args.get("carburant", "")
    couleur = request.args.get("couleur", "")
    prix_min = request.args.get("prix_min", "")
    prix_max = request.args.get("prix_max", "")
    tri = request.args.get("tri", "prix_asc")

    query = """
        SELECT v.*,
               COUNT(l.id_client) as nb_likes,
               (SELECT chemin FROM photo WHERE id_vehicule = v.id_vehicule ORDER BY ordre LIMIT 1) as photo
        FROM vehicule v
        LEFT JOIN like_vehicule l ON v.id_vehicule = l.id_vehicule
        WHERE v.statut = 'en_stock'
    """
    params = []

    if marque:
        query += " AND LOWER(v.marque) LIKE ?"
        params.append(f"%{marque.lower()}%")
    if carburant:
        query += " AND v.carburant = ?"
        params.append(carburant)
    if couleur:
        query += " AND LOWER(v.couleur) LIKE ?"
        params.append(f"%{couleur.lower()}%")
    if prix_min:
        query += " AND v.prix_vente >= ?"
        params.append(float(prix_min))
    if prix_max:
        query += " AND v.prix_vente <= ?"
        params.append(float(prix_max))

    query += " GROUP BY v.id_vehicule"

    order = {
        "prix_asc": "v.prix_vente ASC",
        "prix_desc": "v.prix_vente DESC",
        "annee_desc": "v.annee DESC",
        "km_asc": "v.km ASC",
    }.get(tri, "v.prix_vente ASC")
    query += f" ORDER BY {order}"

    vehicules = conn.execute(query, params).fetchall()
    conn.close()
    return render_template("catalogue.html", vehicules=vehicules,
                           marque=marque, carburant=carburant, couleur=couleur,
                           prix_min=prix_min, prix_max=prix_max, tri=tri)


@app.route("/vehicule/<int:id_vehicule>")
def vehicule_detail(id_vehicule):
    conn = get_db()
    v = conn.execute("""
        SELECT v.*, COUNT(l.id_client) as nb_likes
        FROM vehicule v
        LEFT JOIN like_vehicule l ON v.id_vehicule = l.id_vehicule
        WHERE v.id_vehicule = ?
        GROUP BY v.id_vehicule
    """, (id_vehicule,)).fetchone()

    if not v:
        conn.close()
        return redirect(url_for("catalogue"))

    photos = conn.execute(
        "SELECT chemin FROM photo WHERE id_vehicule = ? ORDER BY ordre", (id_vehicule,)
    ).fetchall()

    # Like de l'utilisateur connecté
    user_liked = False
    if "user_id" in session:
        like = conn.execute(
            "SELECT 1 FROM like_vehicule WHERE id_client=? AND id_vehicule=?",
            (session["user_id"], id_vehicule)
        ).fetchone()
        user_liked = like is not None

    conn.close()
    return render_template("vehicule.html", v=v, photos=photos, user_liked=user_liked)


# ---------------------------
# LIKES
# ---------------------------
@app.route("/like/<int:id_vehicule>", methods=["POST"])
@login_required
def toggle_like(id_vehicule):
    conn = get_db()
    existing = conn.execute(
        "SELECT 1 FROM like_vehicule WHERE id_client=? AND id_vehicule=?",
        (session["user_id"], id_vehicule)
    ).fetchone()

    if existing:
        conn.execute(
            "DELETE FROM like_vehicule WHERE id_client=? AND id_vehicule=?",
            (session["user_id"], id_vehicule)
        )
        liked = False
    else:
        conn.execute(
            "INSERT INTO like_vehicule (id_client, id_vehicule) VALUES (?, ?)",
            (session["user_id"], id_vehicule)
        )
        liked = True

    nb_likes = conn.execute(
        "SELECT COUNT(*) FROM like_vehicule WHERE id_vehicule=?", (id_vehicule,)
    ).fetchone()[0]

    conn.commit()
    conn.close()
    return jsonify({"liked": liked, "nb_likes": nb_likes})


# ---------------------------
# AUTH
# ---------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        action = request.form.get("action")

        if action == "login":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()

            # Connexion admin
            if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
                conn = get_db()
                admin = conn.execute("SELECT id_client FROM client WHERE username='admin'").fetchone()
                conn.close()
                session["user_id"] = admin["id_client"]
                session["username"] = "admin"
                session["role"] = "admin"
                return redirect(url_for("index"))

            conn = get_db()
            user = conn.execute(
                "SELECT * FROM client WHERE username=?", (username,)
            ).fetchone()
            conn.close()

            if user and hash_password(password, user["password_salt"]) == user["password_hash"]:
                session["user_id"] = user["id_client"]
                session["username"] = user["username"]
                session["role"] = user["role"]
                return redirect(url_for("index"))
            else:
                flash("Identifiants incorrects.")

        elif action == "register":
            username = request.form.get("username", "").strip()
            nom = request.form.get("nom", "").strip()
            prenom = request.form.get("prenom", "").strip()
            email = request.form.get("email", "").strip() or None
            telephone = request.form.get("telephone", "").strip() or None
            password = request.form.get("password", "").strip()

            if len(password) < 4:
                flash("Mot de passe trop court (min 4 caractères).")
            else:
                salt = secrets.token_hex(16)
                pw_hash = hash_password(password, salt)
                try:
                    conn = get_db()
                    conn.execute("""
                        INSERT INTO client (username, nom, prenom, email, telephone, password_salt, password_hash, role)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'user')
                    """, (username, nom, prenom, email, telephone, salt, pw_hash))
                    conn.commit()
                    conn.close()
                    flash("Inscription réussie, connecte-toi !")
                except sqlite3.IntegrityError:
                    flash("Username ou email déjà utilisé.")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ---------------------------
# PROFIL
# ---------------------------
@app.route("/profil")
@login_required
def profil():
    conn = get_db()
    user = conn.execute(
        "SELECT * FROM client WHERE id_client=?", (session["user_id"],)
    ).fetchone()

    likes = conn.execute("""
        SELECT v.*, (SELECT chemin FROM photo WHERE id_vehicule = v.id_vehicule ORDER BY ordre LIMIT 1) as photo
        FROM vehicule v
        JOIN like_vehicule l ON v.id_vehicule = l.id_vehicule
        WHERE l.id_client = ?
    """, (session["user_id"],)).fetchall()

    conn.close()
    return render_template("profil.html", user=user, likes=likes)


# ---------------------------
# AJOUTER VEHICULE
# ---------------------------
@app.route("/ajouter", methods=["GET", "POST"])
@login_required
def ajouter_vehicule():
    if request.method == "POST":
        data = {
            "titre": request.form.get("titre"),
            "marque": request.form.get("marque"),
            "modele": request.form.get("modele"),
            "annee": int(request.form.get("annee")),
            "carburant": request.form.get("carburant"),
            "km": int(request.form.get("km")),
            "prix_vente": float(request.form.get("prix_vente")),
            "couleur": request.form.get("couleur"),
            "puissance": request.form.get("puissance") or None,
            "boite": request.form.get("boite"),
            "nb_portes": int(request.form.get("nb_portes")),
            "etat": request.form.get("etat"),
            "localisation": request.form.get("localisation"),
            "description": request.form.get("description"),
        }

        conn = get_db()


        if session["role"] == "admin":
            cur = conn.execute("""
                INSERT INTO vehicule (titre, marque, modele, annee, carburant, km, prix_vente,
                couleur, puissance, boite, nb_portes, etat, localisation, description, statut)
                VALUES (:titre, :marque, :modele, :annee, :carburant, :km, :prix_vente,
                :couleur, :puissance, :boite, :nb_portes, :etat, :localisation, :description, 'en_stock')
            """, data)
            id_vehicule = cur.lastrowid
            conn.commit()

            photos = request.files.getlist("photos")
            for i, photo in enumerate(photos):
                if photo and allowed_file(photo.filename):
                    filename = secrets.token_hex(8) + "_" + secure_filename(photo.filename)
                    photo.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                    conn.execute(
                        "INSERT INTO photo (id_vehicule, chemin, ordre) VALUES (?, ?, ?)",
                         (id_vehicule, f"uploads/{filename}", i)
                        )
                conn.commit()
            conn.close()
            flash("Véhicule ajouté avec succès.")
            return redirect(url_for("catalogue"))

        else:
            # Demande d'ajout
            conn.execute("""
                INSERT INTO demande_ajout_vehicule
                (id_client, date_demande, statut, titre, marque, modele, annee, carburant, km, prix_vente,
                couleur, puissance, boite, nb_portes, etat, localisation, description)
                VALUES (?, ?, 'en_attente', :titre, :marque, :modele, :annee, :carburant, :km, :prix_vente,
                :couleur, :puissance, :boite, :nb_portes, :etat, :localisation, :description)
            """, (session["user_id"], today_iso(), *data.values()))
            conn.commit()
            conn.close()
            flash("Demande envoyée, en attente de validation admin.")
            return redirect(url_for("catalogue"))

    return render_template("ajouter.html")


# ---------------------------
# SUPPRESSION VEHICULE (ADMIN)
# Supprime un véhicule et toutes ses données liées
# (photos, likes) avant de supprimer le véhicule lui-même
# pour respecter les contraintes de clé étrangère
# ---------------------------
@app.route("/admin/supprimer_vehicule/<int:id_vehicule>", methods=["POST"])
@admin_required
def supprimer_vehicule(id_vehicule):
    conn = get_db()
    conn.execute("DELETE FROM photo WHERE id_vehicule=?", (id_vehicule,))
    conn.execute("DELETE FROM like_vehicule WHERE id_vehicule=?", (id_vehicule,))
    conn.execute("DELETE FROM vehicule WHERE id_vehicule=?", (id_vehicule,))
    conn.commit()
    conn.close()
    flash("Véhicule supprimé.")
    return redirect(url_for("admin_panel"))


# ---------------------------
# DEMANDE D'ACHAT
# ---------------------------
@app.route("/acheter/<int:id_vehicule>", methods=["POST"])
@login_required
def acheter(id_vehicule):
    prix_propose = float(request.form.get("prix_propose"))
    commentaire = request.form.get("commentaire") or None

    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO demande_achat (date_demande, id_client, id_vehicule, statut, prix_propose, commentaire)
            VALUES (?, ?, ?, 'en_attente', ?, ?)
        """, (today_iso(), session["user_id"], id_vehicule, prix_propose, commentaire))
        conn.commit()
        flash("Demande d'achat envoyée !")
    except sqlite3.IntegrityError:
        flash("Une demande est déjà en attente pour ce véhicule.")
    conn.close()
    return redirect(url_for("vehicule_detail", id_vehicule=id_vehicule))


# ---------------------------
# MESSAGERIE
# ---------------------------
@app.route("/messages")
@login_required
def messages():
    conn = get_db()
    conversations = conn.execute("""
        SELECT DISTINCT
            CASE WHEN m.id_expediteur = ? THEN m.id_destinataire ELSE m.id_expediteur END as other_id,
            c.username, c.role
        FROM message m
        JOIN client c ON c.id_client = CASE WHEN m.id_expediteur = ? THEN m.id_destinataire ELSE m.id_expediteur END
        WHERE m.id_expediteur = ? OR m.id_destinataire = ?
    """, (session["user_id"],) * 4).fetchall()

    # Admin : liste tous les clients
    all_users = None
    if session["role"] == "admin":
        all_users = conn.execute(
            "SELECT id_client, username, role FROM client ORDER BY username"
        ).fetchall()

    conn.close()
    return render_template("messages.html", conversations=conversations, all_users=all_users)


@app.route("/messages/<int:other_id>")
@login_required
def conversation(other_id):
    conn = get_db()
    other = conn.execute(
        "SELECT id_client, username, role FROM client WHERE id_client=?", (other_id,)
    ).fetchone()
    msgs = conn.execute("""
        SELECT m.*, c.username, c.role
        FROM message m
        JOIN client c ON c.id_client = m.id_expediteur
        WHERE (m.id_expediteur=? AND m.id_destinataire=?)
           OR (m.id_expediteur=? AND m.id_destinataire=?)
        ORDER BY m.date_envoi ASC
    """, (session["user_id"], other_id, other_id, session["user_id"])).fetchall()
    try:
        conn.execute("""
            UPDATE message SET lu=1
            WHERE id_destinataire=? AND id_expediteur=?
        """, (session["user_id"], other_id))
        conn.commit()
    finally:
        conn.close()
    return render_template("conversation.html", other=other, msgs=msgs)


@app.route("/messages/envoyer", methods=["POST"])
@login_required
def envoyer_message():
    id_destinataire = int(request.form.get("id_destinataire"))
    contenu = request.form.get("contenu", "").strip()
    if contenu and session["user_id"] != -1:
        conn = get_db()
        conn.execute("""
            INSERT INTO message (id_expediteur, id_destinataire, contenu, date_envoi)
            VALUES (?, ?, ?, ?)
        """, (session["user_id"], id_destinataire, contenu, today_iso()))
        conn.commit()
        conn.close()
    return redirect(url_for("conversation", other_id=id_destinataire))


# ---------------------------
# POLL MESSAGERIE
# Récupère tous les messages d'une conversation en JSON
# Appelée toutes les 2 secondes par le JS de conversation.html
# Permet d'afficher les nouveaux messages sans recharger la page
# ---------------------------

@app.route("/messages/poll/<int:other_id>")
@login_required
def poll_messages(other_id):
    conn = get_db()
    msgs = conn.execute("""
        SELECT m.id_message, m.contenu, m.date_envoi, m.id_expediteur,
               c.username, c.role
        FROM message m
        JOIN client c ON c.id_client = m.id_expediteur
        WHERE (m.id_expediteur=? AND m.id_destinataire=?)
           OR (m.id_expediteur=? AND m.id_destinataire=?)
        ORDER BY m.date_envoi ASC
    """, (session["user_id"], other_id, other_id, session["user_id"])).fetchall()
    conn.close()

    return jsonify([{
        "id_message": m["id_message"],
        "contenu": m["contenu"],
        "date_envoi": m["date_envoi"],
        "username": m["username"],
        "role": m["role"],
        "is_me": m["id_expediteur"] == session["user_id"]
    } for m in msgs])

# ---------------------------
# PANEL ADMIN
# ---------------------------
@app.route("/admin")
@admin_required
def admin_panel():
    conn = get_db()
    demandes_achat = conn.execute("""
        SELECT d.*, c.username, v.titre, v.marque, v.modele
        FROM demande_achat d
        JOIN client c ON d.id_client = c.id_client
        JOIN vehicule v ON d.id_vehicule = v.id_vehicule
        WHERE d.statut = 'en_attente'
    """).fetchall()

    demandes_ajout = conn.execute("""
        SELECT d.*, c.username
        FROM demande_ajout_vehicule d
        JOIN client c ON d.id_client = c.id_client
        WHERE d.statut = 'en_attente'
    """).fetchall()

    clients = conn.execute("SELECT * FROM client ORDER BY username").fetchall()
    ventes = conn.execute("""
        SELECT v.*, c.username, ve.titre
        FROM vente v
        JOIN client c ON v.id_client = c.id_client
        JOIN vehicule ve ON v.id_vehicule = ve.id_vehicule
        ORDER BY v.date_vente DESC
    """).fetchall()

    conn.close()
    return render_template("admin.html",
                           demandes_achat=demandes_achat,
                           demandes_ajout=demandes_ajout,
                           clients=clients,
                           ventes=ventes)


@app.route("/admin/traiter_achat/<int:id_demande>", methods=["POST"])
@admin_required
def traiter_achat(id_demande):
    decision = request.form.get("decision")
    conn = get_db()
    demande = conn.execute(
        "SELECT * FROM demande_achat WHERE id_demande=?", (id_demande,)
    ).fetchone()

    if decision == "accepter":
        prix_final = float(request.form.get("prix_final", demande["prix_propose"]))
        conn.execute("""
            INSERT INTO vente (date_vente, id_client, id_vehicule, prix_final)
            VALUES (?, ?, ?, ?)
        """, (today_iso(), demande["id_client"], demande["id_vehicule"], prix_final))
        conn.execute("UPDATE vehicule SET statut='vendu' WHERE id_vehicule=?", (demande["id_vehicule"],))
        conn.execute("UPDATE demande_achat SET statut='acceptee' WHERE id_demande=?", (id_demande,))
    else:
        conn.execute("UPDATE demande_achat SET statut='refusee' WHERE id_demande=?", (id_demande,))

    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel"))


@app.route("/admin/traiter_ajout/<int:id_demande>", methods=["POST"])
@admin_required
def traiter_ajout(id_demande):
    decision = request.form.get("decision")
    conn = get_db()

    if decision == "accepter":
        d = conn.execute(
            "SELECT * FROM demande_ajout_vehicule WHERE id_demande=?", (id_demande,)
        ).fetchone()
        cur = conn.execute("""
            INSERT INTO vehicule (titre, marque, modele, annee, carburant, km, prix_vente,
            couleur, puissance, boite, nb_portes, etat, localisation, description, statut)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'en_stock')
        """, (d["titre"], d["marque"], d["modele"], d["annee"], d["carburant"], d["km"],
              d["prix_vente"], d["couleur"], d["puissance"], d["boite"], d["nb_portes"],
              d["etat"], d["localisation"], d["description"]))
        conn.execute("UPDATE demande_ajout_vehicule SET statut='acceptee' WHERE id_demande=?", (id_demande,))
    else:
        conn.execute("UPDATE demande_ajout_vehicule SET statut='refusee' WHERE id_demande=?", (id_demande,))

    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel"))


@app.route("/admin/role/<int:id_client>", methods=["POST"])
@admin_required
def changer_role(id_client):
    role = request.form.get("role")
    if role in ("user", "verified", "admin"):
        conn = get_db()
        conn.execute("UPDATE client SET role=? WHERE id_client=?", (role, id_client))
        conn.commit()
        conn.close()
    return redirect(url_for("admin_panel"))


@app.route("/admin/supprimer_client/<int:id_client>", methods=["POST"])
@admin_required
def supprimer_client(id_client):
    conn = get_db()
    conn.execute("DELETE FROM client WHERE id_client=?", (id_client,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_panel"))


# ---------------------------
# WEBSOCKET MESSAGERIE
# ---------------------------

    conn = get_db()
    if user_id != -1:
        conn.execute("""
            INSERT INTO message (id_expediteur, id_destinataire, contenu, date_envoi)
            VALUES (?, ?, ?, ?)
        """, (user_id, other_id, contenu, today_iso()))
        conn.commit()
        user = conn.execute(
            "SELECT username, role FROM client WHERE id_client=?", (user_id,)
        ).fetchone()
        username = user["username"]
        role = user["role"]
    else:
        username = "admin"
        role = "admin"
    conn.close()

    emit("message", {
        "contenu": contenu,
        "username": username,
        "role": role,
        "date": today_iso()
    }, room=room)

# ---------------------------
# MAIN
# ---------------------------
if __name__ == "__main__":
    init_db()
    app.run(debug=False, host="0.0.0.0", port=5000)    
    '''
    Ensuite les autres PC du réseau peuvent accéder au site via ton IP locale, par exemple :
    http://172.17.6.241:5000
    '''