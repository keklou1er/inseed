"""
vues/ihpc.py — IHPC (Indice Harmonisé des Prix à la Consommation) : vente,
règlement de dette, recherche de solde.

============================================================================
D'OÙ VIENT CETTE PAGE ?
============================================================================
Portage de web/ihpc.php. Les trois boutons "Vente" / "Règlement" /
"Recherche de solde" du PHP (voir assets/app.js::selectionnerFormulaire)
deviennent st.tabs() ci-dessous, comme pour vues/comptabilite.py.

============================================================================
PHP → STREAMLIT : LE "PANIER" DE VENTE EN COURS ($_SESSION['vente'])
============================================================================
Une vente se déroule en PLUSIEURS étapes : d'abord on identifie le vendeur
(avec son mot de passe), puis on ajoute une ou plusieurs lignes de produits
au panier, puis on valide la vente entière d'un coup. Le PHP gardait ce
panier "en cours de construction" dans $_SESSION['vente'] entre chaque
rechargement de page. L'équivalent Streamlit est
st.session_state["vente_en_cours"] : un dictionnaire qui survit d'un
rerun à l'autre, tant que l'onglet du navigateur reste ouvert.

⚠️ DIFFÉRENCE VOULUE PAR RAPPORT AU PHP : vendeurs, marchés, acheteurs,
produits, transactions et recherches de solde sont maintenant isolés par
région (voir services_ihpc.py, section "ISOLATION PAR RÉGION").
============================================================================
"""

import pandas as pd
import streamlit as st

from auth import exiger_connexion, utilisateur_connecte, region_actuelle
from ui_helpers import flash, afficher_flash, fmt_montant
from services_ihpc import (
    lister_vendeurs,
    lister_marches,
    lister_acheteurs,
    lister_produits,
    valider_ou_creer_vendeur,
    authentifier_vendeur,
    enregistrer_marche,
    enregistrer_acheteur,
    enregistrer_produit,
    solde_compte,
    enregistrer_paiement_dette,
    enregistrer_vente,
    lister_transactions,
)

exiger_connexion()
afficher_flash()

region_id = utilisateur_connecte()["region_id"]
region = region_actuelle()

st.title("📊 IHPC / Indice des prix")
st.caption(f"Région : {region['nom']}" if region else "Vue globale (toutes régions) — compte sans région assignée")

if "vente_en_cours" not in st.session_state:
    st.session_state["vente_en_cours"] = None

onglet_vente, onglet_reglement, onglet_recherche = st.tabs(
    ["🧺 Vente", "💳 Règlement", "🔍 Recherche de solde"]
)

# ----------------------------------------------------------------------
# Onglet 1 : Vente (identification du vendeur, puis panier de produits)
# ----------------------------------------------------------------------
with onglet_vente:
    vente = st.session_state["vente_en_cours"]

    if vente is None:
        st.subheader("Formulaire des tiers")
        # Les listes ci-dessous sont juste des SUGGESTIONS (comme le
        # <datalist> du PHP) : on peut toujours taper un nom nouveau,
        # ce qui crée automatiquement le vendeur/marché/acheteur.
        st.caption(
            "Vendeurs connus : " + (", ".join(lister_vendeurs(region_id)) or "aucun pour l'instant")
        )
        with st.form("formulaire_tiers", clear_on_submit=True):
            vendeur = st.text_input("Vendeur :", placeholder="saisir ici le nom du vendeur")
            motdepasse = st.text_input(
                "Mot de passe :", type="password", placeholder="créer ici le mot de passe"
            )
            marche = st.text_input("Marché :", placeholder="saisir ici le nom du marché")
            acheteur = st.text_input("Acheteur :", placeholder="saisir ici le nom de l'acheteur")
            envoye = st.form_submit_button("Valider le vendeur")

        if envoye:
            res_agent = valider_ou_creer_vendeur(vendeur, motdepasse, region_id)
            if not res_agent["ok"]:
                flash("error", res_agent["message"])
            elif marche.strip() == "" or acheteur.strip() == "":
                flash("error", "Veuillez renseigner le marché et l'acheteur.")
            else:
                enregistrer_marche(marche, region_id)
                enregistrer_acheteur(acheteur, region_id)
                st.session_state["vente_en_cours"] = {
                    "agent": vendeur.strip(),
                    "marche": marche.strip(),
                    "acheteur": acheteur.strip(),
                    "lignes": [],
                }
                flash("info", "Vendeur validé. Ajoutez les produits vendus.")
            st.rerun()

    else:
        colonne_info, colonne_bouton = st.columns([4, 1])
        with colonne_info:
            st.markdown(
                f"Vendeur : **{vente['agent']}** — Marché : **{vente['marche']}** — Acheteur : **{vente['acheteur']}**"
            )
        with colonne_bouton:
            if st.button("Changer de vendeur"):
                st.session_state["vente_en_cours"] = None
                st.rerun()

        total_panier = sum(l["montant"] for l in vente["lignes"])
        st.subheader(f"Montant à payer : {fmt_montant(total_panier)} FCFA")

        st.caption(
            "Produits connus : " + (", ".join(lister_produits(region_id)) or "aucun pour l'instant")
        )
        with st.form("formulaire_ligne", clear_on_submit=True):
            colonne_produit, colonne_qte, colonne_prix = st.columns(3)
            with colonne_produit:
                produit = st.text_input("Produit :", placeholder="nom du produit")
            with colonne_qte:
                # max_value=3 : règle métier reprise du PHP (max="3") — voir astuce 1 de services_ihpc.py.
                quantite = st.number_input("Quantité :", min_value=1, max_value=3, step=1, value=1)
            with colonne_prix:
                prix = st.number_input("Prix unitaire :", min_value=0.01, step=1.0, format="%.2f")
            ajouter = st.form_submit_button("Ajouter au panier")

        if ajouter:
            if produit.strip() == "" or any(c.isdigit() for c in produit):
                flash("error", "Le nom du produit ne peut pas être vide ni contenir de chiffres.")
            else:
                resultat_produit = enregistrer_produit(produit, region_id)
                if not resultat_produit["ok"]:
                    flash("error", resultat_produit["message"])
                else:
                    vente["lignes"].append(
                        {
                            "vendeur": vente["agent"],
                            "marche": vente["marche"],
                            "acheteur": vente["acheteur"],
                            "produit": produit.strip(),
                            "quantite": int(quantite),
                            "prix": float(prix),
                            "montant": int(quantite) * float(prix),
                        }
                    )
                    st.session_state["vente_en_cours"] = vente
            st.rerun()

        if vente["lignes"]:
            df_panier = pd.DataFrame(vente["lignes"])[["produit", "quantite", "prix", "montant"]].rename(
                columns={"produit": "Produit", "quantite": "Quantité", "prix": "Prix unitaire", "montant": "Montant"}
            )
            st.dataframe(df_panier, use_container_width=True, hide_index=True)

        with st.form("formulaire_valider_vente"):
            montant_verse = st.number_input("Montant versé :", min_value=0.0, step=1.0, format="%.2f")
            valider = st.form_submit_button("Enregistrer la vente")

        if valider:
            resultat = enregistrer_vente(vente["agent"], vente["lignes"], float(montant_verse), region_id)
            flash("info" if resultat["ok"] else "error", resultat["message"])
            if resultat["ok"]:
                st.session_state["vente_en_cours"] = None
            st.rerun()

