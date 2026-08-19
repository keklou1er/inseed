"""
services_comptabilite.py — Logique métier du module Comptabilité.

============================================================================
D'OÙ VIENT CE FICHIER ?
============================================================================
Portage de la partie "1. LOGIQUE COMPTABLE" de web/services.php
(EnregistrerUnBien, SoldeTresorerie, BalanceGenerale, EnregistrerRessourceEmploi).

============================================================================
POURQUOI UN FICHIER SÉPARÉ PAR MODULE (au lieu d'UN SEUL services.py
géant comme en PHP, qui fait 1574 lignes) ?
============================================================================
Pour que ce soit facile à retrouver : si vous voulez changer une règle de
comptabilité, vous ouvrez CE fichier (une centaine de lignes), pas un
fichier de 1500 lignes qui mélange comptabilité, RH, documentation...
Chaque module aura son propre services_xxx.py (services_secretariat.py à
la Phase 2, services_ihpc.py à la Phase 3, etc.).

============================================================================
COMPTABILITÉ PAR RÉGION
============================================================================
Le PHP ne filtrait JAMAIS par région (toutes les directions régionales
partageaient le même patrimoine et la même trésorerie), malgré la colonne
region_id présente sur les tables `patrimoine` et `operations`. Sur
demande explicite, ce portage Python CORRIGE ce point : chaque direction
régionale a maintenant sa propre comptabilité séparée.

Cas particulier — le compte "admin" de démarrage (voir db.py) n'a AUCUNE
région assignée (region_id = NULL) : toutes les fonctions ci-dessous
traitent region_id=None comme une VUE GLOBALE (aucun filtre, on voit tout,
toutes régions confondues), plutôt que "ne rien montrer". C'est pratique
avant que les comptes régionaux n'existent, et cohérent avec le fait
qu'un tel compte n'appartient à aucune direction en particulier.

La table `ecritures` (les lignes débit/crédit) n'a pas de colonne
region_id à elle : la région d'une écriture est toujours celle de
l'opération à laquelle elle est rattachée (jointure sur operations).
============================================================================
"""

from datetime import datetime

from db import get_connection, executer, condition_region

TYPES_DE_BIENS = ["Immobilier", "Véhicule", "Mobilier", "Informatique"]
ETATS_DE_BIEN = ["En usage", "Hors usage", "En rebut"]
TYPES_DE_FLUX = ["Dépense", "Recette"]


def enregistrer_un_bien(type_bien: str, etat: str, nom: str, lieu: str, region_id: int | None) -> dict:
    """Ajoute un bien (matériel, véhicule...) au patrimoine de la région donnée."""
    nom = nom.strip()
    lieu = lieu.strip()
    if type_bien == "" or etat == "" or nom == "" or lieu == "":
        return {"ok": False, "message": "Veuillez remplir tous les champs."}

    conn = get_connection()
    try:
        date = datetime.now().strftime("%Y-%m-%d %H:%M")
        executer(
            conn,
            "INSERT INTO patrimoine (date, type, nom, etat, lieu, region_id) VALUES (?, ?, ?, ?, ?, ?)",
            (date, type_bien, nom, etat, lieu, region_id),
        )
        conn.commit()
        return {"ok": True, "message": "Bien enregistré."}
    finally:
        conn.close()


def lister_patrimoine(region_id: int | None) -> list:
    """Retourne les lignes du patrimoine de la région donnée, les plus récentes en premier."""
    conn = get_connection()
    try:
        clause, parametres = condition_region(region_id)
        return executer(
            conn,
            f"SELECT id, date, type, nom, etat, lieu FROM patrimoine WHERE 1=1{clause} ORDER BY id DESC",
            parametres,
        ).fetchall()
    finally:
        conn.close()


