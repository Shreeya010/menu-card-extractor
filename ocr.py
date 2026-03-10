import requests
import base64
import json
import re
from PIL import Image
from io import BytesIO


# =====================================================
# PROMPT
# =====================================================

PROMPT = """
You are a restaurant menu OCR extractor.

Extract all menu items from the image and return ONLY a valid JSON array.

IMPORTANT:
Return ONLY JSON.
Do NOT add explanations.
Do NOT add markdown.
Do NOT add text outside JSON.

Required format:

[
  {
    "Category": "FOOD",
    "Subcategory": "Main section name exactly as written (e.g. BREAKFAST / FAST FOOD / BIRYANI / CURRY)",
    "ItemName": "Exact cleaned item name",
    "Rate": "Only numeric price"
  }
]

STRICT RULES:

1. Category must always be "FOOD".

2. Subcategory must be the menu section header under which the item appears
   (examples: BIRYANI, FAST FOOD, BREAKFAST, CURRY, NOODLES, DRINKS, STARTERS).

3. ItemName must contain ONLY the dish name.

4. Ignore any starting characters like:
   /  -  •  .  *
   Example:
   /Paneer Bhurji → Paneer Bhurji

5. If an item contains (H/F) or (H-F) it means Half and Full portions.
   You must create TWO separate items.

   Example:
   Paneer Bhurji (H/F)

   Output:
   Paneer Bhurji Half
   Paneer Bhurji Full

6. Remove brackets after processing.
   Do NOT keep (H/F), (H-F), (), [] or {} in the final ItemName.

7. Remove special characters from ItemName:
   :, (, ), [, ], { }

8. Ignore descriptions or extra words like:
   "served with", "special", "chef choice", etc.

9. Remove currency symbols such as:
   ₹  Rs  INR  $  €

10. Rate must contain ONLY numbers.

    Example:
    ₹250 → 250
    Rs.180 → 180

11. Do NOT invent menu items.
    Only extract items clearly visible in the menu.

12. Do NOT include extra fields.
    Only return:

Category  
Subcategory  
ItemName  
Rate

Return ONLY the JSON array.
"""


# =====================================================
# Validate API Key Format
# =====================================================

def validate_api_key_format(api_key: str):
    pattern = r"^AIza[0-9A-Za-z\-_]{30,}$"
    return re.match(pattern, api_key)


# =====================================================
# Verify API Key
# =====================================================

def verify_api_key(api_key: str):

    endpoint = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash-lite:generateContent?key={api_key}"

    test_payload = {
        "contents": [
            {"parts": [{"text": "Say OK"}]}
        ]
    }

    response = requests.post(endpoint, json=test_payload)

    if response.status_code == 200:
        return True, None

    if response.status_code == 429:
        return False, "Free tier limit exceeded (5 images per minute). Try again after 60 seconds."

    return False, "Invalid API key."


# =====================================================
# CLEAN TEXT FUNCTION
# =====================================================

def clean_item_name(name):

    if not name:
        return ""

    name = name.strip()

    # remove starting / - . *
    name = re.sub(r"^[\/\-\.\*\•]+", "", name)

    # remove brackets
    name = re.sub(r"[\(\)\[\]\{\}]", "", name)

    # remove colon
    name = name.replace(":", "")

    # remove special characters
    name = re.sub(r"[^A-Za-z0-9 ]", "", name)

    return name.strip()


def clean_price(price):
    """
    Keep only numbers in price.
    """
    if not price:
        return ""

    return re.sub(r"[^0-9]", "", str(price))

from PIL import ImageEnhance

def compress_image(image_path):

    img = Image.open(image_path)

    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    # Resize
    img.thumbnail((1600,1600))

    # Improve contrast
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.7)

    # Improve sharpness
    sharp = ImageEnhance.Sharpness(img)
    img = sharp.enhance(2)

    buffer = BytesIO()

    img.save(buffer, format="JPEG", quality=70, optimize=True)

    return base64.b64encode(buffer.getvalue()).decode("utf-8")

