#!/bin/bash
# coding: utf-8
# SPDX-License-Identifier: CC0-1.0

# Automatically install/upgrade Python dependencies in a virtual environment
# Assumes the venv is in `venv` in the current directory.
# Pip, wheel, and poetry will be upgraded to the latest version. All other
# dependencies are installed based on poetry.lock. This script should be called
# from the root directory of the repository.

source venv/bin/activate

pip install --upgrade pip wheel poetry

poetry install --no-root

deactivate
