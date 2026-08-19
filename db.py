"""
db.py — Connexion à la base de données et création des tables.

============================================================================
D'OÙ VIENT CE FICHIER ?
============================================================================
Il remplace deux fichiers PHP à la fois :
  - web/config.php    (quels sont l'hôte, le nom de la base, etc.)
  - web/database.php  (comment on s'y connecte, et la liste des CREATE
                        TABLE qui construisent toute la base au premier
                        lancement)

Le PHP se connectait à un serveur MySQL séparé (celui de l'hébergeur OVH,
ou un XAMPP local). Ici, on utilise SQLite par défaut : c'est une base de
données qui vit dans UN SEUL FICHIER (data/gestion.db), sans serveur à
installer ni à démarrer. C'est le choix le plus simple à héberger et à
sauvegarder (il suffit de copier le fichier .db).

Si un jour vous changez d'hébergeur et qu'il impose PostgreSQL, vous n'avez
PAS besoin de réécrire ce fichier : il suffit de définir la variable
d'environnement DATABASE_URL (voir plus bas, section "CHANGER DE BASE").

============================================================================
POURQUOI CE DÉCOUPAGE (get_connection / adapter_requete / etc.) ?
============================================================================
SQLite et PostgreSQL n'utilisent pas exactement la même façon d'écrire les
requêtes préparées (SQLite attend des "?", PostgreSQL attend des "%s").
Plutôt que d'obliger CHAQUE fonction de models.py/services.py à connaître
cette différence, tout le reste du code écrit ses requêtes SQL avec des
"?" (comme en SQLite), et c'est ce fichier — et lui seul — qui traduit au
besoin. Résultat : vous pouvez lire et modifier models.py/services.py sans
jamais avoir à vous soucier de quelle base de données tourne derrière.
============================================================================
"""

import os
import sqlite3
from pathlib import Path

# ----------------------------------------------------------------------
# 1. OÙ EST LA BASE DE DONNÉES ?
# ----------------------------------------------------------------------
# Par défaut : un fichier SQLite dans streamlit_app/data/gestion.db.
# Le dossier "data" est créé automatiquement s'il n'existe pas encore.
DOSSIER_APP = Path(__file__).resolve().parent
DOSSIER_DONNEES = DOSSIER_APP / "data"
DOSSIER_DONNEES.mkdir(exist_ok=True)
CHEMIN_SQLITE_PAR_DEFAUT = DOSSIER_DONNEES / "gestion.db"

# CHANGER DE BASE : pour passer sur PostgreSQL (par exemple chez un
# hébergeur qui l'impose), définissez la variable d'environnement
# DATABASE_URL avant de lancer l'application, par exemple :
#
#   DATABASE_URL=postgresql://utilisateur:motdepasse@hote:5432/nom_base
#
# Sous Windows (PowerShell), avant de lancer streamlit :
#   $env:DATABASE_URL = "postgresql://utilisateur:motdepasse@hote:5432/nom_base"
#   streamlit run app.py
#
# Sans cette variable, l'application utilise SQLite automatiquement — rien
# à configurer, c'est le fonctionnement "prêt à l'emploi".
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
UTILISE_POSTGRESQL = DATABASE_URL.startswith("postgresql://") or DATABASE_URL.startswith("postgres://")


def get_connection():
    """
    Retourne une connexion à la base de données, prête à l'emploi.

    Astuce : dans TOUT le reste du code (models.py, services.py, les
    pages), on écrit toujours :
        conn = get_connection()
        curseur = conn.cursor()
        curseur.execute("SELECT ... WHERE nom = ?", (valeur,))
    ... avec des "?" comme dans ce fichier, même si la base réelle est
    PostgreSQL (voir adapter_requete ci-dessous, appelée automatiquement).
    """
    if UTILISE_POSTGRESQL:
        return _connexion_postgresql()
    return _connexion_sqlite()


