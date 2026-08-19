"""
vues/documentation.py — Documentation : catégories, documents, versions, accès.

============================================================================
D'OÙ VIENT CETTE PAGE ?
============================================================================
Portage de web/documentation.php. Les 4 liens de navigation du PHP
("Documents", "Catégories", "Versions", "Accès", pilotés par
?section=...) deviennent st.tabs() ci-dessous.

⚠️ ISOLATION PAR RÉGION (comme les autres modules) — voir
services_documentation.py, section "ISOLATION PAR RÉGION".
============================================================================
"""

import pandas as pd
import streamlit as st

from auth import exiger_connexion, utilisateur_connecte, region_actuelle
from db import get_connection, executer
from ui_helpers import flash, afficher_flash, selection_id_tableau
from services_documentation import (
    EXTENSIONS_AUTORISEES,
    TYPES_DE_DOCUMENT,
    STATUTS_DOCUMENT,
    TYPES_ACCES,
    enregistrer_categorie,
    modifier_categorie,
    lister_categories,
    enregistrer_document,
    modifier_document,
    lister_documents,
    supprimer_document,
    obtenir_fichier_document,
    enregistrer_version_document,
    lister_versions_document,
    accorder_acces_document,
    lister_acces_document,
)

exiger_connexion()
afficher_flash()

region_id = utilisateur_connecte()["region_id"]
region = region_actuelle()

st.title("📁 Documentation")
st.caption(f"Région : {region['nom']}" if region else "Vue globale (toutes régions) — compte sans région assignée")

categories = lister_categories(region_id)
documents = lister_documents(region_id)
options_categories = {c["nom"]: c["id"] for c in categories}
options_documents = {d["titre"]: d["id"] for d in documents}

onglet_documents, onglet_categories, onglet_versions, onglet_acces = st.tabs(
    ["📄 Documents", "📂 Catégories", "📜 Versions", "🔐 Accès"]
)

