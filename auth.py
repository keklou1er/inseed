"""
auth.py — Connexion, mots de passe, régions et rôles.

============================================================================
D'OÙ VIENT CE FICHIER ?
============================================================================
Portage de web/includes/auth.php. En PHP, "être connecté" se retenait dans
$_SESSION (une mémoire côté serveur propre à chaque visiteur). En
Streamlit, l'équivalent exact est st.session_state : un dictionnaire qui
survit tant que l'onglet du navigateur reste ouvert, propre à chaque
utilisateur, et qui est ré-empli à chaque interaction (bouton cliqué,
formulaire envoyé...).

CE QU'IL FAUT RETENIR : dans TOUT le reste de l'application, pour savoir
"est-ce que quelqu'un est connecté ?", on appelle utilisateur_connecte().
Pour bloquer l'accès à une page, on appelle exiger_connexion() tout en
haut de cette page (avant d'afficher quoi que ce soit d'autre).
============================================================================
POURQUOI hashlib.scrypt AU LIEU DE password_hash() (PHP) ?
============================================================================
PHP a une fonction toute prête, password_hash(), qui fait ça très bien.
Python n'a pas d'équivalent aussi direct dans sa bibliothèque standard,
mais hashlib.scrypt() (inclus avec Python, pas besoin d'installer quoi
que ce soit) fait exactement le même travail : il transforme un mot de
passe en une empreinte impossible à "retourner" pour retrouver le mot de
passe d'origine, et volontairement lente à calculer (pour décourager les
essais en masse en cas de vol de la base). On ne stocke JAMAIS le mot de
passe lui-même, seulement cette empreinte (colonne motdepasse_hash).
============================================================================
POURQUOI LA CONNEXION SURVIT-ELLE À UN RAFRAÎCHISSEMENT (F5) ?
============================================================================
st.session_state est attaché à la connexion technique (WebSocket) entre le
navigateur et le serveur Streamlit : un rafraîchissement complet de la
page (F5, ou l'URL retapée) ouvre une connexion TOUTE NEUVE, et
st.session_state repart donc à zéro — contrairement à $_SESSION en PHP,
qui survit grâce à un cookie envoyé à chaque requête.

La solution ici : au moment de la connexion, on crée un "jeton" aléatoire
(un long texte impossible à deviner), on l'enregistre dans la table
sessions_actives (voir db.py) à côté de l'identifiant de l'utilisateur, et
on le range dans l'URL via st.query_params — qui, lui, SURVIT à un F5
(il fait partie de l'adresse affichée dans le navigateur). Au prochain
chargement de page, restaurer_session_depuis_url() relit ce jeton dans
l'URL, le retrouve dans sessions_actives, et reconnecte automatiquement
l'utilisateur — sans qu'il ait besoin de retaper son mot de passe.
============================================================================
"""

import hashlib
import hmac
import os
import secrets

import streamlit as st

from db import get_connection, executer


# ----------------------------------------------------------------------
# 1. MOTS DE PASSE : ne jamais stocker un mot de passe en clair.
# ----------------------------------------------------------------------
def hacher_mot_de_passe(motdepasse: str) -> str:
    """Transforme un mot de passe en empreinte à stocker en base."""
    sel = os.urandom(16)
    empreinte = hashlib.scrypt(motdepasse.encode("utf-8"), salt=sel, n=2**14, r=8, p=1)
    # On stocke "sel_en_hexadécimal$empreinte_en_hexadécimal" dans une
    # seule colonne texte, pour ne pas avoir besoin de deux colonnes.
    return sel.hex() + "$" + empreinte.hex()


