"""
vues/secretariat.py — Secrétariat (courriers arrivée/départ + pièces jointes).

============================================================================
D'OÙ VIENT CETTE PAGE ?
============================================================================
Portage de web/secretariat.php + web/fichier.php (visualisation/téléchargement
d'une pièce jointe).

============================================================================
PHP → STREAMLIT : L'UPLOAD DE FICHIER
============================================================================
Le formulaire PHP avait un champ <input type="file"> avec
enctype="multipart/form-data". L'équivalent Streamlit est st.file_uploader()
ci-dessous : le paramètre "type=" fait exactement ce que faisait l'attribut
HTML "accept" (limiter les extensions proposées dans la boîte de dialogue
du navigateur) — mais comme en PHP, la VRAIE validation (taille, extension)
est refaite côté serveur dans services_secretariat.py, car un utilisateur
malintentionné pourrait contourner cette limite côté navigateur.

============================================================================
PHP → STREAMLIT : VOIR/TÉLÉCHARGER UNE PIÈCE JOINTE
============================================================================
web/fichier.php était une URL séparée (fichier.php?table=...&id=...) que le
lien "Voir" du tableau ouvrait dans un nouvel onglet. Streamlit n'a pas de
"route" séparée de ce type : l'équivalent est st.download_button(), qui
propose directement le fichier au téléchargement (voir la section
"Pièces jointes" en bas de page). C'est un peu moins pratique pour les PDF
(qui s'ouvraient directement dans l'onglet côté PHP), mais c'est le
mécanisme natif le plus simple et le plus fiable dans Streamlit.

⚠️ DIFFÉRENCE VOULUE PAR RAPPORT AU PHP : comme pour la Comptabilité, le
courrier est maintenant isolé par région (voir services_secretariat.py).
============================================================================
"""

from datetime import date

import pandas as pd
import streamlit as st

from auth import exiger_connexion, utilisateur_connecte
from ui_helpers import flash, afficher_flash, selection_id_tableau
from services_secretariat import (
    EXTENSIONS_AUTORISEES,
    enregistrer_courrier,
    modifier_courrier,
    lister_courriers,
    obtenir_piece_jointe,
)

exiger_connexion()
afficher_flash()

region_id = utilisateur_connecte()["region_id"]

st.title("✉️ Secrétariat")

# ----------------------------------------------------------------------
# Formulaire : nouveau courrier
# ----------------------------------------------------------------------
with st.container(border=True):
    # Applique une réinitialisation en attente (clic sur "Modifier" ou
    # "Annuler") AVANT de créer le moindre widget — voir la note
    # _demander_reinitialisation() dans vues/annuaires.py pour le détail.
    if "_reset_courrier" in st.session_state:
        _valeurs = st.session_state.pop("_reset_courrier")
        st.session_state["courrier_type"] = _valeurs["type_courrier"]
        st.session_state["courrier_date"] = _valeurs["date"]
        st.session_state["courrier_interlocuteur"] = _valeurs["interlocuteur"]
        st.session_state["courrier_objet"] = _valeurs["objet"]
        st.session_state["courrier_en_edition"] = _valeurs["courrier_id"]
        # st.file_uploader ne peut pas être "vidé" en réassignant sa
        # session_state (contrairement à un text_input) : la seule façon
        # fiable de repartir sans fichier sélectionné est de lui donner une
        # NOUVELLE clé à chaque réinitialisation.
        st.session_state["courrier_fichier_version"] = st.session_state.get("courrier_fichier_version", 0) + 1
    elif "courrier_en_edition" not in st.session_state:
        st.session_state["courrier_en_edition"] = None
        st.session_state["courrier_fichier_version"] = 0

    en_edition_courrier = st.session_state["courrier_en_edition"] is not None

    st.subheader("✏️ Modifier le courrier sélectionné" if en_edition_courrier else "Nouveau courrier")

    # clear_on_submit=False volontairement : le formulaire est vidé "à la
    # main" (_reset_courrier) après CHAQUE succès plutôt que par Streamlit —
    # laisser clear_on_submit=True casse le préremplissage d'une
    # modification ultérieure sur les MÊMES clés de widgets (le champ
    # s'affiche bien rempli à l'écran, mais Streamlit le soumet vide).
    with st.form("formulaire_courrier", clear_on_submit=False):
        colonne_gauche, colonne_droite = st.columns(2)
        with colonne_gauche:
            # Le type est verrouillé en modification : changer Arrivée <->
            # Départ signifierait déplacer l'enregistrement vers une autre
            # table (voir la note dans modifier_courrier(), services_secretariat.py).
            type_courrier = st.selectbox(
                "Type :", ["Arrivée", "Départ"], key="courrier_type", disabled=en_edition_courrier,
            )
            date_courrier = st.date_input("Date :", value=date.today(), key="courrier_date")
        with colonne_droite:
            interlocuteur = st.text_input("Expéditeur/Destinataire :", key="courrier_interlocuteur")
            objet = st.text_input("Objet :", key="courrier_objet")

        # Liste des extensions affichées à partir de EXTENSIONS_AUTORISEES
        # (services_secretariat.py) : pour accepter un nouveau format,
        # ajoutez-le à ce dictionnaire, rien à changer ici.
        fichier = st.file_uploader(
            "Pièce jointe :" + (" (laisser vide pour conserver l'actuelle)" if en_edition_courrier else ""),
            type=list(EXTENSIONS_AUTORISEES.keys()),
            key=f"courrier_fichier_{st.session_state['courrier_fichier_version']}",
        )
        envoye = st.form_submit_button("✓ Enregistrer les modifications" if en_edition_courrier else "Ajouter")

    if en_edition_courrier and st.button("✕ Annuler la modification", key="annuler_courrier"):
        st.session_state["_reset_courrier"] = {
            "type_courrier": "Arrivée", "date": date.today(), "interlocuteur": "", "objet": "", "courrier_id": None,
        }
        st.rerun()

    if envoye:
        if en_edition_courrier:
            resultat = modifier_courrier(
                st.session_state["courrier_en_edition"], type_courrier, date_courrier.isoformat(), interlocuteur, objet, fichier
            )
        else:
            resultat = enregistrer_courrier(
                type_courrier, date_courrier.isoformat(), interlocuteur, objet, fichier, region_id
            )
        flash("info" if resultat["ok"] else "error", resultat["message"])
        if resultat["ok"]:
            st.session_state["_reset_courrier"] = {
                "type_courrier": "Arrivée", "date": date.today(), "interlocuteur": "", "objet": "", "courrier_id": None,
            }
        st.rerun()

