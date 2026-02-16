#!/bin/bash

echo "========================================"
echo "Gayathri Smart Speak V4 - Setup"
echo "========================================"
echo ""

echo "Step 1: Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed"
    echo "Please install Python 3.10 or higher"
    exit 1
fi
python3 --version
echo ""

echo "Step 2: Creating virtual environment..."
python3 -m venv venv
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to create virtual environment"
    exit 1
fi
echo ""

echo "Step 3: Activating virtual environment..."
source venv/bin/activate
echo ""

echo "Step 4: Installing dependencies..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install dependencies"
    exit 1
fi
echo ""

echo "Step 5: Checking configuration..."
if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found!"
    exit 1
fi

if grep -q "your_api_key_here" .env; then
    echo ""
    echo "========================================"
    echo "IMPORTANT: Configure your API key!"
    echo "========================================"
    echo ""
    echo "Please edit the .env file and add your GROQ API key:"
    echo "  nano .env"
    echo ""
    echo "Replace 'your_api_key_here' with your actual key"
    echo "Get your API key from: https://console.groq.com/"
    echo ""
    exit 0
fi

echo ""
echo "========================================"
echo "Setup Complete!"
echo "========================================"
echo ""
echo "To start the application, run: ./start.sh"
echo "Or manually run: python app.py"
echo ""
