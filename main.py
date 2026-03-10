from fastapi import FastAPI, UploadFile, File, Request, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import shutil
import os
import uuid
import json
import time

from ocr import extract_menu, validate_api_key_format, verify_api_key
from storage import save_to_excel

app = FastAPI(title="Menu Card Extractor")
app.add_middleware(SessionMiddleware, secret_key="supersecretkey")

templates = Jinja2Templates(directory="templates")

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.state.api_key = None
app.state.api_verified = False
app.state.latest_image_name = None
app.state.request_timestamps = []

# ==============================
# ROOT ROUTE
# ==============================

@app.get("/")
async def root():
    return RedirectResponse(url="/login", status_code=302)


# ==============================
# LOGIN PAGE
# ==============================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


# ==============================
# MAIN APP PAGE
# ==============================

@app.get("/menu-card/app", response_class=HTMLResponse)
async def main_app(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ==============================
# SET API KEY
# ==============================

@app.post("/set-api-key/")
async def set_api_key(request: Request, api_key: str = Form(...)):

    if not validate_api_key_format(api_key):
        return JSONResponse({"error": "Invalid API Key format."}, status_code=400)

    valid, message = verify_api_key(api_key)

    if not valid:
        return JSONResponse({"error": message}, status_code=400)

    app.state.api_key = api_key
    app.state.api_verified = True
    request.session["api_key"] = api_key

    return {"message": "API Key verified successfully"}


# ==============================
# IMAGE UPLOAD
# ==============================

@app.post("/upload/")
async def upload_images(request: Request, files: list[UploadFile] = File(...)):

    api_key = request.session.get("api_key")

    if not api_key:
        return JSONResponse(
            {"error": "Please enter a valid API key first."},
            status_code=403
        )

    current_time = time.time()

    # Remove timestamps older than 60 seconds
    app.state.request_timestamps = [
        t for t in app.state.request_timestamps
        if current_time - t < 60
    ]

    if len(app.state.request_timestamps) >= 5:
        return JSONResponse(
            {"error": "Free tier limit exceeded (5 images per minute). Try again after 60 seconds."},
            status_code=429
        )

    all_results = []

    for file in files:

        original_filename = file.filename
        name_without_ext = os.path.splitext(original_filename)[0]
        app.state.latest_image_name = name_without_ext

        unique_name = f"{uuid.uuid4()}_{original_filename}"
        file_path = os.path.join(UPLOAD_DIR, unique_name)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        extracted_data = extract_menu(file_path, api_key)

        all_results.extend(extracted_data)

    app.state.request_timestamps.append(time.time())

    return {"data": all_results}


# ==============================
# EXPORT EXCEL
# ==============================

@app.post("/export/")
async def export_excel(data: str = Form(...)):

    parsed_data = json.loads(data)
    base_name = app.state.latest_image_name or "menu"

    excel_path = save_to_excel(parsed_data, base_name)

    return FileResponse(
        excel_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{base_name}.xlsx"
    )