def verifier_mot_de_passe(motdepasse: str, empreinte_stockee: str) -> bool:
    """Vérifie qu'un mot de passe saisi correspond à l'empreinte stockée."""
    try:
        sel_hex, empreinte_hex = empreinte_stockee.split("$", 1)
    except ValueError:
        return False
    sel = bytes.fromhex(sel_hex)
    empreinte_attendue = bytes.fromhex(empreinte_hex)
    empreinte_calculee = hashlib.scrypt(motdepasse.encode("utf-8"), salt=sel, n=2**14, r=8, p=1)
    # hmac.compare_digest plutôt que "==" : évite de révéler, via le temps
    # de calcul, à quel endroit la comparaison a échoué (attaque de
    # "timing"). Détail de sécurité, mais qui ne coûte rien à appliquer.
    return hmac.compare_digest(empreinte_calculee, empreinte_attendue)


# ----------------------------------------------------------------------
# 2. SESSION : qui est connecté, sur quelle page a-t-on le droit d'être.
# ----------------------------------------------------------------------
def utilisateur_connecte() -> dict | None:
    """Retourne le dictionnaire de l'utilisateur connecté, ou None."""
    return st.session_state.get("utilisateur")


def exiger_connexion() -> None:
    """
    À appeler tout en haut de CHAQUE page protégée (juste après les
    imports). Si personne n'est connecté, affiche un message et arrête
    complètement l'exécution de la page avec st.stop() — équivalent du
    header('Location: login.php'); exit; en PHP.
    """
    if utilisateur_connecte() is None:
        st.warning("Veuillez vous connecter depuis la page d'accueil pour accéder à cette page.")
        st.stop()


def tenter_connexion(nom: str, motdepasse: str) -> bool:
    """
    Vérifie le nom d'utilisateur et le mot de passe. Si c'est correct,
    mémorise l'utilisateur dans st.session_state ET crée un jeton de
    session persistant (voir la note en haut de ce fichier), puis
    retourne True.
    """
    conn = get_connection()
    try:
        curseur = executer(
            conn,
            "SELECT id, nom, motdepasse_hash, region_id, role FROM utilisateurs WHERE nom = ?",
            (nom.strip(),),
        )
        ligne = curseur.fetchone()
    finally:
        conn.close()

    if ligne is None or not verifier_mot_de_passe(motdepasse, ligne["motdepasse_hash"]):
        return False

    st.session_state["utilisateur"] = {
        "id": ligne["id"],
        "nom": ligne["nom"],
        "region_id": ligne["region_id"],
        "role": ligne["role"],
    }
    jeton = _creer_jeton_session(ligne["id"])
    st.session_state["jeton_session"] = jeton
    st.query_params["session"] = jeton
    return True


def deconnecter() -> None:
    """Oublie l'utilisateur connecté ET supprime son jeton de session persistant."""
    jeton = st.session_state.get("jeton_session") or st.query_params.get("session")
    if jeton:
        _supprimer_jeton_session(jeton)
    st.query_params.clear()
    st.session_state.pop("utilisateur", None)
    st.session_state.pop("jeton_session", None)


# ----------------------------------------------------------------------
# 2 bis. JETON DE SESSION PERSISTANT (survit à un F5) — voir la note
#        "POURQUOI LA CONNEXION SURVIT-ELLE À UN RAFRAÎCHISSEMENT ?" en
#        haut de ce fichier.
# ----------------------------------------------------------------------
def _creer_jeton_session(utilisateur_id: int) -> str:
    # secrets.token_hex (pas random.random) : générateur cryptographique,
    # pour qu'un jeton ne soit pas devinable par quelqu'un d'autre.
    jeton = secrets.token_hex(32)
    conn = get_connection()
    try:
        executer(conn, "INSERT INTO sessions_actives (jeton, utilisateur_id) VALUES (?, ?)", (jeton, utilisateur_id))
        conn.commit()
        return jeton
    finally:
        conn.close()


def _supprimer_jeton_session(jeton: str) -> None:
    conn = get_connection()
    try:
        executer(conn, "DELETE FROM sessions_actives WHERE jeton = ?", (jeton,))
        conn.commit()
    finally:
        conn.close()


def _utilisateur_depuis_jeton(jeton: str) -> dict | None:
    conn = get_connection()
    try:
        ligne = executer(
            conn,
            """
            SELECT u.id, u.nom, u.region_id, u.role
            FROM sessions_actives s
            JOIN utilisateurs u ON u.id = s.utilisateur_id
            WHERE s.jeton = ?
            """,
            (jeton,),
        ).fetchone()
        return dict(ligne) if ligne else None
    finally:
        conn.close()


