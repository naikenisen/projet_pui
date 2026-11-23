; Statistical rules: situations in which the pharmacists of the hospital often make a pharmaceutical intervention (IP).
; Built from preprocessing/ip.json: situations with at least 20 patients with an IP on the theme
; and an IP on the theme for at least 4 % of the treated patients.
; These alerts report no problem: they ask the LLM to look more carefully at the drugs involved.

; Frequent IP situation: one of the drugs of the list is prescribed
(deftemplate risk-situation
  (multislot drugs)
  (slot alert))

(deffacts statistical-risk-situations
  (risk-situation
    (drugs "apixaban" "rivaroxaban" "dabigatran" "edoxaban" "fluindione" "warfarine" "acenocoumarol")
    (alert "Patient à risque : anticoagulant oral, situation fréquente d'IP (9 % des patients traités)"))
  (risk-situation
    (drugs "colchicine" "allopurinol" "febuxostat")
    (alert "Patient à risque : traitement de la goutte, situation fréquente d'IP (11 % des patients traités)"))
  (risk-situation
    (drugs "omeprazole" "esomeprazole" "pantoprazole" "lansoprazole" "rabeprazole")
    (alert "Patient à risque : inhibiteur de la pompe à protons, situation fréquente d'IP (7 % des patients traités)"))
  (risk-situation
    (drugs "atorvastatine" "rosuvastatine" "simvastatine" "pravastatine" "fluvastatine")
    (alert "Patient à risque : statine, situation fréquente d'IP (6 % des patients traités)"))
  (risk-situation
    (drugs "levothyroxine")
    (alert "Patient à risque : lévothyroxine, situation fréquente d'IP (6 % des patients traités)"))
  (risk-situation
    (drugs "sertraline" "paroxetine" "escitalopram" "citalopram" "fluoxetine" "venlafaxine" "duloxetine" "milnacipran"
           "mirtazapine" "mianserine" "vortioxetine" "tianeptine" "amitriptyline" "clomipramine")
    (alert "Patient à risque : antidépresseur, situation fréquente d'IP (5 % des patients traités)"))
  (risk-situation
    (drugs "insuline" "metformine" "gliclazide" "glimepiride" "repaglinide" "sitagliptine" "vildagliptine"
           "dapagliflozine" "empagliflozine" "canagliflozine" "dulaglutide" "liraglutide" "semaglutide")
    (alert "Patient à risque : antidiabétique, situation fréquente d'IP (5 % des patients traités)"))
  (risk-situation
    (drugs "silodosine" "tamsulosine" "alfuzosine" "doxazosine" "dutasteride" "finasteride")
    (alert "Patient à risque : traitement urologique (alpha-bloquant, inhibiteur de la 5-alpha-réductase), situation fréquente d'IP (5 % des patients traités)")))

; Low priority so these alerts are listed after the other rules
(defrule statistical-risk-drug
  (declare (salience -20))
  (risk-situation (drugs $? ?drug $?) (alert ?message))
  (prescribed (line ?line) (drug ?drug))
  =>
  (assert (alert (message ?message) (lines ?line))))

; Vitamin D deficiency: IP for 5 % of the patients below 75 nmol/L (often an untreated deficiency)
(defrule statistical-risk-vitamin-d
  (declare (salience -20))
  (data (name "25-OH-Vitamine D") (value ?value&:(< ?value 75)))
  =>
  (assert (alert (message "Patient à risque : 25-OH-vitamine D inférieure à 75 nmol/L, situation fréquente d'IP (5 % des patients concernés)"))))
