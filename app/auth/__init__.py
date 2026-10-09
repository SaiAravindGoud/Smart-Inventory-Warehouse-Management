from app.auth.dependencies import (
    get_current_user,
    require_admin,
    require_admin_or_inventory_manager,
    require_roles,
    require_warehouse_staff,
)
from app.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)