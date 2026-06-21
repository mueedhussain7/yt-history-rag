import os
import json
import requests
from typing import Optional, Tuple, List, Dict
from dotenv import load_dotenv

load_dotenv()


class ConceptExtractor:
    """
    Extract key concepts from video transcripts using OpenRouter API.
    """

    def __init__(self):
        """Initialize with OpenRouter API key from environment."""
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError(
                "OPENROUTER_API_KEY not found in environment. "
                "Add it to your .env file."
            )
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "openai/gpt-3.5-turbo"
        self.max_concepts = 10

    def extract_concepts(self, transcript: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """
        Extract key concepts from a transcript.

        Args:
            transcript: The video transcript text

        Returns:
            (concepts_list, error_message)
            - If success: (concepts_list, None)
            - If failed: (None, error_reason)
        """
        if not transcript or not transcript.strip():
            return None, "Transcript is empty"

        try:
            # Create prompt for concept extraction
            prompt = self._create_prompt(transcript)

            # Call OpenRouter API
            response_text = self._call_openrouter_api(prompt)
            if not response_text:
                return None, "Failed to get response from OpenRouter"

            # Parse response into concepts
            concepts = self._parse_response(response_text)
            if not concepts:
                return None, "Failed to parse concepts from LLM response"

            return concepts, None

        except Exception as e:
            return None, f"Concept extraction error: {str(e)}"

    def _create_prompt(self, transcript: str) -> str:
        """
        Create a prompt for the LLM to extract concepts.

        Args:
            transcript: The video transcript

        Returns:
            Formatted prompt for the LLM
        """
        # Truncate transcript if too long (to save tokens)
        max_length = 3000
        if len(transcript) > max_length:
            transcript = transcript[:max_length] + "..."

        prompt = f"""Extract the top {self.max_concepts} key concepts from this video transcript.

For each concept, provide:
1. The concept name (short, 1-3 words)
2. A brief description (1-2 sentences)

Return the response as a JSON array with objects containing "name" and "description" fields.
Only return the JSON array, no other text.

Example format:
[
  {{"name": "JavaScript", "description": "A programming language used for web development"}},
  {{"name": "REST API", "description": "An architectural style for building web services"}}
]

Transcript:
{transcript}

JSON Response:"""
        return prompt

    def _call_openrouter_api(self, prompt: str) -> Optional[str]:
        """
        Call OpenRouter API to extract concepts.

        Args:
            prompt: The prompt for the LLM

        Returns:
            LLM response text or None if failed
        """
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                "max_tokens": 1000,
                "temperature": 0.7,
            }

            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30,
            )

            if response.status_code != 200:
                error_msg = response.json().get("error", {}).get("message", "Unknown error")
                return None

            response_data = response.json()
            if "choices" not in response_data or len(response_data["choices"]) == 0:
                return None

            return response_data["choices"][0]["message"]["content"]

        except requests.Timeout:
            return None
        except requests.RequestException as e:
            return None
        except Exception as e:
            return None

    def _parse_response(self, response_text: str) -> Optional[List[Dict]]:
        """
        Parse LLM response into structured concepts.

        Args:
            response_text: Raw response from LLM

        Returns:
            List of concept dicts or None if parsing fails
        """
        try:
            # Try to parse as JSON
            concepts = json.loads(response_text)

            # Validate structure
            if not isinstance(concepts, list):
                return None

            # Validate each concept has required fields
            validated_concepts = []
            for concept in concepts:
                if isinstance(concept, dict) and "name" in concept and "description" in concept:
                    validated_concepts.append({
                        "name": str(concept["name"]).strip(),
                        "description": str(concept["description"]).strip(),
                    })

            return validated_concepts if validated_concepts else None

        except json.JSONDecodeError:
            # If JSON parsing fails, try to extract JSON from text
            try:
                # Look for JSON array in response
                start_idx = response_text.find("[")
                end_idx = response_text.rfind("]") + 1

                if start_idx != -1 and end_idx > start_idx:
                    json_str = response_text[start_idx:end_idx]
                    concepts = json.loads(json_str)

                    if isinstance(concepts, list):
                        validated_concepts = []
                        for concept in concepts:
                            if isinstance(concept, dict) and "name" in concept and "description" in concept:
                                validated_concepts.append({
                                    "name": str(concept["name"]).strip(),
                                    "description": str(concept["description"]).strip(),
                                })
                        return validated_concepts if validated_concepts else None

                return None
            except Exception:
                return None
