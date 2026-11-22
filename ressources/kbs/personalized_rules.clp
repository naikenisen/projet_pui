; Apixaban : dose réduite si au moins 2 critères parmi âge, poids et créatinine
(defrule apixaban-criterion-age
  (data (name "age") (value ?v&:(>= ?v 80)))
  =>
  (assert (apixaban-criterion age)))
(defrule apixaban-criterion-weight
  (data (name "weight_kg") (value ?v&:(<= ?v 60)))
  =>
  (assert (apixaban-criterion weight)))
(defrule apixaban-criterion-creatinine
  (data (name "Créatinine (sang)") (value ?v&:(>= ?v 133)))
  =>
  (assert (apixaban-criterion creatinine)))
(defrule apixaban-dose
  (prescribed (line ?l) (drug "apixaban"))
  (ingredient (line ?l) (dosage ?d&:(<> ?d 2.5)))
  (apixaban-criterion ?c1)
  (apixaban-criterion ?c2&~?c1)
  =>
  (assert (alert (message "Apixaban : la dose recommandée est 2,5 mg deux fois par jour (au moins 2 critères parmi âge ≥ 80 ans, poids ≤ 60 kg, créatinine ≥ 133 µmol/L)") (lines ?l))))

; Ramipril + spironolactone : risque d'hyperkaliémie
(defrule ramipril-spironolactone
  (prescribed (line ?l1) (drug "ramipril"))
  (prescribed (line ?l2&~?l1) (drug "spironolactone"))
  =>
  (assert (alert (message "Interaction ramipril + spironolactone : risque d'hyperkaliémie, surveiller la kaliémie") (lines ?l1 ?l2))))

; Daptomycine : posologie inférieure à 10 mg/kg/jour
(defrule daptomycine-dose
  (prescribed (line ?l) (drug "daptomycine"))
  (dose-per-kg (line ?l) (mg ?mg&:(< ?mg 10)))
  =>
  (assert (alert (message "Daptomycine : la posologie recommandée est désormais de 10 mg/kg/jour ; la dose prescrite est inférieure (ex : 8 mg/kg/jour), à réévaluer et adapter au poids du patient") (lines ?l))))