def restaurer_session_depuis_url() -> None:
    """
    À appeler tout en haut de app.py, avant toute autre logique. Si
    personne n'est connecté dans st.session_state (ex. après un F5) mais
    que l'URL contient encore un jeton valide (?session=...), reconnecte
    automatiquement l'utilisateur correspondant.
    """
    if utilisateur_connecte() is not None:
        return
    jeton = st.query_params.get("session")
    if not jeton:
        return
    utilisateur = _utilisateur_depuis_jeton(jeton)
    if utilisateur is not None:
        st.session_state["utilisateur"] = utilisateur
        st.session_state["jeton_session"] = jeton


def reappliquer_jeton_dans_url() -> None:
    """
    À appeler à chaque exécution de app.py (donc à chaque navigation entre
    pages), juste après restaurer_session_depuis_url(). st.navigation et
    st.page_link reconstruisent l'URL cible à partir du seul nom de la
    page cliquée, sans reporter la query string existante : le jeton
    ?session=... disparaît donc de la barre d'adresse dès qu'on clique sur
    un lien de menu — même si la connexion, elle, reste active dans
    st.session_state à ce moment-là. Le problème ne se voit qu'au prochain
    F5 (ou lien copié/partagé), puisque restaurer_session_depuis_url() ne
    retrouve alors plus rien dans l'URL. On réécrit donc le jeton ici à
    chaque page pour qu'il survive à la navigation.
    """
    if utilisateur_connecte() is None:
        return
    jeton = st.session_state.get("jeton_session")
    if jeton and st.query_params.get("session") != jeton:
        st.query_params["session"] = jeton


def modifier_utilisateur(
    utilisateur_id: int, region_id: int | None, role: str, nouveau_motdepasse: str = "", confirmation: str = ""
) -> dict:
    """
    Met à jour la région et le rôle d'un compte existant (voir
    creer_utilisateur pour la création). nouveau_motdepasse est optionnel :
    laissé vide, le mot de passe actuel est conservé ; renseigné, il
    remplace l'ancien (confirmation doit alors correspondre).
    """
    if nouveau_motdepasse != "":
        if len(nouveau_motdepasse) < 4:
            return {"ok": False, "message": "Le mot de passe doit contenir au moins 4 caractères."}
        if nouveau_motdepasse != confirmation:
            return {"ok": False, "message": "La confirmation ne correspond pas au mot de passe."}

    conn = get_connection()
    try:
        if nouveau_motdepasse == "":
            executer(
                conn, "UPDATE utilisateurs SET region_id = ?, role = ? WHERE id = ?",
                (region_id, role, utilisateur_id),
            )
        else:
            executer(
                conn, "UPDATE utilisateurs SET region_id = ?, role = ?, motdepasse_hash = ? WHERE id = ?",
                (region_id, role, hacher_mot_de_passe(nouveau_motdepasse), utilisateur_id),
            )
        conn.commit()
        return {"ok": True, "message": "Compte modifié."}
    finally:
        conn.close()


def nombre_utilisateurs() -> int:
    conn = get_connection()
    try:
        return executer(conn, "SELECT COUNT(*) AS total FROM utilisateurs").fetchone()["total"]
    finally:
        conn.close()


