; Base du KBS : modèle des faits, conversions d'unités, calculs de dose et règle générique d'interaction.
; kbs.py ne fait que traduire le dossier patient en faits : tout le raisonnement est dans les fichiers .clp.

; ---------- Faits créés à partir du dossier patient ----------

; Donnée chiffrée du patient : âge, poids, taille, IMC, surface corporelle ou paramètre biologique
; ex. (data (name "weight_kg") (value 72)), (data (name "Créatinine (sang)") (value 140))
(deftemplate data
  (slot name)
  (slot value))

; Ligne de prescription, numérotée à partir de 0
; quantity : quantité par jour (0 si inconnue), unit : unité de prise, ingredients : nombre de principes actifs
(deftemplate treatment
  (slot line)
  (slot label)
  (slot quantity (default 0))
  (slot unit (default ""))
  (slot ingredients (default 0)))

; Principe actif n° number d'une ligne, ex. dosage 5 et unit "mg" pour « APIXABAN 5 MG »
(deftemplate ingredient
  (slot line)
  (slot number)
  (slot dosage)
  (slot unit))

; Médicament cité sur une ligne : un fait par suite de mots du libellé, en minuscules sans accents
; ex. (prescribed (line 0) (drug "apixaban")) pour « APIXABAN 5 MG (ELIQUIS), CPR »
(deftemplate prescribed
  (slot line)
  (slot drug))

; ---------- Faits déduits par les règles ----------

; Dose en mg par jour d'administration
(deftemplate daily-dose
  (slot line)
  (slot mg))

; Dose en mg/kg par jour d'administration
(deftemplate dose-per-kg
  (slot line)
  (slot mg))

; Alerte pour le pharmacien, avec les lignes de prescription concernées
(deftemplate alert
  (slot message)
  (multislot lines))

; ---------- Calcul des doses ----------

(deftemplate unit-to-mg
  (slot unit)
  (slot factor))

; Unités de prise (milligramme(s)...) et unités de dosage des principes actifs (mg...)
(deffacts units
  (unit-to-mg (unit "milligramme(s)") (factor 1))
  (unit-to-mg (unit "gramme(s)") (factor 1000))
  (unit-to-mg (unit "microgramme(s)") (factor 0.001))
  (unit-to-mg (unit "mg") (factor 1))
  (unit-to-mg (unit "g") (factor 1000))
  (unit-to-mg (unit "ug") (factor 0.001)))

; Unité de prise en masse : 0,7 gramme(s) par jour -> 700 mg
(defrule daily-dose-from-intake-unit
  (treatment (line ?l) (quantity ?q&:(> ?q 0)) (unit ?u))
  (unit-to-mg (unit ?u) (factor ?f))
  =>
  (assert (daily-dose (line ?l) (mg (* ?q ?f)))))

; Sinon, avec un seul principe actif : 2 comprimé(s) de 350 mg par jour -> 700 mg
(defrule daily-dose-from-dosage
  (treatment (line ?l) (quantity ?q&:(> ?q 0)) (unit ?u) (ingredients 1))
  (not (unit-to-mg (unit ?u)))
  (ingredient (line ?l) (dosage ?d) (unit ?du))
  (unit-to-mg (unit ?du) (factor ?f))
  =>
  (assert (daily-dose (line ?l) (mg (* ?q ?d ?f)))))

(defrule dose-per-kg
  (daily-dose (line ?l) (mg ?mg))
  (data (name "weight_kg") (value ?w&:(> ?w 0)))
  =>
  (assert (dose-per-kg (line ?l) (mg (/ ?mg ?w)))))

; ---------- Interactions (faits de generic_rules.clp) ----------

; Interaction entre un médicament du groupe a et un médicament du groupe b
(deftemplate interaction
  (slot title)
  (slot level (default ""))
  (multislot drugs-a)
  (multislot drugs-b)
  (slot alert))

; Les deux médicaments doivent être sur des lignes distinctes : une association fixe ne déclenche rien.
; Priorité basse pour que les alertes des règles personnalisées soient listées en premier.
(defrule drug-interaction
  (declare (salience -10))
  (interaction (drugs-a $? ?a $?) (drugs-b $? ?b $?) (alert ?message))
  (prescribed (line ?la) (drug ?a))
  (prescribed (line ?lb&~?la) (drug ?b))
  =>
  (assert (alert (message ?message) (lines ?la ?lb))))
