"""
AI Solver Module with Ollama Integration (CORRECTED)
Handles local AI communication and answer generation.
"""

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    print("[WARN] Install ollama: pip install ollama")

import re
import time
from typing import Optional, Dict


class OllamaSolver:
    """Interface with local Ollama model for question solving and chat interaction"""
    
    def __init__(self, model: str = "qwen2:1.5b"):
        self.model = model
        self.model_available = False
        self.chat_history = [] # Store recent conversation
        
        if not OLLAMA_AVAILABLE:
            print("[ERROR] ollama module not installed")
            return
        
        # Set host properly
        try:
            # ollama.host = "http://localhost:114~34" # Default
            self.model_available = self._check_model_available()
        except Exception as e:
            print(f"❌ Failed to initialize Ollama: {e}")
    
    def warm_up(self):
        """Load model into RAM to avoid cold-start latency"""
        if not self.model_available:
            return
        try:
            print("[AI] Warming up model...")
            ollama.generate(model=self.model, prompt="hi", options={"num_predict": 1})
            print("[AI] Warm-up complete")
        except Exception as e:
            print(f"[AI] Warm-up skipped: {e}")
    
    def _check_model_available(self) -> bool:
        """Check if model is available"""
        try:
            # Get list of models
            response = ollama.list()
            models = response.get('models', []) if isinstance(response, dict) else response.models if hasattr(response, 'models') else []
            
            model_names = []
            if isinstance(models, list):
                for m in models:
                    try:
                        name = m['name'] if isinstance(m, dict) else (m.name if hasattr(m, 'name') else str(m))
                        model_names.append(name)
                    except:
                        model_names.append(str(m))
            
            print(f"[OK] Connected to Ollama. Models: {model_names}")
            
            # Check for requested model or fallback
            if any(self.model in m for m in model_names):
                print(f"[OK] {self.model} available")
                return True
            
            # Fallback to any available deepseek or qwen
            fallback = next((m for m in model_names if 'deepseek' in m.lower() or 'qwen' in m.lower()), None)
            if fallback:
                print(f"[WARN] {self.model} not found. Using fallback: {fallback}")
                self.model = fallback
                return True
                
            print(f"[WARN] No suitable model found. Run: ollama pull {self.model}")
            return False
                
        except Exception as e:
            print(f"[ERROR] Cannot connect to Ollama: {e}")
            return False

    def chat_with_user(self, user_prompt: str, page_context: Optional[str] = None) -> Dict:
        """Interact with user and browser context. Returns {'response': str, 'js_code': str|None}"""
        if not self.model_available:
            return {"response": "Layanan AI (Ollama) tidak tersedia. Pastikan Ollama sudah berjalan.", "js_code": None}

        # Clear history if it gets too long
        if len(self.chat_history) > 10:
            self.chat_history = self.chat_history[-10:]

        system_prompt = f"""[CRITICAL: ACT AS A WEB BROWSER AUTOMATION ENGINE]
You are a 'Browser Automation Agent' integrated into a Python application. You HAVE full control over the browser via JavaScript.

[NO EXCUSES POLICY]
1. NEVER say "I cannot change the website", "I don't have access", or "I am just an AI". 
2. You CAN change anything on the page (CSS, HTML, DOM) using JavaScript.
3. If asked to change the background, use: document.body.style.backgroundColor = 'black';
4. If asked to find something, use the 'Interactive Elements' data below.
5. If the user asks for an action, ALWAYS provide a 'js_code' block. DO NOT ask for permission, JUST DO IT.

[CURRENT PAGE DATA]
{page_context if page_context else "No context available."}

[CAPABILITIES]
- document.querySelector('...').click()
- document.body.style... (for CSS changes)
- window.scrollTo(0, ...)
- document.querySelectorAll('...').length (for counting)

[RULES]
- Respond in INDONESIAN (Bahasa Indonesia).
- Output MUST be a valid JSON object.
- If no action is possible, explain why in 'response' but NEVER claim lack of technical ability.

[JSON FORMAT]
{{
  "response": "Penjelasan tindakan (sedang melakukan apa)",
  "js_code": "document.body.style.backgroundColor = 'red';" 
}}
"""
        try:
            print(f"[AI Solver] Model: {self.model}")
            print(f"[AI Solver] User Prompt: {user_prompt}")
            
            # Build messages list
            messages = [{'role': 'system', 'content': system_prompt}]
            for h in self.chat_history:
                messages.append(h)
            messages.append({'role': 'user', 'content': user_prompt})

            # We use a timeout to prevent long hangs
            response = ollama.chat(
                model=self.model,
                messages=messages,
                format='json',
                stream=False,
                options={
                    "temperature": 0.1, # Even lower temperature for more focus
                    "num_predict": 1000, # Allow more space if needed
                }
            )
            
            content = response.get('message', {}).get('content', '')
            print(f"[AI Solver] AI Raw Response: {content}")
            
            import json
            try:
                # Clean up any markdown code blocks if AI accidentally includes them
                cleaned_content = re.sub(r'```json\s*|\s*```', '', content).strip()
                parsed = json.loads(cleaned_content)
                
                # Coerce to dict if AI returns a list/other structure
                if isinstance(parsed, list):
                    result = parsed[0] if parsed and isinstance(parsed[0], dict) else {"response": str(parsed), "js_code": None}
                elif isinstance(parsed, dict):
                    result = parsed
                else:
                    result = {"response": str(parsed), "js_code": None}
                
                # Double check for required fields
                if "response" not in result:
                    result["response"] = content
                if "js_code" not in result:
                    result["js_code"] = None
                
                # Update history
                self.chat_history.append({'role': 'user', 'content': user_prompt})
                self.chat_history.append({'role': 'assistant', 'content': content})
                    
                return result
            except json.JSONDecodeError:
                # Fallback if JSON is malformed
                # Still update history for context
                self.chat_history.append({'role': 'user', 'content': user_prompt})
                self.chat_history.append({'role': 'assistant', 'content': content})
                return {"response": content, "js_code": None}
                
        except Exception as e:
            print(f"[AI Chat] Error: {e}")
            return {"response": f"Maaf, saya mengalami gangguan: {str(e)}", "js_code": None}
    
    def _build_prompt(self, question_data: dict) -> str:
        """Build prompt for AI"""
        q_num = question_data.get('number', '?')
        q_text = question_data.get('text', '')
        q_type = question_data.get('type', 'unknown')
        options = question_data.get('options', [])
        
        # DEBUG: Log what we received
        print(f"[DEBUG] Q{q_num}: type={q_type}, {len(options)} options extracted")
        if options:
            for i, opt in enumerate(options):
                print(f"  {chr(64+i+1)}) {opt.get('label', '')[:50]}...")
        
        prompt = f"Question #{q_num}:\n{q_text}\n\n"
        
        if options and len(options) > 0 and q_type != "essay":
            prompt += "Options:\n"
            for i, opt in enumerate(options, 1):
                label = opt.get('label', f'Option {i}')
                prompt += f"{chr(64+i)}) {label}\n"
            
            if q_type == "checkbox":
                prompt += "\nQuestion Type: SELECT MULTIPLE ANSWERS (checkbox)\n"
                prompt += f"Provide answer in format: ANSWER: A, B, C (separate with comma if multiple)\n"
            elif q_type == "radio":
                prompt += "\nQuestion Type: SELECT ONE ANSWER (radio)\n"
                prompt += f"Provide answer in format: ANSWER: A\n"
            else:
                prompt += f"\nProvide answer in format: ANSWER: X\n"
        else:
            prompt += "\nProvide a clear, concise answer to the question.\n"
            print(f"[WARNING] Q{q_num}: No options found or essay type - model will answer freeform")
        
        prompt += "\nBe precise and only provide the letter(s) of the correct option(s)."
        
        return prompt
    
    def solve_question(self, question_data: dict) -> Optional[str]:
        """Solve a single question"""
        if not self.model_available:
            return None
        
        prompt = self._build_prompt(question_data)
        q_num = question_data.get('number', '?')
        
        try:
            print(f"[AI] Solving Q{q_num}...")
            
            response = ollama.generate(
                model=self.model,
                prompt=prompt,
                stream=False
            )
            
            if response and 'response' in response:
                answer = self._extract_answer(response['response'])
                if answer:
                    print(f"[AI] Q{q_num} → {answer}")
                    return answer
                    
        except Exception as e:
            print(f"[AI] Error: {e}")
        
        return None
    
    def _extract_answer(self, text: str) -> Optional[str]:
        """Extract answer from response"""
        # Pattern: ANSWER: X or ANSWER: A, B, C
        match = re.search(r'ANSWER:\s*([A-Z0-9\s\,\-]+?)(?:\n|$)', text, re.IGNORECASE)
        if match:
            answer = match.group(1).strip()
            # Clean up - remove extra spaces, keep comma separators for multiple answers
            answer = re.sub(r'\s+', ' ', answer)
            return answer
        
        # Fallback: look for letters at start of line after "is" or colon
        match = re.search(r'(?:is|answer|jawaban|pilihan)[\s:]*([A-Z](?:\s*,\s*[A-Z])*)', text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        # Last fallback: look for any single letter or letter sequence
        match = re.search(r'\b([A-Z])\b', text)
        if match:
            return match.group(1)
        
        return None


class AsyncAISolver:
    """Async AI solver for non-blocking processing"""
    
    def __init__(self, model: str = "shiraTheAgent"):
        self.solver = OllamaSolver(model=model)
        self.results = {}
        self.processing = False
    
    def start_processing(self, questions: list):
        """Start async processing of questions"""
        import threading
        self.processing = True
        thread = threading.Thread(target=self._process_batch, args=(questions,), daemon=True)
        thread.start()
    
    def _process_batch(self, questions: list):
        """Process batch of questions in background"""
        for question in questions:
            if not self.processing:
                break
            
            answer = self.solver.solve_question(question)
            if answer:
                self.results[question.get("number")] = answer
        
        print(f"[AI] Async processing complete. Solved {len(self.results)} questions")
        self.processing = False
    
    def get_results(self) -> Dict[int, str]:
        """Get results of async processing"""
        return self.results.copy()
    
    def is_done(self) -> bool:
        """Check if processing is complete"""
        return not self.processing
