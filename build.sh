# Deactivate any active conda environment
conda deactivate 2>/dev/null || true

# Clear conda environment variables
unset CONDA_DEFAULT_ENV CONDA_PROMPT_MODIFIER 2>/dev/null || true

# Pull the most recent content for all submodules as configured in .gitmodules
git submodule update --init --remote --progress

# Show the resulting commit checked out for every submodule
git submodule status

# Create a Python virtual environment
python -m venv venv

# Activate the virtual environment
source venv/Scripts/activate

# Install required packages from requirements.txt and sphinx-autobuild
pip install -r requirements.txt

# Initialize Jupyter Book configuration for the book directory
teachbooks build book