def modifier_bien(bien_id: int, type_bien: str, etat: str, nom: str, lieu: str) -> dict:
    """Met à jour un bien du patrimoine déjà enregistré (voir enregistrer_un_bien pour la création)."""
    nom = nom.strip()
    lieu = lieu.strip()
    if type_bien == "" or etat == "" or nom == "" or lieu == "":
        return {"ok": False, "message": "Veuillez remplir tous les champs."}

    conn = get_connection()
    try:
        executer(
            conn,
            "UPDATE patrimoine SET type = ?, etat = ?, nom = ?, lieu = ? WHERE id = ?",
            (type_bien, etat, nom, lieu, bien_id),
        )
        conn.commit()
        return {"ok": True, "message": "Bien modifié."}
    finally:
        conn.close()


def solde_tresorerie(region_id: int | None) -> float:
    """
    Solde actuel du compte de trésorerie (compte comptable 515) de la
    région donnée, calculé comme la somme des débits moins la somme des
    crédits sur ce compte — c'est le principe de la comptabilité en
    partie double : voir enregistrer_ressource_emploi() ci-dessous pour
    le détail des écritures.
    """
    conn = get_connection()
    try:
        clause, parametres = condition_region(region_id, colonne="operations.region_id")
        ligne = executer(
            conn,
            f"""
            SELECT SUM(ecritures.debit) AS debit, SUM(ecritures.credit) AS credit
            FROM ecritures
            JOIN operations ON ecritures.id_operation = operations.id_operation
            WHERE ecritures.compte = 515{clause}
            """,
            parametres,
        ).fetchone()
        debit = ligne["debit"] or 0
        credit = ligne["credit"] or 0
        return debit - credit
    finally:
        conn.close()


def balance_generale(region_id: int | None) -> tuple[float, float]:
    """
    Total des débits et des crédits de la région donnée, TOUS comptes
    confondus. En partie double, ces deux totaux doivent TOUJOURS être
    égaux : c'est la "balance vérifiée" affichée sur la page. S'ils
    diffèrent, il y a une erreur quelque part dans les écritures.
    """
    conn = get_connection()
    try:
        clause, parametres = condition_region(region_id, colonne="operations.region_id")
        ligne = executer(
            conn,
            f"""
            SELECT SUM(ecritures.debit) AS debit, SUM(ecritures.credit) AS credit
            FROM ecritures
            JOIN operations ON ecritures.id_operation = operations.id_operation
            WHERE 1=1{clause}
            """,
            parametres,
        ).fetchone()
        return (ligne["debit"] or 0, ligne["credit"] or 0)
    finally:
        conn.close()


def lister_journal(region_id: int | None) -> list:
    """Retourne les écritures du journal comptable de la région donnée, les plus récentes en premier."""
    conn = get_connection()
    try:
        clause, parametres = condition_region(region_id, colonne="operations.region_id")
        return executer(
            conn,
            f"""
            SELECT ecritures.id AS id,
                   operations.date AS date,
                   operations.libelle AS libelle,
                   ecritures.compte AS compte,
                   ecritures.debit AS debit,
                   ecritures.credit AS credit
            FROM ecritures
            JOIN operations ON ecritures.id_operation = operations.id_operation
            WHERE 1=1{clause}
            ORDER BY ecritures.id DESC
            """,
            parametres,
        ).fetchall()
    finally:
        conn.close()


