from azure.storage.blob import BlobServiceClient
import os
import secrets


def get_blob_service():
    conn_str = os.environ.get("AZURE_STORAGE_CONNECTION")
    if not conn_str:
        return None
    return BlobServiceClient.from_connection_string(conn_str)


def upload_image(file):
    blob_service = get_blob_service()
    if not blob_service:
        return None

    container_name = os.environ.get("AZURE_STORAGE_CONTAINER", "car-images")
    container_client = blob_service.get_container_client(container_name)

    ext = file.filename.rsplit(".", 1)[1].lower()
    blob_name = f"{secrets.token_hex(8)}.{ext}"

    blob_client = container_client.get_blob_client(blob_name)
    blob_client.upload_blob(file, overwrite=True)

    return blob_name


def get_image_url(blob_name):
    if not blob_name:
        return None
    account_name = os.environ.get("AZURE_STORAGE_ACCOUNT", "smartdriveimages")
    container_name = os.environ.get("AZURE_STORAGE_CONTAINER", "car-images")
    return f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}"


def delete_image(blob_name):
    if not blob_name:
        return
    blob_service = get_blob_service()
    if not blob_service:
        return
    container_name = os.environ.get("AZURE_STORAGE_CONTAINER", "car-images")
    blob_client = blob_service.get_blob_client(container_name, blob_name)
    try:
        blob_client.delete_blob()
    except Exception:
        pass
