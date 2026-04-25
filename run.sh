#!/bin/bash

# =========================================
# Setup: First-time installation + config
# Usage:
#   ./run.sh setup
#
# Run services only:
#   ./run.sh run
# =========================================

setup() {
    echo "Starting backend setup..."

    cd backend || exit

    if [ ! -d ".venv" ]; then
        echo "Creating virtual environment..."
        if command -v python3 &>/dev/null; then
            python3 -m venv .venv
        else
            python -m venv .venv
        fi
    fi

    echo "Activating virtual environment..."
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
    elif [ -f ".venv/Scripts/activate" ]; then
        source .venv/Scripts/activate
    fi

    pip install -r requirements.txt

    if [ ! -f .env ]; then
        cp .env.example .env
        echo ".env created from .env.example"
        echo "Please edit backend/.env and add:"
        echo "- SUPABASE_URL"
        echo "- POLYMARKET_PRIVATE_KEY"
        echo "- Other required credentials"
    fi

    cd ..

    echo "Starting frontend setup..."

    cd frontend || exit

    npm install

    cd ..

    echo ""
    echo "Setup completed successfully."
    echo "Now run:"
    echo "./run.sh run"
}

run_services() {
    echo "Starting frontend..."

    cd frontend || exit
    npm run dev &
    FRONTEND_PID=$!

    # Clean up the background process when the script exits or is interrupted
    trap "echo 'Stopping services...'; kill $FRONTEND_PID; exit" INT TERM EXIT

    cd ../backend || exit

    echo "Starting backend..."

    if [ -d ".venv" ]; then
        if [ -f ".venv/bin/activate" ]; then
            source .venv/bin/activate
        elif [ -f ".venv/Scripts/activate" ]; then
            source .venv/Scripts/activate
        fi
    else
        echo "Warning: .venv not found. Running without virtual environment. Consider running './run.sh setup'."
    fi

    uvicorn main:app --reload --port 8000
}

case "$1" in
    setup)
        setup
        ;;
    run)
        run_services
        ;;
    *)
        echo "Usage:"
        echo "./run.sh setup   # first-time setup"
        echo "./run.sh run     # start frontend + backend"
        ;;
esac