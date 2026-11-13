"""Select reviewed literal HTML statistics without exporting publisher application code."""

import argparse
from decimal import Decimal
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re


VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}
CONTRACTS = {
    "participation.selected_html_statistics.v1": "participation.native_html_statistics_recipe.v1",
    "participation.selected_html_statistics.v2": "participation.native_html_statistics_recipe.v2",
}


def pin(body):
    return dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest())


class Elements(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.nodes, self.stack = [], []

    def handle_starttag(self, tag, attributes):
        if len(attributes) != len(dict(attributes)):
            raise ValueError("Duplicate native HTML attribute")
        parent = self.stack[-1] if self.stack else None
        index = len(self.nodes)
        self.nodes.append(dict(tag=tag, attributes=dict(attributes), parent=parent,
                               children=[], parts=[], position=self.getpos()))
        if parent is not None:
            self.nodes[parent]["children"].append(index)
            self.nodes[parent]["parts"].append(index)
        if tag not in VOID:
            self.stack.append(index)

    def handle_startendtag(self, tag, attributes):
        self.handle_starttag(tag, attributes)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for position in range(len(self.stack) - 1, -1, -1):
            if self.nodes[self.stack[position]]["tag"] == tag:
                del self.stack[position:]
                return

    def handle_data(self, text):
        if self.stack:
            self.nodes[self.stack[-1]]["parts"].append(text)

    def text(self, index):
        return "".join(self.text(part) if isinstance(part, int) else part
                       for part in self.nodes[index]["parts"])

    def select(self, selector):
        if (not isinstance(selector, dict) or set(selector) - {"tag", "id", "classes", "text"}
                or not isinstance(selector.get("tag"), str)
                or not selector["tag"] or selector["tag"] in {"script", "style"}
                or not isinstance(selector.get("classes", []), list)
                or any(not isinstance(item, str) for item in selector.get("classes", []))):
            raise ValueError("An explicit non-application HTML element selector is required")
        return [i for i, node in enumerate(self.nodes)
                if all((
                    "tag" not in selector or node["tag"] == selector["tag"],
                    "id" not in selector or node["attributes"].get("id") == selector["id"],
                    set(selector.get("classes", [])) <= set(
                        node["attributes"].get("class", "").split()),
                    "text" not in selector or self.text(i).strip() == selector["text"],
                ))]

    def reference(self, index):
        node = self.nodes[index]
        return dict(tag=node["tag"], line=node["position"][0], column=node["position"][1],
                    id=node["attributes"].get("id"),
                    classes=node["attributes"].get("class", "").split())


def value(literal, kind):
    if not isinstance(literal, str) or not literal.strip():
        raise ValueError("An absent native statistic is not a recorded zero")
    if kind == "count":
        if re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)", literal) is None:
            raise ValueError("A literal nonnegative native count is required")
        return int(literal.replace(",", ""))
    if kind == "percentage":
        text = "".join(literal.split())
        if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?%", text) is None:
            raise ValueError("A directly printed native percentage is required")
        if not 0 <= Decimal(text[:-1]) <= 100:
            raise ValueError("Native percentage is outside its stated scale")
        return text
    if kind == "literal":
        return literal
    raise ValueError("Unreviewed native statistic kind")


