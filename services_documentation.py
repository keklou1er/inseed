"""
services_documentation.py — Logique métier du module Documentation :
catégories, documents (avec fichier joint), versions, accès.

============================================================================
D'OÙ VIENT CE FICHIER ?
============================================================================
Portage de web/services.php (EnregistrerCategorie, ListerCategories,
EnregistrerDocument, ListerDocuments, SupprimerDocument,
EnregistrerVersionDocument, ListerVersionsDocument, AccorderAccesDocument,
ListerAccesDocument).

============================================================================
FONCTIONNALITÉS DU PHP NON REPRISES ICI (VOLONTAIREMENT)
============================================================================
ModifierDocument(), ObtenirDocument() et VerifierAccesDocument() existent
côté PHP mais web/documentation.php n'affiche aucun formulaire de
modification de document, ni de contrôle d'accès EFFECTIF avant
téléchargement (le champ "Accès" ne fait qu'ENREGISTRER une autorisation,
rien ne la vérifie encore côté PHP non plus). Comme pour le module RH,
on ne construit pas d'interface pour une fonctionnalité que le PHP
lui-même n'expose pas visiblement.

============================================================================
⚠️ CORRECTION : "ACCORDER L'ACCÈS" DEVIENT UN VRAI "UPSERT"
============================================================================
Le PHP utilise "INSERT ... ON DUPLICATE KEY UPDATE" pour que ré-accorder
un accès au MÊME document + MÊME utilisateur mette à jour la ligne
existante plutôt que d'en créer une deuxième. Mais la table PHP
TableAccesDoc n'a en réalité aucune contrainte UNIQUE(document_id,
utilisateur_id) pour que ça fonctionne vraiment (donc ce ON DUPLICATE KEY
UPDATE ne servait à rien côté MySQL sans cette clé). Ici, la contrainte
UNIQUE(document_id, utilisateur_id) a été ajoutée à la table
`acces_documents` (voir db.py) pour que le upsert fonctionne réellement,
comme l'intention du code PHP le suggérait.

============================================================================
ISOLATION PAR RÉGION
============================================================================
Comme pour les autres modules, le filtrage par région (déjà préparé côté
paramètres dans services.php mais jamais activé par documentation.php) est
ici réellement appliqué — voir condition_region() dans db.py.
============================================================================
"""

from db import get_connection, executer, condition_region

TAILLE_MAX_FICHIER = 10 * 1024 * 1024  # 10 Mo, comme en PHP

EXTENSIONS_AUTORISEES = {
    "pdf": "application/pdf",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "txt": "text/plain",
}

TYPES_DE_DOCUMENT = ["Rapport", "Politique", "Procédure", "Guide", "Manuel", "Formulaire", "Autre"]
STATUTS_DOCUMENT = ["Brouillon", "En révision", "Publié", "Archivé"]
TYPES_ACCES = ["lecture", "lecture_ecriture", "admin"]


def _valider_fichier(fichier) -> dict:
    """fichier : objet renvoyé par st.file_uploader(...), ou None (autorisé)."""
    if fichier is None:
        return {"ok": True, "nom": "", "contenu": None, "taille": 0}
    if fichier.size > TAILLE_MAX_FICHIER:
        return {"ok": False, "message": "Le fichier dépasse la taille maximale de 10 Mo."}
    extension = fichier.name.rsplit(".", 1)[-1].lower() if "." in fichier.name else ""
    if extension not in EXTENSIONS_AUTORISEES:
        formats = ", ".join(sorted(EXTENSIONS_AUTORISEES))
        return {"ok": False, "message": f"Format non autorisé. Formats acceptés : {formats}."}
    return {"ok": True, "nom": fichier.name, "contenu": fichier.getvalue(), "taille": fichier.size}


# ----------------------------------------------------------------------
# 1. CATÉGORIES
# ----------------------------------------------------------------------
def enregistrer_categorie(nom: str, description: str, ordre: int, region_id: int | None) -> dict:
    nom = nom.strip()
    if nom == "":
        return {"ok": False, "message": "Le nom de la catégorie ne peut pas être vide."}
    conn = get_connection()
    try:
        executer(
            conn,
            "INSERT INTO categories_documents (nom, description, ordre, actif, region_id) VALUES (?, ?, ?, 1, ?)",
            (nom, description.strip() or None, ordre, region_id),
        )
        conn.commit()
        return {"ok": True, "message": "Catégorie enregistrée avec succès."}
    finally:
        conn.close()


