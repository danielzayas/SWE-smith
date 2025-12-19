#!/bin/bash
set -euxo pipefail

# Try to find conda installation
if [ -f "/root/miniconda3/bin/activate" ]; then
    . /root/miniconda3/bin/activate
elif [ -f "/opt/miniconda3/bin/activate" ]; then
    . /opt/miniconda3/bin/activate
elif [ -f "$HOME/miniconda3/bin/activate" ]; then
    . "$HOME/miniconda3/bin/activate"
else
    echo "Error: Could not find conda installation"
    exit 1
fi

PYTHON_VERSION="${SWESMITH_PYTHON_VERSION:-3.10}"
echo "> Creating conda env 'testbed' with python=${PYTHON_VERSION}"
conda create -n testbed "python=${PYTHON_VERSION}" -yq
conda activate testbed

# Use conda Python explicitly instead of other Python installations
CONDA_PYTHON="$CONDA_PREFIX/bin/python"

echo "> Installing repo in editable mode"
"$CONDA_PYTHON" -m pip install -e .

echo "> Installing test dependencies (extras -> requirements-test.txt -> profile hook)"
if "$CONDA_PYTHON" -m pip install -e ".[test]"; then
    echo "> Installed test dependencies via extras [test]"
elif [ -f "requirements-test.txt" ]; then
    "$CONDA_PYTHON" -m pip install -r requirements-test.txt
    echo "> Installed test dependencies from requirements-test.txt"
elif [ -n "${SWESMITH_PROFILE_INSTALL_CMDS:-}" ]; then
    echo "> Running profile-provided install_cmds: ${SWESMITH_PROFILE_INSTALL_CMDS}"
    eval "${SWESMITH_PROFILE_INSTALL_CMDS}"
else
    echo "> No explicit test dependency source found; continuing without extra test deps"
fi

if [ -n "${SWESMITH_EXTRA_TEST_DEPS:-}" ]; then
    echo "> Installing extra test deps: ${SWESMITH_EXTRA_TEST_DEPS}"
    "$CONDA_PYTHON" -m pip install ${SWESMITH_EXTRA_TEST_DEPS}
fi

echo "> Ensuring pytest available for smoke"
"$CONDA_PYTHON" -m pip install pytest
