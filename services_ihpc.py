"""
services_ihpc.py — Logique métier du module IHPC (Indice Harmonisé des Prix
à la Consommation) : validation des vendeurs, panier de vente, règlement de
dette, recherche de solde.

============================================================================
D'OÙ VIENT CE FICHIER ?
============================================================================
Portage de la partie "2. LOGIQUE IHPC" de web/services.php
(ValiderOuCreerVendeur, AuthentifierVendeur, EnregistrerMarche,
EnregistrerAcheteur, EnregistrerProduit, SoldeCompte,
EnregistrerPaiementDette, EnregistrerVente) + des fonctions de listing de
web/models.php (ListerLesVendeurs, ListerLesMarches, ListerLesAcheteurs,
ListerLesProduits, MotDePasseVendeur, AjoutDeVendeur, AjoutDeMarche,
AjoutDeLAcheteur, AjoutDeProduit).

============================================================================
⚠️ DEUX DIFFÉRENCES VOULUES PAR RAPPORT AU PHP :
============================================================================
1. MOT DE PASSE DU VENDEUR STOCKÉ EN CLAIR EN PHP → HACHÉ ICI.
   Le PHP original stockait le mot de passe du vendeur tel quel (colonne
   `motdepass`, comparaison `$motdepasseAttendu !== $motdepasse`). La
   table `vendeurs` de ce portage (voir db.py) a été nommée
   `motdepasse_hash` dès le départ : ce fichier utilise donc
   hacher_mot_de_passe()/verifier_mot_de_passe() (les mêmes fonctions que
   pour les comptes utilisateurs, voir auth.py) plutôt que de comparer le
   mot de passe en clair. Note : ce "mot de passe vendeur" reste un
   simple frein contre les erreurs de saisie sur le terrain (pas un vrai
   compte protégé) — voir la remarque du PHP original.

2. ISOLATION PAR RÉGION (comme Comptabilité et Secrétariat).
   Le PHP ne filtrait JAMAIS par région. Ici, vendeurs, marchés,
   acheteurs, produits, transactions et recherches de solde sont limités
   à la région de l'utilisateur connecté (region_id=None → vue globale,
   voir condition_region() dans db.py).

============================================================================
LA RECHERCHE "APPROXIMATIVE" (LIKE '%...%') EST VOULUE, PAS UN BUG
============================================================================
Le PHP retrouve un vendeur/acheteur par un SELECT ... LIKE '%nom saisi%'
plutôt qu'une égalité stricte : un agent peut donc taper juste une partie
du nom pour retrouver un vendeur déjà connu. Ce comportement est reproduit
à l'identique ci-dessous.
============================================================================
"""

from datetime import datetime

from auth import hacher_mot_de_passe, verifier_mot_de_passe
from db import get_connection, executer, condition_region


# ----------------------------------------------------------------------
# 1. LISTES (vendeurs/marchés/acheteurs/produits connus, pour les
#    suggestions affichées dans vues/ihpc.py)
# ----------------------------------------------------------------------
def lister_vendeurs(region_id: int | None) -> list[str]:
    conn = get_connection()
    try:
        clause, parametres = condition_region(region_id)
        lignes = executer(
            conn, f"SELECT fournisseur FROM vendeurs WHERE 1=1{clause} ORDER BY fournisseur", parametres
        ).fetchall()
        return [l["fournisseur"] for l in lignes]
    finally:
        conn.close()


def lister_marches(region_id: int | None) -> list[str]:
    conn = get_connection()
    try:
        clause, parametres = condition_region(region_id)
        lignes = executer(conn, f"SELECT marche FROM marches WHERE 1=1{clause} ORDER BY marche", parametres).fetchall()
        return [l["marche"] for l in lignes]
    finally:
        conn.close()


def lister_acheteurs(region_id: int | None) -> list[str]:
    conn = get_connection()
    try:
        clause, parametres = condition_region(region_id)
        lignes = executer(conn, f"SELECT client FROM acheteurs WHERE 1=1{clause} ORDER BY client", parametres).fetchall()
        return [l["client"] for l in lignes]
    finally:
        conn.close()


