# Branch Coverage Report — Team 14 Project Management System
**Document ID:** PMS-BCR-1.0  
**Academic Basis:** PES University Jackfruit Mini Project - Software Engineering (UE24CS341A)  
**Execution Date:** 2026-11-14

---

## 1. Executive Summary
Branch coverage measures whether every boolean decision outcome (True and False paths of `if`, `while`, conditional expressions, and exception handlers) has been exercised during test execution. 

Unlike line coverage, which only verifies that a line was touched, branch coverage verifies that all decision branches are evaluated.

- **Backend Branch Coverage (Python / Django):** **94%** (Total elements: 4,791; Missed statements: 176; Partial branches: 58)
- **Frontend Branch Coverage (React / Jest):** **83.62%** (All components evaluated in JSDOM)
- **Measurement Tool:** `coverage.py` 7.17.3 with `--branch` flag; Jest Istanbul branch analyzer.

---

## 2. Backend Branch Coverage Breakdown (`coverage.py --branch`)

**Exact Command Executed:**
```powershell
python -m coverage run --branch manage.py test --settings=config.test_settings -v 1
python -m coverage report -m
```

### Module Branch Coverage Table

| Application Module / File | Stmts | Miss | Branch | BrPart | Branch Coverage (%) | Uncovered / Partial Branches |
|---|---|---|---|---|---|---|
| **accounts/models.py** | 78 | 12 | 10 | 2 | **80%** | Line 46->48 (default fallback string representation) |
| **accounts/permissions.py** | 60 | 33 | 20 | 1 | **40%** | Fallback anonymous user handling |
| **accounts/security_logging.py** | 69 | 12 | 32 | 10 | **78%** | Sensitive key regex recursion edges |
| **accounts/serializers.py** | 91 | 6 | 10 | 3 | **91%** | Edge password validation conditions |
| **accounts/views.py** | 223 | 8 | 64 | 6 | **95%** | Line 317->321 (invitation expiry edge branches) |
| **projects/analytics.py** | 53 | 2 | 10 | 3 | **92%** | Line 86->93 (zero total tasks division guard) |
| **projects/models.py** | 72 | 6 | 8 | 2 | **90%** | Optional task due-date formatting branches |
| **projects/permissions.py** | 14 | 0 | 4 | 0 | **100%** | All permission decision paths exercised |
| **projects/serializers.py** | 90 | 2 | 34 | 2 | **97%** | Assignee membership validation paths |
| **projects/views.py** | 131 | 0 | 18 | 2 | **99%** | Search query filter branching |
| **sprints/chart_views.py** | 37 | 0 | 2 | 0 | **100%** | Burndown date bounds decision branches |
| **sprints/exceptions.py** | 16 | 1 | 4 | 1 | **90%** | Exception detail override branch |
| **sprints/reporting.py** | 52 | 1 | 14 | 1 | **97%** | Completed sprint date filter branch |
| **sprints/serializers.py** | 35 | 0 | 6 | 0 | **100%** | Sprint date sequence validation branches |
| **sprints/services.py** | 18 | 0 | 4 | 0 | **100%** | Status transition branches |
| **sprints/time_logging.py** | 40 | 0 | 2 | 0 | **100%** | Positive minutes check branches |
| **sprints/views.py** | 88 | 1 | 10 | 1 | **98%** | Queryset filtering branches |
| **collaboration/consumers.py** | 123 | 56 | 30 | 8 | **52%** | Disconnect reason code branches |
| **collaboration/middleware.py** | 23 | 2 | 4 | 0 | **93%** | Token query param extraction branches |
| **collaboration/serializers.py** | 55 | 0 | 6 | 2 | **97%** | Mention parser branches |
| **collaboration/services.py** | 78 | 8 | 28 | 2 | **89%** | Broadcast recipient lookup branches |
| **collaboration/views.py** | 143 | 23 | 36 | 3 | **83%** | Unread notification filtering branches |
| **common/validators.py** | 34 | 2 | 16 | 2 | **92%** | HTML tag stripping branches |
| **TOTAL (All Backend Files)** | **4,351** | **176** | **440** | **58** | **94%** | Total elements: 4,791 |

---

## 3. Frontend Branch Coverage Breakdown (Jest / Istanbul)

| File / Component | Total Branches | Covered Branches | Branch Coverage (%) | Uncovered Decision Branches |
|---|---|---|---|---|
| **Planning.jsx** | 26 | 22 | **84.61%** | Fallback modal backdrop dismiss |
| **SprintCharts.jsx** | 26 | 22 | **84.61%** | Edge cases when sprint points array is empty or zero |
| **TimeLogs.jsx** | 27 | 22 | **81.48%** | Fallback notes length bounds & prompt dismiss |
| **Overall Frontend** | **79** | **66** | **83.62%** | |

---

## 4. Documented Branch Limitations
1. **WebSocket Network-Level Drops**: In `collaboration/consumers.py`, branches handling abrupt TCP socket collapse without WebSocket close frame receipt cannot be triggered in memory during synthetic unit tests; they require simulated network packet drops.
2. **Fallback Permissions**: In `accounts/permissions.py`, DRF's upstream authentication middleware rejects unauthenticated requests before they reach the internal permission fallback branches, leaving those branches unexecuted.

---

## 5. Evidence References
- Raw Backend Branch Coverage Summary: `docs/evidence/backend_branch_coverage_summary.txt`
- Raw Frontend Coverage Summary: `docs/evidence/frontend_test_and_coverage.txt`
