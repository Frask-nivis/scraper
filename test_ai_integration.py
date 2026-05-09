#!/usr/bin/env python3
"""Test AI integration with questions"""

import json
from ai_solver import OllamaSolver

print("=" * 60)
print("TESTING AI QUESTION SOLVING")
print("=" * 60)

# Initialize AI solver
print("\n1. Initializing AI Solver...")
try:
    ai = OllamaSolver(model="qwen2:1.5b")
    if not ai.model_available:
        print("[ERROR] AI model not available")
        exit(1)
    print("[OK] AI Solver initialized")
except Exception as e:
    print(f"[ERROR] Failed to initialize: {e}")
    exit(1)

# Test simple questions
print("\n2. Testing with sample questions...")

test_questions = [
    {
        "number": 1,
        "text": "Berapa hasil d~ari 2 + 2?",
        "type": "shortanswer",
        "options": []
    },
    {
        "number": 2,
        "text": "Ibukota Prancis adalah?",
        "type": "shortanswer",
        "options": []
    },
    {
        "number": 3,
        "text": "Apakah Python adalah bahasa pemrograman? Benar atau Salah?",
        "type": "truefalse",
        "options": [
            {"index": 0, "label": "Benar"},
            {"index": 1, "label": "Salah"}
        ]
    },
]

for q in test_questions:
    print(f"\nQ{q['number']}: {q['text'][:50]}...")
    try:
        answer = ai.solve_question(q)
        if answer:
            print(f"  -> AI Answer: {answer}")
        else:
            print(f"  -> No answer from AI")
    except Exception as e:
        print(f"  -> Error: {e}")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