def _connexion_sqlite() -> sqlite3.Connection:
    conn = sqlite3.connect(str(CHEMIN_SQLITE_PAR_DEFAUT))
    # sqlite3.Row permet d'accéder aux colonnes par leur nom, comme un
    # dictionnaire (ligne["nom"]) plutôt que par position (ligne[0]) —
    # exactement comme PDO::FETCH_ASSOC en PHP.
    conn.row_factory = sqlite3.Row
    # Sans cette ligne, SQLite n'empêche PAS de violer une contrainte
    # FOREIGN KEY (elle est ignorée par défaut, contrairement à MySQL).
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _connexion_postgresql():
    # Import différé : psycopg2 n'est nécessaire QUE si on utilise
    # PostgreSQL. Un statisticien qui reste sur SQLite n'a pas besoin de
    # l'installer.
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError as erreur:
        raise RuntimeError(
            "DATABASE_URL pointe vers PostgreSQL mais le paquet 'psycopg2-binary' "
            "n'est pas installé. Lancez : pip install psycopg2-binary"
        ) from erreur
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


def executer(conn, sql: str, parametres: tuple = ()):
    """
    Exécute une requête en traduisant si besoin les "?" en "%s" pour
    PostgreSQL. C'est la fonction que models.py/services.py utilisent à
    la place de conn.cursor().execute(...) directement, pour rester
    indépendants de la base réelle.

    Retourne le curseur (pour pouvoir enchaîner .fetchone()/.fetchall()).
    """
    curseur = conn.cursor()
    if UTILISE_POSTGRESQL:
        sql = sql.replace("?", "%s")
    curseur.execute(sql, parametres)
    return curseur


def condition_region(region_id: int | None, colonne: str = "region_id") -> tuple[str, tuple]:
    """
    Fragment de clause SQL (à coller après un "WHERE 1=1" dans une
    requête) + le(s) paramètre(s) associé(s), pour restreindre une
    requête aux données d'une seule région (direction régionale).

    Utilisé par TOUS les services_xxx.py qui isolent leurs données par
    région (comptabilité, secrétariat, IHPC, RH, documentation,
    annuaires...) : chaque module a ses propres tables et requêtes, mais
    la RÈGLE de filtrage est identique partout, donc centralisée ici une
    fois pour toutes plutôt que recopiée dans chaque fichier.

    Cas particulier — region_id = None (le compte "admin" de démarrage,
    qui n'a aucune région assignée : voir _semer_donnees_de_base()
    ci-dessous) : ne filtre RIEN, retourne une chaîne vide et aucun
    paramètre. Ce compte voit alors TOUTES les régions (vue globale),
    ce qui est pratique avant que les comptes régionaux n'existent.

    Exemple d'utilisation typique dans un services_xxx.py :

        clause, parametres = condition_region(region_id)
        executer(conn, f"SELECT ... FROM matable WHERE 1=1{clause}", parametres)

    Si la colonne region_id se trouve sur une table jointe (ex. un
    JOIN), précisez son nom complet avec l'alias de table :

        clause, parametres = condition_region(region_id, colonne="operations.region_id")
    """
    if region_id is None:
        return "", ()
    return f" AND {colonne} = ?", (region_id,)


