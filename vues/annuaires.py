"""
vues/annuaires.py — Annuaires statistiques : création de questionnaires
personnalisés (grille de lignes × colonnes).

============================================================================
D'OÙ VIENT CETTE PAGE ?
============================================================================
Portage de web/annuaires.php. La page PHP actuelle ne fait QUE la
création/modification/suppression de "questionnaires personnalisés" (un
titre + une grille de lignes/colonnes nommées) — voir la note en haut de
services_annuaires.py pour la liste des fonctions de services.php qui
existent mais ne sont PAS utilisées par cette page (statistiques,
graphiques, comparaisons...).

============================================================================
PHP → STREAMLIT : LES BOUTONS "+ Ligne" / "+ Colonne" (JavaScript)
============================================================================
Le PHP ajoutait/retirait des champs <input> à la volée avec du JavaScript
(ajouterChamp()). Streamlit n'exécute pas de JS côté client : l'équivalent
est de garder la liste des libellés dans st.session_state (comme le
panier de vente d'vues/ihpc.py) et de la modifier via de vrais boutons
Python ("+ Ligne", "✕" par ligne), chaque clic déclenchant un st.rerun()
qui réaffiche la grille à jour.
============================================================================
"""

import streamlit as st

from auth import exiger_connexion, utilisateur_connecte, region_actuelle
from ui_helpers import flash, afficher_flash
from services_annuaires import (
    enregistrer_questionnaire,
    modifier_questionnaire,
    obtenir_structure_questionnaire,
    lister_questionnaires,
    supprimer_annuaire,
)

exiger_connexion()
afficher_flash()

region_id = utilisateur_connecte()["region_id"]
region = region_actuelle()

st.title("📚 Annuaires statistiques")
st.caption(f"Région : {region['nom']}" if region else "Vue globale (toutes régions) — compte sans région assignée")


def _demander_reinitialisation(titre: str = "", description: str = "", lignes=None, colonnes=None, annuaire_id=None) -> None:
    """
    Programme un rechargement complet de l'éditeur (titre/description/
    lignes/colonnes) pour le PROCHAIN rerun.

    ⚠️ Pourquoi ne pas juste écrire directement dans
    st.session_state["editeur_titre"] ici ? Parce qu'au moment où cette
    fonction est appelée (ex. après un clic sur "Modifier"), le widget
    st.text_input(key="editeur_titre") a déjà été instancié PLUS HAUT
    dans ce même script — et Streamlit interdit de modifier la valeur
    d'un widget après qu'il a été créé pendant le même passage
    (StreamlitAPIException: "cannot be modified after the widget ... is
    instantiated"). La solution : ranger les nouvelles valeurs dans une
    clé "en attente" (_reset_annuaires), déclencher un st.rerun(), et
    c'est le bloc tout en haut de ce fichier (AVANT tout widget) qui les
    applique réellement au prochain passage.
    """
    st.session_state["_reset_annuaires"] = {
        "titre": titre,
        "description": description,
        "lignes": list(lignes) if lignes else [""],
        "colonnes": list(colonnes) if colonnes else [""],
        "annuaire_id": annuaire_id,
    }


# Applique une réinitialisation en attente (ou initialise l'éditeur au
# tout premier affichage) — TOUJOURS avant de créer le moindre widget.
if "_reset_annuaires" in st.session_state:
    _valeurs = st.session_state.pop("_reset_annuaires")
    for cle in list(st.session_state.keys()):
        if cle.startswith("ligne_") or cle.startswith("colonne_"):
            del st.session_state[cle]
    st.session_state["editeur_titre"] = _valeurs["titre"]
    st.session_state["editeur_description"] = _valeurs["description"]
    st.session_state["editeur_lignes"] = _valeurs["lignes"]
    st.session_state["editeur_colonnes"] = _valeurs["colonnes"]
    st.session_state["annuaire_en_edition"] = _valeurs["annuaire_id"]
    # Pré-remplit aussi directement les clés ligne_0/ligne_1/.../colonne_0/...
    # : s'appuyer uniquement sur le paramètre value=... au moment de créer
    # le widget s'est révélé peu fiable pour le tout premier élément de la
    # liste (bug observé en test navigateur : "Ligne 1" restait vide alors
    # que "Ligne 2" se remplissait correctement). Pré-remplir ici, avant
    # tout widget, est fiable dans tous les cas.
    for _i, _valeur in enumerate(_valeurs["lignes"]):
        st.session_state[f"ligne_{_i}"] = _valeur
    for _i, _valeur in enumerate(_valeurs["colonnes"]):
        st.session_state[f"colonne_{_i}"] = _valeur
elif "editeur_lignes" not in st.session_state:
    st.session_state["editeur_titre"] = ""
    st.session_state["editeur_description"] = ""
    st.session_state["editeur_lignes"] = [""]
    st.session_state["editeur_colonnes"] = [""]
    st.session_state["annuaire_en_edition"] = None

en_edition = st.session_state["annuaire_en_edition"] is not None

