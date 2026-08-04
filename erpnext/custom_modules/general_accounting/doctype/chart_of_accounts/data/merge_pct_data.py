import json
import os
import sys

SOURCE_FILES = [
    "class_1_capitaux.json",
    "class_2_immobilisations.json",
    "class_3_stocks.json",
    "class_4_tiers.json",
    "class_5_financiers.json",
    "class_6_charges.json",
    "class_7_produits.json",
]


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(base_dir, "pct_chart_of_accounts.json")

    merged_records = []
    per_file_counts = {}

    for file_name in SOURCE_FILES:
        file_path = os.path.join(base_dir, file_name)
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        count = len(data)
        per_file_counts[file_name] = count

        for item in data:
            record = {
                "account": str(item.get("account", "")),
                "label": str(item.get("label", "")),
                "direction": str(item.get("direction", "")),
                "account_type": "",
                "nature": "In Progress",
            }
            merged_records.append(record)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(merged_records, f, indent=2, ensure_ascii=False)

    print(f"Total record count: {len(merged_records)}")
    print("Per-source-file record counts:")
    for file_name, count in per_file_counts.items():
        print(f"  {file_name}: {count}")


if __name__ == "__main__":
    main()
