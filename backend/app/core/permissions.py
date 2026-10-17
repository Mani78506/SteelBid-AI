"""Role → permission matrix. Enforced server-side on every request."""

ROLES = ["ADMIN", "SALES", "PROCUREMENT", "INVENTORY", "FABRICATION", "ESTIMATOR", "FINANCE", "VIEWER"]

# permission -> roles allowed
PERMISSIONS: dict[str, set[str]] = {
    "org:manage": {"ADMIN"},
    "customers:write": {"ADMIN", "SALES"},
    "inquiries:write": {"ADMIN", "SALES"},
    "quotations:write": {"ADMIN", "SALES", "ESTIMATOR"},
    "quotations:approve": {"ADMIN", "FINANCE"},
    "sales_orders:write": {"ADMIN", "SALES"},
    "materials:write": {"ADMIN", "INVENTORY", "PROCUREMENT"},
    "warehouses:write": {"ADMIN", "INVENTORY"},
    "inventory:transact": {"ADMIN", "INVENTORY"},
    "inventory:adjust": {"ADMIN", "INVENTORY"},  # authorized adjustment
    "suppliers:write": {"ADMIN", "PROCUREMENT"},
    "procurement:write": {"ADMIN", "PROCUREMENT"},
    "procurement:approve": {"ADMIN", "FINANCE"},
    "fabrication:write": {"ADMIN", "FABRICATION"},
    "projects:write": {"ADMIN", "ESTIMATOR"},
    "tenders:write": {"ADMIN", "ESTIMATOR"},
    "tenders:approve_bid": {"ADMIN", "FINANCE"},
    "logistics:write": {"ADMIN", "INVENTORY", "SALES"},
    "finance:write": {"ADMIN", "FINANCE"},
    "market:write": {"ADMIN", "PROCUREMENT", "ESTIMATOR"},
    "ai:use": {"ADMIN", "SALES", "PROCUREMENT", "INVENTORY", "FABRICATION", "ESTIMATOR", "FINANCE"},
    "audit:read": {"ADMIN"},
    "read": {"ADMIN", "SALES", "PROCUREMENT", "INVENTORY", "FABRICATION", "ESTIMATOR", "FINANCE", "VIEWER"},
}


def role_can(role: str, permission: str) -> bool:
    return role in PERMISSIONS.get(permission, set())
