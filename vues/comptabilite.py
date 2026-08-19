"""
vues/comptabilite.py — Comptabilité (Patrimoine + Journal comptable).

============================================================================
D'OÙ VIENT CETTE PAGE ?
============================================================================
Portage de web/comptabilite.php. Le PHP proposait un bouton "Patrimoine" /
"Journal" qui affichait un seul formulaire à la fois (voir
assets/app.js::selectionnerFormulaire côté PHP) : c'est EXACTEMENT ce que
fait st.tabs() ci-dessous, en une seule ligne.

⚠️ DIFFÉRENCE VOULUE PAR RAPPORT AU PHP : le PHP partageait UNE SEULE
comptabilité entre toutes les directions régionales. Ici, chaque région a
sa propre comptabilité — voir services_comptabilite.py, section
"COMPTABILITÉ PAR RÉGION", pour le détail (et comment revenir en arrière
si besoin).
============================================================================
"""

import pandas as pd
import streamlit as st

from auth import exiger_connexion, utilisateur_connecte, region_actuelle
from ui_helpers import flash, afficher_flash, fmt_montant, selection_id_tableau
from services_comptabilite import (
    TYPES_DE_BIENS,
    ETATS_DE_BIEN,
    TYPES_DE_FLUX,
    enregistrer_un_bien,
    modifier_bien,
    lister_patrimoine,
    enregistrer_ressource_emploi,
    solde_tresorerie,
    balance_generale,
    lister_journal,
)

exiger_connexion()
afficher_flash()

# region_id de l'utilisateur connecté : chaque direction régionale a sa
# propre comptabilité (patrimoine + journal), isolée des autres régions.
# Le compte "admin" de démarrage (sans région assignée) voit une VUE
# GLOBALE (toutes régions confondues) — voir la doc dans
# services_comptabilite.py, section "COMPTABILITÉ PAR RÉGION".
region_id = utilisateur_connecte()["region_id"]
region = region_actuelle()

st.title("💰 Comptabilité")
st.caption(f"Région : {region['nom']}" if region else "Vue globale (toutes régions) — compte sans région assignée")

onglet_patrimoine, onglet_journal = st.tabs(["🏛️ Patrimoine", "📒 Journal comptable"])

# ----------------------------------------------------------------------
# Onglet 1 : Patrimoine (biens durables)
# ----------------------------------------------------------------------
with onglet_patrimoine:
    # Applique une réinitialisation en attente (clic sur "Modifier" ou sur
    # "Annuler" ci-dessous) AVANT de créer le moindre widget — voir la note
    # _demander_reinitialisation() dans vues/annuaires.py pour le détail de
    # pourquoi ce détour par session_state est nécessaire.
    if "_reset_patrimoine" in st.session_state:
        _valeurs = st.session_state.pop("_reset_patrimoine")
        st.session_state["patrimoine_type"] = _valeurs["type_bien"]
        st.session_state["patrimoine_nom"] = _valeurs["nom"]
        st.session_state["patrimoine_etat"] = _valeurs["etat"]
        st.session_state["patrimoine_lieu"] = _valeurs["lieu"]
        st.session_state["patrimoine_en_edition"] = _valeurs["bien_id"]
    elif "patrimoine_en_edition" not in st.session_state:
        st.session_state["patrimoine_en_edition"] = None

    en_edition_patrimoine = st.session_state["patrimoine_en_edition"] is not None

    st.subheader("✏️ Modifier le bien sélectionné" if en_edition_patrimoine else "Formulaire de saisie des opérations")

    # clear_on_submit=False volontairement : le formulaire est vidé "à la
    # main" (_reset_patrimoine) après CHAQUE succès plutôt que par
    # Streamlit — laisser clear_on_submit=True casse le préremplissage
    # d'une modification ultérieure sur les MÊMES clés de widgets (le champ
    # s'affiche bien rempli à l'écran, mais Streamlit le soumet vide).
    with st.form("formulaire_patrimoine", clear_on_submit=False):
        colonne_gauche, colonne_droite = st.columns(2)
        with colonne_gauche:
            type_bien = st.selectbox("Catégorie :", TYPES_DE_BIENS, key="patrimoine_type")
            nom = st.text_input("Désignation :", key="patrimoine_nom")
        with colonne_droite:
            etat = st.selectbox("Etat :", ETATS_DE_BIEN, key="patrimoine_etat")
            lieu = st.text_input("Localisation :", key="patrimoine_lieu")
        envoye = st.form_submit_button("✓ Enregistrer les modifications" if en_edition_patrimoine else "Enregistrer")

    if en_edition_patrimoine and st.button("✕ Annuler la modification", key="annuler_patrimoine"):
        st.session_state["_reset_patrimoine"] = {"type_bien": TYPES_DE_BIENS[0], "nom": "", "etat": ETATS_DE_BIEN[0], "lieu": "", "bien_id": None}
        st.rerun()

    if envoye:
        if en_edition_patrimoine:
            resultat = modifier_bien(st.session_state["patrimoine_en_edition"], type_bien, etat, nom, lieu)
        else:
            resultat = enregistrer_un_bien(type_bien, etat, nom, lieu, region_id)
        flash("info" if resultat["ok"] else "error", resultat["message"])
        if resultat["ok"]:
            st.session_state["_reset_patrimoine"] = {"type_bien": TYPES_DE_BIENS[0], "nom": "", "etat": ETATS_DE_BIEN[0], "lieu": "", "bien_id": None}
        st.rerun()

    st.divider()
    st.subheader("Patrimoine enregistré")
    st.caption("Cliquez sur une ligne du tableau puis sur \"Modifier\" pour la charger dans le formulaire ci-dessus.")
    lignes = lister_patrimoine(region_id)
    if not lignes:
        st.caption("Aucun bien enregistré pour le moment.")
    else:
        biens_par_id = {l["id"]: l for l in lignes}
        df_patrimoine = pd.DataFrame([dict(l) for l in lignes]).rename(
            columns={
                "id": "N°",
                "date": "Date d'enregistrement",
                "type": "Type de matériel",
                "nom": "Désignation",
                "etat": "Etat",
                "lieu": "Localisation",
            }
        )
        id_selectionne = selection_id_tableau(df_patrimoine, "tableau_patrimoine")
        if id_selectionne is not None and st.button("✏️ Modifier le bien sélectionné", key="modifier_patrimoine"):
            bien = biens_par_id[id_selectionne]
            st.session_state["_reset_patrimoine"] = {
                "type_bien": bien["type"], "nom": bien["nom"], "etat": bien["etat"],
                "lieu": bien["lieu"], "bien_id": bien["id"],
            }
            st.rerun()

