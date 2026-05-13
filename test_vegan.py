import json
from src.backend.llm_translator import translate_chat_message

res = translate_chat_message([], [], {}, "ponme una paella vegana para 3")
print(json.dumps(res, indent=2, ensure_ascii=False))