# ----------------------------------------------------------------------
# Onglet 1 : Documents
# ----------------------------------------------------------------------
with onglet_documents:
    noms_categories = {c["id"]: c["nom"] for c in categories}

    # Applique une réinitialisation en attente AVANT de créer le moindre
    # widget — voir la note _demander_reinitialisation() de
    # vues/annuaires.py, et le commentaire sur clear_on_submit dans
    # vues/comptabilite.py (même piège avec les widgets à clé fixe).
    if "_reset_document" in st.session_state:
        _v = st.session_state.pop("_reset_document")
        st.session_state["doc_titre"] = _v["titre"]
        st.session_state["doc_description"] = _v["description"]
        st.session_state["doc_categorie"] = _v["categorie_nom"]
        st.session_state["doc_auteur"] = _v["auteur"]
        st.session_state["doc_type"] = _v["type_document"]
        st.session_state["doc_statut"] = _v["statut"]
        st.session_state["doc_publication"] = _v["date_publication"]
        st.session_state["doc_version"] = _v["numero_version"]
        st.session_state["document_en_edition"] = _v["document_id"]
        # st.file_uploader ne peut pas être "vidé" en réassignant sa
        # session_state : on lui donne une nouvelle clé à chaque reset.
        st.session_state["doc_fichier_version"] = st.session_state.get("doc_fichier_version", 0) + 1
    elif "document_en_edition" not in st.session_state:
        st.session_state["document_en_edition"] = None
        st.session_state["doc_fichier_version"] = 0
        st.session_state["doc_version"] = "1.0"

    en_edition_document = st.session_state["document_en_edition"] is not None

    st.subheader("✏️ Modifier le document sélectionné" if en_edition_document else "Ajouter un document")
    with st.form("formulaire_document", clear_on_submit=False):
        titre = st.text_input("Titre :", key="doc_titre")
        description = st.text_area("Description :", key="doc_description")
        categorie_choisie = st.selectbox("Catégorie :", ["-- Aucune --"] + list(options_categories.keys()), key="doc_categorie")
        auteur = st.text_input("Auteur :", key="doc_auteur")
        type_document = st.selectbox("Type de document :", [""] + TYPES_DE_DOCUMENT, key="doc_type")
        statut = st.selectbox("Statut :", STATUTS_DOCUMENT, key="doc_statut")
        date_publication = st.text_input("Date de publication (AAAA-MM-JJ) :", placeholder="optionnel", key="doc_publication")
        numero_version = st.text_input("Numéro de version :", key="doc_version")
        fichier = st.file_uploader(
            "Fichier :" + (" (laisser vide pour conserver l'actuel)" if en_edition_document else ""),
            type=list(EXTENSIONS_AUTORISEES.keys()), key=f"doc_fichier_{st.session_state['doc_fichier_version']}",
        )
        st.caption("Max 10 Mo — Formats acceptés : PDF, Word, Excel, PowerPoint, TXT")
        envoye = st.form_submit_button("✓ Enregistrer les modifications" if en_edition_document else "Enregistrer")

    if en_edition_document and st.button("✕ Annuler la modification", key="annuler_document"):
        st.session_state["_reset_document"] = {
            "titre": "", "description": "", "categorie_nom": "-- Aucune --", "auteur": "", "type_document": "",
            "statut": STATUTS_DOCUMENT[0], "date_publication": "", "numero_version": "1.0", "document_id": None,
        }
        st.rerun()

    if envoye:
        categorie_id = options_categories.get(categorie_choisie)
        if en_edition_document:
            resultat = modifier_document(
                st.session_state["document_en_edition"], titre, description, categorie_id, auteur,
                type_document, statut, date_publication, numero_version, fichier,
            )
        else:
            resultat = enregistrer_document(
                titre, description, categorie_id, auteur, type_document, statut,
                date_publication, numero_version, fichier, region_id,
            )
        flash("info" if resultat["ok"] else "error", resultat["message"])
        if resultat["ok"]:
            st.session_state["_reset_document"] = {
                "titre": "", "description": "", "categorie_nom": "-- Aucune --", "auteur": "", "type_document": "",
                "statut": STATUTS_DOCUMENT[0], "date_publication": "", "numero_version": "1.0", "document_id": None,
            }
        st.rerun()

    st.divider()
    st.subheader("Documents enregistrés")
    if not documents:
        st.caption("Aucun document enregistré.")
    else:
        st.caption("Cliquez sur une ligne puis sur \"Modifier\" pour la charger dans le formulaire ci-dessus.")
        documents_par_id = {d["id"]: d for d in documents}
        df = pd.DataFrame(
            [
                {
                    "N°": d["id"],
                    "Titre": d["titre"],
                    "Catégorie": noms_categories.get(d["categorie_id"], "N/A"),
                    "Auteur": d["auteur"] or "N/A",
                    "Statut": d["statut"],
                    "Type": d["type_document"] or "N/A",
                    "Téléchargements": d["nombre_telechargements"] or 0,
                }
                for d in documents
            ]
        )
        id_selectionne = selection_id_tableau(df, "tableau_documents")
        if id_selectionne is not None and st.button("✏️ Modifier le document sélectionné", key="modifier_document"):
            d = documents_par_id[id_selectionne]
            st.session_state["_reset_document"] = {
                "titre": d["titre"], "description": d["description"] or "",
                "categorie_nom": noms_categories.get(d["categorie_id"], "-- Aucune --"),
                "auteur": d["auteur"] or "", "type_document": d["type_document"] or "", "statut": d["statut"],
                "date_publication": d["date_publication"] or "", "numero_version": d["numero_version"] or "1.0",
                "document_id": d["id"],
            }
            st.rerun()

        st.markdown("**Fichiers joints / suppression**")
        for d in documents:
            colonne_fichier, colonne_suppr = st.columns([4, 1])
            with colonne_fichier:
                if d["nom_fichier"]:
                    piece = obtenir_fichier_document(d["id"])
                    if piece:
                        st.download_button(
                            f"📎 {d['titre']} ({piece['nom']})",
                            data=piece["contenu"],
                            file_name=piece["nom"],
                            mime=piece["mime"],
                            key=f"fichier_doc_{d['id']}",
                        )
                else:
                    st.caption(f"{d['titre']} — aucun fichier joint")
            with colonne_suppr:
                if st.button("🗑️ Supprimer", key=f"suppr_doc_{d['id']}"):
                    resultat = supprimer_document(d["id"])
                    flash("info" if resultat["ok"] else "error", resultat["message"])
                    st.rerun()

