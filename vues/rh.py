"""
vues/rh.py — Ressources humaines : employés, contrats, congés, formations, paie.

============================================================================
D'OÙ VIENT CETTE PAGE ?
============================================================================
Portage de web/rh.php. Les six boutons de la barre latérale du PHP
("Employés", "Contrats", "Congés", "Formations", "Paie", "Rechercher un
employé") deviennent st.tabs() ci-dessous.

⚠️ ADAPTATIONS VOLONTAIRES PAR RAPPORT AU PHP (détaillées dans
services_rh.py) :
  1. La colonne "Salaire" du tableau employés, cassée en PHP (toujours
     vide à cause d'une erreur de copier-coller), est corrigée ici.
  2. Les listes déroulantes "Employé" (Contrats/Congés/Formations/Paie)
     affichent TOUJOURS tous les employés, même si une recherche est en
     cours dans l'onglet "Recherche" — en PHP, une recherche active
     pouvait accidentellement réduire ces listes partout sur la page
     (effet de bord d'une variable $_GET partagée), ce qui n'est
     probablement pas voulu.
  3. Isolation par région (comme les autres modules) — voir
     services_rh.py, section "ISOLATION PAR RÉGION".
  4. Chaque tableau (Employés/Contrats/Congés/Formations/Paie) permet de
     cliquer sur une ligne puis "Modifier" pour la charger dans le
     formulaire au-dessus — voir selection_id_tableau() dans
     ui_helpers.py, et la note _demander_reinitialisation() de
     vues/annuaires.py pour le mécanisme utilisé.
============================================================================
"""

import pandas as pd
import streamlit as st

from auth import exiger_connexion, utilisateur_connecte, region_actuelle
from ui_helpers import flash, afficher_flash, fmt_montant, selection_id_tableau
from services_rh import (
    TYPES_DE_CONTRAT,
    STATUTS_EMPLOYE,
    TYPES_DE_CONGE,
    STATUTS_CONGE,
    STATUTS_FORMATION,
    STATUTS_PAIE,
    enregistrer_employe,
    modifier_employe,
    lister_employes,
    rechercher_employes,
    enregistrer_contrat,
    modifier_contrat,
    lister_contrats,
    demander_conge,
    modifier_conge,
    lister_conges,
    enregistrer_formation,
    modifier_formation,
    lister_formations,
    enregistrer_paie,
    lister_paies,
)

exiger_connexion()
afficher_flash()

region_id = utilisateur_connecte()["region_id"]
region = region_actuelle()

st.title("👥 Ressources humaines")
st.caption(f"Région : {region['nom']}" if region else "Vue globale (toutes régions) — compte sans région assignée")

employes = lister_employes(region_id)
# {"Nom Prénom": id} — utilisé par les st.selectbox "Employé" des autres onglets.
options_employes = {f"{e['nom']} {e['prenom']}": e["id"] for e in employes}


def _selecteur_employe(cle: str, desactive: bool = False):
    """st.selectbox réutilisé par les onglets Contrats/Congés/Formations/Paie."""
    if not options_employes:
        st.warning("Aucun employé enregistré pour l'instant : ajoutez-en un dans l'onglet Employés.")
        return None
    nom_choisi = st.selectbox("Employé :", options=list(options_employes.keys()), key=cle, disabled=desactive)
    return options_employes[nom_choisi]


onglet_employes, onglet_contrats, onglet_conges, onglet_formations, onglet_paie, onglet_recherche = st.tabs(
    ["👤 Employés", "📄 Contrats", "🌴 Congés", "🎓 Formations", "💵 Paie", "🔍 Recherche"]
)

