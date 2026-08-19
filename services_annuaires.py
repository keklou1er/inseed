"""
services_annuaires.py — Logique métier du module Annuaires statistiques :
création de questionnaires personnalisés (lignes × colonnes).

============================================================================
D'OÙ VIENT CE FICHIER ?
============================================================================
Portage de web/services.php (NormaliserQuestionnaire, EnregistrerQuestionnaire,
ModifierQuestionnaire, ObtenirStructureQuestionnaire, ListerAnnuaires,
ObtenirAnnuaire, SupprimerAnnuaire) + EnregistrerAnnuaire/ModifierAnnuaire
(fonctions génériques utilisées EN INTERNE par les fonctions "Questionnaire").

============================================================================
⚠️ services.php CONTIENT BEAUCOUP PLUS DE FONCTIONS "ANNUAIRES" QUE CE QUI
EST RÉELLEMENT UTILISÉ ICI (ET NON REPRISES) :
============================================================================
CreerComparativeAnnuaires, CalculerStatistiquesAnnuaire,
DonneesGraphiqueAnnuaire, GenererRapportStatistique, ListerStructures,
AjouterEntreeAnnuaire, ListerEntreesAnnuaire... existent dans services.php
mais web/annuaires.php (la page elle-même) ne les appelle JAMAIS : la page
actuelle ne fait QUE la création/modification/suppression de questionnaires
personnalisés (titre + description + une grille de lignes/colonnes
nommées). Ce portage reproduit fidèlement ce que la page fait
RÉELLEMENT, pas l'ensemble des fonctions présentes (mais inutilisées)
dans services.php. Si vous voulez construire les statistiques/graphiques/
comparaisons d'annuaires, dites-le : le code PHP existe déjà comme base
pour une future page.

============================================================================
COMMENT UN QUESTIONNAIRE EST-IL STOCKÉ ?
============================================================================
Comme en PHP : un questionnaire est une ligne de la table `annuaires`
(type_annuaire='Questionnaire') dont la colonne `description` contient un
texte JSON avec la structure complète :
    {"titre": "...", "description": "...", "lignes": [...], "colonnes": [...]}
C'est un choix simple qui évite de créer des tables séparées pour des
grilles de taille variable.

============================================================================
ISOLATION PAR RÉGION
============================================================================
Comme pour les autres modules, le filtrage par région est ici réellement
appliqué à la LISTE des questionnaires — voir condition_region() dans
db.py. Modifier/supprimer un questionnaire agit par identifiant (comme en
PHP) : la page ne propose ces actions que sur des questionnaires déjà
listés (donc déjà filtrés par région).
============================================================================
"""

import json
from datetime import datetime

from db import get_connection, executer, condition_region


def normaliser_questionnaire(lignes: list[str], colonnes: list[str]) -> dict:
    """
    Nettoie une liste de libellés : espaces enlevés, entrées vides
    retirées, doublons retirés (en gardant le premier), ordre conservé.
    """
    def _nettoyer(valeurs: list[str]) -> list[str]:
        vues = set()
        resultat = []
        for valeur in valeurs:
            libelle = str(valeur).strip()
            if libelle == "" or libelle in vues:
                continue
            vues.add(libelle)
            resultat.append(libelle)
        return resultat

    return {"lignes": _nettoyer(lignes), "colonnes": _nettoyer(colonnes)}


def enregistrer_questionnaire(titre: str, description: str, lignes: list[str], colonnes: list[str], region_id: int | None) -> dict:
    titre = titre.strip()
    if titre == "":
        return {"ok": False, "message": "Le titre du questionnaire est obligatoire."}

    structure = normaliser_questionnaire(lignes, colonnes)
    if not structure["lignes"]:
        return {"ok": False, "message": "Ajoutez au moins une ligne au questionnaire."}
    if not structure["colonnes"]:
        return {"ok": False, "message": "Ajoutez au moins une colonne au questionnaire."}

    config = json.dumps(
        {"titre": titre, "description": description.strip(), "lignes": structure["lignes"], "colonnes": structure["colonnes"]},
        ensure_ascii=False,
    )

    conn = get_connection()
    try:
        executer(
            conn,
            """
            INSERT INTO annuaires (titre, description, type_annuaire, annee, statut, format_fichier, region_id)
            VALUES (?, ?, 'Questionnaire', ?, 'Brouillon', 'Questionnaire', ?)
            """,
            (titre, config, datetime.now().year, region_id),
        )
        conn.commit()
        return {"ok": True, "message": "Questionnaire enregistré avec succès."}
    finally:
        conn.close()


