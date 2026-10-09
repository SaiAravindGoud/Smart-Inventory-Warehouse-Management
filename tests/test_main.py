
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "message": "Smart Inventory & Warehouse Management System is running"
    }


def test_current_user_requires_authentication():
    response = client.get("/auth/me")
    assert response.status_code in (401, 403)


def test_inventory_requires_authentication():
    response = client.get("/inventory")
    assert response.status_code in (401, 403)


def test_inventory_detail_requires_authentication():
    response = client.get("/inventory/1/1")
    assert response.status_code in (401, 403)


def test_stock_movements_requires_authentication():
    response = client.get("/stock-movements")
    assert response.status_code in (401, 403)


def test_purchase_order_list_requires_authentication():
    response = client.get("/purchase-orders")
    assert response.status_code in (401, 403)


def test_purchase_order_creation_requires_authentication():
    response = client.post("/purchase-orders", json={})
    assert response.status_code in (401, 403)


def test_sales_order_list_requires_authentication():
    response = client.get("/sales-orders")
    assert response.status_code in (401, 403)


def test_sales_order_creation_requires_authentication():
    response = client.post("/sales-orders", json={})
    assert response.status_code in (401, 403)


def test_sales_order_detail_requires_authentication():
    response = client.get("/sales-orders/1")
    assert response.status_code in (401, 403)


def test_sales_order_confirmation_requires_authentication():
    response = client.put("/sales-orders/1/confirm")
    assert response.status_code in (401, 403)


def test_sales_order_dispatch_requires_authentication():
    response = client.put(
        "/sales-orders/1/dispatch",
        json={
            "courier_name": "Test Courier",
            "tracking_number": "TEST-TRACK-001",
        },
    )
    assert response.status_code in (401, 403)


def test_sales_return_list_requires_authentication():
    response = client.get("/sales-returns")
    assert response.status_code in (401, 403)


def test_sales_return_creation_requires_authentication():
    response = client.post("/sales-returns", json={})
    assert response.status_code in (401, 403)


def test_sales_return_detail_requires_authentication():
    response = client.get("/sales-returns/1")
    assert response.status_code in (401, 403)


def test_sales_return_inspection_requires_authentication():
    response = client.put(
        "/sales-returns/1/inspect",
        json={},
    )
    assert response.status_code in (401, 403)


def test_sales_return_refund_requires_authentication():
    response = client.put("/sales-returns/1/refund")
    assert response.status_code in (401, 403)


def test_sales_return_rejection_requires_authentication():
    response = client.put(
        "/sales-returns/1/reject",
        json={},
    )
    assert response.status_code in (401, 403)

def test_audit_log_list_requires_authentication():
    response = client.get("/audit-logs")
    assert response.status_code in (401, 403)
