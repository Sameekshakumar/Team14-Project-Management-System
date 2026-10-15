# Authentication Module - Setup and Testing

## Overview

This module implements the initial authentication functionality for Team 14's Project Management System.

**Scope:** User registration, login, JWT authentication, and the authenticated user profile endpoint.

**Related requirements:** FR-AUTH-01 to FR-AUTH-04
**Related GitHub issue:** #1 - User registration and login

## Technology Stack

- Backend: Django REST Framework
- Authentication: JSON Web Tokens (JWT)
- Frontend: React with Vite
- Database: PostgreSQL
- Containerization: Docker Compose

## Local Setup

1. Configure local environment variables using the supplied example files. Keep actual credentials in untracked `.env` files.
2. Start PostgreSQL using Docker Compose.
3. Create and activate a Python virtual environment.
4. Install backend dependencies from `backend/requirements.txt`.
5. Run Django database migrations.
6. Start the Django development server.
7. Install frontend dependencies from `frontend/package.json` and start the Vite development server.

## Implemented Authentication Flows

- User registration
- Duplicate-email validation
- Login with valid credentials
- Rejection of incorrect passwords
- Email-format validation
- JWT-based authentication
- Authenticated user profile endpoint

## Testing

The backend authentication test suite contains five tests covering registration, duplicate email, valid login, incorrect password, and invalid email.

**Latest recorded test result:** 5 tests passed.

Run the backend tests using the project's configured Python environment and Django test settings.

## Security Notes

- Never commit `.env` files, credentials, or secret keys.
- Use development-only credentials locally.
- Configure production secrets and security settings separately before deployment.

## Current Scope

This is the initial authentication module. Workspace management, workspace membership, roles, and access-control enforcement must be implemented and tested separately if they are not already present.
