"""
vues/utilisateurs.py — Créer et modifier des comptes (régions/directions et rôles).

============================================================================
D'OÙ VIENT CETTE PAGE ?
============================================================================
Portage de web/utilisateurs.php.

⚠️ CORRECTION PAR RAPPORT AU PHP : le formulaire PHP s'appelait "nouvelle
direction" / "administrateur" mais n'avait PAS de champ pour choisir le
rôle — il envoyait donc TOUJOURS role='agent' (la valeur par défaut de
creer_utilisateur), même si le champ affiché s'appelait "administrateur".
Autrement dit, le PHP créait en réalité des comptes "agent", jamais
"admin_region", malgré ce que dit le formulaire. Ici, on ajoute un vrai
champ "Rôle" pour que ce que vous choisissez soit ce qui est réellement
enregistré.

⚠️ AJOUT PAR RAPPORT AU PHP : le tableau "Comptes existants" permet de
cliquer sur une ligne puis "Modifier" pour charger un compte dans le
formulaire (région, rôle, et remise à zéro optionnelle du mot de passe).
Le nom d'utilisateur n'est volontairement pas modifiable ici (c'est
l'identifiant de connexion) — dites-le si vous avez besoin de renommer
un compte existant.
============================================================================
"""

import pandas as pd
import streamlit as st

from auth import exiger_connexion, utilisateur_connecte, creer_utilisateur, modifier_utilisateur, lister_regions_actives
from db import get_connection, executer
from ui_helpers import flash, afficher_flash, selection_id_tableau

exiger_connexion()
afficher_flash()

# Deuxième vérification, en plus de app.py qui ne propose ce lien qu'aux
# admin_region : si jamais cette page était atteinte autrement, on bloque
# quand même ici. Défense en profondeur, comme le double contrôle PHP.
if utilisateur_connecte().get("role") != "admin_region":
    st.error("Accès réservé aux administrateurs de région.")
    st.stop()

st.title("⚙️ Utilisateurs")

regions = lister_regions_actives()
nom_regions = {r["nom"]: r["id"] for r in regions}
id_vers_nom_region = {r["id"]: r["nom"] for r in regions}

# Applique une réinitialisation en attente AVANT de créer le moindre widget
# — voir la note _demander_reinitialisation() de vues/annuaires.py.
if "_reset_utilisateur" in st.session_state:
    _v = st.session_state.pop("_reset_utilisateur")
    st.session_state["util_region"] = _v["region_nom"]
    st.session_state["util_role"] = _v["role"]
    st.session_state["utilisateur_en_edition"] = _v["utilisateur_id"]
    st.session_state["utilisateur_en_edition_nom"] = _v["nom"]
    # Les champs mot de passe ne sont volontairement PAS préremplis avec
    # session_state (un mot de passe haché ne se "redéchiffre" pas) : ils
    # gardent une clé versionnée pour repartir vides à chaque reset.
    st.session_state["util_motdepasse_version"] = st.session_state.get("util_motdepasse_version", 0) + 1
elif "utilisateur_en_edition" not in st.session_state:
    st.session_state["utilisateur_en_edition"] = None
    st.session_state["util_motdepasse_version"] = 0

en_edition_utilisateur = st.session_state["utilisateur_en_edition"] is not None
_version_mdp = st.session_state["util_motdepasse_version"]

with st.form("formulaire_nouvel_utilisateur", clear_on_submit=False):
    if en_edition_utilisateur:
        st.subheader(f"✏️ Modifier le compte « {st.session_state['utilisateur_en_edition_nom']} »")
    else:
        st.subheader("Créer un compte")

    region_choisie = st.selectbox("Direction (région) :", options=list(nom_regions.keys()), key="util_region")

    if en_edition_utilisateur:
        nom = st.session_state["utilisateur_en_edition_nom"]
        st.caption(f"Nom d'utilisateur : **{nom}** (non modifiable)")
        motdepasse = st.text_input(
            "Nouveau mot de passe :", type="password", placeholder="laisser vide pour ne pas changer",
            key=f"util_motdepasse_{_version_mdp}",
        )
        confirmation = st.text_input("Confirmation :", type="password", key=f"util_confirmation_{_version_mdp}")
    else:
        nom = st.text_input("Nom d'utilisateur :", placeholder="ex. agent_savanes", key=f"util_nom_{_version_mdp}")
        motdepasse = st.text_input("Mot de passe :", type="password", key=f"util_motdepasse_{_version_mdp}")
        confirmation = st.text_input("Confirmation :", type="password", key=f"util_confirmation_{_version_mdp}")

    role = st.radio(
        "Rôle :",
        options=["agent", "admin_region"],
        format_func=lambda r: "Agent" if r == "agent" else "Administrateur de région",
        horizontal=True,
        key="util_role",
    )

    envoye = st.form_submit_button("✓ Enregistrer les modifications" if en_edition_utilisateur else "Créer le compte")

