from openpyxl import Workbook
import os
import re

def clean_text(value):
    if not value:
        return ""
    # Remove colon and extra spaces
    value = value.replace(":", "")
    return value.strip()

def save_to_excel(data, base_name):
    os.makedirs("outputs", exist_ok=True)

    if not base_name.lower().endswith(".xlsx"):
        base_name = f"{base_name}.xlsx"

    output_file = os.path.join("outputs", base_name)

    wb = Workbook()
    ws = wb.active
    ws.title = "Menu Data"

    headers = [
        "Category",
        "Subcategory",
        "ItemName",
        "DisplayIndex",
        "ItemCode(Number)",
        "ShortCode(String)",
        "RATE"
    ]

    ws.append(headers)

    display_index = 1
    item_code = 1

    for row in data:

        category = clean_text(row.get("Category", "FOOD"))
        subcategory = clean_text(row.get("Subcategory", ""))
        item_name = clean_text(row.get("ItemName", ""))
        rate = clean_text(row.get("Rate", ""))

        # Clean item name for shortcode generation
        clean_name = re.sub(r'[^A-Za-z0-9 ]', '', item_name)
        words = clean_name.split()
        short_code = "".join(word[0] for word in words if word).upper()[:5]

        ws.append([
            category,
            subcategory,
            item_name,
            display_index,
            item_code,
            short_code,
            rate
        ])

        display_index += 1
        item_code += 1

    wb.save(output_file)
    return output_file