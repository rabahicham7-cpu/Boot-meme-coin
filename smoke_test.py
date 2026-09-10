import os
import sys
import traceback


print("=" * 60)
print("MEME INTELLIGENCE - SMOKE TEST")
print("=" * 60)

print("\n[1] Python version:")
print(sys.version)

print("\n[2] Testing composite_score...")
try:
    import scoring.composite_score
    print("OK - composite_score imported")
except Exception as e:
    print("FAILED - composite_score")
    print(type(e).__name__, str(e))
    traceback.print_exc()

print("\n[3] Testing main...")
try:
    import main
    print("OK - main imported")
except Exception as e:
    print("FAILED - main")
    print(type(e).__name__, str(e))
    traceback.print_exc()

print("\n[4] Environment variables:")
required = [
    "DISCORD_BOT_TOKEN",
    "HELIUS_API_KEY",
    "GOPLUS_APP_KEY",
    "GOPLUS_APP_SECRET",
    "MOBULA_API_KEY",
]

for name in required:
    value = os.getenv(name)
    if value:
        print(f"OK - {name} exists")
    else:
        print(f"MISSING - {name}")

print("\n" + "=" * 60)
print("SMOKE TEST FINISHED")
print("=" * 60)
