"""
services_secretariat.py — Logique métier du module Secrétariat (courrier).

============================================================================
D'OÙ VIENT CE FICHIER ?
============================================================================
Portage de web/secretariat.php (traitement du formulaire, validation de la
pièce jointe) et de web/fichier.php (téléchargement/visualisation d'une
pièce jointe), + de la fonction extensions_pieces_jointes() de
web/includes/helpers.php.

============================================================================
COMMENT LES FICHIERS SONT-ILS STOCKÉS ?
============================================================================
Comme en PHP : le contenu du fichier (PDF/Word/Excel) est stocké TEL QUEL
dans la base de données, dans une colonne BLOB (fichier_blob), à côté de
son nom d'origine (nom_fichier). Il n'y a donc rien à gérer sur le disque
(pas de dossier "uploads/" à sauvegarder séparément) : sauvegarder le
fichier data/gestion.db suffit à sauvegarder tous les courriers ET leurs
pièces jointes.

============================================================================
PHP → STREAMLIT : COMMENT ON RÉCUPÈRE LE FICHIER ENVOYÉ ?
============================================================================
En PHP, le fichier envoyé arrivait dans $_FILES['piece_jointe'] (tableau
avec 'name', 'size', 'tmp_name', 'error'...). En Streamlit, st.file_uploader
(voir vues/secretariat.py) retourne directement un objet avec les mêmes
informations utiles : .name, .size, et .getvalue() pour lire le contenu —
pas besoin de fichier temporaire à nettoyer, Streamlit s'en occupe.

============================================================================
COURRIER PAR RÉGION
============================================================================
Comme pour la Comptabilité (voir services_comptabilite.py), le PHP ne
filtrait JAMAIS par région malgré la colonne region_id présente sur les
tables `courrier_arrive`/`courrier_depart`. Ce portage Python CORRIGE ce
point : chaque direction régionale ne voit que son propre courrier.
region_id=None (compte "admin" de démarrage, sans région assignée) reste
une VUE GLOBALE — voir condition_region() dans db.py pour le détail de
cette règle, partagée par tous les modules de l'application.
============================================================================
"""

from db import get_connection, executer, condition_region

TAILLE_MAX_PIECE_JOINTE = 10 * 1024 * 1024  # 10 Mo, comme en PHP

# ASTUCE — AUTORISER UN NOUVEAU FORMAT (ex. images .png) : ajoutez une
# ligne ici "extension": "type_mime". C'est la SEULE liste à modifier :
# le formulaire (st.file_uploader) et la validation ci-dessous la lisent
# automatiquement.
EXTENSIONS_AUTORISEES = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

# Type de courrier -> (table, nom de la colonne "interlocuteur"). Ces noms
# viennent de db.py : courrier_arrive a une colonne `expediteur`,
# courrier_depart a une colonne `destinataire`.
TABLE_PAR_TYPE = {
    "Arrivée": ("courrier_arrive", "expediteur"),
    "Départ": ("courrier_depart", "destinataire"),
}


def _valider_piece_jointe(fichier) -> dict:
    """
    fichier : l'objet renvoyé par st.file_uploader(...), ou None si
    l'utilisateur n'a choisi aucun fichier (autorisé, comme en PHP : un
    courrier peut être enregistré sans pièce jointe scannée).
    """
    if fichier is None:
        return {"ok": True, "nom": None, "contenu": None}

    if fichier.size > TAILLE_MAX_PIECE_JOINTE:
        return {"ok": False, "message": "Le fichier dépasse la taille maximale autorisée (10 Mo)."}

    extension = fichier.name.rsplit(".", 1)[-1].lower() if "." in fichier.name else ""
    if extension not in EXTENSIONS_AUTORISEES:
        return {
            "ok": False,
            "message": "Format non autorisé : seuls PDF, Word (.doc/.docx) et Excel (.xls/.xlsx) sont acceptés.",
        }

    return {"ok": True, "nom": fichier.name, "contenu": fichier.getvalue()}


def enregistrer_courrier(
    type_courrier: str, date: str, interlocuteur: str, objet: str, fichier, region_id: int | None
) -> dict:
    """
    Enregistre un courrier arrivée ou départ, avec sa pièce jointe
    éventuelle. `fichier` vient de st.file_uploader() côté page (voir
    ci-dessus) — peut être None.
    """
    interlocuteur = interlocuteur.strip()
    objet = objet.strip()

    if type_courrier not in TABLE_PAR_TYPE:
        return {"ok": False, "message": "Veuillez sélectionner un type de courrier."}
    if date == "" or interlocuteur == "" or objet == "":
        return {"ok": False, "message": "Veuillez remplir tous les champs."}

    piece = _valider_piece_jointe(fichier)
    if not piece["ok"]:
        return piece

    table, colonne_interlocuteur = TABLE_PAR_TYPE[type_courrier]
    nom_fichier = piece["nom"] or "Aucun scan"

    conn = get_connection()
    try:
        # table/colonne_interlocuteur viennent UNIQUEMENT de TABLE_PAR_TYPE
        # ci-dessus (jamais d'une valeur saisie par l'utilisateur), donc ce
        # f-string ne pose pas de risque d'injection SQL.
        executer(
            conn,
            f"""
            INSERT INTO {table} (date, {colonne_interlocuteur}, objet, statut, nom_fichier, fichier_blob, region_id)
            VALUES (?, ?, ?, 'Enregistré', ?, ?, ?)
            """,
            (date, interlocuteur, objet, nom_fichier, piece["contenu"], region_id),
        )
        conn.commit()
        return {"ok": True, "message": "Courrier ajouté."}
    finally:
        conn.close()


