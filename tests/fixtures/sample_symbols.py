"""Synthetic SymbolReference.json-shaped fixture used by generator and CLI tests."""

from __future__ import annotations

from typing import Any


def _code(length: int) -> dict[str, Any]:
    return {"Name": "Code", "TypeArguments": [length]}


def _text(length: int) -> dict[str, Any]:
    return {"Name": "Text", "TypeArguments": [length]}


def _integer() -> dict[str, Any]:
    return {"Name": "Integer"}


def _enum(subtype: str) -> dict[str, Any]:
    return {"Name": "Enum", "Subtype": {"Name": subtype}}


def sample_symbols() -> dict[str, Any]:
    """Return a small but representative SymbolReference document."""
    return {
        "EnumTypes": [
            {
                "Name": "Customer Type",
                "Values": [
                    {"Name": "Person"},
                    {"Ordinal": 1, "Name": "Company"},
                ],
            }
        ],
        "EnumExtensionTypes": [
            {
                "TargetObject": "Customer Type",
                "Values": [{"Ordinal": 10, "Name": "Government"}],
            }
        ],
        "Tables": [
            {
                "Name": "Customer",
                "Properties": [{"Name": "Caption", "Value": "Customer"}],
                "Fields": [
                    {"Name": "No.", "TypeDefinition": _code(20)},
                    {"Name": "Name", "TypeDefinition": _text(100)},
                    {
                        "Name": "Email",
                        "TypeDefinition": _text(80),
                        "Properties": [{"Name": "NotBlank", "Value": True}],
                    },
                    {"Name": "Type", "TypeDefinition": _enum("Customer Type")},
                ],
                "Keys": [
                    {"FieldNames": ["No."]},
                    {"FieldNames": ["Email"]},
                ],
            },
            {
                "Name": "Sales Header",
                "Fields": [
                    {"Name": "Document Type", "TypeDefinition": _integer()},
                    {"Name": "No.", "TypeDefinition": _code(20)},
                    {
                        "Name": "Sell-to Customer No.",
                        "TypeDefinition": _code(20),
                        "Properties": [
                            {
                                "Name": "TableRelation",
                                "Value": ('Customer."No." WHERE("Blocked"=CONST(" "))'),
                            }
                        ],
                    },
                ],
                "Keys": [{"FieldNames": ["Document Type", "No."]}],
            },
            {
                "Name": "Sales Line",
                "Fields": [
                    {"Name": "Document Type", "TypeDefinition": _integer()},
                    {
                        "Name": "Document No.",
                        "TypeDefinition": _code(20),
                        "Properties": [
                            {
                                "Name": "TableRelation",
                                "Value": '"Sales Header"."No."',
                            }
                        ],
                    },
                    {"Name": "Line No.", "TypeDefinition": _integer()},
                    {
                        "Name": "Vendor No.",
                        "TypeDefinition": _code(20),
                        "Properties": [
                            {
                                "Name": "TableRelation",
                                "Value": 'Vendor."No."',
                            }
                        ],
                    },
                    {
                        "Name": "Source No.",
                        "TypeDefinition": _code(20),
                        "Properties": [
                            {
                                "Name": "TableRelation",
                                "Value": (
                                    'IF (Type=CONST(Item)) Item."No." '
                                    'ELSE IF (Type=CONST(Resource)) Resource."No."'
                                ),
                            }
                        ],
                    },
                ],
                "Keys": [{"FieldNames": ["Document Type", "Document No.", "Line No."]}],
            },
            {
                "Name": "Item",
                "Fields": [
                    {"Name": "No.", "TypeDefinition": _code(20)},
                ],
                "Keys": [{"FieldNames": ["No."]}],
            },
            {
                "Name": "Resource",
                "Fields": [
                    {"Name": "No.", "TypeDefinition": _code(20)},
                ],
                "Keys": [{"FieldNames": ["No."]}],
            },
            {
                "Name": "Purchase Header",
                "Fields": [
                    {"Name": "Document Type", "TypeDefinition": _integer()},
                    {"Name": "No.", "TypeDefinition": _code(20)},
                ],
                "Keys": [{"FieldNames": ["Document Type", "No."]}],
            },
            {
                "Name": "Purchase Line",
                "Fields": [
                    {"Name": "Document Type", "TypeDefinition": _integer()},
                    {
                        "Name": "Document No.",
                        "TypeDefinition": _code(20),
                        "Properties": [
                            {
                                "Name": "TableRelation",
                                "Value": '"Purchase Header"."No."',
                            }
                        ],
                    },
                    {"Name": "Line No.", "TypeDefinition": _integer()},
                ],
                "Keys": [{"FieldNames": ["Document Type", "Document No.", "Line No."]}],
            },
        ],
        "TableExtensions": [
            {
                "TargetObject": "Customer",
                "Fields": [
                    {"Name": "Loyalty Points", "TypeDefinition": _integer()},
                ],
            }
        ],
    }
