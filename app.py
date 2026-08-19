"""
app.py — Point d'entrée de l'application. Lancez-la avec :

    streamlit run app.py

============================================================================
D'OÙ VIENT CE FICHIER ?
============================================================================
Il remplace TROIS fichiers PHP à la fois :
  - web/login.php            (écran de connexion)
  - web/includes/header.php  (barre d'onglets / de menu)
  - web/index.php            (tableau de bord avec les "cartes" de services)

============================================================================
POURQUOI st.navigation / st.Page ICI (et pas juste un dossier "pages/") ?
============================================================================
Streamlit propose deux façons de faire une application "multi-pages" :
  1. La façon automatique : un dossier pages/ dont CHAQUE fichier .py
     apparaît TOUJOURS dans le menu, que l'utilisateur soit connecté ou non.
  2. La façon programmée (st.navigation + st.Page, utilisée ici) : c'est
     CE fichier qui décide, à chaque chargement, quelles pages proposer.

On a besoin de la deuxième solution car le menu doit changer selon qui est
connecté : personne ne doit voir "Comptabilité" avant de s'être identifié,
et seul un rôle "admin_region" doit voir la page "Utilisateurs" — exactement
comme web/includes/header.php qui n'affichait le lien "Utilisateurs" que
si $utilisateur['role'] === 'admin_region'.

⚠️ PIÈGE CONSTATÉ ET CORRIGÉ : Streamlit active AUSSI la découverte
automatique (solution 1 ci-dessus) dès qu'un dossier s'appelle EXACTEMENT
"pages" à côté de ce fichier — même si on n'utilise QUE st.navigation().
Résultat : le menu complet apparaissait quand même sur l'écran de
connexion. C'est pour ça que les pages de cette application vivent dans
un dossier "vues/" (et non "pages/") : un simple nom de dossier différent
désactive la découverte automatique et laisse CE fichier seul maître du
menu.
============================================================================
"""

import streamlit as st

from auth import (
    utilisateur_connecte,
    tenter_connexion,
    deconnecter,
    region_actuelle,
    restaurer_session_depuis_url,
    reappliquer_jeton_dans_url,
)
from db import initialiser_la_base_de_donnees

# ----------------------------------------------------------------------
# 1. Réglages généraux de la page (titre de l'onglet du navigateur, icône,
#    largeur). ASTUCE : pour changer les couleurs de l'application
#    (thème), créez/modifiez le fichier .streamlit/config.toml — voir la
#    documentation officielle : https://docs.streamlit.io/library/advanced-features/theming
#    Pas besoin de toucher à ce fichier Python pour ça.
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="Gestion de la Direction Régionale",
    page_icon="🏢",
    layout="wide",
)

# Crée les tables si elles n'existent pas encore (sans effet sinon — voir
# db.py). Appelé à chaque démarrage, comme InitialiserLaBaseDeDonnees()
# était appelée à chaque connexion côté PHP.
initialiser_la_base_de_donnees()

# Restaure la connexion après un rafraîchissement du navigateur (F5) —
# voir restaurer_session_depuis_url() dans auth.py pour le détail. Doit
# être appelé tôt, avant de décider quoi afficher.
restaurer_session_depuis_url()

# Réécrit ?session=... dans l'URL à chaque page : st.navigation/st.page_link
# (le menu) ne reportent pas la query string existante en changeant de
# page, ce qui faisait disparaître le jeton dès le premier clic sur un
# menu — invisible jusqu'au prochain F5, qui redirigeait alors vers le
# login. Voir reappliquer_jeton_dans_url() dans auth.py.
reappliquer_jeton_dans_url()


