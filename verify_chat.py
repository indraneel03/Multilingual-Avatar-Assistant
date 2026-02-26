import os
import sys
import requests
from pathlib import Path

# Add the project root to the Python path
ROOT_DIR = Path(__file__).resolve().parent
sys.path.append(str(ROOT_DIR))

# Now you can import from the project
from avatar_assistant import settings

def verify_chat_flow():
    """
    Verifies the chat flow by sending a request to the avatar_query API
    and checking the response and generated files.
    """
    print("Starting chat flow verification...")

    # 1. Prepare the request
    url = "http://127.0.0.1:8000/api/query/"
    payload = {
        "text": "Hello, how are you?",
        "language": "en",
    }
    print(f"Sending POST request to {url} with payload: {payload}")

    try:
        # 2. Send the request
        response = requests.post(url, data=payload, timeout=300) # 5 minute timeout for SadTalker
        response.raise_for_status()  # Raise an exception for bad status codes

        # 3. Check the response
        print("Request successful!")
        data = response.json()
        print(f"Received JSON response: {data}")

        # 4. Verify the response data
        assert "llm_text" in data, "Response should contain 'llm_text'"
        assert "audio_url" in data, "Response should contain 'audio_url'"
        assert "video_url" in data, "Response should contain 'video_url'"
        print("JSON response contains all the expected fields.")

        # 5. Verify the generated files
        media_root = Path(settings.MEDIA_ROOT)
        audio_path = media_root / Path(data["audio_url"]).name
        video_path = media_root / Path(data["video_url"]).name

        assert audio_path.exists(), f"Audio file not found at {audio_path}"
        print(f"Audio file found at: {audio_path}")

        assert video_path.exists(), f"Video file not found at {video_path}"
        print(f"Video file found at: {video_path}")

        print()
        print("Verification successful! The chat flow is working correctly.")

    except requests.exceptions.RequestException as e:
        print()
        print(f"Error during request: {e}")
        print("Verification failed.")
    except (AssertionError, KeyError) as e:
        print()
        print(f"Error during verification: {e}")
        print("Verification failed.")

if __name__ == "__main__":
    # This is to ensure the Django environment is set up correctly
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "avatar_assistant.settings")
    import django
    django.setup()
    verify_chat_flow()