if en_edition_utilisateur and st.button("✕ Annuler la modification", key="annuler_utilisateur"):
    st.session_state["_reset_utilisateur"] = {
        "region_nom": list(nom_regions.keys())[0] if nom_regions else None, "role": "agent",
        "utilisateur_id": None, "nom": "",
    }
    st.rerun()

if envoye:
    if en_edition_utilisateur:
        resultat = modifier_utilisateur(
            st.session_state["utilisateur_en_edition"], nom_regions.get(region_choisie), role, motdepasse, confirmation
        )
    else:
        resultat = creer_utilisateur(nom, motdepasse, confirmation, nom_regions.get(region_choisie), role)
    if resultat["ok"]:
        st.session_state["_reset_utilisateur"] = {
            "region_nom": list(nom_regions.keys())[0] if nom_regions else None, "role": "agent",
            "utilisateur_id": None, "nom": "",
        }
        flash("info", resultat["message"])
        st.rerun()
    else:
        st.error(resultat["message"])

st.divider()
st.subheader("Comptes existants")

conn = get_connection()
try:
    lignes = executer(
        conn,
        """
        SELECT utilisateurs.id AS id,
               utilisateurs.nom AS nom,
               utilisateurs.region_id AS region_id,
               utilisateurs.role AS role
        FROM utilisateurs
        ORDER BY utilisateurs.nom
        """,
    ).fetchall()
finally:
    conn.close()

if not lignes:
    st.caption("Aucun compte enregistré.")
else:
    st.caption("Cliquez sur une ligne puis sur \"Modifier\" pour charger le compte dans le formulaire ci-dessus.")
    comptes_par_id = {l["id"]: l for l in lignes}
    df = pd.DataFrame(
        [
            {
                "N°": l["id"],
                "Nom d'utilisateur": l["nom"],
                "Région": id_vers_nom_region.get(l["region_id"], "Non définie"),
                "Rôle": l["role"],
            }
            for l in lignes
        ]
    )
    id_selectionne = selection_id_tableau(df, "tableau_utilisateurs")
    if id_selectionne is not None and st.button("✏️ Modifier le compte sélectionné", key="modifier_utilisateur"):
        compte = comptes_par_id[id_selectionne]
        region_nom = id_vers_nom_region.get(compte["region_id"])
        st.session_state["_reset_utilisateur"] = {
            "region_nom": region_nom if region_nom in nom_regions else (list(nom_regions.keys())[0] if nom_regions else None),
            "role": compte["role"], "utilisateur_id": compte["id"], "nom": compte["nom"],
        }
        st.rerun()

# ============================================================================
# ASTUCES POUR LE STATISTICIEN
# ============================================================================
# 1. Pourquoi le nom d'utilisateur n'est pas modifiable dans le formulaire
#    d'édition ? C'est l'identifiant de connexion (colonne UNIQUE
#    `utilisateurs.nom`) — le rendre modifiable demanderait de revérifier
#    l'unicité à la sauvegarde. Si besoin, ajoutez ce contrôle dans
#    modifier_utilisateur() (auth.py) sur le modèle de creer_utilisateur().
#
# 2. Le mot de passe n'est jamais préaffiché en modification (impossible :
#    seule son empreinte est stockée, voir hacher_mot_de_passe() dans
#    auth.py) — le champ reste vide par défaut, ce qui signifie "ne pas
#    changer le mot de passe" côté modifier_utilisateur().
#
# 3. Ajouter une colonne au tableau "Comptes existants" (par exemple pour
#    voir qui a été créé quand) : il faudrait d'abord ajouter une colonne
#    date_creation à la table `utilisateurs` dans db.py (voir l'astuce
#    "AJOUTER UNE COLONNE" en haut de db.py), puis l'ajouter dans le
#    SELECT ci-dessus.
# ============================================================================
