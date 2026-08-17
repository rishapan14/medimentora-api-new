import os
import uuid
from datetime import datetime, timezone

from werkzeug.utils import secure_filename


def utc_now():
    """Return current UTC datetime (naive) for MySQL DateTime compatibility."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def allowed_file(filename, allowed_extensions):
    """Check whether the uploaded file has an allowed extension."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


def save_upload_file(file, upload_folder, allowed_extensions):
    """
    Save an uploaded file to disk with a unique name.
    Returns the relative file path or None if invalid.
    """
    if not file or file.filename == "":
        return None
    if not allowed_file(file.filename, allowed_extensions):
        return None

    os.makedirs(upload_folder, exist_ok=True)
    ext = file.filename.rsplit(".", 1)[1].lower()
    unique_name = f"{uuid.uuid4().hex}.{ext}"
    safe_name = secure_filename(unique_name)
    file_path = os.path.join(upload_folder, safe_name)
    file.save(file_path)
    return file_path