def remove_duplicates(items):

    seen = set()
    result = []

    for item in items:

        key = (item["Subcategory"], item["ItemName"])

        if key not in seen:
            seen.add(key)
            result.append(item)

    return result

# =====================================================
# Extract Menu
# =====================================================

def extract_menu(image_path, api_key):

    endpoint = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash-lite:generateContent?key={api_key}"

    base64_image = compress_image(image_path)

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": PROMPT},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": base64_image
                        }
                    }
                ]
            }
        ]
    }

    response = requests.post(endpoint, json=payload)

    # if response.status_code == 429:
        # raise Exception("Free tier limit exceeded (5 images per minute). Try again after 60 seconds.")

    if response.status_code != 200:
        raise Exception("Invalid API key or Gemini error.")

    result = response.json()

    text = result["candidates"][0]["content"]["parts"][0].get("text", "").strip()

    # Remove markdown formatting safely
    if text.startswith("```"):
        text = text.split("```")[1]

    text = text.replace("json", "").strip()

    # Extract valid JSON array
    match = re.search(r"\[.*\]", text, re.DOTALL)

    if not match:
        return []

    data = json.loads(match.group())

    # -------------------------------------------------
    # FINAL CLEANING BEFORE RETURN
    # -------------------------------------------------

    cleaned_data = []

    for item in data:

        item_name = item.get("ItemName", "")
        rate = clean_price(item.get("Rate", ""))

        # Detect Half/Full
        if "H/F" in item_name or "HF" in item_name:

            base = clean_item_name(item_name.replace("H/F","").replace("HF",""))

            cleaned_data.append({
                "Category": "FOOD",
                "Subcategory": item.get("Subcategory", "").strip(),
                "ItemName": base + " Half",
                "Rate": rate
            })

            cleaned_data.append({
                "Category": "FOOD",
                "Subcategory": item.get("Subcategory", "").strip(),
                "ItemName": base + " Full",
                "Rate": rate
            })

        else:

            cleaned_data.append({
                "Category": "FOOD",
                "Subcategory": item.get("Subcategory", "").strip(),
                "ItemName": clean_item_name(item_name),
                "Rate": rate
            })
    return remove_duplicates(cleaned_data)
# =====================================================
# Extract Menu From Multiple Images (Single Gemini Call)
# =====================================================

def extract_menu_multiple(image_paths, api_key):

    endpoint = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash-lite:generateContent?key={api_key}"

    parts = [{"text": PROMPT}]

    # Add all images
    for image_path in image_paths:

        base64_image = compress_image(image_path)

        parts.append({
            "inline_data": {
                "mime_type": "image/jpeg",
                "data": base64_image
            }
        })

    payload = {
        "contents": [
            {
                "parts": parts
            }
        ]
    }

    response = requests.post(endpoint, json=payload)

    if response.status_code != 200:
        raise Exception("Invalid API key or Gemini error.")

    result = response.json()

    text = result["candidates"][0]["content"]["parts"][0].get("text", "").strip()

    # Remove markdown safely
    if text.startswith("```"):
        text = text.split("```")[1]

    text = text.replace("json", "").strip()

    match = re.search(r"\[.*\]", text, re.DOTALL)

    if not match:
        return []

    data = json.loads(match.group())

    cleaned_data = []

    for item in data:

        item_name = item.get("ItemName", "")
        rate = clean_price(item.get("Rate", ""))

        if "H/F" in item_name or "HF" in item_name:

            base = clean_item_name(item_name.replace("H/F","").replace("HF",""))

            cleaned_data.append({
                "Category": "FOOD",
                "Subcategory": item.get("Subcategory", "").strip(),
                "ItemName": base + " Half",
                "Rate": rate
            })

            cleaned_data.append({
                "Category": "FOOD",
                "Subcategory": item.get("Subcategory", "").strip(),
                "ItemName": base + " Full",
                "Rate": rate
            })

        else:

            cleaned_data.append({
                "Category": "FOOD",
                "Subcategory": item.get("Subcategory", "").strip(),
                "ItemName": clean_item_name(item_name),
                "Rate": rate
            })

    return remove_duplicates(cleaned_data)