# ----------------------------------------------------------------------
# Onglet 2 : Catégories
# ----------------------------------------------------------------------
with onglet_categories:
    if "_reset_categorie" in st.session_state:
        _v = st.session_state.pop("_reset_categorie")
        st.session_state["cat_nom"] = _v["nom"]
        st.session_state["cat_description"] = _v["description"]
        st.session_state["cat_ordre"] = _v["ordre"]
        st.session_state["categorie_en_edition"] = _v["categorie_id"]
    elif "categorie_en_edition" not in st.session_state:
        st.session_state["categorie_en_edition"] = None

    en_edition_categorie = st.session_state["categorie_en_edition"] is not None

    st.subheader("✏️ Modifier la catégorie sélectionnée" if en_edition_categorie else "Ajouter une catégorie")
    with st.form("formulaire_categorie", clear_on_submit=False):
        nom_categorie = st.text_input("Nom :", key="cat_nom")
        description_categorie = st.text_area("Description :", key="cat_description")
        ordre = st.number_input("Ordre d'affichage :", min_value=0, step=1, key="cat_ordre")
        envoye_categorie = st.form_submit_button("✓ Enregistrer les modifications" if en_edition_categorie else "Enregistrer")

    if en_edition_categorie and st.button("✕ Annuler la modification", key="annuler_categorie"):
        st.session_state["_reset_categorie"] = {"nom": "", "description": "", "ordre": 0, "categorie_id": None}
        st.rerun()

    if envoye_categorie:
        if en_edition_categorie:
            resultat = modifier_categorie(st.session_state["categorie_en_edition"], nom_categorie, description_categorie, int(ordre))
        else:
            resultat = enregistrer_categorie(nom_categorie, description_categorie, int(ordre), region_id)
        flash("info" if resultat["ok"] else "error", resultat["message"])
        if resultat["ok"]:
            st.session_state["_reset_categorie"] = {"nom": "", "description": "", "ordre": 0, "categorie_id": None}
        st.rerun()

    st.divider()
    st.subheader("Liste des catégories")
    if not categories:
        st.caption("Aucune catégorie enregistrée.")
    else:
        st.caption("Cliquez sur une ligne puis sur \"Modifier\" pour la charger dans le formulaire ci-dessus.")
        categories_par_id = {c["id"]: c for c in categories}
        df = pd.DataFrame(
            [
                {
                    "N°": c["id"],
                    "Nom": c["nom"],
                    "Description": (c["description"] or "")[:50],
                    "Ordre": c["ordre"],
                    "Statut": "Actif" if c["actif"] else "Inactif",
                }
                for c in categories
            ]
        )
        id_selectionne = selection_id_tableau(df, "tableau_categories")
        if id_selectionne is not None and st.button("✏️ Modifier la catégorie sélectionnée", key="modifier_categorie"):
            c = categories_par_id[id_selectionne]
            st.session_state["_reset_categorie"] = {
                "nom": c["nom"], "description": c["description"] or "", "ordre": c["ordre"], "categorie_id": c["id"],
            }
            st.rerun()

