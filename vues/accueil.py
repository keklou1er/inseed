"""
vues/accueil.py — Tableau de bord (page d'atterrissage après connexion).

============================================================================
D'OÙ VIENT CETTE PAGE ?
============================================================================
Portage de web/index.php : elle affichait une "carte" cliquable par
service (Comptabilité, Secrétariat, ...), construite dynamiquement à
partir de la table `services`. Ici, la table `services` (voir db.py,
SERVICES_PAR_DEFAUT) sert exactement au même usage.

============================================================================
POURQUOI st.page_link ICI ?
============================================================================
st.page_link crée un lien cliquable vers une autre page de l'application
(déclarée dans app.py via st.Page) — c'est l'équivalent du <a href="...">
utilisé par chaque carte du tableau de bord PHP.
============================================================================
"""

import streamlit as st

from auth import exiger_connexion, utilisateur_connecte, region_actuelle, services_disponibles

exiger_connexion()

utilisateur = utilisateur_connecte()
region = region_actuelle()

st.title(f"🏢 {region['nom'] if region else 'ESPACE INSEED'}")
st.caption(f"Bienvenue, {utilisateur['nom']}.")

# ASTUCE : cette table associe le "slug" d'un service (colonne `slug` de
# la table `services`, voir db.py) au fichier de page correspondant.
# Si vous ajoutez un nouveau service dans SERVICES_PAR_DEFAUT (db.py),
# ajoutez ici la ligne qui le relie à sa page.
PAGE_PAR_SLUG = {
    "comptabilite": "vues/comptabilite.py",
    "secretariat": "vues/secretariat.py",
    "ressources_humaines": "vues/rh.py",
    "documentation": "vues/documentation.py",
    "etat_civil": "vues/divers.py",
    "annuaire": "vues/annuaires.py",
    "ihpc": "vues/ihpc.py",
    "autre_service": "vues/divers.py",
}

st.divider()

services = [s for s in services_disponibles() if s["slug"] != "accueil"]

# Affiche les cartes en grille de 3 colonnes (comme les "cartes-services"
# CSS en grille du PHP). st.columns(3) crée 3 colonnes ; on y place les
# services les uns après les autres, en repartant à la colonne 0 tous les
# 3 services.
colonnes = st.columns(3)
for index, service in enumerate(services):
    cible = PAGE_PAR_SLUG.get(service["slug"])
    with colonnes[index % 3]:
        with st.container(border=True):
            st.markdown(f"### {service['icone']} {service['nom']}")
            if cible:
                st.page_link(cible, label="Ouvrir le service", icon="➡️")
            else:
                st.caption("Service non encore relié à une page.")

# ============================================================================
# ASTUCES POUR LE STATISTICIEN
# ============================================================================
# 1. Changer le texte/l'icône d'une carte : modifiez la ligne correspondante
#    dans SERVICES_PAR_DEFAUT, dans db.py — PAS ici. Cette page se contente
#    d'afficher ce qui est en base.
#
# 2. Changer l'ORDRE des cartes : modifiez l'ordre des lignes dans
#    SERVICES_PAR_DEFAUT (db.py). Si vous avez déjà lancé l'application au
#    moins une fois, l'ordre existant en base ne bougera pas tout seul :
#    il faudra soit supprimer data/gestion.db (tout est réinitialisé),
#    soit modifier directement la table `services` avec DB Browser for
#    SQLite (voir astuces de db.py).
# ============================================================================