# ----------------------------------------------------------------------
# 2. CRÉATION DES TABLES (équivalent de InitialiserLaBaseDeDonnees en PHP)
# ----------------------------------------------------------------------
# Chaque chaîne ci-dessous est une commande "CREATE TABLE IF NOT EXISTS" :
# elle ne fait rien si la table existe déjà, donc on peut l'appeler à
# chaque démarrage sans risque d'effacer vos données.
#
# ASTUCE — AJOUTER UNE COLONNE : si vous ajoutez une colonne ICI après
# que la base existe déjà, ça ne suffit pas : "CREATE TABLE IF NOT EXISTS"
# ne modifie pas une table existante. Il faut soit :
#   (a) supprimer le fichier data/gestion.db pour repartir de zéro
#       (vous perdez toutes les données), soit
#   (b) ajouter une ligne du style :
#       conn.execute("ALTER TABLE MaTable ADD COLUMN ma_colonne TEXT")
#       dans initialiser_la_base_de_donnees(), en dessous des CREATE TABLE.
TABLES_SQL = [
    # ---- Régions ("directions régionales") et services (les 9 onglets) ----
    """
    CREATE TABLE IF NOT EXISTS regions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL UNIQUE,
        code TEXT NOT NULL UNIQUE,
        actif INTEGER NOT NULL DEFAULT 1
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS services (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL UNIQUE,
        slug TEXT NOT NULL UNIQUE,
        icone TEXT DEFAULT ''
    )
    """,
    # ---- Comptes utilisateurs ----
    """
    CREATE TABLE IF NOT EXISTS utilisateurs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT NOT NULL UNIQUE,
        motdepasse_hash TEXT NOT NULL,
        region_id INTEGER,
        role TEXT NOT NULL DEFAULT 'agent',
        FOREIGN KEY (region_id) REFERENCES regions(id)
    )
    """,
    # ---- Sessions actives (garder la connexion après un F5) : voir
    # restaurer_session_depuis_url() dans auth.py. ----
    """
    CREATE TABLE IF NOT EXISTS sessions_actives (
        jeton TEXT PRIMARY KEY,
        utilisateur_id INTEGER NOT NULL,
        date_creation TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (utilisateur_id) REFERENCES utilisateurs(id)
    )
    """,
    # ---- Comptabilité ----
    """
    CREATE TABLE IF NOT EXISTS patrimoine (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT DEFAULT CURRENT_TIMESTAMP,
        type TEXT NOT NULL,
        nom TEXT NOT NULL,
        etat TEXT NOT NULL,
        lieu TEXT NOT NULL,
        region_id INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS operations (
        id_operation INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT DEFAULT CURRENT_TIMESTAMP,
        type TEXT NOT NULL,
        libelle TEXT NOT NULL,
        montant REAL DEFAULT 0,
        region_id INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ecritures (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        id_operation INTEGER,
        compte INTEGER,
        debit REAL DEFAULT 0,
        credit REAL DEFAULT 0,
        FOREIGN KEY (id_operation) REFERENCES operations(id_operation)
    )
    """,
    # ---- Secrétariat (courrier) ----
    """
    CREATE TABLE IF NOT EXISTS courrier_depart (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT DEFAULT CURRENT_TIMESTAMP,
        destinataire TEXT NOT NULL,
        objet TEXT NOT NULL,
        statut TEXT NOT NULL,
        nom_fichier TEXT DEFAULT 'Aucun scan',
        fichier_blob BLOB,
        region_id INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS courrier_arrive (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT DEFAULT CURRENT_TIMESTAMP,
        expediteur TEXT NOT NULL,
        objet TEXT NOT NULL,
        statut TEXT NOT NULL,
        nom_fichier TEXT DEFAULT 'Aucun scan',
        fichier_blob BLOB,
        region_id INTEGER
    )
    """,
    # ---- IHPC (indice des prix) ----
    """
    CREATE TABLE IF NOT EXISTS vendeurs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fournisseur TEXT NOT NULL,
        motdepasse_hash TEXT NOT NULL,
        region_id INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS acheteurs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client TEXT NOT NULL,
        region_id INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS marches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        marche TEXT NOT NULL,
        region_id INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS produits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        produit TEXT NOT NULL,
        region_id INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS transactions_ihpc (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_du_jour TEXT DEFAULT CURRENT_TIMESTAMP,
        fournisseur TEXT NOT NULL,
        marche TEXT NOT NULL,
        client TEXT NOT NULL,
        produit TEXT NOT NULL,
        quantites INTEGER DEFAULT 0,
        prix REAL DEFAULT 0,
        montant REAL DEFAULT 0,
        payer REAL DEFAULT 0,
        region_id INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS comptabilite_ihpc (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_du_jour TEXT DEFAULT CURRENT_TIMESTAMP,
        agent TEXT NOT NULL,
        montant REAL DEFAULT 0,
        revente REAL DEFAULT 0,
        depense REAL DEFAULT 0,
        relicat REAL DEFAULT 0,
        impaye REAL DEFAULT 0,
        region_id INTEGER
    )
    """,
    # ---- Ressources humaines ----
    """
    CREATE TABLE IF NOT EXISTS employes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_creation TEXT DEFAULT CURRENT_TIMESTAMP,
        nom TEXT NOT NULL,
        prenom TEXT NOT NULL,
        email TEXT UNIQUE,
        telephone TEXT,
        date_naissance TEXT,
        lieu_naissance TEXT,
        nationalite TEXT,
        numero_id TEXT UNIQUE,
        adresse TEXT,
        fonction TEXT,
        profession TEXT,
        type_contrat TEXT,
        statut TEXT DEFAULT 'Actif',
        date_embauche TEXT NOT NULL,
        salaire_base REAL,
        etat_civil TEXT,
        nombre_enfants INTEGER DEFAULT 0,
        region_id INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS contrats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_creation TEXT DEFAULT CURRENT_TIMESTAMP,
        employe_id INTEGER NOT NULL,
        type_contrat TEXT,
        date_debut TEXT NOT NULL,
        date_fin TEXT,
        duree_essai INTEGER,
        statut TEXT DEFAULT 'Actif',
        region_id INTEGER,
        FOREIGN KEY (employe_id) REFERENCES employes(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS conges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_creation TEXT DEFAULT CURRENT_TIMESTAMP,
        employe_id INTEGER NOT NULL,
        type_conge TEXT NOT NULL,
        date_debut TEXT NOT NULL,
        date_fin TEXT NOT NULL,
        nombre_jours INTEGER,
        motif TEXT,
        statut TEXT DEFAULT 'En attente',
        approuve_par INTEGER,
        date_approbation TEXT,
        region_id INTEGER,
        FOREIGN KEY (employe_id) REFERENCES employes(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS formations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_creation TEXT DEFAULT CURRENT_TIMESTAMP,
        employe_id INTEGER NOT NULL,
        titre TEXT NOT NULL,
        domaine TEXT,
        date_debut TEXT NOT NULL,
        date_fin TEXT,
        organisme TEXT,
        cout REAL,
        certificat TEXT,
        statut TEXT DEFAULT 'En cours',
        region_id INTEGER,
        FOREIGN KEY (employe_id) REFERENCES employes(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS paies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_creation TEXT DEFAULT CURRENT_TIMESTAMP,
        employe_id INTEGER NOT NULL,
        mois_annee TEXT NOT NULL,
        salaire_base REAL,
        primes REAL DEFAULT 0,
        retenues REAL DEFAULT 0,
        cotisations_sociales REAL DEFAULT 0,
        salaire_net REAL,
        date_versement TEXT,
        statut TEXT DEFAULT 'En attente',
        region_id INTEGER,
        FOREIGN KEY (employe_id) REFERENCES employes(id),
        UNIQUE (employe_id, mois_annee)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS evaluations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_creation TEXT DEFAULT CURRENT_TIMESTAMP,
        employe_id INTEGER NOT NULL,
        evaluateur_id INTEGER,
        periode_debut TEXT,
        periode_fin TEXT,
        note_performance INTEGER,
        commentaires TEXT,
        competences_cles TEXT,
        points_amelioration TEXT,
        date_evaluation TEXT,
        region_id INTEGER,
        FOREIGN KEY (employe_id) REFERENCES employes(id)
    )
    """,
    # ---- Documentation ----
    """
    CREATE TABLE IF NOT EXISTS categories_documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_creation TEXT DEFAULT CURRENT_TIMESTAMP,
        nom TEXT NOT NULL,
        description TEXT,
        ordre INTEGER DEFAULT 0,
        actif INTEGER DEFAULT 1,
        region_id INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_creation TEXT DEFAULT CURRENT_TIMESTAMP,
        date_modification TEXT,
        titre TEXT NOT NULL,
        description TEXT,
        categorie_id INTEGER,
        auteur TEXT,
        type_document TEXT,
        statut TEXT DEFAULT 'Brouillon',
        date_publication TEXT,
        numero_version TEXT,
        fichier_blob BLOB,
        nom_fichier TEXT,
        taille_fichier INTEGER,
        nombre_telechargements INTEGER DEFAULT 0,
        region_id INTEGER,
        FOREIGN KEY (categorie_id) REFERENCES categories_documents(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS versions_documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_creation TEXT DEFAULT CURRENT_TIMESTAMP,
        document_id INTEGER NOT NULL,
        numero_version TEXT,
        changements TEXT,
        auteur_modification TEXT,
        fichier_blob BLOB,
        nom_fichier TEXT,
        region_id INTEGER,
        FOREIGN KEY (document_id) REFERENCES documents(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS acces_documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_creation TEXT DEFAULT CURRENT_TIMESTAMP,
        document_id INTEGER NOT NULL,
        utilisateur_id INTEGER,
        type_acces TEXT DEFAULT 'lecture',
        date_expiration TEXT,
        region_id INTEGER,
        FOREIGN KEY (document_id) REFERENCES documents(id),
        FOREIGN KEY (utilisateur_id) REFERENCES utilisateurs(id),
        UNIQUE (document_id, utilisateur_id)
    )
    """,
    # ---- Annuaires statistiques ----
    """
    CREATE TABLE IF NOT EXISTS annuaires (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_creation TEXT DEFAULT CURRENT_TIMESTAMP,
        titre TEXT NOT NULL,
        description TEXT,
        type_annuaire TEXT,
        annee INTEGER,
        mois INTEGER,
        date_publication TEXT,
        statut TEXT DEFAULT 'Brouillon',
        format_fichier TEXT,
        fichier_blob BLOB,
        nom_fichier TEXT,
        nombre_telechargements INTEGER DEFAULT 0,
        region_id INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS entrees_annuaire (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_creation TEXT DEFAULT CURRENT_TIMESTAMP,
        annuaire_id INTEGER NOT NULL,
        type_entree TEXT,
        libelle TEXT NOT NULL,
        valeur REAL,
        pourcentage REAL,
        description TEXT,
        unite TEXT,
        notes TEXT,
        ordre INTEGER DEFAULT 0,
        region_id INTEGER,
        FOREIGN KEY (annuaire_id) REFERENCES annuaires(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS comparatifs_annuaires (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date_creation TEXT DEFAULT CURRENT_TIMESTAMP,
        titre TEXT NOT NULL,
        description TEXT,
        annuaire_source_id INTEGER,
        annuaire_comparaison_id INTEGER,
        type_comparaison TEXT,
        resultats TEXT,
        date_generation TEXT,
        region_id INTEGER,
        FOREIGN KEY (annuaire_source_id) REFERENCES annuaires(id),
        FOREIGN KEY (annuaire_comparaison_id) REFERENCES annuaires(id)
    )
    """,
]

