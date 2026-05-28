"""Test: Paella + Pizza sin gluten flows."""
import requests
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
BASE = "http://localhost:8000"

print("=" * 60)
print("  TEST: Paella Valenciana + Pizza Sin Gluten")
print("=" * 60)

# ═══════════════════════════════════════════════════
# TEST 1: Paella Valenciana con ingredientes correctos
# ═══════════════════════════════════════════════════
print("\n── TEST 1: Paella Valenciana ──")
r1 = requests.post(f"{BASE}/api/chat/start")
d1 = r1.json()
sid1 = d1["session_id"]

r2 = requests.post(f"{BASE}/api/chat/message", json={
    "session_id": sid1,
    "message": "Quiero hacer una paella valenciana para 4",
    "ai_mode": "demo"
})
d2 = r2.json()
cart_names = [p["name"].lower() for p in d2["current_cart"]]
print(f"   Cart items: {len(d2['current_cart'])}")
print(f"   Total: {d2['total']}€")
print(f"   Products: {[p['name'][:30] for p in d2['current_cart']]}")
print(f"   Agent logs: {d2.get('agent_logs', [])}")

# Verify: NO salmon, NO chorizo, NO gambas in paella
for bad_ingredient in ["salmón", "chorizo", "gambas", "mejillones", "salchichas"]:
    assert not any(bad_ingredient in name for name in cart_names), \
        f"❌ FAIL: '{bad_ingredient}' found in paella valenciana cart!"

# Verify: arroz should be there
assert any("arroz" in name for name in cart_names), "❌ FAIL: 'arroz' not found in paella!"
print("   ✅ Paella ingredients are correct (no inventions)")

# ═══════════════════════════════════════════════════
# TEST 2: Pizza sin gluten (must add pizza + register allergy)
# ═══════════════════════════════════════════════════
print("\n── TEST 2: Pizza Sin Gluten ──")
r3 = requests.post(f"{BASE}/api/chat/start")
d3 = r3.json()
sid2 = d3["session_id"]

r4 = requests.post(f"{BASE}/api/chat/message", json={
    "session_id": sid2,
    "message": "Quiero una pizza sin gluten",
    "ai_mode": "demo"
})
d4 = r4.json()
print(f"   Action: {d4.get('action', 'N/A')}")
print(f"   Message preview: {d4['mercadin_message'][:100]}...")
print(f"   Cart items: {len(d4['current_cart'])}")
print(f"   Total: {d4['total']}€")
print(f"   Products: {[p['name'][:30] for p in d4['current_cart']]}")

# Key assertion: the cart should NOT be empty — the pizza should be added
assert len(d4["current_cart"]) > 0, "❌ FAIL: Pizza sin gluten returned empty cart!"
assert d4.get("total", 0) > 0, "❌ FAIL: Pizza sin gluten has 0€ total!"
print("   ✅ Pizza sin gluten: cart has products!")

# Verify: no gluten products should be in the cart (masa de pizza, pan, etc.)
# The CSP filter should have removed gluten-containing products
cart_names_2 = [p["name"].lower() for p in d4["current_cart"]]
gluten_words = ["pan ", "harina", "espagueti", "macarron", "galleta", "cereal"]
for gw in gluten_words:
    assert not any(gw in name for name in cart_names_2), \
        f"❌ FAIL: Gluten product '{gw}' found in sin-gluten cart!"
print("   ✅ No gluten products in the cart")

print("\n" + "=" * 60)
print("  ✅ ALL TESTS PASSED!")
print("=" * 60)
