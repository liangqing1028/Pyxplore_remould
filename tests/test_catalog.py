import ast

from wpem_desktop.catalog import API_PATH, OPERATIONS, parameters


def test_all_public_scientific_capabilities_are_reachable():
    api = ast.parse(API_PATH.read_text(encoding="utf-8"))
    exported = {node.name for node in api.body if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")}
    direct = {operation.api for operation in OPERATIONS}
    integrated = {"export_refined_cifs", "FileTypeCovert"}
    assert not exported - direct - integrated
    for operation in OPERATIONS:
        fields = parameters(operation)
        assert len({field["key"] for field in fields}) == len(fields)
        assert "return_diagnostics" not in {field["key"] for field in fields}