st.divider()

# ----------------------------------------------------------------------
# Tableau des courriers enregistrés (arrivée + départ mélangés)
# ----------------------------------------------------------------------
st.subheader("Courriers enregistrés")
lignes = lister_courriers(region_id)

if not lignes:
    st.caption("Aucun courrier enregistré pour le moment.")
else:
    courriers_par_id = {l["id"]: l for l in lignes}
    df = pd.DataFrame([dict(l) for l in lignes])
    df["piece_jointe"] = df["nom_fichier"].apply(
        lambda n: f"📎 {n}" if n and n != "Aucun scan" else "—"
    )
    df_affiche = df.drop(columns=["nom_fichier"]).rename(
        columns={
            "id": "N°",
            "date": "Date",
            "type": "Type",
            "interlocuteur": "Interlocuteur",
            "objet": "Objet",
            "piece_jointe": "Pièce jointe",
        }
    )
    st.caption("Cliquez sur une ligne puis sur \"Modifier\" pour la charger dans le formulaire ci-dessus.")
    id_selectionne = selection_id_tableau(df_affiche, "tableau_courriers")
    if id_selectionne is not None and st.button("✏️ Modifier le courrier sélectionné", key="modifier_courrier"):
        courrier = courriers_par_id[id_selectionne]
        st.session_state["_reset_courrier"] = {
            "type_courrier": courrier["type"], "date": date.fromisoformat(courrier["date"]),
            "interlocuteur": courrier["interlocuteur"], "objet": courrier["objet"], "courrier_id": courrier["id"],
        }
        st.rerun()

    # ------------------------------------------------------------------
    # Téléchargement des pièces jointes (équivalent du lien "Voir" du PHP)
    # ------------------------------------------------------------------
    lignes_avec_piece = [l for l in lignes if l["nom_fichier"] and l["nom_fichier"] != "Aucun scan"]
    if lignes_avec_piece:
        st.subheader("Pièces jointes")
        for ligne in lignes_avec_piece:
            piece = obtenir_piece_jointe(ligne["type"], ligne["id"])
            if piece is None:
                continue
            st.download_button(
                label=f"📎 {ligne['type']} — {ligne['objet']} ({piece['nom']})",
                data=piece["contenu"],
                file_name=piece["nom"],
                mime=piece["mime"],
                # key unique obligatoire : plusieurs boutons sur la même
                # page doivent pouvoir être distingués par Streamlit.
                key=f"piece_{ligne['type']}_{ligne['id']}",
            )

# ============================================================================
# ASTUCES POUR LE STATISTICIEN
# ============================================================================
# 1. Changer le message d'accueil du champ Type ou ajouter un 3e type de
#    courrier : modifiez la liste ["Arrivée", "Départ"] du st.selectbox
#    ci-dessus, ET la table TABLE_PAR_TYPE dans services_secretariat.py
#    (il faudrait alors aussi créer une nouvelle table dans db.py pour ce
#    3e type, sur le modèle de courrier_arrive/courrier_depart).
#
# 2. st.file_uploader garde le fichier choisi en mémoire tant que le
#    formulaire n'a pas été envoyé ; clear_on_submit=True le retire du
#    formulaire après l'envoi, comme les autres champs.
#
# 3. Le tableau "Courriers enregistrés" permet de cliquer sur une ligne
#    puis "Modifier" pour la charger dans le formulaire (voir
#    selection_id_tableau() dans ui_helpers.py). Il n'y a en revanche
#    toujours pas de suppression : dites-le si vous en avez besoin.
# ============================================================================
