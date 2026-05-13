import json
from src.backend.llm_translator import translate_chat_message

res = translate_chat_message([], [], {}, "Compra semanal para un atleta con 50 euros")
print(json.dumps(res, indent=2, ensure_ascii=False))