# Les 5 régions administratives du Togo (reprises telles quelles du PHP).
# ASTUCE : pour changer la liste des régions, modifiez ce dictionnaire —
# {nom affiché: code court} — puis relancez l'application.
REGIONS_PAR_DEFAUT = {
    "Savanes": "SAV",
    "Kara": "KAR",
    "Centrale": "CEN",
    "Plateaux": "PLA",
    "Maritime": "MAR",
}

# Les 9 services (== les 9 onglets/pages de l'application). "slug" doit
# rester stable : c'est ce qui relie une carte du tableau de bord à sa
# page (voir app.py). "icone" est juste un caractère affiché sur la carte.
SERVICES_PAR_DEFAUT = [
    ("Accueil", "accueil", "🏠"),
    ("Comptabilité", "comptabilite", "💰"),
    ("Secrétariat", "secretariat", "✉️"),
    ("Statistiques des faits d'état civil", "etat_civil", "📋"),
    ("Ressources humaines", "ressources_humaines", "👥"),
    ("IHPC / Indice des prix", "ihpc", "📊"),
    ("Annuaires statistiques", "annuaire", "📚"),
    ("Documentation et publication", "documentation", "📁"),
    ("Autre service", "autre_service", "➕"),
]


def initialiser_la_base_de_donnees() -> None:
    """
    Crée toutes les tables si elles n'existent pas encore, puis ajoute les
    régions/services par défaut et un premier compte administrateur.

    Appelée une fois au démarrage de app.py. Ne fait rien de destructeur :
    on peut l'appeler à chaque lancement de l'application sans risque.
    """
    conn = get_connection()
    try:
        for sql in TABLES_SQL:
            executer(conn, sql)
        conn.commit()
        _semer_donnees_de_base(conn)
        conn.commit()
    finally:
        conn.close()


