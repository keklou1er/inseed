"""
services_rh.py — Logique métier du module Ressources Humaines (RH) :
employés, contrats, congés, formations, paie.

============================================================================
D'OÙ VIENT CE FICHIER ?
============================================================================
Portage de la partie "3. LOGIQUE GESTION RESSOURCES HUMAINES" de
web/services.php (EnregistrerEmploye, ListerLesEmployes, RechercherEmployes,
EnregistrerContrat, ListerContrats, DemanderCongé, ListerConges,
EnregistrerFormation, ListerFormations, EnregistrerPaie, ListerPaies).

============================================================================
FONCTIONNALITÉS DU PHP NON REPRISES ICI (VOLONTAIREMENT)
============================================================================
web/services.php contient aussi ModifierEmploye(), SupprimerEmploye() et
ValiderCongé() — mais web/rh.php (la page elle-même) n'affiche AUCUN
formulaire ni bouton qui les utilise (seul le traitement POST existe,
jamais déclenché depuis l'interface visible). Ce sont donc des
fonctionnalités mortes côté PHP. Pour rester fidèle à ce que
l'utilisateur voit et utilise réellement, ce portage ne les reprend pas
non plus. Si vous voulez ajouter un bouton "Modifier"/"Supprimer" un
employé ou "Approuver"/"Rejeter" un congé, dites-le : le code PHP
équivalent existe déjà et peut servir de base.

============================================================================
⚠️ CORRECTION PAR RAPPORT AU PHP : LA COLONNE "SALAIRE" DU TABLEAU EMPLOYÉS
============================================================================
Dans web/rh.php, la définition des colonnes du tableau employés contient
une erreur de copier-coller :
    'Salaire' => fmt_montant('salaire_base' ?? 0)
Ceci calcule fmt_montant() sur la CHAÎNE littérale 'salaire_base' (pas sur
la valeur de la ligne), ce qui donne toujours "0" comme intitulé de
colonne — et comme la clé 'Salaire' (majuscule) ne correspond à aucune
colonne réelle de la table ('salaire_base', minuscule), la cellule est
TOUJOURS VIDE pour chaque employé. Le salaire n'est donc, en pratique,
jamais affiché dans le tableau PHP. Ici, la page (vues/rh.py) affiche
correctement la colonne "Salaire (FCFA)" avec la vraie valeur de chaque
employé.

============================================================================
ISOLATION PAR RÉGION
============================================================================
services.php accepte déjà un paramètre region_id sur presque toutes ces
fonctions (quelqu'un l'avait préparé), mais web/rh.php ne le passe JAMAIS
(région toujours à null). Comme pour la Comptabilité, le Secrétariat et
l'IHPC, ce portage active réellement le filtrage par région — voir
condition_region() dans db.py.
============================================================================
"""

import re

from db import get_connection, executer, condition_region

TYPES_DE_CONTRAT = ["CDI", "CDD", "Stagiaire", "Temporaire"]
STATUTS_EMPLOYE = ["Actif", "En congé", "Inactif", "Suspendu"]
TYPES_DE_CONGE = ["Annuel", "Maladie", "Maternité", "Paternité", "Sabbatique", "Autre"]
STATUTS_CONGE = ["En attente", "Approuvé", "Rejeté"]
STATUTS_FORMATION = ["En cours", "Terminée", "Annulée"]
STATUTS_PAIE = ["En attente", "Approuvé", "Versé"]

