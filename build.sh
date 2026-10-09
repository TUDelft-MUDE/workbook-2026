# Deactivate any active conda environment
conda deactivate 2>/dev/null || true

# Clear conda environment variables
unset CONDA_DEFAULT_ENV CONDA_PROMPT_MODIFIER 2>/dev/null || true

# Create a Python virtual environment
python -m venv venv

# Activate the virtual environment
source venv/Scripts/activate

# Install required packages from requirements.txt and sphinx-autobuild
pip install -r requirements.txt

# Initialize Jupyter Book configuration for the book directory
teachbooks build book 2>&1 | grep --line-buffered -v "Replacement link .* already exists in output directory\|^Cloning into"
exit "${PIPESTATUS[0]}"