# ----------------------------------------------------------------------
# Onglet 1 : Employés
# ----------------------------------------------------------------------
with onglet_employes:
    if "_reset_employe" in st.session_state:
        _v = st.session_state.pop("_reset_employe")
        st.session_state["emp_nom"] = _v["nom"]
        st.session_state["emp_prenom"] = _v["prenom"]
        st.session_state["emp_email"] = _v["email"]
        st.session_state["emp_telephone"] = _v["telephone"]
        st.session_state["emp_naissance"] = _v["date_naissance"]
        st.session_state["emp_fonction"] = _v["fonction"]
        st.session_state["emp_type_contrat"] = _v["type_contrat"]
        st.session_state["emp_embauche"] = _v["date_embauche"]
        st.session_state["emp_profession"] = _v["profession"]
        st.session_state["emp_statut"] = _v["statut"]
        st.session_state["emp_salaire"] = _v["salaire_base"]
        st.session_state["employe_en_edition"] = _v["employe_id"]
    elif "employe_en_edition" not in st.session_state:
        st.session_state["employe_en_edition"] = None

    en_edition_employe = st.session_state["employe_en_edition"] is not None

    st.subheader("✏️ Modifier l'employé sélectionné" if en_edition_employe else "Ajouter un nouvel employé")
    # clear_on_submit=False volontairement partout dans ce fichier : le vider
    # est fait "à la main" ci-dessous (_reset_employe) après CHAQUE succès,
    # création ou modification. Laisser Streamlit vider le formulaire lui-
    # même (clear_on_submit=True) casse le préremplissage d'une modification
    # ultérieure sur les MÊMES clés de widgets — le champ s'affiche bien
    # rempli à l'écran, mais Streamlit le soumet quand même comme vide.
    with st.form("formulaire_employe", clear_on_submit=False):
        colonne_gauche, colonne_droite = st.columns(2)
        with colonne_gauche:
            nom = st.text_input("Nom :", key="emp_nom")
            email = st.text_input("Email :", key="emp_email")
            date_naissance = st.text_input("Date de naissance (AAAA-MM-JJ) :", placeholder="optionnel", key="emp_naissance")
            fonction = st.text_input("Fonction :", key="emp_fonction")
            type_contrat = st.selectbox("Type de contrat :", TYPES_DE_CONTRAT, key="emp_type_contrat")
            date_embauche = st.text_input("Date d'embauche (AAAA-MM-JJ) :", key="emp_embauche")
        with colonne_droite:
            prenom = st.text_input("Prénom :", key="emp_prenom")
            telephone = st.text_input("Téléphone :", key="emp_telephone")
            profession = st.text_input("Profession :", key="emp_profession")
            statut = st.selectbox("Statut :", STATUTS_EMPLOYE, key="emp_statut")
            salaire_base = st.number_input("Salaire base (FCFA) :", min_value=0.0, step=1000.0, format="%.2f", key="emp_salaire")
        envoye = st.form_submit_button("✓ Enregistrer les modifications" if en_edition_employe else "Enregistrer l'employé")

    if en_edition_employe and st.button("✕ Annuler la modification", key="annuler_employe"):
        st.session_state["_reset_employe"] = {
            "nom": "", "prenom": "", "email": "", "telephone": "", "date_naissance": "", "fonction": "",
            "type_contrat": TYPES_DE_CONTRAT[0], "date_embauche": "", "profession": "", "statut": STATUTS_EMPLOYE[0],
            "salaire_base": 0.0, "employe_id": None,
        }
        st.rerun()

    if envoye:
        if en_edition_employe:
            resultat = modifier_employe(
                st.session_state["employe_en_edition"], nom, prenom, email, telephone, date_naissance, "", "", "", "",
                fonction, profession, type_contrat, statut, date_embauche, float(salaire_base),
            )
        else:
            resultat = enregistrer_employe(
                nom, prenom, email, telephone, date_naissance, "", "", "", "",
                fonction, profession, type_contrat, statut, date_embauche, float(salaire_base), region_id,
            )
        flash("info" if resultat["ok"] else "error", resultat["message"])
        if resultat["ok"]:
            st.session_state["_reset_employe"] = {
                "nom": "", "prenom": "", "email": "", "telephone": "", "date_naissance": "", "fonction": "",
                "type_contrat": TYPES_DE_CONTRAT[0], "date_embauche": "", "profession": "", "statut": STATUTS_EMPLOYE[0],
                "salaire_base": 0.0, "employe_id": None,
            }
        st.rerun()

    st.divider()
    st.subheader("Employés enregistrés")
    if not employes:
        st.caption("Aucun employé enregistré pour le moment.")
    else:
        st.caption("Cliquez sur une ligne puis sur \"Modifier\" pour la charger dans le formulaire ci-dessus.")
        employes_par_id = {e["id"]: e for e in employes}
        df = pd.DataFrame([dict(e) for e in employes])
        # Colonne "Salaire" recalculée correctement (voir la note de
        # correction en haut de services_rh.py et de ce fichier).
        df["Salaire (FCFA)"] = df["salaire_base"].apply(fmt_montant)
        df_affiche = df[
            ["id", "nom", "prenom", "email", "fonction", "profession", "type_contrat", "statut", "date_embauche", "Salaire (FCFA)"]
        ].rename(
            columns={
                "id": "N°", "nom": "Nom", "prenom": "Prénom", "email": "Email", "fonction": "Fonction",
                "profession": "Profession", "type_contrat": "Type de contrat", "statut": "Statut",
                "date_embauche": "Date embauche",
            }
        )
        id_selectionne = selection_id_tableau(df_affiche, "tableau_employes")
        if id_selectionne is not None and st.button("✏️ Modifier l'employé sélectionné", key="modifier_employe"):
            e = employes_par_id[id_selectionne]
            st.session_state["_reset_employe"] = {
                "nom": e["nom"], "prenom": e["prenom"], "email": e["email"] or "", "telephone": e["telephone"] or "",
                "date_naissance": e["date_naissance"] or "", "fonction": e["fonction"],
                "type_contrat": e["type_contrat"], "date_embauche": e["date_embauche"], "profession": e["profession"],
                "statut": e["statut"], "salaire_base": e["salaire_base"], "employe_id": e["id"],
            }
            st.rerun()

