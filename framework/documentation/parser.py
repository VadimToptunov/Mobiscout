"""
Code Parser - Extract code structure and documentation
"""

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional


@dataclass
class FunctionDoc:
    """Documentation for a function"""
    name: str
    signature: str
    docstring: Optional[str]
    parameters: List[Dict[str, Any]]
    return_type: Optional[str]
    decorators: List[str] = field(default_factory=list)
    line_number: int = 0


@dataclass
class ClassDoc:
    """Documentation for a class"""
    name: str
    docstring: Optional[str]
    bases: List[str]
    methods: List[FunctionDoc] = field(default_factory=list)
    attributes: List[Dict[str, Any]] = field(default_factory=list)
    decorators: List[str] = field(default_factory=list)
    line_number: int = 0


@dataclass
class ModuleDoc:
    """Documentation for a module"""
    name: str
    path: Path
    docstring: Optional[str]
    classes: List[ClassDoc] = field(default_factory=list)
    functions: List[FunctionDoc] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    constants: Dict[str, Any] = field(default_factory=dict)


class CodeParser:
    """Parse Python code to extract documentation"""

    def parse_file(self, file_path: Path) -> ModuleDoc:
        """Parse a Python file"""
        with open(file_path) as f:
            source = f.read()

        tree = ast.parse(source, filename=str(file_path))

        module_doc = ModuleDoc(
            name=file_path.stem,
            path=file_path,
            docstring=ast.get_docstring(tree),
        )

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_doc = self._parse_class(node)
                module_doc.classes.append(class_doc)
            elif isinstance(node, ast.FunctionDef):
                # Only top-level functions
                if isinstance(getattr(node, "parent", None), ast.Module):
                    func_doc = self._parse_function(node)
                    module_doc.functions.append(func_doc)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    module_doc.imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module_doc.imports.append(node.module)
            elif isinstance(node, ast.Assign):
                # Extract module-level constants
                if isinstance(getattr(node, "parent", None), ast.Module):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            module_doc.constants[target.id] = self._get_value(node.value)

        return module_doc

    def _parse_class(self, node: ast.ClassDef) -> ClassDoc:
        """Parse a class definition"""
        bases = [self._get_name(base) for base in node.bases]
        decorators = [self._get_name(dec) for dec in node.decorator_list]

        class_doc = ClassDoc(
            name=node.name,
            docstring=ast.get_docstring(node),
            bases=bases,
            decorators=decorators,
            line_number=node.lineno,
        )

        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                method_doc = self._parse_function(item)
                class_doc.methods.append(method_doc)
            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        class_doc.attributes.append({
                            "name": target.id,
                            "type": self._get_annotation(item),
                            "value": self._get_value(item.value),
                        })
            elif isinstance(item, ast.AnnAssign):
                if isinstance(item.target, ast.Name):
                    class_doc.attributes.append({
                        "name": item.target.id,
                        "type": self._get_annotation(item),
                        "value": self._get_value(item.value) if item.value else None,
                    })

        return class_doc

    def _parse_function(self, node: ast.FunctionDef) -> FunctionDoc:
        """Parse a function definition"""
        decorators = [self._get_name(dec) for dec in node.decorator_list]

        # Extract parameters
        parameters = []
        for arg in node.args.args:
            param = {
                "name": arg.arg,
                "type": self._get_annotation(arg),
                "default": None,
            }
            parameters.append(param)

        # Add defaults
        defaults = node.args.defaults
        if defaults:
            for i, default in enumerate(defaults):
                param_idx = len(parameters) - len(defaults) + i
                parameters[param_idx]["default"] = self._get_value(default)

        # Get return type
        return_type = self._get_annotation(node) if node.returns else None

        # Build signature
        param_strs = []
        for param in parameters:
            param_str = param["name"]
            if param["type"]:
                param_str += f": {param['type']}"
            if param["default"] is not None:
                param_str += f" = {param['default']}"
            param_strs.append(param_str)

        signature = f"{node.name}({', '.join(param_strs)})"
        if return_type:
            signature += f" -> {return_type}"

        return FunctionDoc(
            name=node.name,
            signature=signature,
            docstring=ast.get_docstring(node),
            parameters=parameters,
            return_type=return_type,
            decorators=decorators,
            line_number=node.lineno,
        )

    def _get_name(self, node: ast.expr) -> str:
        """Get name from AST node"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_name(node.value)}.{node.attr}"
        elif isinstance(node, ast.Subscript):
            return f"{self._get_name(node.value)}[{self._get_name(node.slice)}]"
        elif isinstance(node, ast.Call):
            return self._get_name(node.func)
        else:
            return ast.unparse(node) if hasattr(ast, "unparse") else str(node)

    def _get_annotation(self, node: Any) -> Optional[str]:
        """Get type annotation from node"""
        if hasattr(node, "annotation") and node.annotation:
            return self._get_name(node.annotation)
        elif hasattr(node, "returns") and node.returns:
            return self._get_name(node.returns)
        return None

    def _get_value(self, node: ast.expr) -> Any:
        """Get value from AST node"""
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Num):
            return node.n
        elif isinstance(node, ast.Str):
            return node.s
        elif isinstance(node, ast.NameConstant):
            return node.value
        elif isinstance(node, ast.List):
            return [self._get_value(elt) for elt in node.elts]
        elif isinstance(node, ast.Dict):
            return {
                self._get_value(k): self._get_value(v)
                for k, v in zip(node.keys, node.values)
            }
        else:
            return ast.unparse(node) if hasattr(ast, "unparse") else "..."


class DocstringParser:
    """Parse docstrings in various formats"""

    @staticmethod
    def parse_google_style(docstring: str) -> Dict[str, Any]:
        """Parse Google-style docstring"""
        if not docstring:
            return {}

        sections: Dict[str, Any] = {
            "description": [],
            "args": [],
            "returns": None,
            "raises": [],
            "example": [],
        }

        current_section = "description"
        lines = docstring.split("\n")

        for line in lines:
            line = line.strip()

            if line.startswith("Args:"):
                current_section = "args"
            elif line.startswith("Returns:"):
                current_section = "returns"
            elif line.startswith("Raises:"):
                current_section = "raises"
            elif line.startswith("Example"):
                current_section = "example"
            elif line:
                if current_section == "description":
                    sections["description"].append(line)
                elif current_section == "args":
                    if ":" in line:
                        sections["args"].append(line)
                elif current_section == "returns":
                    if sections["returns"] is None:
                        sections["returns"] = line
                    else:
                        sections["returns"] += " " + line
                elif current_section == "raises":
                    sections["raises"].append(line)
                elif current_section == "example":
                    sections["example"].append(line)

        sections["description"] = " ".join(sections["description"])
        sections["example"] = "\n".join(sections["example"])

        return sections

    @staticmethod
    def parse_numpy_style(docstring: str) -> Dict[str, Any]:
        """Parse NumPy-style docstring"""
        if not docstring:
            return {}

        sections: Dict[str, Any] = {
            "description": [],
            "parameters": [],
            "returns": None,
            "raises": [],
            "examples": [],
        }

        current_section = "description"
        lines = docstring.split("\n")

        for line in lines:
            stripped = line.strip()

            if stripped == "Parameters" or stripped == "----------":
                current_section = "parameters"
            elif stripped == "Returns":
                current_section = "returns"
            elif stripped == "Raises":
                current_section = "raises"
            elif stripped == "Examples":
                current_section = "examples"
            elif stripped:
                if current_section == "description":
                    sections["description"].append(stripped)
                elif current_section == "parameters":
                    sections["parameters"].append(stripped)
                elif current_section == "returns":
                    if sections["returns"] is None:
                        sections["returns"] = stripped
                    else:
                        sections["returns"] += " " + stripped
                elif current_section == "raises":
                    sections["raises"].append(stripped)
                elif current_section == "examples":
                    sections["examples"].append(stripped)

        sections["description"] = " ".join(sections["description"])
        sections["examples"] = "\n".join(sections["examples"])

        return sections
