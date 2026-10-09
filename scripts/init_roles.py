#!/usr/bin/env python3
"""
Initialize roles in the database.

This script ensures that all default roles are created in the database.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.storage.connection import get_db_manager
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_roles():
    """Initialize default roles in the database."""
    db_manager = get_db_manager()
    db_manager.initialize()
    
    # SQL to insert default roles
    roles_sql = """
    INSERT INTO roles (role_id, name, description, permissions, is_system_role) VALUES
    ('role-viewer', 'Viewer', 'Read-only access to findings and cases', '{
        "findings.read": true,
        "cases.read": true,
        "detections.read": false,
        "detections.write": false,
        "integrations.read": false,
        "users.read": false,
        "settings.read": false,
        "ai_chat.use": false,
        "tools.invoke": false,
        "mcp.use": false,
        "mcp.admin": false,
        "ai_decisions.approve": false
    }', true),
    ('role-analyst', 'Analyst', 'Full access to findings and cases, limited integrations', '{
        "findings.read": true,
        "findings.write": true,
        "findings.delete": false,
        "cases.read": true,
        "cases.write": true,
        "cases.delete": false,
        "cases.assign": false,
        "detections.read": false,
        "detections.write": false,
        "integrations.read": true,
        "integrations.write": false,
        "users.read": false,
        "settings.read": true,
        "settings.write": false,
        "ai_chat.use": true,
        "tools.invoke": true,
        "mcp.use": true,
        "mcp.admin": false,
        "ai_decisions.approve": false
    }', true),
    ('role-senior-analyst', 'Senior Analyst', 'Full analyst access plus approval rights', '{
        "findings.read": true,
        "findings.write": true,
        "findings.delete": true,
        "cases.read": true,
        "cases.write": true,
        "cases.delete": false,
        "cases.assign": true,
        "detections.read": false,
        "detections.write": false,
        "integrations.read": true,
        "integrations.write": true,
        "users.read": true,
        "settings.read": true,
        "settings.write": false,
        "ai_chat.use": true,
        "tools.invoke": true,
        "mcp.use": true,
        "mcp.admin": false,
        "ai_decisions.approve": true
    }', true),
    ('role-manager', 'Manager', 'User management and all integrations', '{
        "findings.read": true,
        "findings.write": true,
        "findings.delete": true,
        "cases.read": true,
        "cases.write": true,
        "cases.delete": true,
        "cases.assign": true,
        "detections.read": true,
        "detections.write": true,
        "integrations.read": true,
        "integrations.write": true,
        "users.read": true,
        "users.write": true,
        "users.delete": false,
        "settings.read": true,
        "settings.write": true,
        "ai_chat.use": true,
        "tools.invoke": true,
        "mcp.use": true,
        "mcp.admin": true,
        "ai_decisions.approve": true
    }', true),
    ('role-admin', 'Admin', 'Full system access', '{
        "findings.read": true,
        "findings.write": true,
        "findings.delete": true,
        "cases.read": true,
        "cases.write": true,
        "cases.delete": true,
        "cases.assign": true,
        "detections.read": true,
        "detections.write": true,
        "integrations.read": true,
        "integrations.write": true,
        "users.read": true,
        "users.write": true,
        "users.delete": true,
        "settings.read": true,
        "settings.write": true,
        "ai_chat.use": true,
        "tools.invoke": true,
        "mcp.use": true,
        "mcp.admin": true,
        "ai_decisions.approve": true
    }', true)
    ON CONFLICT (role_id) DO NOTHING;
    """

    # The INSERT above is skipped for a role that already exists (ON CONFLICT
    # DO NOTHING), so an upgraded deployment would keep permission maps that
    # lack every key this vocabulary gains -- and a gate naming one of the new
    # permissions would deny every user on that role. The merge adds exactly
    # these keys, and only to system roles: their maps are code-defined (no
    # API mutates them), so restamping the canonical values cannot clobber an
    # operator's edit. Custom roles are never touched.
    role_permission_updates_sql = """
    UPDATE roles SET permissions = permissions || '{
        "detections.read": false,
        "detections.write": false,
        "tools.invoke": false,
        "mcp.use": false,
        "mcp.admin": false
    }'::jsonb
    WHERE role_id = 'role-viewer' AND is_system_role;
    UPDATE roles SET permissions = permissions || '{
        "detections.read": false,
        "detections.write": false,
        "tools.invoke": true,
        "mcp.use": true,
        "mcp.admin": false
    }'::jsonb
    WHERE role_id = 'role-analyst' AND is_system_role;
    UPDATE roles SET permissions = permissions || '{
        "detections.read": false,
        "detections.write": false,
        "tools.invoke": true,
        "mcp.use": true,
        "mcp.admin": false
    }'::jsonb
    WHERE role_id = 'role-senior-analyst' AND is_system_role;
    UPDATE roles SET permissions = permissions || '{
        "detections.read": true,
        "detections.write": true,
        "tools.invoke": true,
        "mcp.use": true,
        "mcp.admin": true
    }'::jsonb
    WHERE role_id = 'role-manager' AND is_system_role;
    UPDATE roles SET permissions = permissions || '{
        "detections.read": true,
        "detections.write": true,
        "tools.invoke": true,
        "mcp.use": true,
        "mcp.admin": true
    }'::jsonb
    WHERE role_id = 'role-admin' AND is_system_role;
    """
    
    try:
        with db_manager.session_scope() as session:
            # Create roles table if it doesn't exist
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS roles (
                    role_id VARCHAR(50) PRIMARY KEY,
                    name VARCHAR(100) UNIQUE NOT NULL,
                    description TEXT NOT NULL,
                    permissions JSONB NOT NULL DEFAULT '{}',
                    is_system_role BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
            """))
            
            # Insert default roles
            session.execute(text(roles_sql))
            # Carry existing system roles up to the current vocabulary; a
            # fresh install already holds these values from the INSERT.
            session.execute(text(role_permission_updates_sql))
            
            # Count roles
            result = session.execute(text("SELECT COUNT(*) FROM roles"))
            count = result.scalar()
            
            logger.info(f"✓ Roles initialized successfully. Total roles: {count}")
            
            # List roles
            result = session.execute(text("SELECT role_id, name, description FROM roles ORDER BY role_id"))
            roles = result.fetchall()
            logger.info("\nAvailable roles:")
            for role in roles:
                logger.info(f"  - {role[0]}: {role[1]} - {role[2]}")
    
    except Exception as e:
        logger.error(f"❌ Failed to initialize roles: {e}")
        raise


if __name__ == "__main__":
    init_roles()