# ----------------------------------------------------------------------
# Onglet 2 : Contrats
# ----------------------------------------------------------------------
with onglet_contrats:
    if "_reset_contrat" in st.session_state:
        _v = st.session_state.pop("_reset_contrat")
        if _v["employe_nom"] is not None:
            st.session_state["employe_contrat"] = _v["employe_nom"]
        st.session_state["type_contrat_c"] = _v["type_contrat"]
        st.session_state["date_debut_c"] = _v["date_debut"]
        st.session_state["date_fin_c"] = _v["date_fin"]
        st.session_state["duree_essai_c"] = _v["duree_essai"]
        st.session_state["contrat_en_edition"] = _v["contrat_id"]
        st.session_state["contrat_statut_actuel"] = _v["statut"]
    elif "contrat_en_edition" not in st.session_state:
        st.session_state["contrat_en_edition"] = None

    en_edition_contrat = st.session_state["contrat_en_edition"] is not None

    st.subheader("✏️ Modifier le contrat sélectionné" if en_edition_contrat else "Ajouter un contrat")
    with st.form("formulaire_contrat", clear_on_submit=False):
        employe_id = _selecteur_employe("employe_contrat", desactive=en_edition_contrat)
        type_contrat_c = st.selectbox("Type de contrat :", TYPES_DE_CONTRAT, key="type_contrat_c")
        date_debut_c = st.text_input("Date début (AAAA-MM-JJ) :", key="date_debut_c")
        date_fin_c = st.text_input("Date fin (AAAA-MM-JJ) :", placeholder="optionnel", key="date_fin_c")
        duree_essai = st.number_input("Durée essai (mois) :", min_value=0, step=1, key="duree_essai_c")
        envoye_contrat = st.form_submit_button("✓ Enregistrer les modifications" if en_edition_contrat else "Enregistrer le contrat")

    if en_edition_contrat and st.button("✕ Annuler la modification", key="annuler_contrat"):
        st.session_state["_reset_contrat"] = {
            "employe_nom": None, "type_contrat": TYPES_DE_CONTRAT[0], "date_debut": "", "date_fin": "",
            "duree_essai": 0, "contrat_id": None, "statut": "Actif",
        }
        st.rerun()

    if envoye_contrat:
        if employe_id is None:
            flash("error", "Veuillez d'abord ajouter un employé.")
        elif en_edition_contrat:
            resultat = modifier_contrat(
                st.session_state["contrat_en_edition"], type_contrat_c, date_debut_c, date_fin_c,
                int(duree_essai), st.session_state["contrat_statut_actuel"],
            )
            flash("info" if resultat["ok"] else "error", resultat["message"])
            if resultat["ok"]:
                st.session_state["_reset_contrat"] = {
                    "employe_nom": None, "type_contrat": TYPES_DE_CONTRAT[0], "date_debut": "", "date_fin": "",
                    "duree_essai": 0, "contrat_id": None, "statut": "Actif",
                }
        else:
            resultat = enregistrer_contrat(employe_id, type_contrat_c, date_debut_c, date_fin_c, int(duree_essai), "Actif", region_id)
            flash("info" if resultat["ok"] else "error", resultat["message"])
            if resultat["ok"]:
                st.session_state["_reset_contrat"] = {
                    "employe_nom": None, "type_contrat": TYPES_DE_CONTRAT[0], "date_debut": "", "date_fin": "",
                    "duree_essai": 0, "contrat_id": None, "statut": "Actif",
                }
        st.rerun()

    st.divider()
    st.subheader("Contrats enregistrés")
    contrats = lister_contrats(region_id)
    if not contrats:
        st.caption("Aucun contrat enregistré pour le moment.")
    else:
        st.caption("Cliquez sur une ligne puis sur \"Modifier\" pour la charger dans le formulaire ci-dessus.")
        contrats_par_id = {c["id"]: c for c in contrats}
        df = pd.DataFrame(
            [
                {
                    "N°": c["id"],
                    "Employé": f"{c['nom']} {c['prenom']}",
                    "Type": c["type_contrat"],
                    "Date début": c["date_debut"],
                    "Date fin": c["date_fin"] or "-",
                    "Statut": c["statut"],
                }
                for c in contrats
            ]
        )
        id_selectionne = selection_id_tableau(df, "tableau_contrats")
        if id_selectionne is not None and st.button("✏️ Modifier le contrat sélectionné", key="modifier_contrat"):
            c = contrats_par_id[id_selectionne]
            st.session_state["_reset_contrat"] = {
                "employe_nom": f"{c['nom']} {c['prenom']}", "type_contrat": c["type_contrat"],
                "date_debut": c["date_debut"], "date_fin": c["date_fin"] or "", "duree_essai": c["duree_essai"] or 0,
                "contrat_id": c["id"], "statut": c["statut"],
            }
            st.rerun()

