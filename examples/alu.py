def alu(a: int, b: int, op: str) -> int:
    if op == "add":
        return (a + b) & 0xFF
    if op == "sub":
        return (a - b) & 0xFF
    if op == "and":
        return a & b
    if op == "or":
        return a | b
    if op == "xor":
        return a ^ b
    raise ValueError(f"Unsupported operation: {op}")
