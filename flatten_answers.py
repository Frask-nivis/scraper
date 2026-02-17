import json

# Load answers.json
with open("answers.json", "r", encoding="utf-8") as f:
    data = json.load(f)

def flatten_quiz_sections(obj):
    """Flatten nested quiz sections to top level"""
    if not isinstance(obj, dict):
        return obj
    
    result = {}
    for key, value in obj.items():
        if isinstance(value, dict):
            # Check if this is a nested quiz section (all values are dicts with "answers")
            is_quiz_section = all(
                isinstance(v, dict) and "answers" in v 
                for v in value.values()
            )
            
            if is_quiz_section and key not in ("answers",):
                # This is a quiz section, flatten it to top level
                for q_text, q_answers in value.items():
                    result[q_text] = q_answers
            else:
                # Regular entry
                result[key] = value
        else:
            result[key] = value
    
    return result

flattened = flatten_quiz_sections(data)

# Save flattened answers.json
with open("answers.json", "w", encoding="utf-8") as f:
    json.dump(flattened, f, indent=4, ensure_ascii=False)

print("✅ answers.json flattened - nested quiz sections merged to top level")
print(f"Total entries: {len(flattened)}")
