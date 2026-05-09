#!/usr/bin/env python3
"""Test script to verify fixes for True/False and Ollama"""

import sys
import json

print("=" * 60)
print("TESTING FIXES")
print("=" * 60)

# Test 1: Ollama connection
print("\n1. Testing Ollama API compatibility fix...")
try:
    from ai_solver import OllamaSolver
    solver = OllamaSolver(model="qwen2:1.5b")
    if solver.model_available:
        print("[OK] OllamaSolver initialized successfully")
        print(f"[OK] Model is available: {solver.model}")
    else:
        print("[WARN] Ollama service may not be running")
except Exception as e:
    print(f"[ERROR] Failed to initialize OllamaSolver: {e}")

# Test 2: Check True/False answer normalization
print("\n2. Testing True/False answer normalization...")
try:
    from scraper_engine import ScraperEngine
    engine = ScraperEngine()
    
    test_cases = [
        ("benar", "benar"),
        ("SALAH", "salah"),
        ("'true'", "true"),
        ("'false'", "false"),
        ("the correct answer is 'true'.", "true"),
        ("The correct answer is salah", "salah"),
        ("Benar.", "benar"),
    ]
    
    all_passed = True
    for input_val, expected in test_cases:
        result = engine._normalize_answer_text(input_val)
        status = "[OK]" if result == expected else "[FAIL]"
        if result != expected:
            all_passed = False
        print(f"{status} normalize('{input_val}') -> '{result}' (expected: '{expected}')")
    
    if all_passed:
        print("[OK] All normalization tests passed")
    else:
        print("[WARN] Some normalization tests failed")
        
except Exception as e:
    print(f"[ERROR] Failed normalization test: {e}")

# Test 3: Check answers.json
print("\n3. Checking saved answers...")
try:
    with open("answers.json", "r", encoding="utf-8") as f:
        answers = json.load(f)
    print(f"[OK] Loaded {len(answers)} saved answers")
    
    # Show sample answers
    sample_keys = list(answers.keys())[:3]
    for key in sample_keys:
        val = answers[key]
        if isinstance(val, dict) and "answers" in val:
            print(f"  - '{key[:50]}...' -> {val['answers']}")
        else:
            print(f"  - '{key[:50]}...' -> {val}")
            
except Exception as e:
    print(f"[ERROR] Failed to check answers: {e}")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