def validate(selected):
    if (selected["contract"] not in CONTRACTS
            or selected["recipe"]["contract"] != CONTRACTS[selected["contract"]]
            or selected["source"] != selected["recipe"]["source"]
            or selected["whole_publisher_html_redistributed"] is not False):
        raise ValueError("Native HTML statistic selection contract changed")
    recipe = selected["recipe"]
    declarations = recipe["fields"]
    if (len({r["name"] for r in declarations}) != len(declarations)
            or set(selected["fields"]) != {r["name"] for r in declarations}):
        raise ValueError("Complete selected statistic inventory changed")
    for declaration in declarations:
        field = selected["fields"][declaration["name"]]
        expected = declaration.get("expected_matches", 1)
        if (type(expected) is not int or expected < 1
                or set(field) != {"literal", "value", "kind", "native_label", "source_elements"}
                or field["kind"] != declaration["kind"]
                or field["native_label"] != declaration["native_label"]
                or not field["source_elements"]
                or len(field["source_elements"]) != expected
                or type(field["value"]) is not type(value(field["literal"], field["kind"]))
                or field["value"] != value(field["literal"], field["kind"])):
            raise ValueError("Selected statistic differs from its complete native literal")
    if len(selected["assertions"]) != len(recipe["assertions"]):
        raise ValueError("Native election/source assertion inventory changed")
    for declaration, assertion in zip(recipe["assertions"], selected["assertions"]):
        if (assertion["selector"] != declaration["selector"]
                or assertion["value"] != declaration["expected"]
                or assertion["attribute"] != declaration.get("attribute")):
            raise ValueError("Native election/source assertion failed")
    if len(selected["opaque_context"]) != len(recipe.get("opaque_context", [])):
        raise ValueError("Opaque native context inventory changed")
    for declaration, context in zip(recipe.get("opaque_context", []), selected["opaque_context"]):
        if (context["selector"] != declaration["selector"]
                or context["attribute"] != declaration.get("attribute")
                or context["statistical_role_qualified"] is not False):
            raise ValueError("Opaque native fields cannot acquire an inferred statistical role")
    roles = recipe["roles"]
    if set(roles) != {"count", "denominator", "percentage", "clock"}:
        raise ValueError("Complete distinct statistical roles are required")
    present = [name for name in roles.values() if name is not None]
    if (len(set(present)) != len(present) or roles["count"] is None
            or selected["contract"].endswith(".v1") and len(present) != len(roles)):
        raise ValueError("Statistical roles must be distinct")
    fields = selected["fields"]
    if any(roles[role] is not None and (
            roles[role] not in fields or fields[roles[role]]["kind"] != kind) for role, kind in (
            ("count", "count"), ("denominator", "count"),
            ("percentage", "percentage"), ("clock", "literal"))):
        raise ValueError("Native statistical role kinds differ from their reviewed literals")
    count = fields[roles["count"]]["value"]
    if roles["denominator"] is None:
        return selected
    registered = fields[roles["denominator"]]["value"]
    if type(count) is not int or type(registered) is not int or not 0 <= count <= registered or registered <= 0:
        raise ValueError("Native source count/register values require separate review")
    if roles["percentage"] is None:
        return selected
    printed = fields[roles["percentage"]]["value"][:-1]
    decimals = len(printed.partition(".")[2])
    if abs(Decimal(100 * count) / registered - Decimal(printed)) > Decimal(5).scaleb(-decimals-1):
        raise ValueError("Native printed fraction does not reconcile to count/register fields")
    return selected


