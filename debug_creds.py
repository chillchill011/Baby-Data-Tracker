import os
import base64
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get the Base64 string from environment variable
google_credentials_json_b64 = os.getenv("GOOGLE_CREDENTIALS_JSON_BASE64")

if not google_credentials_json_b64:
    print("Error: GOOGLE_CREDENTIALS_JSON_BASE64 environment variable not found.")
    exit(1)

print(f"--- DEBUG: Raw Base64 string length: {len(google_credentials_json_b64)}")
print(f"--- DEBUG: Raw Base64 string (first 200 chars): {google_credentials_json_b64[:200]}")

try:
    # Step 1: Decode from Base64
    decoded_string = base64.b64decode(google_credentials_json_b64).decode('utf-8')

    print(f"--- DEBUG: Decoded string length: {len(decoded_string)}")
    print(f"--- DEBUG: Decoded string (first 200 chars): {decoded_string[:200]}")
    print("--- DEBUG: Full Decoded String (for inspection):")
    print(decoded_string) # Print the full decoded string for manual inspection

    # Step 2: Parse as JSON
    credentials_info = json.loads(decoded_string)

    print("\n--- SUCCESS: JSON parsing successful! ---")
    print(f"Project ID: {credentials_info.get('project_id')}")
    print(f"Client Email: {credentials_info.get('client_email')}")

except base64.binascii.Error as e:
    print(f"--- ERROR: Base64 Decoding Error: {e}")
    print("This usually means the Base64 string itself is malformed (e.g., contains invalid characters or incorrect padding).")
except json.JSONDecodeError as e:
    print(f"--- ERROR: JSON Decoding Error: {e}")
    print(f"Error details: {e}")
    print(f"The invalid character is likely in the decoded string above. Check line {e.lineno}, column {e.colno}")
except Exception as e:
    print(f"--- ERROR: An unexpected error occurred: {e}")