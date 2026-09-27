"""Small inventory calculations shared by both entrypoints."""

from decimal import Decimal
from typing import Any


def stock_summary(products: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate inventory value without floating-point rounding."""
    value = sum(
        (Decimal(product["unit_price"]) * product["quantity"] for product in products),
        Decimal("0"),
    )
    return {
        "product_count": len(products),
        "total_units": sum(product["quantity"] for product in products),
        "stock_value": f"{value:.2f}",
    }


def reorder_summary(products: list[dict[str, Any]]) -> dict[str, Any]:
    """List products below their minimum stock level."""
    items = [
        {
            "name": product["name"],
            "units_to_order": product["minimum_stock"] - product["quantity"],
        }
        for product in products
        if product["quantity"] < product["minimum_stock"]
    ]
    return {"items": items, "total_units_to_order": sum(item["units_to_order"] for item in items)}
