# Code Coverage Report — Team 14 Project Management System
**Document ID:** PMS-CCR-1.0  
**Academic Basis:** PES University Jackfruit Mini Project - Software Engineering (UE24CS341A)  
**Execution Date:** 2026-11-14

---

## 1. Executive Summary
This report documents the statement and line code coverage achieved during the execution of all automated test suites on both the Django backend and React frontend.

- **Backend Statement Coverage:** **96%** (4,175 / 4,351 statements executed)
- **Frontend Statement Coverage:** **92.38%** (Line Coverage: **95.33%**)
- **Coverage Measurement Tools:** `coverage.py` 7.17.3 (Backend), Jest 30.5.2 / Istanbul (Frontend)

---

## 2. Backend Code Coverage Breakdown (`coverage.py`)

**Exact Command Executed:**
```powershell
python -m coverage run manage.py test --settings=config.test_settings -v 2
python -m coverage report
```

### Module Breakdown Table

| Application Module | Stmts | Miss | Statement Coverage (%) |
|---|---|---|---|
| **accounts** | 1,489 | 71 | **95.2%** |
| - `accounts/models.py` | 78 | 12 | 85% |
| - `accounts/permissions.py` | 60 | 33 | 45% |
| - `accounts/security_logging.py` | 69 | 12 | 83% |
| - `accounts/serializers.py` | 91 | 6 | 93% |
| - `accounts/views.py` | 223 | 8 | 96% |
| - `accounts/tests*.py` | 1,089 | 0 | 100% |
| **projects** | 772 | 8 | **99.0%** |
| - `projects/models.py` | 72 | 6 | 92% |
| - `projects/permissions.py` | 14 | 0 | 100% |
| - `projects/analytics.py` | 53 | 2 | 96% |
| - `projects/serializers.py` | 90 | 2 | 98% |
| - `projects/views.py` | 131 | 0 | 100% |
| - `projects/tests*.py` | 517 | 0 | 100% |
| **sprints** | 777 | 3 | **99.6%** |
| - `sprints/chart_views.py` | 37 | 0 | 100% |
| - `sprints/models.py` | 39 | 0 | 100% |
| - `sprints/reporting.py` | 52 | 1 | 98% |
| - `sprints/serializers.py` | 35 | 0 | 100% |
| - `sprints/services.py` | 18 | 0 | 100% |
| - `sprints/time_logging.py` | 40 | 0 | 100% |
| - `sprints/views.py` | 88 | 1 | 99% |
| - `sprints/tests*.py` | 526 | 0 | 100% |
| **collaboration** | 489 | 89 | **81.8%** |
| - `collaboration/consumers.py` | 123 | 56 | 54% |
| - `collaboration/middleware.py` | 23 | 2 | 91% |
| - `collaboration/models.py` | 42 | 0 | 100% |
| - `collaboration/services.py` | 78 | 8 | 90% |
| - `collaboration/views.py` | 143 | 23 | 84% |
| - `collaboration/tests*.py` | 208 | 0 | 100% |
| **common** | 101 | 2 | **98.0%** |
| - `common/validators.py` | 34 | 2 | 94% |
| - `common/test_sanitization.py` | 67 | 0 | 100% |
| **config / core** | 723 | 3 | **99.6%** |
| **TOTAL** | **4,351** | **176** | **96%** |

---

## 3. Frontend Code Coverage Breakdown (Jest / Istanbul)

**Exact Command Executed:**
```powershell
npm test -- --coverage --watchAll=false
```

| Component | Statements | Branches | Functions | Lines |
|---|---|---|---|---|
| **Planning.jsx** | 90.21% | 84.61% | 86.00% | 95.31% |
| **SprintCharts.jsx** | 98.21% | 84.61% | 100.00% | 100.00% |
| **TimeLogs.jsx** | 90.32% | 81.48% | 89.47% | 92.00% |
| **TOTAL** | **92.38%** | **83.62%** | **89.53%** | **95.33%** |

---

## 4. Evidence References
- Raw Backend Coverage Summary: `docs/evidence/backend_coverage_summary.txt`
- Raw Frontend Coverage Summary: `docs/evidence/frontend_test_and_coverage.txt`
