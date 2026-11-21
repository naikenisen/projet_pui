"""How many patients does filter 1 extract (= number of patients in preprocessing/dataset/ and full_dataset/)?

Uses exactly the same functions and the same seed as preprocessing.py.
"""

from preprocessing import (
    DICTIONARY, SEED, biology_before_day, choose_days, load_biology, load_clinical,
    load_treatments, prescriptions_of_the_day, read_raw_csv,
)

raw = read_raw_csv("treatments")
patient_column = next(raw_name for raw_name, name in DICTIONARY["treatments"]["columns"].items() if name == "patient_id")
excluded = DICTIONARY["treatments"].get("exclude", {})
print("=== Raw TREATMENTS")
print(f"CSV rows                        : {len(raw)}")
print(f"patients                        : {raw[patient_column].nunique()}")
for column, values in excluded.items():
    print(f"rows per {column}:", raw[column].replace("", "(empty)").value_counts().to_dict())

lines, _ = load_treatments()
print("\n=== Grouped prescriptions (1 CSV row per active ingredient -> 1 prescription)")
print(f"without excluded statuses {excluded} : {len(lines)}  ({lines['patient_id'].nunique()} patients)")

days = choose_days(lines)
presc = prescriptions_of_the_day(lines, days)
presc_count = presc.groupby("patient_id").size()

print(f"\n=== FILTER 1 (seed = {SEED})")
print(f">>> PATIENTS IN THE JSON        : {len(days)}")
print(f"lost because only cancelled/deleted : {raw[patient_column].nunique() - len(days)}")
print(f"concomitant prescriptions / patient : median {presc_count.median():.0f}, "
      f"min {presc_count.min()}, max {presc_count.max()}, total {presc_count.sum()}")
print("reference dates per year        :", days.dt.year.value_counts().sort_index().to_dict())

clinical = load_clinical()
with_clinical = days.index.isin(clinical.index)
print(f"\n=== Data associated with the {len(days)} patients")
print(f"with CLINICAL data              : {with_clinical.sum()}")
print(f"  of which known weight         : {clinical.reindex(days.index)['weight_kg'].notna().sum()}")
print(f"  of which known height         : {clinical.reindex(days.index)['height_cm'].notna().sum()}")

biology, _ = load_biology()
biology = biology_before_day(biology, days)
biology_count = biology.groupby("patient_id").size().reindex(days.index, fill_value=0)
print(f"FILTER 2 - with >= 1 laboratory result before the day : {(biology_count > 0).sum()}")
print(f"  tests / patient (if > 0)      : median {biology_count[biology_count > 0].median():.0f}, max {biology_count.max()}")
print(f"  without any laboratory value before the day : {(biology_count == 0).sum()}")
print(f"with CLINICAL + biology + treatments : {(with_clinical & (biology_count > 0).to_numpy()).sum()}")
