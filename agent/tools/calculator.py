from __future__ import annotations

import math


ALLOWED_NAMES = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
ALLOWED_NAMES.update({
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
})


def evaluate_expression(expression: str) -> float | int | str:
    """Safely evaluate a math expression.

    Extremely limited eval using math symbols and functions only.
    """
    try:
        code = compile(expression, "<expr>", "eval")
        for name in code.co_names:
            if name not in ALLOWED_NAMES:
                return "Unsupported identifier in expression"
        return eval(code, {"__builtins__": {}}, ALLOWED_NAMES)
    except Exception as exc:
        return f"Error: {exc}"



if __name__ == "__main__":
    # Test the function
    expressions = [
        "2 + 2",
        "sin(pi / 2)",
        "log(100, 10)",
        "sqrt(16) + 3 * (2 - 1)",
        "unknown_func(5)",
        "2 ** 10",
    ]

    for expr in expressions:
        result = evaluate_expression(expr)
        print(f"{expr} = {result}")