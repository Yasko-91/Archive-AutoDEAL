PRAGMA foreign_keys = ON;

-- =========================
-- TABLE CLIENT
-- =========================
CREATE TABLE IF NOT EXISTS client (
    id_client      INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT NOT NULL UNIQUE,
    nom            TEXT NOT NULL,
    prenom         TEXT NOT NULL,
    telephone      TEXT,
    email          TEXT UNIQUE,
    password_salt  TEXT NOT NULL,
    password_hash  TEXT NOT NULL,
    role           TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user', 'verified'))
);

-- =========================
-- TABLE VEHICULE
-- =========================
CREATE TABLE IF NOT EXISTS vehicule (
    id_vehicule  INTEGER PRIMARY KEY AUTOINCREMENT,
    titre        TEXT NOT NULL,
    marque       TEXT NOT NULL,
    modele       TEXT NOT NULL,
    annee        INTEGER NOT NULL CHECK (annee >= 1950),
    carburant    TEXT NOT NULL CHECK (carburant IN ('essence','diesel','hybride','electrique')),
    km           INTEGER NOT NULL CHECK (km >= 0),
    prix_vente   REAL NOT NULL CHECK (prix_vente > 0),
    couleur      TEXT NOT NULL,
    puissance    INTEGER,
    boite        TEXT NOT NULL CHECK (boite IN ('manuelle','automatique')),
    nb_portes    INTEGER NOT NULL CHECK (nb_portes IN (3, 5)),
    etat         TEXT NOT NULL CHECK (etat IN ('neuf','occasion','accidente')),
    localisation TEXT NOT NULL,
    description  TEXT,
    statut       TEXT NOT NULL DEFAULT 'en_stock' CHECK (statut IN ('en_stock','vendu'))
);

-- =========================
-- TABLE PHOTOS
-- =========================
CREATE TABLE IF NOT EXISTS photo (
    id_photo    INTEGER PRIMARY KEY AUTOINCREMENT,
    id_vehicule INTEGER NOT NULL,
    chemin      TEXT NOT NULL,
    ordre       INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (id_vehicule) REFERENCES vehicule(id_vehicule) ON DELETE CASCADE
);

-- =========================
-- TABLE LIKES
-- =========================
CREATE TABLE IF NOT EXISTS like_vehicule (
    id_client   INTEGER NOT NULL,
    id_vehicule INTEGER NOT NULL,
    PRIMARY KEY (id_client, id_vehicule),
    FOREIGN KEY (id_client) REFERENCES client(id_client) ON DELETE CASCADE,
    FOREIGN KEY (id_vehicule) REFERENCES vehicule(id_vehicule) ON DELETE CASCADE
);

-- =========================
-- TABLE MESSAGES
-- =========================
CREATE TABLE IF NOT EXISTS message (
    id_message     INTEGER PRIMARY KEY AUTOINCREMENT,
    id_expediteur  INTEGER NOT NULL,
    id_destinataire INTEGER NOT NULL,
    contenu        TEXT NOT NULL,
    date_envoi     TEXT NOT NULL,
    lu             INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (id_expediteur) REFERENCES client(id_client) ON DELETE CASCADE,
    FOREIGN KEY (id_destinataire) REFERENCES client(id_client) ON DELETE CASCADE
);

-- =========================
-- TABLE DEMANDE D'ACHAT
-- =========================
CREATE TABLE IF NOT EXISTS demande_achat (
    id_demande    INTEGER PRIMARY KEY AUTOINCREMENT,
    date_demande  TEXT NOT NULL,
    id_client     INTEGER NOT NULL,
    id_vehicule   INTEGER NOT NULL,
    statut        TEXT NOT NULL DEFAULT 'en_attente' CHECK (statut IN ('en_attente','acceptee','refusee')),
    prix_propose  REAL NOT NULL CHECK (prix_propose > 0),
    commentaire   TEXT,
    FOREIGN KEY (id_client) REFERENCES client(id_client),
    FOREIGN KEY (id_vehicule) REFERENCES vehicule(id_vehicule)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_demande_unique_pending
ON demande_achat(id_vehicule)
WHERE statut = 'en_attente';

-- =========================
-- TABLE DEMANDE AJOUT VEHICULE
-- (envoyée par un utilisateur, validée par admin)
-- =========================
CREATE TABLE IF NOT EXISTS demande_ajout_vehicule (
    id_demande   INTEGER PRIMARY KEY AUTOINCREMENT,
    id_client    INTEGER NOT NULL,
    date_demande TEXT NOT NULL,
    statut       TEXT NOT NULL DEFAULT 'en_attente' CHECK (statut IN ('en_attente','acceptee','refusee')),
    titre        TEXT NOT NULL,
    marque       TEXT NOT NULL,
    modele       TEXT NOT NULL,
    annee        INTEGER NOT NULL,
    carburant    TEXT NOT NULL,
    km           INTEGER NOT NULL,
    prix_vente   REAL NOT NULL,
    couleur      TEXT NOT NULL,
    puissance    INTEGER,
    boite        TEXT NOT NULL,
    nb_portes    INTEGER NOT NULL,
    etat         TEXT NOT NULL,
    localisation TEXT NOT NULL,
    description  TEXT,
    FOREIGN KEY (id_client) REFERENCES client(id_client)
);

-- =========================
-- TABLE VENTE
-- =========================
CREATE TABLE IF NOT EXISTS vente (
    id_vente    INTEGER PRIMARY KEY AUTOINCREMENT,
    date_vente  TEXT NOT NULL,
    id_client   INTEGER NOT NULL,
    id_vehicule INTEGER NOT NULL UNIQUE,
    prix_final  REAL NOT NULL CHECK (prix_final > 0),
    FOREIGN KEY (id_client) REFERENCES client(id_client),
    FOREIGN KEY (id_vehicule) REFERENCES vehicule(id_vehicule)
);

-- =========================
-- INDEX
-- =========================
CREATE INDEX IF NOT EXISTS idx_vehicule_statut ON vehicule(statut);
CREATE INDEX IF NOT EXISTS idx_vehicule_prix   ON vehicule(prix_vente);
CREATE INDEX IF NOT EXISTS idx_vente_date      ON vente(date_vente);
CREATE INDEX IF NOT EXISTS idx_demande_statut  ON demande_achat(statut);
CREATE INDEX IF NOT EXISTS idx_message_dest    ON message(id_destinataire);
