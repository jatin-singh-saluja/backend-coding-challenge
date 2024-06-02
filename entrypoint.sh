#!/bin/sh
# entrypoint.sh

# Exit immediately if a command exits with a non-zero status
set -e

# Show the current poetry environment to help debug if necessary
poetry env info

# Check if the first argument is pytest or code-quality
if [ "$1" = 'pytest' ]; then
  # Run pytest with any additional arguments passed to the script
  shift
  exec poetry run pytest "$@"
elif [ "$1" = 'code-quality' ]; then
  # Run all code quality checks
  shift
  poetry run black .
  poetry run autopep8 --in-place --recursive .
  poetry run isort .
  poetry run mypy gistapi || true  # Ignore mypy errors
  poetry run flake8 .
else
  # Run the Flask application using poetry
  exec poetry run flask run --host=0.0.0.0 --port=9876
fi
