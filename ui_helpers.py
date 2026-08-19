"""
ui_helpers.py — Petites aides d'affichage réutilisées par toutes les pages.

============================================================================
D'OÙ VIENT CE FICHIER ?
============================================================================
Portage de web/includes/helpers.php (flash(), afficher_flash(),
fmt_montant(), render_table_bascule()).

============================================================================
flash() EN PHP VS EN STREAMLIT — POURQUOI CE N'EST PAS JUSTE st.success() ?
============================================================================
En PHP, le motif classique est : on traite un formulaire, puis on fait
"header('Location: ...')" (une redirection) pour éviter que rafraîchir la
page (F5) ne renvoie le formulaire une deuxième fois. Le problème, c'est
que le message de succès ("Bien enregistré.") doit "survivre" à cette
redirection : flash() le range dans $_SESSION, et la page suivante
l'affiche puis l'efface.

En Streamlit, il n'y a pas de "redirection" au sens web classique, mais le
même besoin existe : après avoir cliqué sur un bouton dans un st.form, le
script Python entier est ré-exécuté de haut en bas ("un rerun"). Si on
appelle juste st.success("Bien enregistré.") au milieu du traitement, le
message peut apparaître au mauvais endroit ou disparaître trop vite selon
l'endroit du script où on se trouve. flash()/afficher_flash() résolvent
ça exactement comme en PHP : on RANGE le message dans st.session_state,
et on l'AFFICHE une fois, tout en haut de la page, après le rerun.

RÈGLE SIMPLE pour le statisticien qui ajoute une action :
  - Si le message doit apparaître sur la MÊME page juste après le clic
    (formulaire qui reste affiché) → st.success("...") / st.error("...")
    directement suffit.
  - Si l'action fait ensuite st.rerun() ou change de page (st.switch_page)
    → utilisez flash("info", "...") avant, puis afficher_flash() sera
    appelée automatiquement en haut de la page suivante.
============================================================================
"""

import streamlit as st


def flash(type_message: str, message: str) -> None:
    """
    Mémorise un message à afficher après le prochain rerun.
    type_message : "info" (vert) ou "error" (rouge).
    """
    if "messages_flash" not in st.session_state:
        st.session_state["messages_flash"] = []
    st.session_state["messages_flash"].append({"type": type_message, "message": message})


def afficher_flash() -> None:
    """
    Affiche tous les messages en attente puis les efface. À appeler une
    seule fois, tout en haut de chaque page (juste après exiger_connexion()).
    """
    messages = st.session_state.pop("messages_flash", [])
    for m in messages:
        if m["type"] == "error":
            st.error(m["message"])
        else:
            st.success(m["message"])


def selection_id_tableau(df, cle: str, colonne_id: str = "N°") -> int | None:
    """
    Affiche un tableau où on peut cliquer sur une ligne pour la
    sélectionner (une seule à la fois), et retourne l'identifiant de la
    ligne cliquée (valeur de la colonne `colonne_id`, qui doit faire
    partie de `df`), ou None si aucune ligne n'est sélectionnée.

    Nécessite Streamlit >= 1.35 (paramètres on_select/selection_mode de
    st.dataframe). Utilisé partout dans l'application où on propose
    "cliquer sur une ligne pour la modifier", pour ne pas réécrire ce
    même mécanisme de sélection dans chaque vue.
    """
    evenement = st.dataframe(
        df, use_container_width=True, hide_index=True,
        on_select="rerun", selection_mode="single-row", key=cle,
    )
    lignes_selectionnees = evenement.selection.rows if evenement and evenement.selection else []
    if not lignes_selectionnees:
        return None
    return int(df.iloc[lignes_selectionnees[0]][colonne_id])


def fmt_montant(valeur) -> str:
    """
    Formate un montant en FCFA façon "1 234" (milliers séparés par une
    espace, comme fmt_montant() en PHP). Exemple d'utilisation :
        st.write(f"Solde actuel : {fmt_montant(solde)} FCFA")
    """
    try:
        valeur = float(valeur)
    except (TypeError, ValueError):
        valeur = 0.0
    # "{:,.0f}" met des virgules ("1,234") ; on les remplace ensuite par
    # des espaces ("1 234"), qui est l'habitude française/FCFA.
    return f"{valeur:,.0f}".replace(",", " ")


# ============================================================================
# ASTUCES POUR LE STATISTICIEN
# ============================================================================
# 1. Afficher un tableau de données EN LECTURE SEULE : ce fichier ne
#    contient volontairement PAS de fonction "render_table" générique
#    comme en PHP (pour éditer une ligne, voir selection_id_tableau()
#    ci-dessus), car Streamlit a déjà tout ce qu'il faut, en une ligne :
#
#        import pandas as pd
#        st.dataframe(pd.DataFrame(lignes), use_container_width=True)
#
#    où "lignes" est une liste de dictionnaires (exactement ce que
#    retournent les fonctions de models.py/services.py). Pandas construit
#    lui-même les en-têtes de colonnes à partir des clés du dictionnaire.
#
#    Pour renommer une colonne affichée SANS toucher à la base de
#    données, utilisez .rename() :
#
#        df = pd.DataFrame(lignes).rename(columns={"nom": "Désignation"})
#        st.dataframe(df, use_container_width=True)
#
# 2. Cacher/afficher un tableau au clic d'un bouton (comme le bouton
#    "Afficher le tableau" côté PHP) : en Streamlit, on utilise une case
#    à cocher ou un bouton qui bascule une valeur en mémoire :
#
#        if "afficher_tableau_x" not in st.session_state:
#            st.session_state["afficher_tableau_x"] = False
#        if st.button("Afficher/Masquer le tableau"):
#            st.session_state["afficher_tableau_x"] = not st.session_state["afficher_tableau_x"]
#        if st.session_state["afficher_tableau_x"]:
#            st.dataframe(df, use_container_width=True)
#
# 3. Les onglets JS du PHP (choisir quel formulaire afficher) deviennent
#    st.tabs(["Onglet 1", "Onglet 2"]) — voir vues/comptabilite.py, qui
#    est le premier exemple concret dans cette application.
# ============================================================================