with st.container(border=True):
    st.subheader("✏️ Modifier le questionnaire" if en_edition else "➕ Créer un questionnaire")

    colonne_titre, colonne_description = st.columns(2)
    with colonne_titre:
        titre = st.text_input("Titre du questionnaire :", key="editeur_titre")
    with colonne_description:
        description = st.text_area("Description :", key="editeur_description")

    colonne_lignes, colonne_colonnes = st.columns(2)

    with colonne_lignes:
        st.markdown("**Lignes**")
        lignes_actuelles = []
        for i, valeur in enumerate(st.session_state["editeur_lignes"]):
            c_champ, c_bouton = st.columns([5, 1])
            with c_champ:
                v = st.text_input(
                    f"Ligne {i + 1}", value=valeur, key=f"ligne_{i}",
                    placeholder="Libellé de la ligne", label_visibility="collapsed",
                )
            with c_bouton:
                if st.button("✕", key=f"suppr_ligne_{i}") and len(st.session_state["editeur_lignes"]) > 1:
                    st.session_state["editeur_lignes"].pop(i)
                    st.rerun()
            lignes_actuelles.append(v)
        st.session_state["editeur_lignes"] = lignes_actuelles
        if st.button("+ Ligne"):
            st.session_state["editeur_lignes"].append("")
            st.rerun()

    with colonne_colonnes:
        st.markdown("**Colonnes**")
        colonnes_actuelles = []
        for i, valeur in enumerate(st.session_state["editeur_colonnes"]):
            c_champ, c_bouton = st.columns([5, 1])
            with c_champ:
                v = st.text_input(
                    f"Colonne {i + 1}", value=valeur, key=f"colonne_{i}",
                    placeholder="Libellé de la colonne", label_visibility="collapsed",
                )
            with c_bouton:
                if st.button("✕", key=f"suppr_colonne_{i}") and len(st.session_state["editeur_colonnes"]) > 1:
                    st.session_state["editeur_colonnes"].pop(i)
                    st.rerun()
            colonnes_actuelles.append(v)
        st.session_state["editeur_colonnes"] = colonnes_actuelles
        if st.button("+ Colonne"):
            st.session_state["editeur_colonnes"].append("")
            st.rerun()

    st.divider()
    colonne_enregistrer, colonne_annuler = st.columns([1, 1])
    with colonne_enregistrer:
        enregistrer_clic = st.button(
            "✓ Enregistrer les modifications" if en_edition else "➕ Créer le questionnaire",
            type="primary", use_container_width=True,
        )
    with colonne_annuler:
        if en_edition and st.button("✕ Annuler", use_container_width=True):
            _demander_reinitialisation()
            st.rerun()

    if enregistrer_clic:
        if en_edition:
            resultat = modifier_questionnaire(
                st.session_state["annuaire_en_edition"], titre, description, lignes_actuelles, colonnes_actuelles
            )
        else:
            resultat = enregistrer_questionnaire(titre, description, lignes_actuelles, colonnes_actuelles, region_id)
        flash("info" if resultat["ok"] else "error", resultat["message"])
        if resultat["ok"]:
            _demander_reinitialisation()
        st.rerun()

st.divider()
st.subheader("📋 Questionnaires enregistrés")

questionnaires = lister_questionnaires(region_id)
if not questionnaires:
    st.info("Aucun questionnaire n'a encore été créé.")
else:
    for q in questionnaires:
        structure = obtenir_structure_questionnaire(q["id"])
        colonne_info, colonne_modifier, colonne_supprimer = st.columns([6, 1, 1])
        with colonne_info:
            st.markdown(f"**{q['titre']}** — {len(structure['lignes'])} ligne(s), {len(structure['colonnes'])} colonne(s)")
            if structure["description"]:
                st.caption(structure["description"])
        with colonne_modifier:
            if st.button("✏️ Modifier", key=f"modifier_{q['id']}"):
                _demander_reinitialisation(
                    titre=structure["titre"], description=structure["description"],
                    lignes=structure["lignes"], colonnes=structure["colonnes"], annuaire_id=q["id"],
                )
                st.rerun()
        with colonne_supprimer:
            if st.button("🗑️ Supprimer", key=f"suppr_{q['id']}"):
                resultat = supprimer_annuaire(q["id"])
                flash("info" if resultat["ok"] else "error", resultat["message"])
                if st.session_state["annuaire_en_edition"] == q["id"]:
                    _demander_reinitialisation()
                st.rerun()

# ============================================================================
# ASTUCES POUR LE STATISTICIEN
# ============================================================================
# 1. La grille lignes × colonnes ne stocke QUE les libellés (la structure
#    du questionnaire), pas de valeurs saisies dedans — comme en PHP.
#    Pour aller plus loin (saisir des valeurs dans chaque case et les
#    enregistrer), il faudrait une nouvelle table dédiée : dites-le si
#    vous voulez cette fonctionnalité, elle n'existe pas encore côté PHP.
#
# 2. Pourquoi _demander_reinitialisation() efface les clés ligne_*/colonne_*
#    de st.session_state avant de les recréer ? Parce qu'un widget
#    Streamlit qui a déjà une clé en mémoire IGNORE le paramètre
#    value=... qu'on lui repasse (il continue d'afficher ce que
#    l'utilisateur avait tapé). Pour forcer un vrai rechargement (ex. en
#    ouvrant "Modifier" sur un autre questionnaire), il faut d'abord
#    supprimer ces anciennes clés.
# ============================================================================