def modifier_courrier(id_courrier: int, type_courrier: str, date: str, interlocuteur: str, objet: str, fichier) -> dict:
    """
    Met à jour un courrier déjà enregistré (voir enregistrer_courrier pour
    la création). `fichier` peut être None : dans ce cas, la pièce jointe
    déjà enregistrée est conservée telle quelle — seul un nouveau fichier
    choisi dans st.file_uploader() la remplace.

    ⚠️ `type_courrier` ici est le type ACTUEL du courrier (Arrivée/Départ),
    pas un nouveau type à basculer vers : passer d'Arrivée à Départ
    changerait de table (courrier_arrive -> courrier_depart), ce qui n'est
    pas pris en charge par cette fonction — voir l'astuce en bas du fichier
    si ce besoin se présente.
    """
    interlocuteur = interlocuteur.strip()
    objet = objet.strip()

    if type_courrier not in TABLE_PAR_TYPE:
        return {"ok": False, "message": "Veuillez sélectionner un type de courrier."}
    if date == "" or interlocuteur == "" or objet == "":
        return {"ok": False, "message": "Veuillez remplir tous les champs."}

    piece = _valider_piece_jointe(fichier)
    if not piece["ok"]:
        return piece

    table, colonne_interlocuteur = TABLE_PAR_TYPE[type_courrier]

    conn = get_connection()
    try:
        if piece["nom"] is None:
            # Aucun nouveau fichier choisi : on ne touche pas à la pièce
            # jointe déjà enregistrée (nom_fichier / fichier_blob).
            executer(
                conn,
                f"UPDATE {table} SET date = ?, {colonne_interlocuteur} = ?, objet = ? WHERE id = ?",
                (date, interlocuteur, objet, id_courrier),
            )
        else:
            executer(
                conn,
                f"UPDATE {table} SET date = ?, {colonne_interlocuteur} = ?, objet = ?, nom_fichier = ?, fichier_blob = ? WHERE id = ?",
                (date, interlocuteur, objet, piece["nom"], piece["contenu"], id_courrier),
            )
        conn.commit()
        return {"ok": True, "message": "Courrier modifié."}
    finally:
        conn.close()


def lister_courriers(region_id: int | None) -> list:
    """
    Retourne les courriers (arrivée + départ mélangés) de la région
    donnée, les plus récents en premier — portage du UNION ALL de
    web/secretariat.php, avec le filtre par région ajouté (voir la note
    "COURRIER PAR RÉGION" en haut de ce fichier).
    """
    conn = get_connection()
    try:
        clause, parametres = condition_region(region_id)
        return executer(
            conn,
            f"""
            SELECT id, date, 'Arrivée' AS type, expediteur AS interlocuteur, objet, nom_fichier
            FROM courrier_arrive
            WHERE 1=1{clause}
            UNION ALL
            SELECT id, date, 'Départ' AS type, destinataire AS interlocuteur, objet, nom_fichier
            FROM courrier_depart
            WHERE 1=1{clause}
            ORDER BY date DESC
            """,
            parametres + parametres,
        ).fetchall()
    finally:
        conn.close()


def obtenir_piece_jointe(type_courrier: str, id_courrier: int) -> dict | None:
    """
    Retourne {"nom": ..., "contenu": bytes, "mime": ...} pour la pièce
    jointe d'un courrier, ou None si le courrier n'existe pas ou n'a pas
    de pièce jointe. Utilisé par vues/secretariat.py pour proposer un
    bouton de téléchargement (équivalent de web/fichier.php).
    """
    if type_courrier not in TABLE_PAR_TYPE:
        return None
    table, _ = TABLE_PAR_TYPE[type_courrier]

    conn = get_connection()
    try:
        ligne = executer(
            conn, f"SELECT nom_fichier, fichier_blob FROM {table} WHERE id = ?", (id_courrier,)
        ).fetchone()
    finally:
        conn.close()

    if ligne is None or ligne["fichier_blob"] is None:
        return None

    nom = ligne["nom_fichier"] or "document"
    extension = nom.rsplit(".", 1)[-1].lower() if "." in nom else ""
    mime = EXTENSIONS_AUTORISEES.get(extension, "application/octet-stream")
    # bytes(...) : normalise le contenu quelle que soit la base (SQLite
    # renvoie déjà des bytes, PostgreSQL/psycopg2 renvoie parfois un
    # "memoryview" pour une colonne bytea).
    contenu = bytes(ligne["fichier_blob"])
    return {"nom": nom, "contenu": contenu, "mime": mime}


# ============================================================================
# ASTUCES POUR LE STATISTICIEN
# ============================================================================
# 1. Ajouter un champ au formulaire (ex. "Référence") : ajoutez la colonne
#    dans db.py (tables courrier_arrive ET courrier_depart — voir l'astuce
#    "AJOUTER UNE COLONNE" en haut de db.py), ajoutez le champ dans
#    vues/secretariat.py, puis passez-le à enregistrer_courrier() ET à la
#    requête INSERT ci-dessus.
#
# 2. Pourquoi le contenu du fichier est-il stocké EN BASE (BLOB) plutôt que
#    dans un dossier sur le disque ? Pour que "sauvegarder l'application"
#    se résume à "copier un seul fichier" (data/gestion.db). L'inconvénient
#    est que la base grossit avec chaque pièce jointe — pour une utilisation
#    de bureau/régionale (quelques dizaines de courriers par mois), ce n'est
#    pas un problème.
#
# 3. Tester ce fichier sans lancer Streamlit :
#        from services_secretariat import lister_courriers
#        print(lister_courriers())
# ============================================================================