# ----------------------------------------------------------------------
# 2. ÉCRAN DE CONNEXION (affiché seulement si personne n'est connecté)
# ----------------------------------------------------------------------
def afficher_ecran_connexion() -> None:
    # st.columns([1, 1, 1]) : place le formulaire dans la colonne du
    # milieu, qui occupe donc 1/3 de la largeur de la page — les deux
    # colonnes vides de chaque côté servent juste à centrer visuellement.
    _gauche, colonne_centrale, _droite = st.columns([1, 1, 1])
    with colonne_centrale:
        st.title("🏢 Connexion")
        st.caption("Plateforme de gestion — connectez-vous pour continuer.")

        # st.form regroupe plusieurs champs et un seul bouton "Envoyer" : rien
        # n'est traité tant qu'on n'a pas cliqué sur ce bouton (contrairement à
        # des champs isolés, qui redéclenchent un rerun à chaque frappe). C'est
        # l'équivalent direct d'un <form method="post"> en PHP.
        with st.form("formulaire_connexion"):
            nom = st.text_input("Nom d'utilisateur")
            motdepasse = st.text_input("Mot de passe", type="password")
            envoye = st.form_submit_button("Se connecter", use_container_width=True)

        if envoye:
            if tenter_connexion(nom, motdepasse):
                st.rerun()  # recharge la page : app.py va maintenant voir un utilisateur connecté
            else:
                st.error("Nom d'utilisateur ou mot de passe incorrect.")

        st.info(
            "Première utilisation ? Un compte de démarrage existe déjà :\n\n"
            "**Utilisateur :** `admin` — **Mot de passe :** `changez-moi`\n\n"
            "Connectez-vous avec ce compte puis changez immédiatement ce mot de "
            "passe depuis la page **Utilisateurs** (voir les astuces dans auth.py)."
        )


# ----------------------------------------------------------------------
# 3. BARRE LATÉRALE UNE FOIS CONNECTÉ (équivalent de la "barre-auth" PHP :
#    nom d'utilisateur, région, bouton de déconnexion)
# ----------------------------------------------------------------------
def afficher_barre_utilisateur() -> None:
    utilisateur = utilisateur_connecte()
    region = region_actuelle()
    with st.sidebar:
        st.markdown(f"**Utilisateur :** {utilisateur['nom']}")
        st.markdown(f"**Région :** {region['nom'] if region else 'Non définie'}")
        if st.button("🚪 Déconnexion", use_container_width=True):
            deconnecter()
            st.rerun()
        st.divider()


# ----------------------------------------------------------------------
# 4. LOGIQUE PRINCIPALE
# ----------------------------------------------------------------------
if utilisateur_connecte() is None:
    afficher_ecran_connexion()
else:
    afficher_barre_utilisateur()

    # Chaque entrée du menu pointe vers un fichier du dossier vues/, comme
    # chaque onglet PHP pointait vers un fichier .php du même nom. Pour
    # ajouter une page, créez un fichier vues/mon_service.py (voir
    # vues/comptabilite.py comme modèle) puis ajoutez une ligne ici.
    # (Le dossier s'appelle "vues", pas "pages" — voir la note "PIÈGE
    # CONSTATÉ ET CORRIGÉ" tout en haut de ce fichier.)
    pages = [
        st.Page("vues/accueil.py", title="Accueil", icon="🏠", default=True),
        st.Page("vues/comptabilite.py", title="Comptabilité", icon="💰"),
        st.Page("vues/secretariat.py", title="Secrétariat", icon="✉️"),
        st.Page("vues/ihpc.py", title="IHPC / Indice des prix", icon="📊"),
        st.Page("vues/rh.py", title="Ressources humaines", icon="👥"),
        st.Page("vues/documentation.py", title="Documentation", icon="📁"),
        st.Page("vues/annuaires.py", title="Annuaires statistiques", icon="📚"),
        st.Page("vues/divers.py", title="État civil / Autre service", icon="➕"),
    ]

    # "Utilisateurs" est réservée au rôle admin_region — copie exacte de la
    # règle PHP (`if (($utilisateur['role'] ?? '') === 'admin_region')`).
    if utilisateur_connecte().get("role") == "admin_region":
        pages.append(st.Page("vues/utilisateurs.py", title="Utilisateurs", icon="⚙️"))

    navigation = st.navigation(pages)
    navigation.run()


# ============================================================================
# ASTUCES POUR LE STATISTICIEN
# ============================================================================
# 1. Ajouter une page : créez vues/mon_service.py en copiant la structure
#    de vues/comptabilite.py (les deux premières lignes doivent toujours
#    être l'import et l'appel à exiger_connexion()), puis ajoutez-la à la
#    liste "pages" ci-dessus.
#
# 2. Changer le titre de l'application (celui affiché dans l'onglet du
#    navigateur) : modifiez "page_title" dans st.set_page_config() plus
#    haut.
#
# 3. Retirer le compte de démarrage "admin" : voir les astuces tout en bas
#    de auth.py.
# ============================================================================
