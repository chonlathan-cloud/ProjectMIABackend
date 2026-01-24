from google.cloud import storage
from src.config import settings
from typing import Tuple, Optional
import uuid
from datetime import datetime
from urllib.parse import quote


class StorageService:
    """Service for Google Cloud Storage operations."""
    
    def __init__(self):
        self.client = storage.Client()
        self.bucket_name = settings.gcs_bucket_name
        self.bucket = self.client.bucket(self.bucket_name)
    
    async def upload_file(
        self,
        file_content: bytes,
        filename: str,
        content_type: str,
        folder_prefix: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Upload a file to Google Cloud Storage.
        
        Args:
            file_content: Binary file content
            filename: Original filename
            content_type: MIME type (e.g., 'application/pdf', 'image/jpeg')
            
        Returns:
            Tuple of (blob_name, public_url)
        """
        try:
            # Normalize optional folder segment (avoid path traversal)
            safe_folder = None
            if folder_prefix:
                normalized = folder_prefix.strip().replace("/", "-").replace("\\", "-")
                safe_folder = normalized or None

            # Generate unique filename
            file_extension = filename.split('.')[-1] if '.' in filename else 'bin'
            unique_filename = f"{uuid.uuid4()}.{file_extension}"
            
            # Create blob path with timestamp folder
            timestamp = datetime.utcnow().strftime("%Y/%m/%d")
            base_prefix = "uploads"
            if safe_folder:
                base_prefix = f"{base_prefix}/{safe_folder}"
            blob_name = f"{base_prefix}/{timestamp}/{unique_filename}"
            
            # Create blob
            blob = self.bucket.blob(blob_name)
            
            # Set content type
            blob.content_type = content_type
            
            # Upload file
            blob.upload_from_string(file_content, content_type=content_type)
            
            # Make blob publicly accessible (optional - adjust based on requirements)
            # blob.make_public()
            
            # Get public URL
            public_url = (
                f"https://storage.googleapis.com/{self.bucket_name}/"
                f"{quote(blob_name, safe='/')}"
            )
            
            return blob_name, public_url
            
        except Exception as e:
            raise Exception(f"File upload failed: {str(e)}")
    
    async def delete_file(self, blob_name: str) -> bool:
        """
        Delete a file from Google Cloud Storage.
        
        Args:
            blob_name: Name of the blob to delete
            
        Returns:
            True if successful
        """
        try:
            blob = self.bucket.blob(blob_name)
            blob.delete()
            return True
            
        except Exception as e:
            raise Exception(f"File deletion failed: {str(e)}")
    
    async def get_signed_url(self, blob_name: str, expiration: int = 3600) -> str:
        """
        Generate a signed URL for temporary access to a private file.
        
        Args:
            blob_name: Name of the blob
            expiration: URL expiration time in seconds (default 1 hour)
            
        Returns:
            Signed URL
        """
        try:
            blob = self.bucket.blob(blob_name)
            
            url = blob.generate_signed_url(
                version="v4",
                expiration=expiration,
                method="GET"
            )
            
            return url
            
        except Exception as e:
            raise Exception(f"Signed URL generation failed: {str(e)}")


# Global storage service instance
storage_service = StorageService()