# ----------------------------------------------------------------------
# Onglet 2 : Règlement d'une dette existante
# ----------------------------------------------------------------------
with onglet_reglement:
    st.subheader("Règlement")
    with st.form("formulaire_reglement", clear_on_submit=True):
        creancier_r = st.text_input("Créancier :", placeholder="saisir ici le nom du créancier")
        motdepasse_r = st.text_input("Mot de passe :", type="password")
        debiteur_r = st.text_input("Débiteur :", placeholder="saisir ici le nom du débiteur")
        montant_reglement = st.number_input("Montant :", min_value=0.0, step=1.0, format="%.2f")
        envoye_reglement = st.form_submit_button("Enregistrer")

    if envoye_reglement:
        auth = authentifier_vendeur(creancier_r, motdepasse_r, region_id)
        if not auth["ok"]:
            flash("error", auth["message"])
        else:
            resultat = enregistrer_paiement_dette(creancier_r, debiteur_r, float(montant_reglement), region_id)
            flash("info" if resultat["ok"] else "error", resultat["message"])
        st.rerun()

# ----------------------------------------------------------------------
# Onglet 3 : Recherche de solde (créancier ↔ débiteur)
# ----------------------------------------------------------------------
with onglet_recherche:
    st.subheader("Recherche de solde")
    with st.form("formulaire_recherche_solde", clear_on_submit=True):
        creancier = st.text_input("Créancier recherché :", placeholder="saisir ici le nom du créancier recherché")
        motdepasse = st.text_input("Mot de passe :", type="password")
        debiteur = st.text_input("Débiteur recherché :", placeholder="saisir ici le nom du débiteur recherché")
        envoye_recherche = st.form_submit_button("Voir le solde")

    if envoye_recherche:
        auth = authentifier_vendeur(creancier, motdepasse, region_id)
        if not auth["ok"]:
            flash("error", auth["message"])
        else:
            solde = solde_compte(creancier.strip(), debiteur.strip(), region_id)
            if not solde["ok"]:
                flash("error", solde["message"])
            else:
                flash(
                    "info",
                    f"Le solde du compte {solde['debiteur']} auprès de {solde['creancier']} est de "
                    f"{fmt_montant(solde['solde'])} FCFA",
                )
        st.rerun()

st.divider()

# ----------------------------------------------------------------------
# Tableau des transactions (achats + règlements de dette)
# ----------------------------------------------------------------------
st.subheader("Transactions")
lignes = lister_transactions(region_id)
if not lignes:
    st.caption("Aucune transaction enregistrée pour le moment.")
else:
    df = pd.DataFrame([dict(l) for l in lignes]).rename(
        columns={
            "date_du_jour": "Date",
            "fournisseur": "Fournisseur",
            "marche": "Marché",
            "client": "Client",
            "produit": "Produit",
            "quantites": "Quantité",
            "prix": "Prix unitaire",
            "montant": "Montant",
            "payer": "Somme versée",
        }
    )
    st.dataframe(df, use_container_width=True, hide_index=True)

# ============================================================================
# ASTUCES POUR LE STATISTICIEN
# ============================================================================
# 1. "Vendeurs/Produits connus" affichés en st.caption() au-dessus des
#    formulaires : c'est l'équivalent simplifié du <datalist> HTML du PHP
#    (qui proposait une auto-complétion dans le champ texte). Streamlit
#    n'a pas de widget natif "texte + suggestions déroulantes" ; afficher
#    la liste juste au-dessus reste simple à comprendre pour un
#    statisticien et à modifier (pas de composant tiers à installer).
#
# 2. Le mot de passe du vendeur SERT UNIQUEMENT à retrouver/protéger sa
#    fiche vendeur (éviter qu'un autre agent ne vende "au nom de" un
#    vendeur existant par erreur) — ce n'est PAS un compte de connexion à
#    l'application (voir la note de sécurité en haut de services_ihpc.py).
#
# 3. Tester ce fichier sans lancer Streamlit : voir les astuces en bas de
#    services_ihpc.py.
# ============================================================================
