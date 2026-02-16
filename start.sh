#!/bin/bash

echo "========================================"
echo "Gayathri Smart Speak V4"
echo "========================================"
echo ""
echo "Starting application..."
echo ""
echo "Access the application at: http://localhost:5000"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

python app.py