_REGEX_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ----------------------------------------------------------------------
# 1. EMPLOYÉS
# ----------------------------------------------------------------------
def enregistrer_employe(
    nom: str, prenom: str, email: str, telephone: str, date_naissance: str,
    lieu_naissance: str, nationalite: str, numero_id: str, adresse: str,
    fonction: str, profession: str, type_contrat: str, statut: str,
    date_embauche: str, salaire_base: float, region_id: int | None,
) -> dict:
    nom = nom.strip()
    prenom = prenom.strip()
    email = email.strip()
    fonction = fonction.strip()
    profession = profession.strip()
    statut = statut.strip() or "Actif"

    if nom == "" or prenom == "" or fonction == "" or profession == "" or type_contrat == "" or date_embauche == "":
        return {"ok": False, "message": "Veuillez remplir tous les champs obligatoires."}
    if email != "" and not _REGEX_EMAIL.match(email):
        return {"ok": False, "message": "L'adresse email n'est pas valide."}
    if salaire_base < 0:
        return {"ok": False, "message": "Le salaire base ne peut pas être négatif."}

    conn = get_connection()
    try:
        executer(
            conn,
            """
            INSERT INTO employes (
                nom, prenom, email, telephone, date_naissance, lieu_naissance,
                nationalite, numero_id, adresse, fonction, profession, type_contrat,
                statut, date_embauche, salaire_base, region_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                nom, prenom, email or None, telephone or None, date_naissance or None,
                lieu_naissance or None, nationalite or None, numero_id or None, adresse or None,
                fonction, profession, type_contrat, statut, date_embauche, salaire_base, region_id,
            ),
        )
        conn.commit()
        return {"ok": True, "message": "Employé enregistré avec succès."}
    finally:
        conn.close()


def lister_employes(region_id: int | None) -> list:
    conn = get_connection()
    try:
        clause, parametres = condition_region(region_id)
        return executer(
            conn, f"SELECT * FROM employes WHERE 1=1{clause} ORDER BY nom, prenom", parametres
        ).fetchall()
    finally:
        conn.close()


def modifier_employe(
    employe_id: int, nom: str, prenom: str, email: str, telephone: str, date_naissance: str,
    lieu_naissance: str, nationalite: str, numero_id: str, adresse: str,
    fonction: str, profession: str, type_contrat: str, statut: str,
    date_embauche: str, salaire_base: float,
) -> dict:
    """Met à jour un employé déjà enregistré (voir enregistrer_employe pour la création)."""
    nom = nom.strip()
    prenom = prenom.strip()
    email = email.strip()
    fonction = fonction.strip()
    profession = profession.strip()
    statut = statut.strip() or "Actif"

    if nom == "" or prenom == "" or fonction == "" or profession == "" or type_contrat == "" or date_embauche == "":
        return {"ok": False, "message": "Veuillez remplir tous les champs obligatoires."}
    if email != "" and not _REGEX_EMAIL.match(email):
        return {"ok": False, "message": "L'adresse email n'est pas valide."}
    if salaire_base < 0:
        return {"ok": False, "message": "Le salaire base ne peut pas être négatif."}

    conn = get_connection()
    try:
        executer(
            conn,
            """
            UPDATE employes SET
                nom = ?, prenom = ?, email = ?, telephone = ?, date_naissance = ?, lieu_naissance = ?,
                nationalite = ?, numero_id = ?, adresse = ?, fonction = ?, profession = ?, type_contrat = ?,
                statut = ?, date_embauche = ?, salaire_base = ?
            WHERE id = ?
            """,
            (
                nom, prenom, email or None, telephone or None, date_naissance or None,
                lieu_naissance or None, nationalite or None, numero_id or None, adresse or None,
                fonction, profession, type_contrat, statut, date_embauche, salaire_base, employe_id,
            ),
        )
        conn.commit()
        return {"ok": True, "message": "Employé modifié avec succès."}
    finally:
        conn.close()


def rechercher_employes(terme: str, region_id: int | None) -> list:
    """
    Recherche approximative (insensible à la casse) sur nom, prénom,
    email, fonction, profession, type de contrat et numéro d'identité —
    exactement les mêmes colonnes que RechercherEmployes() en PHP.
    """
    terme = terme.strip()
    conn = get_connection()
    try:
        clause, parametres = condition_region(region_id)
        if terme == "":
            return executer(
                conn, f"SELECT * FROM employes WHERE 1=1{clause} ORDER BY nom, prenom", parametres
            ).fetchall()

        motif = f"%{terme.lower()}%"
        return executer(
            conn,
            f"""
            SELECT * FROM employes WHERE 1=1{clause} AND (
                LOWER(nom) LIKE ? OR LOWER(prenom) LIKE ?
                OR LOWER(nom || ' ' || prenom) LIKE ?
                OR LOWER(email) LIKE ? OR LOWER(fonction) LIKE ?
                OR LOWER(profession) LIKE ? OR LOWER(type_contrat) LIKE ?
                OR LOWER(numero_id) LIKE ?
            )
            ORDER BY nom, prenom
            """,
            parametres + (motif, motif, motif, motif, motif, motif, motif, motif),
        ).fetchall()
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 2. CONTRATS
# ----------------------------------------------------------------------
def enregistrer_contrat(
    employe_id: int, type_contrat: str, date_debut: str, date_fin: str,
    duree_essai: int, statut: str, region_id: int | None,
) -> dict:
    if type_contrat == "" or date_debut == "":
        return {"ok": False, "message": "Veuillez remplir les champs obligatoires."}
    conn = get_connection()
    try:
        executer(
            conn,
            "INSERT INTO contrats (employe_id, type_contrat, date_debut, date_fin, duree_essai, statut, region_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (employe_id, type_contrat, date_debut, date_fin or None, duree_essai, statut or "Actif", region_id),
        )
        conn.commit()
        return {"ok": True, "message": "Contrat enregistré avec succès."}
    finally:
        conn.close()


def modifier_contrat(contrat_id: int, type_contrat: str, date_debut: str, date_fin: str, duree_essai: int, statut: str) -> dict:
    """Met à jour un contrat déjà enregistré (voir enregistrer_contrat pour la création)."""
    if type_contrat == "" or date_debut == "":
        return {"ok": False, "message": "Veuillez remplir les champs obligatoires."}
    conn = get_connection()
    try:
        executer(
            conn,
            "UPDATE contrats SET type_contrat = ?, date_debut = ?, date_fin = ?, duree_essai = ?, statut = ? WHERE id = ?",
            (type_contrat, date_debut, date_fin or None, duree_essai, statut or "Actif", contrat_id),
        )
        conn.commit()
        return {"ok": True, "message": "Contrat modifié avec succès."}
    finally:
        conn.close()


def lister_contrats(region_id: int | None) -> list:
    conn = get_connection()
    try:
        clause, parametres = condition_region(region_id, colonne="c.region_id")
        return executer(
            conn,
            f"""
            SELECT c.*, e.nom, e.prenom FROM contrats c
            JOIN employes e ON c.employe_id = e.id
            WHERE 1=1{clause}
            ORDER BY c.date_debut DESC
            """,
            parametres,
        ).fetchall()
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 3. CONGÉS
# ----------------------------------------------------------------------
def demander_conge(
    employe_id: int, type_conge: str, date_debut: str, date_fin: str,
    nombre_jours: int, motif: str, region_id: int | None,
) -> dict:
    if type_conge == "" or date_debut == "" or date_fin == "":
        return {"ok": False, "message": "Veuillez remplir les champs obligatoires."}
    if nombre_jours <= 0:
        return {"ok": False, "message": "Le nombre de jours doit être supérieur à 0."}
    conn = get_connection()
    try:
        executer(
            conn,
            """
            INSERT INTO conges (employe_id, type_conge, date_debut, date_fin, nombre_jours, motif, statut, region_id)
            VALUES (?, ?, ?, ?, ?, ?, 'En attente', ?)
            """,
            (employe_id, type_conge, date_debut, date_fin, nombre_jours, motif or None, region_id),
        )
        conn.commit()
        return {"ok": True, "message": "Demande de congé enregistrée. En attente d'approbation."}
    finally:
        conn.close()


def modifier_conge(
    conge_id: int, type_conge: str, date_debut: str, date_fin: str, nombre_jours: int, motif: str, statut: str
) -> dict:
    """
    Met à jour une demande de congé déjà enregistrée (voir demander_conge
    pour la création) — permet aussi de faire passer le statut de "En
    attente" à "Approuvé"/"Rejeté" en la modifiant.
    """
    if type_conge == "" or date_debut == "" or date_fin == "":
        return {"ok": False, "message": "Veuillez remplir les champs obligatoires."}
    if nombre_jours <= 0:
        return {"ok": False, "message": "Le nombre de jours doit être supérieur à 0."}
    conn = get_connection()
    try:
        executer(
            conn,
            """
            UPDATE conges SET type_conge = ?, date_debut = ?, date_fin = ?, nombre_jours = ?, motif = ?, statut = ?
            WHERE id = ?
            """,
            (type_conge, date_debut, date_fin, nombre_jours, motif or None, statut or "En attente", conge_id),
        )
        conn.commit()
        return {"ok": True, "message": "Demande de congé modifiée avec succès."}
    finally:
        conn.close()


def lister_conges(region_id: int | None) -> list:
    conn = get_connection()
    try:
        clause, parametres = condition_region(region_id, colonne="c.region_id")
        return executer(
            conn,
            f"""
            SELECT c.*, e.nom, e.prenom FROM conges c
            JOIN employes e ON c.employe_id = e.id
            WHERE 1=1{clause}
            ORDER BY c.date_debut DESC
            """,
            parametres,
        ).fetchall()
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 4. FORMATIONS
# ----------------------------------------------------------------------
def enregistrer_formation(
    employe_id: int, titre: str, domaine: str, date_debut: str, date_fin: str,
    organisme: str, cout: float, statut: str, region_id: int | None,
) -> dict:
    if titre == "" or date_debut == "":
        return {"ok": False, "message": "Veuillez remplir les champs obligatoires."}
    if cout < 0:
        return {"ok": False, "message": "Le coût ne peut pas être négatif."}
    conn = get_connection()
    try:
        executer(
            conn,
            """
            INSERT INTO formations (employe_id, titre, domaine, date_debut, date_fin, organisme, cout, statut, region_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (employe_id, titre, domaine or None, date_debut, date_fin or None, organisme or None, cout, statut or "En cours", region_id),
        )
        conn.commit()
        return {"ok": True, "message": "Formation enregistrée avec succès."}
    finally:
        conn.close()


def modifier_formation(
    formation_id: int, titre: str, domaine: str, date_debut: str, date_fin: str, organisme: str, cout: float, statut: str
) -> dict:
    """Met à jour une formation déjà enregistrée (voir enregistrer_formation pour la création)."""
    if titre == "" or date_debut == "":
        return {"ok": False, "message": "Veuillez remplir les champs obligatoires."}
    if cout < 0:
        return {"ok": False, "message": "Le coût ne peut pas être négatif."}
    conn = get_connection()
    try:
        executer(
            conn,
            """
            UPDATE formations SET titre = ?, domaine = ?, date_debut = ?, date_fin = ?, organisme = ?, cout = ?, statut = ?
            WHERE id = ?
            """,
            (titre, domaine or None, date_debut, date_fin or None, organisme or None, cout, statut or "En cours", formation_id),
        )
        conn.commit()
        return {"ok": True, "message": "Formation modifiée avec succès."}
    finally:
        conn.close()


def lister_formations(region_id: int | None) -> list:
    conn = get_connection()
    try:
        clause, parametres = condition_region(region_id, colonne="f.region_id")
        return executer(
            conn,
            f"""
            SELECT f.*, e.nom, e.prenom FROM formations f
            JOIN employes e ON f.employe_id = e.id
            WHERE 1=1{clause}
            ORDER BY f.date_debut DESC
            """,
            parametres,
        ).fetchall()
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 5. PAIE
# ----------------------------------------------------------------------
def enregistrer_paie(
    employe_id: int, mois_annee: str, salaire_base: float, primes: float,
    retenues: float, cotisations_sociales: float, statut: str, region_id: int | None,
) -> dict:
    """
    Comme en PHP (ON DUPLICATE KEY UPDATE), ré-enregistrer une paie pour
    le même employé + même mois/année MET À JOUR la ligne existante au
    lieu d'en créer une deuxième (contrainte UNIQUE(employe_id, mois_annee)
    — voir db.py, table `paies`).
    """
    if mois_annee.strip() == "" or salaire_base < 0:
        return {"ok": False, "message": "Données invalides."}

    salaire_net = salaire_base + primes - retenues - cotisations_sociales

    conn = get_connection()
    try:
        executer(
            conn,
            """
            INSERT INTO paies (employe_id, mois_annee, salaire_base, primes, retenues, cotisations_sociales, salaire_net, statut, region_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(employe_id, mois_annee) DO UPDATE SET
                salaire_base = excluded.salaire_base,
                primes = excluded.primes,
                retenues = excluded.retenues,
                cotisations_sociales = excluded.cotisations_sociales,
                salaire_net = excluded.salaire_net,
                statut = excluded.statut
            """,
            (employe_id, mois_annee.strip(), salaire_base, primes, retenues, cotisations_sociales, salaire_net, statut or "En attente", region_id),
        )
        conn.commit()
        return {"ok": True, "message": "Paie enregistrée avec succès.", "salaire_net": salaire_net}
    finally:
        conn.close()


def lister_paies(region_id: int | None) -> list:
    conn = get_connection()
    try:
        clause, parametres = condition_region(region_id, colonne="p.region_id")
        return executer(
            conn,
            f"""
            SELECT p.*, e.nom, e.prenom FROM paies p
            JOIN employes e ON p.employe_id = e.id
            WHERE 1=1{clause}
            ORDER BY p.mois_annee DESC, e.nom
            """,
            parametres,
        ).fetchall()
    finally:
        conn.close()


# ============================================================================
# ASTUCES POUR LE STATISTICIEN
# ============================================================================
# 1. La liste TYPES_DE_CONTRAT (ou STATUTS_EMPLOYE, TYPES_DE_CONGE,
#    STATUTS_PAIE) tout en haut de ce fichier alimente automatiquement les
#    st.selectbox() de vues/rh.py : pour ajouter/retirer une option,
#    modifiez juste la liste ici.
#
# 2. La contrainte "un seul enregistrement de paie par employé et par
#    mois" (UNIQUE(employe_id, mois_annee)) vient de db.py. Pour
#    l'assouplir (permettre plusieurs paies le même mois), il faudrait
#    retirer cette contrainte dans db.py ET changer le INSERT ... ON
#    CONFLICT ci-dessus en simple INSERT.
#
# 3. Tester ce fichier sans lancer Streamlit :
#        from services_rh import enregistrer_employe, lister_employes
#        print(enregistrer_employe("Mensah", "Kodjo", "", "", "", "", "", "", "", "Comptable", "Comptable", "CDI", "Actif", "2026-01-01", 150000, 1))
#        print(lister_employes(1))
# ============================================================================