def _semer_donnees_de_base(conn) -> None:
    # Régions.
    for nom, code in REGIONS_PAR_DEFAUT.items():
        executer(conn, "INSERT OR IGNORE INTO regions (nom, code) VALUES (?, ?)", (nom, code))

    # Services (les cartes du tableau de bord / entrées du menu).
    for nom, slug, icone in SERVICES_PAR_DEFAUT:
        executer(
            conn,
            "INSERT OR IGNORE INTO services (nom, slug, icone) VALUES (?, ?, ?)",
            (nom, slug, icone),
        )

    # Compte administrateur de démarrage, pour pouvoir se connecter la
    # toute première fois (avant qu'aucun autre compte n'existe).
    #
    # ⚠️ SÉCURITÉ : ce compte est créé avec un mot de passe FIXE et connu
    # de quiconque lit ce code source. C'est volontaire (il faut bien un
    # premier compte pour démarrer), mais vous DEVEZ le changer dès votre
    # première connexion : allez dans la page "Utilisateurs" et créez
    # votre propre compte, ou changez ce mot de passe. Ne laissez jamais
    # ce compte de démarrage actif sur une application accessible sur
    # Internet.
    curseur = executer(conn, "SELECT COUNT(*) AS total FROM utilisateurs")
    if curseur.fetchone()["total"] == 0:
        # Import différé pour éviter un import circulaire (auth.py a
        # aussi besoin de db.py).
        from auth import hacher_mot_de_passe

        executer(
            conn,
            "INSERT INTO utilisateurs (nom, motdepasse_hash, region_id, role) VALUES (?, ?, NULL, 'admin_region')",
            ("admin", hacher_mot_de_passe("changez-moi")),
        )


# ============================================================================
# ASTUCES POUR LE STATISTICIEN
# ============================================================================
# 1. Voir le contenu de la base sans écrire de code : installez l'extension
#    VS Code "SQLite Viewer" (ou l'outil gratuit "DB Browser for SQLite",
#    https://sqlitebrowser.org/), puis ouvrez data/gestion.db.
#
# 2. Sauvegarder vos données : copiez simplement le fichier
#    data/gestion.db ailleurs (clé USB, autre dossier...). Tout est dedans.
#
# 3. Repartir de zéro (tout effacer) : fermez l'application puis supprimez
#    data/gestion.db. Il sera recréé vide (avec le compte "admin" de
#    démarrage) au prochain lancement.
#
# 4. Ajouter une nouvelle table : copiez le modèle d'une des chaînes SQL
#    ci-dessus dans TABLES_SQL, changez le nom de la table et ses colonnes,
#    puis relancez l'application — la table sera créée automatiquement.
# ============================================================================
