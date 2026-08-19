"""
vues/mon_compte.py — Page "Mon compte" : changer son propre mot de passe.

============================================================================
D'OÙ VIENT CETTE PAGE ?
============================================================================
N'existe pas côté PHP. Jusqu'ici, seul un admin_region pouvait changer un
mot de passe (page Utilisateurs, réservée à ce rôle) — un agent normal
n'avait donc aucun moyen de changer le sien lui-même. Cette page comble ce
manque : elle est accessible à TOUT utilisateur connecté (voir app.py, où
elle est ajoutée à la liste des pages sans condition de rôle).

============================================================================
POURQUOI DEMANDER L'ANCIEN MOT DE PASSE ICI, ALORS QUE modifier_utilisateur()
(page Utilisateurs) NE LE DEMANDE PAS ?
============================================================================
Un admin qui réinitialise le mot de passe de quelqu'un d'autre n'est pas
censé connaître son mot de passe actuel — exiger l'ancien n'aurait aucun
sens dans ce cas. Mais ICI, c'est l'utilisateur lui-même qui agit sur son
propre compte : demander l'ancien mot de passe protège contre le cas d'une
session laissée ouverte sur un poste partagé (voir changer_mon_mot_de_passe()
dans auth.py pour le détail).
============================================================================
"""

import streamlit as st

from auth import exiger_connexion, utilisateur_connecte, changer_mon_mot_de_passe
from ui_helpers import flash, afficher_flash

exiger_connexion()
afficher_flash()

utilisateur = utilisateur_connecte()

st.title("🔑 Mon compte")
st.caption(f"Connecté en tant que **{utilisateur['nom']}**.")

st.subheader("Changer mon mot de passe")
with st.form("formulaire_changer_mot_de_passe", clear_on_submit=True):
    motdepasse_actuel = st.text_input("Mot de passe actuel :", type="password")
    nouveau_motdepasse = st.text_input("Nouveau mot de passe :", type="password")
    confirmation = st.text_input("Confirmation :", type="password")
    envoye = st.form_submit_button("Changer le mot de passe")

if envoye:
    resultat = changer_mon_mot_de_passe(motdepasse_actuel, nouveau_motdepasse, confirmation)
    flash("info" if resultat["ok"] else "error", resultat["message"])
    st.rerun()

# ============================================================================
# ASTUCES POUR LE STATISTICIEN
# ============================================================================
# 1. clear_on_submit=True est sans danger ici (contrairement aux
#    formulaires "cliquer pour modifier" des autres pages) : ce formulaire
#    n'a pas de mode édition qui préremplit ses champs depuis
#    session_state, donc pas de risque de rencontrer le piège documenté
#    dans vues/comptabilite.py (clear_on_submit qui empêche un
#    préremplissage ultérieur).
#
# 2. Un utilisateur a complètement oublié son mot de passe (donc ne peut
#    pas passer par cette page, qui exige l'ancien) : voir l'astuce 3 en
#    bas de auth.py — un admin_region doit le réinitialiser depuis la page
#    Utilisateurs.
# ============================================================================