# ----------------------------------------------------------------------
# Onglet 3 : Congés
# ----------------------------------------------------------------------
with onglet_conges:
    if "_reset_conge" in st.session_state:
        _v = st.session_state.pop("_reset_conge")
        if _v["employe_nom"] is not None:
            st.session_state["employe_conge"] = _v["employe_nom"]
        st.session_state["conge_type"] = _v["type_conge"]
        st.session_state["date_debut_conge"] = _v["date_debut"]
        st.session_state["date_fin_conge"] = _v["date_fin"]
        st.session_state["conge_jours"] = _v["nombre_jours"]
        st.session_state["conge_motif"] = _v["motif"]
        st.session_state["conge_statut"] = _v["statut"]
        st.session_state["conge_en_edition"] = _v["conge_id"]
    elif "conge_en_edition" not in st.session_state:
        st.session_state["conge_en_edition"] = None

    en_edition_conge = st.session_state["conge_en_edition"] is not None

    st.subheader("✏️ Modifier la demande sélectionnée" if en_edition_conge else "Demander un congé")
    with st.form("formulaire_conge", clear_on_submit=False):
        employe_id_conge = _selecteur_employe("employe_conge", desactive=en_edition_conge)
        type_conge = st.selectbox("Type de congé :", TYPES_DE_CONGE, key="conge_type")
        date_debut_conge = st.text_input("Date début (AAAA-MM-JJ) :", key="date_debut_conge")
        date_fin_conge = st.text_input("Date fin (AAAA-MM-JJ) :", key="date_fin_conge")
        nombre_jours = st.number_input("Nombre de jours :", min_value=1, step=1, key="conge_jours")
        motif = st.text_area("Motif :", key="conge_motif")
        if en_edition_conge:
            statut_conge = st.selectbox("Statut :", STATUTS_CONGE, key="conge_statut")
        envoye_conge = st.form_submit_button("✓ Enregistrer les modifications" if en_edition_conge else "Demander le congé")

    if en_edition_conge and st.button("✕ Annuler la modification", key="annuler_conge"):
        st.session_state["_reset_conge"] = {
            "employe_nom": None, "type_conge": TYPES_DE_CONGE[0], "date_debut": "", "date_fin": "",
            "nombre_jours": 1, "motif": "", "statut": STATUTS_CONGE[0], "conge_id": None,
        }
        st.rerun()

    if envoye_conge:
        if employe_id_conge is None:
            flash("error", "Veuillez d'abord ajouter un employé.")
        elif en_edition_conge:
            resultat = modifier_conge(
                st.session_state["conge_en_edition"], type_conge, date_debut_conge, date_fin_conge,
                int(nombre_jours), motif, statut_conge,
            )
            flash("info" if resultat["ok"] else "error", resultat["message"])
            if resultat["ok"]:
                st.session_state["_reset_conge"] = {
                    "employe_nom": None, "type_conge": TYPES_DE_CONGE[0], "date_debut": "", "date_fin": "",
                    "nombre_jours": 1, "motif": "", "statut": STATUTS_CONGE[0], "conge_id": None,
                }
        else:
            resultat = demander_conge(
                employe_id_conge, type_conge, date_debut_conge, date_fin_conge, int(nombre_jours), motif, region_id
            )
            flash("info" if resultat["ok"] else "error", resultat["message"])
            if resultat["ok"]:
                st.session_state["_reset_conge"] = {
                    "employe_nom": None, "type_conge": TYPES_DE_CONGE[0], "date_debut": "", "date_fin": "",
                    "nombre_jours": 1, "motif": "", "statut": STATUTS_CONGE[0], "conge_id": None,
                }
        st.rerun()

    st.divider()
    st.subheader("Demandes de congé")
    conges = lister_conges(region_id)
    if not conges:
        st.caption("Aucune demande de congé pour le moment.")
    else:
        st.caption("Cliquez sur une ligne puis sur \"Modifier\" pour la charger dans le formulaire ci-dessus (utile pour approuver/rejeter).")
        conges_par_id = {c["id"]: c for c in conges}
        df = pd.DataFrame(
            [
                {
                    "N°": c["id"],
                    "Employé": f"{c['nom']} {c['prenom']}",
                    "Type": c["type_conge"],
                    "Début": c["date_debut"],
                    "Fin": c["date_fin"],
                    "Jours": c["nombre_jours"],
                    "Statut": c["statut"],
                }
                for c in conges
            ]
        )
        id_selectionne = selection_id_tableau(df, "tableau_conges")
        if id_selectionne is not None and st.button("✏️ Modifier la demande sélectionnée", key="modifier_conge"):
            c = conges_par_id[id_selectionne]
            st.session_state["_reset_conge"] = {
                "employe_nom": f"{c['nom']} {c['prenom']}", "type_conge": c["type_conge"],
                "date_debut": c["date_debut"], "date_fin": c["date_fin"], "nombre_jours": c["nombre_jours"],
                "motif": c["motif"] or "", "statut": c["statut"], "conge_id": c["id"],
            }
            st.rerun()

