"""
Quick test to verify Ollama installation and connectivity
"""

import sys

print("=" * 60)
print("OLLAMA CONNECTIVITY TEST")
print("=" * 60)

# Test 1: Check if ollama module is installed
print("\n1️⃣  Checking if ollama module is installed...")
try:
    import ollama
    print("   ✅ ollama module found")
    print(f"   Location: {ollama.__file__}")
except ImportError as e:
    print(f"   ❌ ollama module not found: {e}")
    print("   Fix: pip install ollama")
    sys.exit(1)

# Test 2: Check ollama version
print("\n2️⃣  Checking ollama version...")
try:
    print(f"   Version: {ollama.__version__ if hasattr(ollama, '__version__') else 'unknown'}")
except Exception as e:
    print(f"   Could not get version: {e}")

# Test 3: Try to list models
print("\n3️⃣  Attempting to connect to Ollama service...")
try:
    ollama.host = "http://localhost:11434"
    response = ollama.list()
    print(f"   ✅ Connected successfully!")
    print(f"   Response type: {type(response)}")
    print(f"   Response: {response}")
    
    # Handle both dict and custom object responses
    if hasattr(response, 'models'):
        models_list = response.models
    elif isinstance(response, dict) and 'models' in response:
        models_list = response['models']
    else:
        models_list = []
    
    print(f"   Models available: {len(models_list)}")
    
    available_models = []
    for model in models_list:
        if hasattr(model, 'name'):
            model_name = model.name
        elif isinstance(model, dict) and 'name' in model:
            model_name = model['name']
        else:
            model_name = str(model)
        
        print(f"      - {model_name}")
        available_models.append(model_name)

except Exception as e:
    print(f"   ❌ Connection failed: {e}")
    print(f"   Error type: {type(e).__name__}")
    print("   Fix: Make sure Ollama is running")
    print("   In another terminal, run: ollama serve")
    sys.exit(1)

# Test 4: Check for qwen2:1.5b
print("\n4️⃣  Checking for qwen2:1.5b model...")
qwen_found = any('qwen' in m.lower() for m in available_models)

if qwen_found:
    print("   ✅ qwen2:1.5b model is installed")
else:
    print("   ❌ qwen2:1.5b not found")
    print("   Fix: Pull the model with: ollama pull qwen2:1.5b")
    print("   This will download ~4GB, so be patient!")

print("\n" + "=" * 60)
print("✅ All tests passed! Ready to use AI Solver" if qwen_found else "⚠️  Some tests failed. See fixes above.")
print("=" * 60)
