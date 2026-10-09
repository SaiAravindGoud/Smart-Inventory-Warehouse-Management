# Smart Inventory & Warehouse Management System

A REST API built with FastAPI and MySQL to manage warehouse inventory, stock movements, suppliers, purchasing, sales, returns, and reporting.

## Features

- **Authentication and authorization:** JWT-based login and role-based access control.
- **User management:** Admin, Inventory Manager, and Warehouse Staff roles.
- **Warehouse management:** Support warehouse-related inventory operations.
- **Product and category management:** Organize products and categories.
- **Inventory management:** Track stock levels and stock movements.
- **Supplier management:** Maintain supplier records and contact details.
- **Customer management:** Maintain customer information and credit limits.
- **Purchase orders:** Manage purchasing and receiving workflows.
- **Sales orders:** Manage sales orders, confirmation, and dispatch.
- **Sales returns and refunds:** Record returns, inspect returned items, and process eligible refunds.
- **Audit logs:** Track important system operations.
- **Reports:** Dashboard, stock valuation, low-stock, sales, top-products, dead-stock, and supplier-performance reports.
- **Email notifications:** SMTP-based email configuration.
- **Database migrations:** Manage schema changes using Alembic.
- **Automated tests:** Pytest and FastAPI TestClient.

## Technology Stack

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- MySQL and PyMySQL
- Alembic
- JWT authentication
- Uvicorn
- Pytest

## Prerequisites

- Python 3.9 or newer
- MySQL Server
- Git

## Installation

### 1. Clone the repository

Replace `YOUR_GITHUB_REPOSITORY_URL` with your actual GitHub repository URL.

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
cd Smart-Inventory-Warehouse-Management
```

### 2. Create and activate a virtual environment

On Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

The project uses a local `.env` file for configuration.

If you do not already have a `.env` file, create one from the template:

```powershell
Copy-Item .env.example .env
```

If `.env` already exists, **do not overwrite it**. Edit the existing file instead.

Configure your MySQL connection, a strong JWT secret, and SMTP credentials if email notifications are required.

Never commit `.env` or publish real passwords, tokens, or email app passwords.

### 5. Create the MySQL database

Create the database in MySQL:

```sql
CREATE DATABASE smart_inventory_db;
```

Make sure the database name and credentials in `.env` match your local configuration.

### 6. Apply database migrations

```powershell
python -m alembic upgrade head
```

### 7. Start the application

```powershell
python -m uvicorn app.main:app --reload
```

API endpoints:

- API base URL: `http://127.0.0.1:8000`
- Swagger documentation: `http://127.0.0.1:8000/docs`
- ReDoc documentation: `http://127.0.0.1:8000/redoc`

## Running Tests

With the virtual environment activated:

```powershell
python -m pytest -v
```

Tests may require the appropriate database and environment configuration.

## Database Migrations

Check the current migration:

```powershell
python -m alembic current
```

List migration heads:

```powershell
python -m alembic heads
```

Apply migrations:

```powershell
python -m alembic upgrade head
```

## Security Notes

- Keep `.env` private.
- Use strong, unique secrets.
- Never publish database passwords, SMTP credentials, or access tokens.
- Apply appropriate permissions to each user role.
- Use HTTPS and production-grade settings when deploying.

## Project Status

This project is under development. Review the available endpoints, configuration, and automated tests before using it in a production environment.