"""Offline deployment preflight; complements, not replaces, strict runtime tests."""
import ast
import sys
from pathlib import Path

def has_assignment(tree, target, module, function, prefix):
    for n in ast.walk(tree):
        if not isinstance(n,ast.Assign) or len(n.targets)!=1:continue
        if not isinstance(n.targets[0],ast.Name) or n.targets[0].id!=target:continue
        call=n.value
        if not isinstance(call,ast.Call) or not isinstance(call.func,ast.Attribute):continue
        if not isinstance(call.func.value,ast.Name) or call.func.value.id!=module or call.func.attr!=function:continue
        if len(call.args)<len(prefix):continue
        if all(isinstance(x,ast.Name) and x.id==name for x,name in zip(call.args,prefix)):
            return True
    return False

def verify(source):
    tree=ast.parse(source)
    functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="publish"]
    if len(functions)!=1:return False
    publish=functions[0]
    return (has_assignment(publish,"published","eligibility","select_public_source_rows",("new","visual_public"))
            and has_assignment(publish,"published","browser_price","apply",("published",)))

def main():
    try:
        if len(sys.argv)!=2 or not verify(Path(sys.argv[1]).read_text(encoding="utf-8")):
            raise ValueError("gate")
    except (OSError,ValueError,SyntaxError):
        print("STOP_SOURCE_PUBLISHER_STRICT_GATE_OR_PRICE_OVERLAY_NOT_FOUND")
        return 2
    print("JAMAICA_PUBLISHER_STRICT_GATE_STRUCTURE=PASS")
    return 0

if __name__=="__main__":raise SystemExit(main())