def creer_utilisateur(
    nom: str, motdepasse: str, confirmation: str, region_id: int | None, role: str = "agent"
) -> dict:
    """
    Crée un nouveau compte. Retourne {"ok": True/False, "message": "..."}
    — c'est la page appelante (vues/utilisateurs.py) qui affiche ce
    message avec st.success()/st.error().
    """
    nom = nom.strip()
    if nom == "":
        return {"ok": False, "message": "Le nom d'utilisateur est obligatoire."}
    if len(motdepasse) < 4:
        return {"ok": False, "message": "Le mot de passe doit contenir au moins 4 caractères."}
    if motdepasse != confirmation:
        return {"ok": False, "message": "La confirmation ne correspond pas au mot de passe."}

    conn = get_connection()
    try:
        deja_pris = executer(conn, "SELECT 1 FROM utilisateurs WHERE nom = ?", (nom,)).fetchone()
        if deja_pris:
            return {"ok": False, "message": "Ce nom d'utilisateur existe déjà."}

        executer(
            conn,
            "INSERT INTO utilisateurs (nom, motdepasse_hash, region_id, role) VALUES (?, ?, ?, ?)",
            (nom, hacher_mot_de_passe(motdepasse), region_id, role),
        )
        conn.commit()
        return {"ok": True, "message": "Compte créé."}
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 3. RÉGIONS ET SERVICES : de quoi construire le tableau de bord et les
#    menus (voir app.py).
# ----------------------------------------------------------------------
def region_actuelle() -> dict | None:
    """La région (direction régionale) de l'utilisateur connecté, si définie."""
    utilisateur = utilisateur_connecte()
    if not utilisateur or not utilisateur.get("region_id"):
        return None
    conn = get_connection()
    try:
        return executer(conn, "SELECT * FROM regions WHERE id = ?", (utilisateur["region_id"],)).fetchone()
    finally:
        conn.close()


def lister_regions_actives() -> list:
    """Toutes les régions actives — utilisé par le formulaire de création de compte."""
    conn = get_connection()
    try:
        return executer(conn, "SELECT id, nom FROM regions WHERE actif = 1 ORDER BY nom").fetchall()
    finally:
        conn.close()


def services_disponibles() -> list:
    """
    La liste des 9 services (== les cartes du tableau de bord / les
    entrées du menu). Malgré son nom (repris du PHP), cette fonction ne
    filtre PAS par région : tous les utilisateurs voient les mêmes
    services, seules leurs DONNÉES sont propres à leur région.
    """
    conn = get_connection()
    try:
        return executer(conn, "SELECT * FROM services ORDER BY id").fetchall()
    finally:
        conn.close()


# ============================================================================
# ASTUCES POUR LE STATISTICIEN
# ============================================================================
# 1. Changer le mot de passe du compte "admin" de démarrage : connectez-
#    vous (admin / changez-moi), allez sur la page "Utilisateurs", créez
#    votre propre compte avec le rôle "admin_region", reconnectez-vous
#    avec ce nouveau compte, puis supprimez la ligne "admin" dans la table
#    utilisateurs (via DB Browser for SQLite, voir astuces de db.py).
#
# 2. Ajouter un rôle : le rôle est juste du texte libre dans la colonne
#    utilisateurs.role. Le seul rôle actuellement "spécial" dans le code
#    est "admin_region" (seul rôle qui voit le lien "Utilisateurs" — voir
#    app.py). Pour ajouter une règle liée à un nouveau rôle, cherchez
#    `role == "admin_region"` dans le code et ajoutez votre propre
#    condition à côté.
#
# 3. Un utilisateur oublie son mot de passe : il n'y a pas d'écran "mot de
#    passe oublié" (pas d'envoi d'e-mail configuré). Un administrateur
#    doit recréer le compte, ou modifier directement la base avec :
#        from auth import hacher_mot_de_passe
#        print(hacher_mot_de_passe("nouveau_mot_de_passe"))
#    puis coller le résultat dans la colonne motdepasse_hash via DB
#    Browser for SQLite.
#
# 4. La table sessions_actives grossit un peu à chaque connexion (une
#    ligne par connexion, supprimée automatiquement à la déconnexion —
#    mais PAS si l'utilisateur ferme simplement l'onglet sans cliquer sur
#    "Déconnexion"). Sans conséquence pour un usage normal ; pour
#    nettoyer les jetons anciens, on peut supprimer toutes les lignes de
#    plus de X jours via DB Browser for SQLite :
#        DELETE FROM sessions_actives WHERE date_creation < date('now', '-30 days');
# ============================================================================
