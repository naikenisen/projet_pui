; KBS base: fact templates, unit conversions, dose computations and generic interaction rule.
; kbs.py only translates the patient record into facts: all the reasoning is in the .clp files.

; ---------- Facts created from the patient record ----------

; Numeric patient data: age, weight, height, BMI, body surface area or lab parameter
; e.g. (data (name "weight_kg") (value 72)), (data (name "Créatinine (sang)") (value 140))
(deftemplate data
  (slot name)
  (slot value))

; Date on which the prescription is analysed, e.g. (reference-date (date "2026-08-15"))
(deftemplate reference-date
  (slot date))

; Prescription line, numbered from 0
; name: label before the strength, e.g. "IRBESARTAN" for "IRBESARTAN 150 MG (LABO ARROW), CPR"
; quantity: quantity per day (0 if unknown), unit: intake unit, ingredients: number of active ingredients
; start and end: dates "YYYY-MM-DD" ("" if unknown)
(deftemplate treatment
  (slot line)
  (slot label)
  (slot name (default ""))
  (slot quantity (default 0))
  (slot unit (default ""))
  (slot ingredients (default 0))
  (slot start (default ""))
  (slot end (default ""))
  (slot as_needed (default FALSE)))

; Active ingredient number <number> of a line, e.g. dosage 5 and unit "mg" for "APIXABAN 5 MG"
(deftemplate ingredient
  (slot line)
  (slot number)
  (slot dosage)
  (slot unit))

; Drug cited on a line: one fact per word sequence of the label, lowercase without accents
; e.g. (prescribed (line 0) (drug "apixaban")) for "APIXABAN 5 MG (ELIQUIS), CPR"
(deftemplate prescribed
  (slot line)
  (slot drug))

; ---------- Facts deduced by the rules ----------

; Status of a line on the reference date: "ongoing", "ended" or "upcoming"
(deftemplate line-status
  (slot line)
  (slot status))

; Scheduled line ongoing on the reference date
(deftemplate ongoing-line
  (slot line)
  (slot name))

; Active ingredient dose per administration day, e.g. (line-dose (line 0) (amount 3000) (unit "mg"))
; unit: "mg", "µg", "IU", "anti-Xa IU" or "U"
(deftemplate line-dose
  (slot line)
  (slot amount)
  (slot unit))

; Dose in mg per administration day
(deftemplate daily-dose
  (slot line)
  (slot mg))

; Dose in mg/kg per administration day
(deftemplate dose-per-kg
  (slot line)
  (slot mg))

; Alert for the pharmacist, with the prescription lines involved
(deftemplate alert
  (slot message)
  (multislot lines))

; ---------- Line status ----------

; Dates "YYYY-MM-DD" compare as strings
(defrule line-upcoming
  (reference-date (date ?today))
  (treatment (line ?l) (start ?s&:(> (str-compare ?s ?today) 0)))
  =>
  (assert (line-status (line ?l) (status "upcoming"))))

(defrule line-ended
  (reference-date (date ?today))
  (treatment (line ?l) (start ?s&:(<= (str-compare ?s ?today) 0)) (end ?e&~""&:(< (str-compare ?e ?today) 0)))
  =>
  (assert (line-status (line ?l) (status "ended"))))

(defrule line-ongoing
  (reference-date (date ?today))
  (treatment (line ?l) (start ?s&:(<= (str-compare ?s ?today) 0)) (end ?e&:(or (eq ?e "") (>= (str-compare ?e ?today) 0))))
  =>
  (assert (line-status (line ?l) (status "ongoing"))))

; Without a reference date, every line is considered ongoing
(defrule line-ongoing-without-reference-date
  (not (reference-date))
  (treatment (line ?l))
  =>
  (assert (line-status (line ?l) (status "ongoing"))))

; ---------- Dose computation ----------

(deftemplate unit-conversion
  (slot unit)
  (slot factor)
  (slot symbol))

; Intake units that are already an amount of active ingredient (milligramme(s)...)
; and active ingredient dosage units (mg...)
(deffacts units
  (unit-conversion (unit "milligramme(s)") (factor 1) (symbol "mg"))
  (unit-conversion (unit "gramme(s)") (factor 1000) (symbol "mg"))
  (unit-conversion (unit "microgramme(s)") (factor 1) (symbol "µg"))
  (unit-conversion (unit "unité(s) internationale(s)") (factor 1) (symbol "IU"))
  (unit-conversion (unit "unité(s) internationale(s) anti-Xa") (factor 1) (symbol "anti-Xa IU"))
  (unit-conversion (unit "mg") (factor 1) (symbol "mg"))
  (unit-conversion (unit "g") (factor 1000) (symbol "mg"))
  (unit-conversion (unit "ug") (factor 1) (symbol "µg"))
  (unit-conversion (unit "iu") (factor 1) (symbol "IU"))
  (unit-conversion (unit "axa_iu") (factor 1) (symbol "anti-Xa IU"))
  (unit-conversion (unit "u") (factor 1) (symbol "U")))