def enregistrer_ressource_emploi(libelle: str, type_flux: str, montant: float, region_id: int | None) -> dict:
    """
    Enregistre une dépense ou une recette, et passe AUTOMATIQUEMENT les
    écritures comptables en partie double correspondantes (deux lignes
    "débit"/deux lignes "crédit" qui s'équilibrent toujours).

    ASTUCE — CHANGER LES NUMÉROS DE COMPTE : les numéros 607/401/515/411/706
    sont ceux du plan comptable utilisé par l'application de bureau
    d'origine (607 = achats, 401 = fournisseurs, 515 = trésor public,
    411 = usagers, 706 = prestations de services). Pour les adapter à un
    autre plan comptable, changez simplement ces nombres ci-dessous — le
    reste du calcul (solde, balance) fonctionne avec N'IMPORTE QUEL numéro
    de compte, du moment que chaque écriture est équilibrée (même montant
    en débit d'un côté, en crédit de l'autre).
    """
    libelle = libelle.strip()
    if libelle == "" or montant <= 0:
        return {"ok": False, "message": "Libellé invalide ou montant inférieur ou égal à 0."}

    if type_flux == "Dépense" and montant > solde_tresorerie(region_id):
        return {"ok": False, "message": "Vous ne pouvez pas réaliser cette opération : solde de trésorerie insuffisant."}

    conn = get_connection()
    try:
        date = datetime.now().strftime("%Y-%m-%d %H:%M")

        # RETURNING id_operation : récupère l'identifiant généré par
        # l'INSERT, pour pouvoir relier les écritures à cette opération
        # (fonctionne aussi bien avec SQLite qu'avec PostgreSQL — voir
        # db.py, section "CHANGER DE BASE"). region_id est stocké sur
        # l'opération ; les écritures qui en découlent (ci-dessous)
        # héritent de cette région via la jointure, sans avoir besoin de
        # leur propre colonne region_id.
        ligne = executer(
            conn,
            "INSERT INTO operations (date, libelle, type, montant, region_id) VALUES (?, ?, ?, ?, ?) RETURNING id_operation",
            (date, libelle, type_flux, montant, region_id),
        ).fetchone()
        id_operation = ligne["id_operation"]

        def ecriture(compte: int, debit: float, credit: float) -> None:
            executer(
                conn,
                "INSERT INTO ecritures (id_operation, compte, debit, credit) VALUES (?, ?, ?, ?)",
                (id_operation, compte, debit, credit),
            )

        if type_flux == "Dépense":
            # Étape 1 : reconnaissance de la dette (607 Achat / 401 Fournisseur)
            ecriture(607, montant, 0)
            ecriture(401, 0, montant)
            # Étape 2 : règlement effectif (401 Fournisseur / 515 Trésor Public)
            ecriture(401, montant, 0)
            ecriture(515, 0, montant)
        elif type_flux == "Recette":
            # Étape 1 : constatation de la créance (411 Usager / 706 Prestation)
            ecriture(411, montant, 0)
            ecriture(706, 0, montant)
            # Étape 2 : encaissement effectif (515 Trésor Public / 411 Usager)
            ecriture(515, montant, 0)
            ecriture(411, 0, montant)

        conn.commit()
        return {
            "ok": True,
            "message": f"{type_flux} enregistrée. Les écritures automatisées en partie double ont été passées au journal.",
        }
    finally:
        conn.close()


# ============================================================================
# ASTUCES POUR LE STATISTICIEN
# ============================================================================
# 1. Ajouter une nouvelle catégorie de bien (ex. "Terrain") : ajoutez-la
#    simplement dans la liste TYPES_DE_BIENS tout en haut de ce fichier.
#    Elle apparaîtra automatiquement dans le formulaire (vues/comptabilite.py
#    lit cette liste, il n'y a rien d'autre à modifier).
#
# 2. Comprendre "en partie double" : chaque opération économique est
#    enregistrée DEUX fois — une fois en "débit" sur un compte, une fois
#    en "crédit" sur un autre compte, pour le MÊME montant. C'est ce qui
#    permet de vérifier qu'aucune écriture n'a été oubliée : la somme de
#    tous les débits doit toujours égaler la somme de tous les crédits
#    (voir balance_generale()).
#
# 3. Tester ce fichier sans lancer Streamlit : ouvrez un terminal Python
#    dans le dossier streamlit_app/ et essayez (1 = un identifiant de
#    région existant, ou None pour la vue globale) :
#        from services_comptabilite import enregistrer_un_bien, lister_patrimoine
#        print(enregistrer_un_bien("Informatique", "En usage", "Ordinateur test", "Bureau 3", 1))
#        print(lister_patrimoine(1))
#
# 4. Revenir à une comptabilité UNIQUE partagée entre toutes les régions
#    (comme l'était le PHP) : il suffirait d'appeler chaque fonction avec
#    region_id=None partout dans vues/comptabilite.py — la vue globale
#    (voir plus haut) fait exactement ça.
# ============================================================================