def lister_produits(region_id: int | None) -> list[str]:
    conn = get_connection()
    try:
        clause, parametres = condition_region(region_id)
        lignes = executer(conn, f"SELECT produit FROM produits WHERE 1=1{clause} ORDER BY produit", parametres).fetchall()
        return [l["produit"] for l in lignes]
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 2. VENDEUR : validation/inscription, authentification
# ----------------------------------------------------------------------
def _mot_de_passe_hash_vendeur(nom_approchant: str, region_id: int | None) -> str | None:
    conn = get_connection()
    try:
        clause, parametres = condition_region(region_id)
        ligne = executer(
            conn,
            f"SELECT motdepasse_hash FROM vendeurs WHERE fournisseur LIKE ?{clause} LIMIT 1",
            ("%" + nom_approchant + "%",) + parametres,
        ).fetchone()
        return None if ligne is None else ligne["motdepasse_hash"]
    finally:
        conn.close()


def valider_ou_creer_vendeur(nom: str, motdepasse: str, region_id: int | None) -> dict:
    """
    Si le vendeur existe déjà (recherche approximative par nom), vérifie
    son mot de passe. Sinon, l'inscrit avec ce mot de passe (première
    vente de ce vendeur = création automatique de son compte).
    """
    nom_saisi = nom.strip()
    if any(caractere.isdigit() for caractere in nom):
        return {"ok": False, "message": "Le nom ne peut pas contenir de chiffres."}
    if nom_saisi == "":
        return {"ok": False, "message": "Le nom ne peut pas être vide."}
    if motdepasse == "":
        return {"ok": False, "message": "Le mot de passe ne peut pas être vide."}

    hash_attendu = _mot_de_passe_hash_vendeur(nom, region_id)
    if hash_attendu is not None:
        if not verifier_mot_de_passe(motdepasse, hash_attendu):
            return {"ok": False, "message": "Mot de passe incorrect ; veuillez réessayer."}
        return {"ok": True, "message": "", "nouveau": False}

    conn = get_connection()
    try:
        executer(
            conn,
            "INSERT INTO vendeurs (fournisseur, motdepasse_hash, region_id) VALUES (?, ?, ?)",
            (nom_saisi, hacher_mot_de_passe(motdepasse), region_id),
        )
        conn.commit()
        return {"ok": True, "message": "", "nouveau": True}
    finally:
        conn.close()


def authentifier_vendeur(nom: str, motdepasse: str, region_id: int | None) -> dict:
    nom_saisi = nom.strip()
    if nom_saisi == "":
        return {"ok": False, "message": "Le nom du créancier ne peut pas être vide."}
    hash_attendu = _mot_de_passe_hash_vendeur(nom, region_id)
    if hash_attendu is None:
        return {"ok": False, "message": "Ce vendeur est introuvable."}
    if not verifier_mot_de_passe(motdepasse, hash_attendu):
        return {"ok": False, "message": "Mot de passe incorrect."}
    return {"ok": True, "message": ""}


# ----------------------------------------------------------------------
# 3. MARCHÉ / ACHETEUR / PRODUIT : enregistrement "si nouveau seulement"
# ----------------------------------------------------------------------
def enregistrer_marche(marche: str, region_id: int | None) -> dict:
    nom = marche.strip()
    if nom == "":
        return {"ok": False, "message": "Le nom du marché ne peut pas être vide."}
    if nom in lister_marches(region_id):
        return {"ok": True, "message": "Ce marché existe déjà."}
    conn = get_connection()
    try:
        executer(conn, "INSERT INTO marches (marche, region_id) VALUES (?, ?)", (nom, region_id))
        conn.commit()
        return {"ok": True, "message": "Marché enregistré."}
    finally:
        conn.close()


