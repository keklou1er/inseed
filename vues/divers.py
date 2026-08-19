"""
vues/divers.py — Services encore à l'état d'ébauche (état civil, annuaire,
autre service).

============================================================================
D'OÙ VIENT CETTE PAGE ?
============================================================================
Portage de web/divers.php, qui regroupe 3 pseudo-pages sélectionnées via
?page=... (etat_civil, annuaire, autre_service), chacune affichant
uniquement "Service non encore implémenté". Ici, st.tabs() remplace ce
sélecteur ?page=...

⚠️ Le sous-onglet "Annuaire" ci-dessous est un doublon hérité du PHP :
le VRAI module Annuaires statistiques (questionnaires personnalisés) est
maintenant une page à part entière — voir vues/annuaires.py. Ce
sous-onglet reste ici pour rester fidèle à web/divers.php tel qu'il est
actuellement (il n'a jamais été retiré côté PHP non plus).
============================================================================
"""

import streamlit as st

from auth import exiger_connexion

exiger_connexion()

st.title("➕ Autres services")

PAGES = {
    "État civil": "Service des statistiques des faits d'état civil",
    "Annuaire": "Service des annuaires statistiques",
    "Autre service": "Autres services",
}

for onglet, (titre_section, contenu) in zip(st.tabs(list(PAGES.keys())), PAGES.items()):
    with onglet:
        st.subheader(contenu)
        st.info("Service non encore implémenté (état identique à l'application de bureau).")

# ============================================================================
# ASTUCES POUR LE STATISTICIEN
# ============================================================================
# 1. Pour construire un de ces services (ex. "État civil"), remplacez son
#    bloc st.info(...) ci-dessus par un vrai formulaire + tableau — voir
#    vues/comptabilite.py comme modèle le plus simple à copier.
# ============================================================================
