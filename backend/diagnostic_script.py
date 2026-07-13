import os
import sys
import traceback
from dotenv import load_dotenv

print('1. Environment Configuration')
env_loaded = load_dotenv()
print(f'Env loaded: {env_loaded}')
print(f'LLM_MODEL: {os.getenv("LLM_MODEL")}')
api_key = os.getenv("GEMINI_API_KEY", "")
print(f'GEMINI_API_KEY: {api_key[:12]}***' if api_key else 'GEMINI_API_KEY: Not found')
print(f'Python version: {sys.version}')
try:
    import google.genai
    print(f'google-genai version: {google.genai.__version__}')
except Exception as e:
    print(f'google-genai version: Error - {e}')

print('\n2. Testing Gemini API directly')
from google import genai
from google.genai import types
import json

try:
    client = genai.Client(api_key=api_key)
    print(f'Model string: {os.getenv("LLM_MODEL")}')
    
    prompt = 'Test prompt'
    system_instruction = 'Test system instruction'
    
    print('Sending request...')
    response = client.models.generate_content(
        model=os.getenv("LLM_MODEL"),
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2,
        ),
    )
    print('Request successful.')
    print(response.text)
except Exception as e:
    print('Exception occurred:')
    print(type(e).__name__)
    print(str(e))
    traceback.print_exc()
