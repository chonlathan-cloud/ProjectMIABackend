from google.cloud import aiplatform
import vertexai
from src.config import settings
from typing import Dict, Any, List
import json


# Initialize Vertex AI
vertexai.init(
    project=settings.google_cloud_project,
    location=settings.vertex_ai_location
)


class AIService:
    """Service for Vertex AI operations."""
    
    def __init__(self):
        try:
            from vertexai.generative_models import GenerativeModel, Part
        except ImportError:
            try:
                from vertexai.preview.generative_models import GenerativeModel, Part
            except ImportError as exc:
                raise ImportError(
                    "vertexai GenerativeModel not available. "
                    "Upgrade google-cloud-aiplatform or adjust imports."
                ) from exc

        self._part_class = Part
        self.model = GenerativeModel(settings.vertex_ai_model)
        self.embedding_model_name = f"projects/{settings.google_cloud_project}/locations/{settings.vertex_ai_location}/publishers/google/models/{settings.vertex_ai_embedding_model}"
    
    async def generate_line_flex_message(
        self,
        user_prompt: str,
        products: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Generate LINE Flex Message JSON from natural language prompt.
        
        Args:
            user_prompt: User's marketing request (e.g., "Promote coffee with 20% discount")
            products: List of shop products for context
            
        Returns:
            Dict containing Flex Message JSON structure
        """
        # Prepare products context
        products_text = "\n".join([
            f"- {p.get('name', 'Unknown')}: {p.get('price', 0)} THB"
            for p in products
        ])
        
        # Construct prompt
        prompt = f"""Role: Marketing Expert & JSON Engineer

Task: Create a LINE Flex Message (JSON format) to promote products based on the user's request.

User Request: "{user_prompt}"

Available Shop Products:
{products_text}

Requirements:
1. Create a visually appealing Flex Bubble message
2. Include relevant product information
3. Use attractive colors and layout
4. Add call-to-action buttons
5. Output ONLY valid JSON in LINE Flex Message format

Output the complete Flex Message JSON structure starting with:
{{
  "type": "bubble",
  ...
}}

Do not include any explanation, only the JSON."""

        try:
            # Generate content
            response = self.model.generate_content(prompt)
            
            # Extract JSON from response
            response_text = response.text.strip()
            
            # Clean up response (remove markdown code blocks if present)
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            
            response_text = response_text.strip()
            
            # Parse JSON
            flex_message = json.loads(response_text)
            
            return flex_message
            
        except json.JSONDecodeError as e:
            # Fallback to basic template if JSON parsing fails
            return {
                "type": "bubble",
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": user_prompt,
                            "weight": "bold",
                            "size": "xl"
                        }
                    ]
                }
            }
        except Exception as e:
            raise Exception(f"AI generation failed: {str(e)}")
    
    async def generate_embeddings(self, text: str) -> List[float]:
        """
        Generate text embeddings for RAG (Retrieval-Augmented Generation).
        
        Args:
            text: Text to embed
            
        Returns:
            List of embedding values (vector)
        """
        try:
            # Use Vertex AI Text Embeddings API
            client = aiplatform.gapic.PredictionServiceClient()
            
            instances = [{"content": text}]
            
            response = client.predict(
                endpoint=self.embedding_model_name,
                instances=instances
            )
            
            # Extract embeddings from response
            embeddings = response.predictions[0]["embeddings"]["values"]
            
            return embeddings
            
        except Exception as e:
            raise Exception(f"Embedding generation failed: {str(e)}")
    
    async def extract_text_from_document(self, file_content: bytes, mime_type: str) -> str:
        """
        Extract text from PDF or image using Vertex AI.
        
        Args:
            file_content: Binary file content
            mime_type: MIME type (e.g., 'application/pdf', 'image/jpeg')
            
        Returns:
            Extracted text content
        """
        try:
            # Create a Part from the file content
            document_part = self._part_class.from_data(data=file_content, mime_type=mime_type)
            
            # Use Gemini to extract text
            prompt = "Extract all text from this document. Return only the text content, no explanations."
            
            response = self.model.generate_content([prompt, document_part])
            
            return response.text
            
        except Exception as e:
            raise Exception(f"Text extraction failed: {str(e)}")


# Global AI service instance
ai_service = AIService()