# ----------------------------------------------------------------------
# Onglet 2 : Journal comptable (emplois / ressources) + trésorerie
# ----------------------------------------------------------------------
with onglet_journal:
    colonne_formulaire, colonne_treso = st.columns([2, 1])

    with colonne_formulaire:
        st.subheader("Formulaire de saisie des opérations")
        with st.form("formulaire_operation", clear_on_submit=True):
            type_flux = st.selectbox("Flux :", TYPES_DE_FLUX)
            libelle = st.text_input("Libellé :")
            montant = st.number_input("Montant :", min_value=0.0, step=100.0, format="%.2f")
            envoye_operation = st.form_submit_button("Enregistrer")

        if envoye_operation:
            resultat = enregistrer_ressource_emploi(libelle, type_flux, montant, region_id)
            flash("info" if resultat["ok"] else "error", resultat["message"])
            st.rerun()

    with colonne_treso:
        st.subheader("Situation de la trésorerie")
        solde = solde_tresorerie(region_id)
        total_debit, total_credit = balance_generale(region_id)
        st.metric("Solde actuel", f"{fmt_montant(solde)} FCFA")
        if abs(total_debit - total_credit) < 0.005:
            st.success(f"Balance vérifiée (Débit : {fmt_montant(total_debit)} = Crédit : {fmt_montant(total_credit)})")
        else:
            st.error("Alerte : déséquilibre détecté dans la balance !")

    st.divider()
    st.subheader("Journal comptable")
    st.caption(
        "Journal en lecture seule, volontairement : une écriture comptable ne se corrige pas en la "
        "réécrivant (ça casserait l'équilibre débit = crédit), mais en passant une contre-écriture."
    )
    lignes_journal = lister_journal(region_id)
    df_journal = pd.DataFrame([dict(l) for l in lignes_journal]).rename(
        columns={
            "id": "N° Reg",
            "date": "Date / Heure",
            "libelle": "Libellé administratif",
            "compte": "N° Compte",
            "debit": "Débit",
            "credit": "Crédit",
        }
    )
    st.dataframe(df_journal, use_container_width=True, hide_index=True)

# ============================================================================
# ASTUCES POUR LE STATISTICIEN
# ============================================================================
# 1. Ajouter un champ au formulaire Patrimoine (ex. "Numéro d'inventaire") :
#      a) Ajoutez la colonne dans db.py (table `patrimoine`) — voir
#         l'astuce "AJOUTER UNE COLONNE" en haut de db.py.
#      b) Ajoutez un champ st.text_input(...) dans le formulaire ci-dessus.
#      c) Passez sa valeur à enregistrer_un_bien() dans
#         services_comptabilite.py (il faudra ajouter ce paramètre à la
#         fonction ET à la requête INSERT).
#
# 2. clear_on_submit=True (dans st.form) : vide automatiquement le
#    formulaire après l'envoi, pour ne pas avoir à re-effacer les champs
#    à la main avant la saisie suivante — équivalent du entry.delete(0, END)
#    répété dans l'app de bureau.
#
# 3. st.rerun() après un enregistrement : force Streamlit à ré-exécuter
#    toute la page depuis le début, ce qui recharge les tableaux avec la
#    nouvelle ligne tout juste ajoutée. Sans ça, le tableau resterait
#    affiché tel qu'il était AVANT l'ajout jusqu'au prochain clic.
# ============================================================================