# ----------------------------------------------------------------------
# Onglet 4 : Formations
# ----------------------------------------------------------------------
with onglet_formations:
    if "_reset_formation" in st.session_state:
        _v = st.session_state.pop("_reset_formation")
        if _v["employe_nom"] is not None:
            st.session_state["employe_formation"] = _v["employe_nom"]
        st.session_state["form_titre"] = _v["titre"]
        st.session_state["form_domaine"] = _v["domaine"]
        st.session_state["date_debut_formation"] = _v["date_debut"]
        st.session_state["date_fin_formation"] = _v["date_fin"]
        st.session_state["form_organisme"] = _v["organisme"]
        st.session_state["form_cout"] = _v["cout"]
        st.session_state["form_statut"] = _v["statut"]
        st.session_state["formation_en_edition"] = _v["formation_id"]
    elif "formation_en_edition" not in st.session_state:
        st.session_state["formation_en_edition"] = None

    en_edition_formation = st.session_state["formation_en_edition"] is not None

    st.subheader("✏️ Modifier la formation sélectionnée" if en_edition_formation else "Ajouter une formation")
    with st.form("formulaire_formation", clear_on_submit=False):
        employe_id_formation = _selecteur_employe("employe_formation", desactive=en_edition_formation)
        titre = st.text_input("Titre de la formation :", key="form_titre")
        domaine = st.text_input("Domaine :", placeholder="optionnel", key="form_domaine")
        date_debut_formation = st.text_input("Date début (AAAA-MM-JJ) :", key="date_debut_formation")
        date_fin_formation = st.text_input("Date fin (AAAA-MM-JJ) :", placeholder="optionnel", key="date_fin_formation")
        organisme = st.text_input("Organisme :", placeholder="optionnel", key="form_organisme")
        cout = st.number_input("Coût (FCFA) :", min_value=0.0, step=1000.0, format="%.2f", key="form_cout")
        if en_edition_formation:
            statut_formation = st.selectbox("Statut :", STATUTS_FORMATION, key="form_statut")
        envoye_formation = st.form_submit_button("✓ Enregistrer les modifications" if en_edition_formation else "Enregistrer la formation")

    if en_edition_formation and st.button("✕ Annuler la modification", key="annuler_formation"):
        st.session_state["_reset_formation"] = {
            "employe_nom": None, "titre": "", "domaine": "", "date_debut": "", "date_fin": "",
            "organisme": "", "cout": 0.0, "statut": STATUTS_FORMATION[0], "formation_id": None,
        }
        st.rerun()

    if envoye_formation:
        if employe_id_formation is None:
            flash("error", "Veuillez d'abord ajouter un employé.")
        elif en_edition_formation:
            resultat = modifier_formation(
                st.session_state["formation_en_edition"], titre, domaine, date_debut_formation,
                date_fin_formation, organisme, float(cout), statut_formation,
            )
            flash("info" if resultat["ok"] else "error", resultat["message"])
            if resultat["ok"]:
                st.session_state["_reset_formation"] = {
                    "employe_nom": None, "titre": "", "domaine": "", "date_debut": "", "date_fin": "",
                    "organisme": "", "cout": 0.0, "statut": STATUTS_FORMATION[0], "formation_id": None,
                }
        else:
            resultat = enregistrer_formation(
                employe_id_formation, titre, domaine, date_debut_formation, date_fin_formation,
                organisme, float(cout), "En cours", region_id,
            )
            flash("info" if resultat["ok"] else "error", resultat["message"])
            if resultat["ok"]:
                st.session_state["_reset_formation"] = {
                    "employe_nom": None, "titre": "", "domaine": "", "date_debut": "", "date_fin": "",
                    "organisme": "", "cout": 0.0, "statut": STATUTS_FORMATION[0], "formation_id": None,
                }
        st.rerun()

    st.divider()
    st.subheader("Formations enregistrées")
    formations = lister_formations(region_id)
    if not formations:
        st.caption("Aucune formation enregistrée pour le moment.")
    else:
        st.caption("Cliquez sur une ligne puis sur \"Modifier\" pour la charger dans le formulaire ci-dessus.")
        formations_par_id = {f["id"]: f for f in formations}
        df = pd.DataFrame(
            [
                {
                    "N°": f["id"],
                    "Employé": f"{f['nom']} {f['prenom']}",
                    "Titre": f["titre"],
                    "Domaine": f["domaine"] or "-",
                    "Début": f["date_debut"],
                    "Fin": f["date_fin"] or "-",
                    "Organisme": f["organisme"] or "-",
                    "Coût": fmt_montant(f["cout"] or 0),
                }
                for f in formations
            ]
        )
        id_selectionne = selection_id_tableau(df, "tableau_formations")
        if id_selectionne is not None and st.button("✏️ Modifier la formation sélectionnée", key="modifier_formation"):
            f = formations_par_id[id_selectionne]
            st.session_state["_reset_formation"] = {
                "employe_nom": f"{f['nom']} {f['prenom']}", "titre": f["titre"], "domaine": f["domaine"] or "",
                "date_debut": f["date_debut"], "date_fin": f["date_fin"] or "", "organisme": f["organisme"] or "",
                "cout": f["cout"] or 0.0, "statut": f["statut"], "formation_id": f["id"],
            }
            st.rerun()

