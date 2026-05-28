import pytest
from src.backend.agents import CartState, _demo_culinary_supervisor

def test_culinary_supervisor_removes_inventions():
    """
    Test that the culinary supervisor removes ingredients that don't belong
    to a traditional recipe (statement) like Paella Valenciana.
    """
    state = CartState(
        notes="paella valenciana",
        selected_products=[
            {"id": 1, "name": "Arroz Redondo Hacendado", "subcategory": "arroz", "price": 1.0},
            {"id": 2, "name": "Muslos de pollo", "subcategory": "pollo", "price": 4.0},
            {"id": 3, "name": "Chorizo Extra", "subcategory": "embutido", "price": 2.0}, # INVENTED
            {"id": 4, "name": "Salchichas frescas", "subcategory": "embutido", "price": 2.5}, # INVENTED
            {"id": 5, "name": "Azafrán molido Hacendado", "subcategory": "especias", "price": 3.0}, # LEGIT
            {"id": 6, "name": "Pimentón de la Vera", "subcategory": "especias", "price": 1.5}, # LEGIT
        ],
        agent_logs=[]
    )
    
    new_state = _demo_culinary_supervisor(state)
    
    names = [p["name"] for p in new_state.selected_products]
    
    # Legit ingredients should remain
    assert "Arroz Redondo Hacendado" in names
    assert "Muslos de pollo" in names
    assert "Azafrán molido Hacendado" in names
    assert "Pimentón de la Vera" in names
    
    # Inventions should be blocked
    assert "Chorizo Extra" not in names
    assert "Salchichas frescas" not in names
    
    assert len(new_state.agent_logs) == 1
    assert "Chorizo Extra" in new_state.agent_logs[0]

def test_culinary_supervisor_allows_universals():
    """
    Test that universal ingredients like salt and water are always allowed
    even if they are not explicitly listed in the strict recipe definition.
    """
    state = CartState(
        notes="paella valenciana",
        selected_products=[
            {"id": 1, "name": "Arroz Redondo Hacendado", "subcategory": "arroz", "price": 1.0},
            {"id": 5, "name": "Sal fina", "subcategory": "sal", "price": 0.5},
            {"id": 6, "name": "Agua mineral", "subcategory": "agua", "price": 0.2},
        ],
        agent_logs=[]
    )
    
    new_state = _demo_culinary_supervisor(state)
    assert len(new_state.selected_products) == 3

def test_culinary_supervisor_ignores_non_statements():
    """
    Test that the agent does not touch recipes that are not statements
    (i.e., not in the strict _RECIPE_DB).
    """
    state = CartState(
        notes="receta inventada",
        selected_products=[
            {"id": 1, "name": "Cualquier cosa", "subcategory": "varios", "price": 1.0},
            {"id": 2, "name": "Otra cosa", "subcategory": "varios", "price": 2.0},
        ],
        agent_logs=[]
    )
    
    new_state = _demo_culinary_supervisor(state)
    assert len(new_state.selected_products) == 2
    assert len(new_state.agent_logs) == 0

def test_culinary_supervisor_salmon_blocked_in_paella():
    """
    Test that salmon is NOT allowed in paella valenciana.
    """
    state = CartState(
        notes="paella valenciana",
        selected_products=[
            {"id": 1, "name": "Arroz Redondo Hacendado", "subcategory": "arroz", "price": 1.0},
            {"id": 2, "name": "Filetes de salmón", "subcategory": "pescado fresco", "price": 8.0},
        ],
        agent_logs=[]
    )
    
    new_state = _demo_culinary_supervisor(state)
    names = [p["name"] for p in new_state.selected_products]
    assert "Arroz Redondo Hacendado" in names
    assert "Filetes de salmón" not in names
