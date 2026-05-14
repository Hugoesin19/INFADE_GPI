from src.backend.llm_translator import _extract_ingredients_with_llm
from unittest.mock import patch

with patch('google.genai.Client') as MockClient:
    mock_instance = MockClient.return_value
    mock_instance.models.generate_content.return_value.text = '{"nombre": "Muffins", "tipo": "postre", "ingredientes": ["Plátano de Canarias", "Huevos L"]}'
    res = _extract_ingredients_with_llm("muffins con platano")
    print("Ingredientes extraídos:", res)
    
    # Let's inspect the actual prompt passed
    args, kwargs = mock_instance.models.generate_content.call_args
    prompt = kwargs['contents']
    print("\n--- INICIO DEL PROMPT ENVIADO A GEMINI ---")
    print(prompt[:500] + "...\n[...]\n..." + prompt[-300:])
    print("--- FIN DEL PROMPT ---")