# ----------------------------------------------------------------------
# Onglet 3 : Versions
# ----------------------------------------------------------------------
with onglet_versions:
    st.subheader("Ajouter une nouvelle version")
    if not options_documents:
        st.warning("Aucun document enregistré pour l'instant : ajoutez-en un dans l'onglet Documents.")
    else:
        with st.form("formulaire_version", clear_on_submit=True):
            document_choisi = st.selectbox("Document :", list(options_documents.keys()))
            numero_version_v = st.text_input("Numéro de version :", placeholder="Ex : 2.1")
            changements = st.text_area("Changements / Notes :")
            auteur_modification = st.text_input("Auteur de la modification :")
            fichier_v = st.file_uploader("Fichier :", type=list(EXTENSIONS_AUTORISEES.keys()), key="fichier_version")
            envoye_version = st.form_submit_button("Enregistrer la version")

        if envoye_version:
            document_id = options_documents[document_choisi]
            resultat = enregistrer_version_document(
                document_id, numero_version_v, changements, auteur_modification, fichier_v, region_id
            )
            flash("info" if resultat["ok"] else "error", resultat["message"])
            st.rerun()

    st.divider()
    st.subheader("Historique des versions")
    au_moins_une_version = False
    for d in documents:
        versions = lister_versions_document(d["id"])
        if not versions:
            continue
        au_moins_une_version = True
        st.markdown(f"**{d['titre']}**")
        df = pd.DataFrame(
            [
                {
                    "Numéro": v["numero_version"],
                    "Auteur": v["auteur_modification"] or "N/A",
                    "Changements": (v["changements"] or "")[:50],
                    "Fichier": v["nom_fichier"] or "N/A",
                    "Date": v["date_creation"],
                }
                for v in versions
            ]
        )
        st.dataframe(df, use_container_width=True, hide_index=True)
    if not au_moins_une_version:
        st.caption("Aucune version enregistrée.")

# ----------------------------------------------------------------------
# Onglet 4 : Accès
# ----------------------------------------------------------------------
with onglet_acces:
    conn = get_connection()
    try:
        utilisateurs = executer(conn, "SELECT id, nom FROM utilisateurs ORDER BY nom").fetchall()
    finally:
        conn.close()
    options_utilisateurs = {u["nom"]: u["id"] for u in utilisateurs}

    st.subheader("Accorder l'accès à un document")
    if not options_documents:
        st.warning("Aucun document enregistré pour l'instant : ajoutez-en un dans l'onglet Documents.")
    else:
        with st.form("formulaire_acces", clear_on_submit=True):
            document_choisi_acces = st.selectbox("Document :", list(options_documents.keys()), key="doc_acces")
            utilisateur_choisi = st.selectbox("Utilisateur :", list(options_utilisateurs.keys()))
            type_acces = st.selectbox("Type d'accès :", TYPES_ACCES)
            date_expiration = st.text_input("Date d'expiration (AAAA-MM-JJ) :", placeholder="optionnel")
            envoye_acces = st.form_submit_button("Accorder l'accès")

        if envoye_acces:
            document_id = options_documents[document_choisi_acces]
            utilisateur_id = options_utilisateurs[utilisateur_choisi]
            resultat = accorder_acces_document(document_id, utilisateur_id, type_acces, date_expiration, region_id)
            flash("info" if resultat["ok"] else "error", resultat["message"])
            st.rerun()

    st.divider()
    st.subheader("Accès par document")
    au_moins_un_acces = False
    for d in documents:
        acces = lister_acces_document(d["id"])
        if not acces:
            continue
        au_moins_un_acces = True
        st.markdown(f"**{d['titre']}**")
        df = pd.DataFrame(
            [
                {
                    "Utilisateur": a["nom"],
                    "Type d'accès": a["type_acces"],
                    "Expiration": a["date_expiration"] or "Illimité",
                    "Accordé le": a["date_creation"],
                }
                for a in acces
            ]
        )
        st.dataframe(df, use_container_width=True, hide_index=True)
    if not au_moins_un_acces:
        st.caption("Aucun accès configuré.")

# ============================================================================
# ASTUCES POUR LE STATISTICIEN
# ============================================================================
# 1. "Accorder l'accès" à un document qui a déjà un accès pour le même
#    utilisateur MET À JOUR le type d'accès existant plutôt que d'en créer
#    un deuxième (voir la note de correction dans services_documentation.py).
#
# 2. Les onglets "Versions" et "Accès" affichent un mini-tableau PAR
#    document (seulement pour ceux qui ont au moins une version/un accès)
#    — c'est le même principe d'affichage que web/documentation.php.
#
# 3. Tester la logique sans lancer Streamlit : voir les astuces en bas de
#    services_documentation.py.
# ============================================================================