def modifier_questionnaire(annuaire_id: int, titre: str, description: str, lignes: list[str], colonnes: list[str]) -> dict:
    titre = titre.strip()
    if titre == "":
        return {"ok": False, "message": "Le titre du questionnaire est obligatoire."}

    structure = normaliser_questionnaire(lignes, colonnes)
    if not structure["lignes"]:
        return {"ok": False, "message": "Ajoutez au moins une ligne au questionnaire."}
    if not structure["colonnes"]:
        return {"ok": False, "message": "Ajoutez au moins une colonne au questionnaire."}

    config = json.dumps(
        {"titre": titre, "description": description.strip(), "lignes": structure["lignes"], "colonnes": structure["colonnes"]},
        ensure_ascii=False,
    )

    conn = get_connection()
    try:
        executer(
            conn,
            "UPDATE annuaires SET titre = ?, description = ? WHERE id = ?",
            (titre, config, annuaire_id),
        )
        conn.commit()
        return {"ok": True, "message": "Questionnaire modifié avec succès."}
    finally:
        conn.close()


def obtenir_structure_questionnaire(annuaire_id: int) -> dict:
    annuaire = obtenir_annuaire(annuaire_id)
    if annuaire is None:
        return {"titre": "", "description": "", "lignes": [], "colonnes": []}
    try:
        data = json.loads(annuaire["description"] or "{}")
    except (TypeError, ValueError):
        return {"titre": annuaire["titre"], "description": "", "lignes": [], "colonnes": []}
    if not isinstance(data, dict):
        return {"titre": annuaire["titre"], "description": "", "lignes": [], "colonnes": []}
    return {
        "titre": annuaire["titre"],
        "description": data.get("description", ""),
        "lignes": list(data.get("lignes") or []),
        "colonnes": list(data.get("colonnes") or []),
    }


def lister_questionnaires(region_id: int | None) -> list:
    conn = get_connection()
    try:
        clause, parametres = condition_region(region_id)
        return executer(
            conn,
            f"SELECT * FROM annuaires WHERE type_annuaire = 'Questionnaire'{clause} ORDER BY annee DESC, mois DESC, titre",
            parametres,
        ).fetchall()
    finally:
        conn.close()


def obtenir_annuaire(annuaire_id: int):
    conn = get_connection()
    try:
        return executer(conn, "SELECT * FROM annuaires WHERE id = ?", (annuaire_id,)).fetchone()
    finally:
        conn.close()


def supprimer_annuaire(annuaire_id: int) -> dict:
    """Supprime l'annuaire ET ses entrées/comparaisons associées (cascade manuelle, comme en PHP)."""
    conn = get_connection()
    try:
        executer(conn, "DELETE FROM entrees_annuaire WHERE annuaire_id = ?", (annuaire_id,))
        executer(
            conn,
            "DELETE FROM comparatifs_annuaires WHERE annuaire_source_id = ? OR annuaire_comparaison_id = ?",
            (annuaire_id, annuaire_id),
        )
        executer(conn, "DELETE FROM annuaires WHERE id = ?", (annuaire_id,))
        conn.commit()
        return {"ok": True, "message": "Annuaire supprimé avec succès."}
    finally:
        conn.close()


# ============================================================================
# ASTUCES POUR LE STATISTICIEN
# ============================================================================
# 1. Le questionnaire est une simple grille "lignes × colonnes" nommées
#    (par ex. des lignes "Homme"/"Femme" et des colonnes "0-14 ans"/
#    "15-64 ans"/"65 ans et +" pour un questionnaire de pyramide des
#    âges) : ce module ne gère QUE la structure (les libellés), pas la
#    saisie de valeurs dans la grille — comme en PHP.
#
# 2. Tester ce fichier sans lancer Streamlit :
#        from services_annuaires import enregistrer_questionnaire, lister_questionnaires
#        print(enregistrer_questionnaire("Pyramide des âges", "", ["Hommes", "Femmes"], ["0-14", "15-64", "65+"], 1))
#        print(lister_questionnaires(1))
# ============================================================================
