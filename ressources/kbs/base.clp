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

; Dose in mg per administration day
(deftemplate daily-dose
  (slot line)
  (slot mg))

; Dose in mg/kg per administration day
(deftemplate dose-per-kg
  (slot line)
  (slot mg))

; Scheduled line ongoing on the reference date
(deftemplate ongoing-line
  (slot line)
  (slot name))

; Alert for the pharmacist, with the prescription lines involved
(deftemplate alert
  (slot message)
  (multislot lines))

; ---------- Dose computation ----------

(deftemplate unit-to-mg
  (slot unit)
  (slot factor))

; Intake units (milligramme(s)...) and active ingredient dosage units (mg...)
(deffacts units
  (unit-to-mg (unit "milligramme(s)") (factor 1))
  (unit-to-mg (unit "gramme(s)") (factor 1000))
  (unit-to-mg (unit "microgramme(s)") (factor 0.001))
  (unit-to-mg (unit "mg") (factor 1))
  (unit-to-mg (unit "g") (factor 1000))
  (unit-to-mg (unit "ug") (factor 0.001)))

; Intake unit is a mass: 0.7 gramme(s) per day -> 700 mg
(defrule daily-dose-from-intake-unit
  (treatment (line ?l) (quantity ?q&:(> ?q 0)) (unit ?u))
  (unit-to-mg (unit ?u) (factor ?f))
  =>
  (assert (daily-dose (line ?l) (mg (* ?q ?f)))))

; Otherwise, with a single active ingredient: 2 comprimé(s) of 350 mg per day -> 700 mg
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

; ---------- Same drug on several lines ----------

; Dates "YYYY-MM-DD" compare as strings
(defrule ongoing-scheduled-line
  (reference-date (date ?today))
  (treatment (line ?l) (name ?n&~"") (as_needed FALSE) (start ?s) (end ?e))
  (test (and (<= (str-compare ?s ?today) 0) (or (eq ?e "") (>= (str-compare ?e ?today) 0))))
  =>
  (assert (ongoing-line (line ?l) (name ?n))))

; Often deliberate, to obtain a specific dosage. The alert gives the total dose so that the LLM can judge it.
; Fires for each pair of lines, but CLIPS ignores the identical alerts.
; Low priority so the daily doses are computed first.
(defrule same-drug-several-lines
  (declare (salience -5))
  (ongoing-line (line ?l1) (name ?n))
  (ongoing-line (line ?l2&:(> ?l2 ?l1)) (name ?n))
  =>
  (bind ?lines (create$))
  (do-for-all-facts ((?o ongoing-line)) (eq ?o:name ?n) (bind ?lines (create$ ?lines ?o:line)))
  (bind ?total 0)
  (bind ?doses 0)
  (do-for-all-facts ((?d daily-dose)) (member$ ?d:line ?lines)
    (bind ?total (+ ?total ?d:mg))
    (bind ?doses (+ ?doses 1)))
  (bind ?message (str-cat ?n " sur plusieurs lignes en cours"))
  (if (= ?doses (length$ ?lines))
    then (bind ?message (str-cat ?message ", dose totale " (format nil "%g" ?total) " mg par jour")))
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