def extract(body, recipe):
    if (set(recipe) != {"contract", "source", "encoding", "fields", "roles", "assertions", "opaque_context"}
            or recipe["contract"] not in CONTRACTS.values()
            or pin(body) != recipe["source"]["pin"]):
        raise ValueError("An exact pinned original and reviewed HTML statistics recipe are required")
    parser = Elements()
    parser.feed(body.decode(recipe["encoding"]))
    parser.close()

    def single(declaration):
        matches = parser.select(declaration["selector"])
        if len(matches) != 1:
            raise ValueError("Native HTML assertion/context element is absent or ambiguous")
        index = matches[0]
        attribute = declaration.get("attribute")
        literal = (parser.nodes[index]["attributes"].get(attribute)
                   if attribute else parser.text(index).strip())
        return dict(selector=declaration["selector"], attribute=attribute, value=literal,
                    source_element=parser.reference(index))

    assertions = [single(item) for item in recipe["assertions"]]
    context = [dict(single(item), statistical_role_qualified=False) for item in recipe["opaque_context"]]
    fields = {}
    for declaration in recipe["fields"]:
        selector = declaration["selector"]
        matches = parser.select(selector)
        expected = declaration.get("expected_matches", 1)
        if type(expected) is not int or expected < 1 or len(matches) != expected:
            raise ValueError("Native HTML statistic is absent or ambiguous")
        if "following_sibling" in declaration:
            values = []
            allowed = set(parser.select(declaration["following_sibling"]))
            for index in matches:
                node = parser.nodes[index]
                if node["parent"] is None or parser.text(index).strip() != declaration["native_label"]:
                    raise ValueError("Native count label differs from its reviewed literal")
                siblings = parser.nodes[node["parent"]]["children"]
                position = siblings.index(index) + 1
                if position >= len(siblings) or siblings[position] not in allowed:
                    raise ValueError("Native statistic is not the next element beside its own label")
                values.append(siblings[position])
            matches = values
        literals = [parser.text(index).strip() for index in matches]
        if any(literal != literals[0] for literal in literals):
            raise ValueError("Repeated desktop/mobile native statistic disagrees")
        literal = literals[0]
        if "prefix" in declaration:
            prefix = declaration["prefix"]
            if not prefix or not literal.startswith(prefix):
                raise ValueError("Native clock label differs from its reviewed prefix")
            literal = literal[len(prefix):].strip()
        if "suffix" in declaration:
            suffix = declaration["suffix"]
            if not suffix or not literal.endswith(suffix):
                raise ValueError("Native statistic differs from its reviewed suffix")
            literal = literal[:-len(suffix)].strip()
        fields[declaration["name"]] = dict(
            literal=literal, value=value(literal, declaration["kind"]), kind=declaration["kind"],
            native_label=declaration["native_label"],
            source_elements=[parser.reference(index) for index in matches])
    contract = next(name for name, recipe_contract in CONTRACTS.items()
                    if recipe_contract == recipe["contract"])
    return validate(dict(contract=contract,
                         source=recipe["source"], recipe=recipe, fields=fields,
                         assertions=assertions, opaque_context=context,
                         whole_publisher_html_redistributed=False))


def binding_cells(binding, selected, spec, inputs):
    validate(selected)
    name = spec.get("format", {}).get("html_statistics_recipe_input")
    if (name not in inputs or name not in spec["inputs"]
            or json.loads(inputs[name]) != selected["recipe"]
            or selected["source"]["id"] != binding["source_id"]
            or selected["source"]["state_code"] != spec["geography"]["state_code"]
            or selected["source"]["election_year"] != spec["election"]["year"]
            or binding.get("source_role") != "native_registration_ballot_reported_turnout_statistics"):
        raise ValueError("Selected native statistics need their complete reviewed recipe and source scope")
    scope = binding.get("value_scope", "cell")
    if scope == "source":
        actual = selected["source"]
        for key in binding["value_path"].split("."):
            if not isinstance(actual, dict) or key not in actual:
                raise ValueError("Selected native source provenance is absent")
            actual = actual[key]
        if binding.get("parse") != "literal":
            raise ValueError("Source provenance is literal metadata, never a statistical count")
        return [], [dict(value=actual, native_status="literal")]
    if scope != "cell" or binding["measure"] not in selected["fields"]:
        raise ValueError("A direct selected HTML statistic is required")
    selected_field = selected["fields"][binding["measure"]]
    if binding.get("parse") == "count" and selected_field["kind"] != "count":
        raise ValueError("A count must come from its own native count literal")
    if binding.get("native_measure_header") != selected_field["native_label"]:
        raise ValueError("Native statistical label differs from the reviewed source field")
    views = [dict(source_annotations=dict(
        native_column_headers={binding["measure"]: selected_field["native_label"]}))]
    return views, [dict(value=selected_field["value"], native_status="reported")]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True, type=Path)
    parser.add_argument("--recipe", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a new factual selection path")
    result = extract(args.original.read_bytes(), json.loads(args.recipe.read_bytes()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
