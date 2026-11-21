# Regression tests

Created by CloudMonkey. Run `python -m pytest -q`. Tests reset a disposable database; never supply customer storage. PostgreSQL tests require POSTLANE_TEST_DATABASE_URL with a database named postlane_test. Coverage includes authorization, approvals, provider failure handling and installation operations.
