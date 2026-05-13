from google import genai
import os
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", "AIzaSyCsX76xPfpgSCgZwDE1j-BJ3qpMNToT_rU"))
for m in client.models.list():
    print(m.name)
