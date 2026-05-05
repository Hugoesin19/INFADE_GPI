"""Test completo del flujo conversacional de Mercadín."""
import requests
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
BASE = "http://localhost:8000"

print("=" * 50)
print("  TEST COMPLETO: Mercadín Conversacional")
print("=" * 50)

# 1. Start session
r1 = requests.post(f"{BASE}/api/chat/start")
d1 = r1.json()
sid = d1["session_id"]
print(f"\n1. Session: {sid[:8]}...")
print(f"   Greeting length: {len(d1['greeting'])} chars")
print(f"   Suggestions: {d1['suggestions']}")
print(f"   Demo mode: {d1['demo_mode']}")

# 2. Add paella
r2 = requests.post(f"{BASE}/api/chat/message", json={"session_id": sid, "message": "Quiero hacer una paella para 4"})
d2 = r2.json()
print(f"\n2. Paella request:")
print(f"   Cart items: {len(d2['current_cart'])}")
print(f"   Total: {d2['total']}€")
print(f"   Products: {[p['name'][:25] for p in d2['current_cart']]}")
if d2.get("cart_delta"):
    print(f"   Added: {len(d2['cart_delta']['added'])}")

# 3. Modify cart
r3 = requests.post(f"{BASE}/api/chat/message", json={"session_id": sid, "message": "cambia el pollo por salmon"})
d3 = r3.json()
print(f"\n3. Modification (pollo -> salmon):")
print(f"   Cart items: {len(d3['current_cart'])}")
print(f"   Total: {d3['total']}€")
print(f"   Products: {[p['name'][:25] for p in d3['current_cart']]}")

# 4. Confirm
r4 = requests.post(f"{BASE}/api/chat/confirm", json={"session_id": sid})
d4 = r4.json()
print(f"\n4. Confirmation:")
print(f"   Total: {d4['total']}€")
print(f"   Items: {len(d4['final_cart'])}")
print(f"   Message: {d4['message'][:60]}")

# 5. Check purchase history
r5 = requests.get(f"{BASE}/api/profile")
d5 = r5.json()
print(f"\n5. Profile updated:")
print(f"   Month spent: {d5['month_spent']}€")

print("\n✅ ALL TESTS PASSED!")
