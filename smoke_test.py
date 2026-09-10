import subprocess
import sys
import traceback


print("=" * 60)
print("MEME INTELLIGENCE - SMOKE TEST")
print("=" * 60)


# --------------------------------------------------
# 1. Python version
# --------------------------------------------------

print("\n[1] Python version:")

print(sys.version)


# --------------------------------------------------
# 2. Compile all Python files
# --------------------------------------------------

print("\n[2] Compiling all Python files...")

result = subprocess.run(
    [
        sys.executable,
        "-m",
        "compileall",
        "-q",
        ".",
    ],
    capture_output=True,
    text=True,
)


if result.returncode == 0:

    print(
        "OK - all Python files compiled successfully"
    )

else:

    print(
        "FAILED - Python compilation error"
    )

    print(result.stdout)
    print(result.stderr)

    sys.exit(1)


# --------------------------------------------------
# 3. Test composite_score
# --------------------------------------------------

print(
    "\n[3] Testing composite_score import..."
)

try:

    import scoring.composite_score

    print(
        "OK - composite_score imported successfully"
    )

except Exception as error:

    print(
        "FAILED - composite_score import"
    )

    print(
        type(error).__name__,
        str(error)
    )

    traceback.print_exc()

    sys.exit(1)


# --------------------------------------------------
# 4. Test composite calculation
# --------------------------------------------------

print(
    "\n[4] Testing composite_score function..."
)

try:

    from scoring.composite_score import (
        calculate_composite_score
    )

    result = calculate_composite_score(

        security_score=80,

        liquidity_score=70,

        holder_score=75,

        trader_analysis={
            "average_score": 65,
            "confidence": 80,
        },

        smart_money_analysis={
            "smart_money_score": 60,
            "confidence": 80,
            "flow": "balanced",
        },

        funding_analysis={
            "risk_score": 20,
            "confidence": 80,
        },
    )

    print(
        "OK - composite calculation works"
    )

    print(
        "Result:",
        result
    )

except Exception as error:

    print(
        "FAILED - composite calculation"
    )

    print(
        type(error).__name__,
        str(error)
    )

    traceback.print_exc()

    sys.exit(1)


# --------------------------------------------------
# 5. Test analysis_engine
# --------------------------------------------------

print(
    "\n[5] Testing analysis_engine import..."
)

try:

    from analysis_engine import (
        analyze_intelligence_layers
    )

    print(
        "OK - analysis_engine imported successfully"
    )

except Exception as error:

    print(
        "FAILED - analysis_engine import"
    )

    print(
        type(error).__name__,
        str(error)
    )

    traceback.print_exc()

    sys.exit(1)


# --------------------------------------------------
# 6. Test required functions
# --------------------------------------------------

print(
    "\n[6] Testing intelligence functions..."
)

try:

    from intelligence.trader_intelligence import (
        analyze_traders
    )

    from intelligence.smart_money import (
        analyze_smart_money
    )

    from intelligence.funding_intelligence import (
        analyze_funding_relationships
    )

    print(
        "OK - Trader Intelligence imported"
    )

    print(
        "OK - Smart Money imported"
    )

    print(
        "OK - Funding Intelligence imported"
    )

except Exception as error:

    print(
        "FAILED - intelligence imports"
    )

    print(
        type(error).__name__,
        str(error)
    )

    traceback.print_exc()

    sys.exit(1)


# --------------------------------------------------
# 7. Test Mobula data layer
# --------------------------------------------------

print(
    "\n[7] Testing Mobula data layer..."
)

try:

    from data.mobula import (
        get_token_trader_positions
    )

    print(
        "OK - Mobula trader function imported"
    )

except Exception as error:

    print(
        "FAILED - Mobula import"
    )

    print(
        type(error).__name__,
        str(error)
    )

    traceback.print_exc()

    sys.exit(1)


# --------------------------------------------------
# Final result
# --------------------------------------------------

print("\n" + "=" * 60)

print(
    "SMOKE TEST PASSED"
)

print("=" * 60)