# ----------------------------------------------------------------------
# Onglet 5 : Paie
# ----------------------------------------------------------------------
with onglet_paie:
    if "_reset_paie" in st.session_state:
        _v = st.session_state.pop("_reset_paie")
        if _v["employe_nom"] is not None:
            st.session_state["employe_paie"] = _v["employe_nom"]
        st.session_state["paie_mois"] = _v["mois_annee"]
        st.session_state["paie_salaire"] = _v["salaire_base"]
        st.session_state["paie_primes"] = _v["primes"]
        st.session_state["paie_retenues"] = _v["retenues"]
        st.session_state["paie_cotisations"] = _v["cotisations_sociales"]
        st.session_state["paie_statut"] = _v["statut"]
        st.session_state["paie_en_edition"] = _v["paie_id"]
    elif "paie_en_edition" not in st.session_state:
        st.session_state["paie_en_edition"] = None

    en_edition_paie = st.session_state["paie_en_edition"] is not None

    st.subheader("✏️ Modifier la paie sélectionnée" if en_edition_paie else "Enregistrer une paie")
    if en_edition_paie:
        st.caption(
            "Employé et mois/année sont verrouillés : ré-enregistrer une paie pour le même employé et le même "
            "mois met à jour cette paie (une seule paie par employé et par mois)."
        )
    with st.form("formulaire_paie", clear_on_submit=False):
        employe_id_paie = _selecteur_employe("employe_paie", desactive=en_edition_paie)
        mois_annee = st.text_input("Mois/Année (MM-AAAA) :", placeholder="01-2026", key="paie_mois", disabled=en_edition_paie)
        salaire_base_paie = st.number_input("Salaire base (FCFA) :", min_value=0.0, step=1000.0, format="%.2f", key="paie_salaire")
        primes = st.number_input("Primes (FCFA) :", min_value=0.0, step=1000.0, format="%.2f", key="paie_primes")
        retenues = st.number_input("Retenues (FCFA) :", min_value=0.0, step=1000.0, format="%.2f", key="paie_retenues")
        cotisations_sociales = st.number_input("Cotisations sociales (FCFA) :", min_value=0.0, step=1000.0, format="%.2f", key="paie_cotisations")
        statut_paie = st.selectbox("Statut :", STATUTS_PAIE, key="paie_statut")
        envoye_paie = st.form_submit_button("✓ Enregistrer les modifications" if en_edition_paie else "Enregistrer la paie")

    if en_edition_paie and st.button("✕ Annuler la modification", key="annuler_paie"):
        st.session_state["_reset_paie"] = {
            "employe_nom": None, "mois_annee": "", "salaire_base": 0.0, "primes": 0.0, "retenues": 0.0,
            "cotisations_sociales": 0.0, "statut": STATUTS_PAIE[0], "paie_id": None,
        }
        st.rerun()

    if envoye_paie:
        if employe_id_paie is None:
            flash("error", "Veuillez d'abord ajouter un employé.")
        else:
            # enregistrer_paie() met déjà à jour la paie existante au lieu
            # d'en créer une deuxième si employé + mois/année correspondent
            # à une paie déjà enregistrée (UPSERT — voir services_rh.py) :
            # pas besoin d'une fonction "modifier_paie" séparée.
            resultat = enregistrer_paie(
                employe_id_paie, mois_annee, float(salaire_base_paie), float(primes),
                float(retenues), float(cotisations_sociales), statut_paie, region_id,
            )
            flash("info" if resultat["ok"] else "error", resultat["message"])
            if resultat["ok"]:
                st.session_state["_reset_paie"] = {
                    "employe_nom": None, "mois_annee": "", "salaire_base": 0.0, "primes": 0.0, "retenues": 0.0,
                    "cotisations_sociales": 0.0, "statut": STATUTS_PAIE[0], "paie_id": None,
                }
        st.rerun()

    st.divider()
    st.subheader("Paies enregistrées")
    paies = lister_paies(region_id)
    if not paies:
        st.caption("Aucune paie enregistrée pour le moment.")
    else:
        st.caption("Cliquez sur une ligne puis sur \"Modifier\" pour la charger dans le formulaire ci-dessus.")
        paies_par_id = {p["id"]: p for p in paies}
        df = pd.DataFrame(
            [
                {
                    "N°": p["id"],
                    "Employé": f"{p['nom']} {p['prenom']}",
                    "Mois": p["mois_annee"],
                    "Salaire base": fmt_montant(p["salaire_base"]),
                    "Primes": fmt_montant(p["primes"]),
                    "Retenues": fmt_montant(p["retenues"]),
                    "Cotisations": fmt_montant(p["cotisations_sociales"]),
                    "Net": fmt_montant(p["salaire_net"]),
                    "Statut": p["statut"],
                }
                for p in paies
            ]
        )
        id_selectionne = selection_id_tableau(df, "tableau_paies")
        if id_selectionne is not None and st.button("✏️ Modifier la paie sélectionnée", key="modifier_paie"):
            p = paies_par_id[id_selectionne]
            st.session_state["_reset_paie"] = {
                "employe_nom": f"{p['nom']} {p['prenom']}", "mois_annee": p["mois_annee"],
                "salaire_base": p["salaire_base"], "primes": p["primes"], "retenues": p["retenues"],
                "cotisations_sociales": p["cotisations_sociales"], "statut": p["statut"], "paie_id": p["id"],
            }
            st.rerun()