def enregistrer_acheteur(client: str, region_id: int | None) -> dict:
    nom = client.strip()
    if any(caractere.isdigit() for caractere in client):
        return {"ok": False, "message": "Le nom de l'acheteur ne peut pas contenir de chiffres."}
    if nom == "":
        return {"ok": False, "message": "Le nom de l'acheteur ne peut pas être vide."}
    if nom in lister_acheteurs(region_id):
        return {"ok": True, "message": "Cet acheteur existe déjà."}
    conn = get_connection()
    try:
        executer(conn, "INSERT INTO acheteurs (client, region_id) VALUES (?, ?)", (nom, region_id))
        conn.commit()
        return {"ok": True, "message": "Acheteur enregistré."}
    finally:
        conn.close()


def enregistrer_produit(produit: str, region_id: int | None) -> dict:
    nom = produit.strip()
    if any(caractere.isdigit() for caractere in produit):
        return {"ok": False, "message": "Le nom du produit ne peut pas contenir de chiffres."}
    if nom == "":
        return {"ok": False, "message": "Le nom du produit ne peut pas être vide."}
    if nom in lister_produits(region_id):
        return {"ok": True, "message": "Ce produit existe déjà."}
    conn = get_connection()
    try:
        executer(conn, "INSERT INTO produits (produit, region_id) VALUES (?, ?)", (nom, region_id))
        conn.commit()
        return {"ok": True, "message": "Produit enregistré."}
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 4. SOLDE / RÈGLEMENT / VENTE
# ----------------------------------------------------------------------
def solde_compte(creancier_saisi: str, debiteur_saisi: str, region_id: int | None) -> dict:
    """
    Retrouve le vendeur/acheteur par recherche approximative dans
    l'historique des transactions, puis calcule solde = total des ventes
    - total déjà payé, pour ce couple précis.
    """
    conn = get_connection()
    try:
        clause, parametres = condition_region(region_id)

        ligne = executer(
            conn,
            f"SELECT fournisseur FROM transactions_ihpc WHERE fournisseur LIKE ?{clause} LIMIT 1",
            ("%" + creancier_saisi + "%",) + parametres,
        ).fetchone()
        if ligne is None:
            return {"ok": False, "message": f"Le vendeur {creancier_saisi} n'a encore effectué de vente."}
        fournisseur = ligne["fournisseur"]

        ligne = executer(
            conn,
            f"SELECT client FROM transactions_ihpc WHERE client LIKE ?{clause} LIMIT 1",
            ("%" + debiteur_saisi + "%",) + parametres,
        ).fetchone()
        if ligne is None:
            return {"ok": False, "message": f"L'acheteur {debiteur_saisi} n'a encore effectué d'achat."}
        client = ligne["client"]

        ligne = executer(
            conn,
            "SELECT SUM(montant) AS montant, SUM(payer) AS payer FROM transactions_ihpc WHERE fournisseur = ? AND client = ?",
            (fournisseur, client),
        ).fetchone()
        montant = ligne["montant"] or 0
        payer = ligne["payer"] or 0

        return {"ok": True, "creancier": fournisseur, "debiteur": client, "solde": montant - payer}
    finally:
        conn.close()


def enregistrer_paiement_dette(creancier: str, debiteur: str, montant: float, region_id: int | None) -> dict:
    creancier_saisi = creancier.strip()
    debiteur_saisi = debiteur.strip()
    if creancier_saisi == "" or debiteur_saisi == "":
        return {"ok": False, "message": "Veuillez renseigner le créancier et le débiteur."}
    if montant <= 0:
        return {"ok": False, "message": "Le montant du règlement doit être positif."}

    solde = solde_compte(creancier_saisi, debiteur_saisi, region_id)
    if not solde["ok"]:
        return solde
    if montant > solde["solde"]:
        solde_fmt = f"{solde['solde']:,.0f}".replace(",", " ")
        return {"ok": False, "message": f"Le règlement ne peut pas dépasser {solde_fmt} FCFA."}

    conn = get_connection()
    try:
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        executer(
            conn,
            """
            INSERT INTO transactions_ihpc (date_du_jour, fournisseur, marche, client, produit, quantites, prix, montant, payer, region_id)
            VALUES (?, ?, '', ?, '', 0, 0, 0, ?, ?)
            """,
            (date, creancier_saisi, debiteur_saisi, montant, region_id),
        )
        conn.commit()
        return {"ok": True, "message": "Règlement enregistré."}
    finally:
        conn.close()