def modifier_categorie(categorie_id: int, nom: str, description: str, ordre: int) -> dict:
    """Met à jour une catégorie déjà enregistrée (voir enregistrer_categorie pour la création)."""
    nom = nom.strip()
    if nom == "":
        return {"ok": False, "message": "Le nom de la catégorie ne peut pas être vide."}
    conn = get_connection()
    try:
        executer(
            conn,
            "UPDATE categories_documents SET nom = ?, description = ?, ordre = ? WHERE id = ?",
            (nom, description.strip() or None, ordre, categorie_id),
        )
        conn.commit()
        return {"ok": True, "message": "Catégorie modifiée avec succès."}
    finally:
        conn.close()


def lister_categories(region_id: int | None) -> list:
    conn = get_connection()
    try:
        clause, parametres = condition_region(region_id)
        return executer(
            conn, f"SELECT * FROM categories_documents WHERE actif = 1{clause} ORDER BY ordre, nom", parametres
        ).fetchall()
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 2. DOCUMENTS
# ----------------------------------------------------------------------
def enregistrer_document(
    titre: str, description: str, categorie_id: int | None, auteur: str, type_document: str,
    statut: str, date_publication: str, numero_version: str, fichier, region_id: int | None,
) -> dict:
    titre = titre.strip()
    if titre == "":
        return {"ok": False, "message": "Le titre du document ne peut pas être vide."}

    piece = _valider_fichier(fichier)
    if not piece["ok"]:
        return piece

    conn = get_connection()
    try:
        executer(
            conn,
            """
            INSERT INTO documents (
                titre, description, categorie_id, auteur, type_document, statut,
                date_publication, numero_version, fichier_blob, nom_fichier, taille_fichier, region_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                titre, description.strip() or None, categorie_id, auteur.strip() or None,
                type_document or None, statut or "Brouillon", date_publication or None,
                numero_version.strip() or "1.0", piece["contenu"], piece["nom"], piece["taille"], region_id,
            ),
        )
        conn.commit()
        return {"ok": True, "message": "Document enregistré avec succès."}
    finally:
        conn.close()


def modifier_document(
    document_id: int, titre: str, description: str, categorie_id: int | None, auteur: str, type_document: str,
    statut: str, date_publication: str, numero_version: str, fichier,
) -> dict:
    """
    Met à jour un document déjà enregistré (voir enregistrer_document pour
    la création). `fichier` peut être None : dans ce cas, le fichier déjà
    enregistré est conservé tel quel — seul un nouveau fichier choisi dans
    st.file_uploader() le remplace.
    """
    titre = titre.strip()
    if titre == "":
        return {"ok": False, "message": "Le titre du document ne peut pas être vide."}

    piece = _valider_fichier(fichier)
    if not piece["ok"]:
        return piece

    conn = get_connection()
    try:
        if piece["nom"] == "":
            executer(
                conn,
                """
                UPDATE documents SET titre = ?, description = ?, categorie_id = ?, auteur = ?, type_document = ?,
                    statut = ?, date_publication = ?, numero_version = ?
                WHERE id = ?
                """,
                (
                    titre, description.strip() or None, categorie_id, auteur.strip() or None,
                    type_document or None, statut or "Brouillon", date_publication or None,
                    numero_version.strip() or "1.0", document_id,
                ),
            )
        else:
            executer(
                conn,
                """
                UPDATE documents SET titre = ?, description = ?, categorie_id = ?, auteur = ?, type_document = ?,
                    statut = ?, date_publication = ?, numero_version = ?, fichier_blob = ?, nom_fichier = ?, taille_fichier = ?
                WHERE id = ?
                """,
                (
                    titre, description.strip() or None, categorie_id, auteur.strip() or None,
                    type_document or None, statut or "Brouillon", date_publication or None,
                    numero_version.strip() or "1.0", piece["contenu"], piece["nom"], piece["taille"], document_id,
                ),
            )
        conn.commit()
        return {"ok": True, "message": "Document modifié avec succès."}
    finally:
        conn.close()


def lister_documents(region_id: int | None) -> list:
    conn = get_connection()
    try:
        clause, parametres = condition_region(region_id)
        return executer(
            conn,
            f"SELECT * FROM documents WHERE 1=1{clause} ORDER BY date_publication DESC, date_creation DESC",
            parametres,
        ).fetchall()
    finally:
        conn.close()


def supprimer_document(document_id: int) -> dict:
    conn = get_connection()
    try:
        executer(conn, "DELETE FROM documents WHERE id = ?", (document_id,))
        conn.commit()
        return {"ok": True, "message": "Document supprimé avec succès."}
    finally:
        conn.close()


def obtenir_fichier_document(document_id: int) -> dict | None:
    """Contenu + nom + type MIME du fichier joint à un document (pour le téléchargement)."""
    conn = get_connection()
    try:
        ligne = executer(
            conn, "SELECT nom_fichier, fichier_blob FROM documents WHERE id = ?", (document_id,)
        ).fetchone()
    finally:
        conn.close()
    if ligne is None or ligne["fichier_blob"] is None:
        return None
    nom = ligne["nom_fichier"] or "document"
    extension = nom.rsplit(".", 1)[-1].lower() if "." in nom else ""
    mime = EXTENSIONS_AUTORISEES.get(extension, "application/octet-stream")
    return {"nom": nom, "contenu": bytes(ligne["fichier_blob"]), "mime": mime}


# ----------------------------------------------------------------------
# 3. VERSIONS
# ----------------------------------------------------------------------
def enregistrer_version_document(
    document_id: int, numero_version: str, changements: str, auteur_modification: str, fichier, region_id: int | None
) -> dict:
    numero_version = numero_version.strip()
    if numero_version == "":
        return {"ok": False, "message": "Le numéro de version ne peut pas être vide."}

    piece = _valider_fichier(fichier)
    if not piece["ok"]:
        return piece

    conn = get_connection()
    try:
        executer(
            conn,
            """
            INSERT INTO versions_documents (document_id, numero_version, changements, auteur_modification, fichier_blob, nom_fichier, region_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (document_id, numero_version, changements.strip() or None, auteur_modification.strip() or None, piece["contenu"], piece["nom"], region_id),
        )
        conn.commit()
        return {"ok": True, "message": "Version enregistrée avec succès."}
    finally:
        conn.close()


def lister_versions_document(document_id: int) -> list:
    conn = get_connection()
    try:
        return executer(
            conn, "SELECT * FROM versions_documents WHERE document_id = ? ORDER BY date_creation DESC", (document_id,)
        ).fetchall()
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 4. ACCÈS
# ----------------------------------------------------------------------
def accorder_acces_document(
    document_id: int, utilisateur_id: int, type_acces: str, date_expiration: str, region_id: int | None
) -> dict:
    if type_acces == "":
        return {"ok": False, "message": "Le type d'accès ne peut pas être vide."}
    conn = get_connection()
    try:
        executer(
            conn,
            """
            INSERT INTO acces_documents (document_id, utilisateur_id, type_acces, date_expiration, region_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(document_id, utilisateur_id) DO UPDATE SET
                type_acces = excluded.type_acces,
                date_expiration = excluded.date_expiration
            """,
            (document_id, utilisateur_id, type_acces, date_expiration or None, region_id),
        )
        conn.commit()
        return {"ok": True, "message": "Accès accordé avec succès."}
    finally:
        conn.close()


def lister_acces_document(document_id: int) -> list:
    conn = get_connection()
    try:
        return executer(
            conn,
            """
            SELECT a.*, u.nom FROM acces_documents a
            JOIN utilisateurs u ON a.utilisateur_id = u.id
            WHERE a.document_id = ?
            ORDER BY u.nom
            """,
            (document_id,),
        ).fetchall()
    finally:
        conn.close()


# ============================================================================
# ASTUCES POUR LE STATISTICIEN
# ============================================================================
# 1. Ajouter un format de fichier accepté (ex. .csv) : ajoutez-le dans
#    EXTENSIONS_AUTORISEES tout en haut de ce fichier — le formulaire
#    (vues/documentation.py, st.file_uploader) le proposera
#    automatiquement.
#
# 2. Le champ "changements" d'une version (notes de mise à jour) s'appelle
#    `changes` dans le PHP d'origine mais `changements` ici — un simple
#    renommage pour rester cohérent avec le reste de la base en français.
#
# 3. Tester ce fichier sans lancer Streamlit :
#        from services_documentation import enregistrer_categorie, lister_categories
#        print(enregistrer_categorie("Rapports annuels", "", 0, 1))
#        print(lister_categories(1))
# ============================================================================
