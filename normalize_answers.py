import json

# Load answers.json
with open("answers.json", "r", encoding="utf-8") as f:
    data = json.load(f)

def normalize_answers(obj):
    """Recursively normalize all answer entries to standard format"""
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            # If value is a nested dict with quiz questions
            if isinstance(value, dict):
                # Check if it's a quiz section or a standard answer entry
                if "type" in value and "answer" in value:
                    # Convert quiz format to standard format
                    normalized = normalize_quiz_answer(value)
                    result[key] = normalized
                elif "answers" in value:
                    # Already standard format
                    result[key] = {"answers": value["answers"]}
                else:
                    # Might be a nested quiz section, recurse
                    result[key] = normalize_answers(value)
            elif isinstance(value, list):
                # Plain list -> convert to standard format
                result[key] = {"answers": value}
            elif isinstance(value, str):
                # Plain string -> convert to standard format
                result[key] = {"answers": [value]}
            else:
                result[key] = value
        return result
    return obj

def normalize_quiz_answer(quiz_answer):
    """Convert quiz format {"type": "...", "answer": "..."} to standard format"""
    if "answer" in quiz_answer:
        answer_val = quiz_answer["answer"]
        if isinstance(answer_val, list):
            return {"answers": answer_val}
        else:
            return {"answers": [answer_val]}
    return quiz_answer

normalized = normalize_answers(data)

# Save normalized answers.json
with open("answers.json", "w", encoding="utf-8") as f:
    json.dump(normalized, f, indent=4, ensure_ascii=False)

print("✅ answers.json normalized to standard format")
print(f"Total entries: {len(normalized)}")