def enregistrer_vente(agent: str, lignes_panier: list[dict], montant_verse: float, region_id: int | None) -> dict:
    """
    Enregistre toutes les lignes du panier comme autant de transactions,
    puis une ligne récapitulative dans la "comptabilité IHPC" (revente =
    somme des lignes vendues ce jour, pour cet agent).
    """
    if not lignes_panier:
        return {"ok": False, "message": "Le panier est vide."}
    total_panier = sum(ligne["montant"] for ligne in lignes_panier)
    if montant_verse > total_panier:
        total_fmt = f"{total_panier:,.0f}".replace(",", " ")
        return {"ok": False, "message": f"Le montant à payer ne peut dépasser {total_fmt} FCFA."}

    conn = get_connection()
    try:
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        revente = 0.0
        for ligne in lignes_panier:
            executer(
                conn,
                """
                INSERT INTO transactions_ihpc (date_du_jour, fournisseur, marche, client, produit, quantites, prix, montant, payer, region_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    date,
                    ligne["vendeur"],
                    ligne["marche"],
                    ligne["acheteur"],
                    ligne["produit"],
                    ligne["quantite"],
                    ligne["prix"],
                    ligne["montant"],
                    region_id,
                ),
            )
            revente += float(ligne["montant"])

        executer(
            conn,
            """
            INSERT INTO comptabilite_ihpc (date_du_jour, agent, montant, revente, depense, relicat, impaye, region_id)
            VALUES (?, ?, 0, ?, 0, 0, 0, ?)
            """,
            (date, agent, revente, region_id),
        )
        conn.commit()
        return {"ok": True, "message": "Vente enregistrée."}
    finally:
        conn.close()


def lister_transactions(region_id: int | None, limite: int = 200) -> list:
    """Les 200 dernières transactions (achats + règlements de dette), les plus récentes en premier."""
    conn = get_connection()
    try:
        clause, parametres = condition_region(region_id)
        return executer(
            conn,
            f"""
            SELECT date_du_jour, fournisseur, marche, client, produit, quantites, prix, montant, payer
            FROM transactions_ihpc
            WHERE 1=1{clause}
            ORDER BY id DESC
            LIMIT {int(limite)}
            """,
            parametres,
        ).fetchall()
    finally:
        conn.close()


# ============================================================================
# ASTUCES POUR LE STATISTICIEN
# ============================================================================
# 1. La quantité est volontairement limitée à 3 (voir vues/ihpc.py,
#    st.number_input(..., max_value=3)) : c'est une règle métier reprise
#    telle quelle du formulaire PHP (max="3"), pas une limite technique.
#    Pour l'augmenter, changez juste ce max_value dans vues/ihpc.py.
#
# 2. Pourquoi le "panier" (lignes_panier) n'est-il pas dans la base de
#    données tant que la vente n'est pas validée ? Comme en PHP
#    ($_SESSION['vente']), c'est un état TEMPORAIRE propre à la session
#    du navigateur : st.session_state["vente_en_cours"] (voir
#    vues/ihpc.py) joue exactement le même rôle. Rien n'est écrit en
#    base tant que "Enregistrer la vente" n'a pas été cliqué.
#
# 3. Tester ce fichier sans lancer Streamlit :
#        from services_ihpc import valider_ou_creer_vendeur, lister_vendeurs
#        print(valider_ou_creer_vendeur("Kodjo", "1234", 1))
#        print(lister_vendeurs(1))
# ============================================================================