# ----------------------------------------------------------------------
# Onglet 6 : Recherche d'un employé
# ----------------------------------------------------------------------
with onglet_recherche:
    st.subheader("Rechercher un employé")
    terme = st.text_input("Nom de l'employé :", placeholder="Saisir le nom ou le prénom", key="terme_recherche")
    resultats = rechercher_employes(terme, region_id)

    if not resultats:
        st.info("Aucun employé trouvé pour ce nom.")
    else:
        df = pd.DataFrame([dict(e) for e in resultats])
        df["Salaire (FCFA)"] = df["salaire_base"].apply(fmt_montant)
        df_affiche = df[
            ["nom", "prenom", "email", "fonction", "profession", "type_contrat", "statut", "date_embauche", "Salaire (FCFA)"]
        ].rename(
            columns={
                "nom": "Nom", "prenom": "Prénom", "email": "Email", "fonction": "Fonction",
                "profession": "Profession", "type_contrat": "Type de contrat", "statut": "Statut",
                "date_embauche": "Date embauche",
            }
        )
        st.dataframe(df_affiche, use_container_width=True, hide_index=True)
        st.caption("Pour modifier un employé trouvé ici, utilisez le tableau de l'onglet \"Employés\".")

# ============================================================================
# ASTUCES POUR LE STATISTICIEN
# ============================================================================
# 1. Les dates (naissance, embauche, début/fin de contrat...) sont de
#    simples st.text_input avec un format suggéré (AAAA-MM-JJ) plutôt que
#    des st.date_input : ça permet de laisser un champ optionnel VIDE
#    facilement (un st.date_input impose toujours une date). Si vous
#    préférez un vrai calendrier, remplacez le champ par
#    st.date_input(...).isoformat() — voir vues/secretariat.py pour un
#    exemple avec st.date_input obligatoire.
#
# 2. _selecteur_employe() est une petite fonction PARTAGÉE par les onglets
#    Contrats/Congés/Formations/Paie, pour ne pas répéter 4 fois le même
#    st.selectbox. Chaque appel reçoit une "key" différente (paramètre
#    "cle") car Streamlit exige une clé unique par widget sur la page.
#    Le paramètre "desactive" verrouille le sélecteur pendant une
#    modification, pour ne pas changer accidentellement l'employé
#    concerné par un contrat/congé/formation/paie déjà enregistré.
#
# 3. Tester la logique sans lancer Streamlit : voir les astuces en bas de
#    services_rh.py.
# ============================================================================
