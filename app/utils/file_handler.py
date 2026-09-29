"""
app/utils/file_handler.py
Secure file upload handling, validation, hashing, and storage (FR v, xii, xiv).
"""
import os
import uuid
from werkzeug.utils import secure_filename
from flask import current_app
from .hash_utils import compute_bytes_sha256, compute_sha256

ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def allowed_file(filename: str) -> bool:
    """Check if file extension is supported."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_file_extension(filename: str) -> str:
    """Extract lowercased file extension."""
    if '.' in filename:
        return filename.rsplit('.', 1)[1].lower()
    return ''


def save_secure_upload(file_storage, subfolder: str = "general", custom_name: str = None) -> dict:
    """
    Validates, securely hashes, and saves an uploaded file to disk.

    Args:
        file_storage: werkzeug.datastructures.FileStorage object from request.files
        subfolder: category or user/claim directory
        custom_name: optional prefix or explicit filename base

    Returns:
        dict with:
            - file_name: original safe filename
            - saved_filename: actual disk filename
            - file_path: relative path stored in DB
            - absolute_path: full filesystem path
            - file_hash: SHA-256 hex digest
            - file_size: size in bytes
            - mime_type: content type string
    """
    if not file_storage or not file_storage.filename:
        raise ValueError("No file provided for upload.")

    orig_filename = secure_filename(file_storage.filename)
    if not orig_filename or not allowed_file(orig_filename):
        raise ValueError(f"File type not permitted. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

    # Read bytes into memory to inspect size and compute hash
    file_bytes = file_storage.read()
    file_size = len(file_bytes)

    if file_size > MAX_FILE_SIZE:
        raise ValueError(f"File exceeds maximum allowed size of {MAX_FILE_SIZE // (1024 * 1024)}MB.")

    file_hash = compute_bytes_sha256(file_bytes)

    # Determine storage directory
    base_upload_dir = current_app.config.get('UPLOAD_FOLDER', 'static/uploads')
    target_dir = os.path.join(base_upload_dir, subfolder)
    os.makedirs(target_dir, exist_ok=True)

    ext = get_file_extension(orig_filename)
    unique_prefix = str(uuid.uuid4())[:12]
    if custom_name:
        safe_custom = secure_filename(custom_name)
        disk_filename = f"{safe_custom}_{unique_prefix}.{ext}"
    else:
        name_root = orig_filename.rsplit('.', 1)[0]
        disk_filename = f"{name_root}_{unique_prefix}.{ext}"

    absolute_path = os.path.join(target_dir, disk_filename)
    relative_path = os.path.relpath(absolute_path, start=os.getcwd()).replace('\\', '/')

    with open(absolute_path, 'wb') as f:
        f.write(file_bytes)

    mime_type = file_storage.content_type or 'application/octet-stream'

    return {
        'file_name': orig_filename,
        'saved_filename': disk_filename,
        'file_path': relative_path,
        'absolute_path': absolute_path,
        'file_hash': file_hash,
        'file_size': file_size,
        'mime_type': mime_type,
    }