; Intake units of a unit form: the active ingredient dosage is the amount per unit
(deffacts unit-forms
  (unit-form "comprimé") (unit-form "gélule") (unit-form "sachet") (unit-form "ampoule") (unit-form "seringue")
  (unit-form "capsule") (unit-form "suppositoire") (unit-form "stylo") (unit-form "film"))

; Intake unit is an amount of active ingredient: 0.7 gramme(s) per day -> 700 mg
(defrule line-dose-from-intake-unit
  (treatment (line ?l) (quantity ?q&:(> ?q 0)) (unit ?u))
  (unit-conversion (unit ?u) (factor ?f) (symbol ?s))
  =>
  (assert (line-dose (line ?l) (amount (* ?q ?f)) (unit ?s))))

; Unit form with a single active ingredient: 2 comprimé(s) of 350 mg per day -> 700 mg
(defrule line-dose-from-dosage
  (treatment (line ?l) (quantity ?q&:(> ?q 0)) (unit ?u) (ingredients 1))
  (unit-form ?form&:(eq (str-index ?form ?u) 1))
  (ingredient (line ?l) (dosage ?d) (unit ?du))
  (unit-conversion (unit ?du) (factor ?f) (symbol ?s))
  =>
  (assert (line-dose (line ?l) (amount (* ?q ?d ?f)) (unit ?s))))

(defrule daily-dose
  (line-dose (line ?l) (amount ?a) (unit ?u&"mg"|"µg"))
  =>
  (assert (daily-dose (line ?l) (mg (if (eq ?u "mg") then ?a else (/ ?a 1000))))))

(defrule dose-per-kg
  (daily-dose (line ?l) (mg ?mg))
  (data (name "weight_kg") (value ?w&:(> ?w 0)))
  =>
  (assert (dose-per-kg (line ?l) (mg (/ ?mg ?w)))))

; ---------- Same drug on several lines ----------

(defrule ongoing-scheduled-line
  (line-status (line ?l) (status "ongoing"))
  (treatment (line ?l) (name ?n&~"") (as_needed FALSE))
  =>
  (assert (ongoing-line (line ?l) (name ?n))))

; Often deliberate, to obtain a specific dosage. The alert gives the total dose so that the LLM can judge it.
; Fires for each pair of lines, but CLIPS ignores the identical alerts.
; Low priority so the doses are computed first.
(defrule same-drug-several-lines
  (declare (salience -5))
  (ongoing-line (line ?l1) (name ?n))
  (ongoing-line (line ?l2&:(> ?l2 ?l1)) (name ?n))
  =>
  (bind ?lines (create$))
  (do-for-all-facts ((?o ongoing-line)) (eq ?o:name ?n) (bind ?lines (create$ ?lines ?o:line)))
  (bind ?unit "")
  (bind ?total 0)
  (bind ?doses 0)
  (do-for-all-facts ((?d line-dose)) (member$ ?d:line ?lines)
    (if (eq ?unit "") then (bind ?unit ?d:unit))
    (if (eq ?unit ?d:unit) then
      (bind ?total (+ ?total ?d:amount))
      (bind ?doses (+ ?doses 1))))
  (bind ?message (str-cat ?n " sur plusieurs lignes en cours"))
  (if (= ?doses (length$ ?lines))
    then (bind ?message (str-cat ?message ", dose totale " (format nil "%g" ?total) " " ?unit " par jour")))
  (assert (alert (message (str-cat ?message " : association de dosages souvent volontaire pour obtenir une posologie précise, à signaler seulement si la dose totale est inhabituelle ou dépasse la dose maximale")) (lines ?lines))))

; ---------- Interactions (facts of generic_rules.clp) ----------

; Interaction between a drug of group a and a drug of group b
(deftemplate interaction
  (slot title)
  (slot level (default ""))
  (multislot drugs-a)
  (multislot drugs-b)
  (slot alert))

; The two drugs must be on distinct lines: a fixed combination triggers nothing.
; Low priority so the alerts of the personalized rules are listed first.
(defrule drug-interaction
  (declare (salience -10))
  (interaction (drugs-a $? ?a $?) (drugs-b $? ?b $?) (alert ?message))
  (prescribed (line ?la) (drug ?a))
  (prescribed (line ?lb&~?la) (drug ?b))
  =>
  (assert (alert (message ?message) (lines ?la ?lb))))
