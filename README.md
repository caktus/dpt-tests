dpt-tests
=========

Tests for the Caktus django-project-template. To run, first add these variables
to your shell environment:

    export GITHUB_USER="CHANGE-ME"  # should be a dedicated test user
    export GITHUB_PASSWORD="CHANGE-ME"
    export AWS_ACCESS_KEY_ID="CHANGE-ME"
    export AWS_SECRET_ACCESS_KEY="CHANGE-ME"

Next, install build dependencies and run the tests:

    apt-get install python-dev libpq-dev
    mkvirtualenv dpt-tests
    pip install -r requirements.txt
    ./run-tests.py
