"""
Question Parser and Classifier Module
Handles parsing quiz questions, classifying types, and extracting metadata.
"""

from enum import Enum
from typing import Dict, List, Optional
import re


class QuestionType(Enum):
    """Supported question types"""
    RADIO = "radio"              # Single choice
    CHECKBOX = "checkbox"        # Multiple choice
    TRUEFALSE = "truefalse"     # True/False
    ESSAY = "essay"              # Open-ended
    SHORTANSWER = "shortanswer" # Short text
    NUMERICAL = "numerical"     # Number input
    UNKNOWN = "unknown"


class QuestionParser:
    """Parse and classify quiz questions"""
    
    def __init__(self):
        self.parsed_cache = {}
        
    def detect_question_type(self, question_element) -> QuestionType:
        """Detect question type from HTML element attributes"""
        try:
            q_class = question_element.get_attribute("class") or ""
            q_class_lower = q_class.lower()
            
            if "truefalse" in q_class_lower:
                return QuestionType.TRUEFALSE
            elif "multichoice" in q_class_lower:
                checkboxes = question_element.locator('input[type="checkbox"]').count()
                if checkboxes > 0:
                    return QuestionType.CHECKBOX
                return QuestionType.RADIO
            elif "essay" in q_class_lower:
                return QuestionType.ESSAY
            elif "shortanswer" in q_class_lower:
                return QuestionType.SHORTANSWER
            elif "numerical" in q_class_lower:
                return QuestionType.NUMERICAL
            
            # Fallback: detect by input type
            radios = question_element.locator('input[type="radio"]').count()
            checkboxes = question_element.locator('input[type="checkbox"]').count()
            textarea = question_element.locator('textarea').count()
            text_input = question_element.locator('input[type="text"]').count()
            
            if checkboxes > 0:
                return QuestionType.CHECKBOX
            elif radios > 0:
                return QuestionType.RADIO
            elif textarea > 0:
                return QuestionType.ESSAY
            elif text_input > 0:
                return QuestionType.SHORTANSWER
                
        except Exception as e:
            print(f"Error detecting question type: {e}")
        
        return QuestionType.UNKNOWN

    def extract_question_text(self, question_element) -> str:
        """Extract question text from element"""
        try:
            qtext = question_element.locator(".qtext")
            if qtext.count() > 0:
                return qtext.inner_text().strip()
        except Exception as e:
            print(f"Error extracting question text: {e}")
        
        return ""

    def extract_options(self, question_element, q_type: QuestionType) -> List[Dict[str, str]]:
        """Extract answer options based on question type"""
        options = []
        
        try:
            if q_type == QuestionType.TRUEFALSE:
                options = self._extract_radio_options(question_element)
            elif q_type == QuestionType.RADIO:
                options = self._extract_radio_options(question_element)
            elif q_type == QuestionType.CHECKBOX:
                options = self._extract_checkbox_options(question_element)
            elif q_type in [QuestionType.ESSAY, QuestionType.SHORTANSWER]:
                options = [{"label": "Open-ended response", "value": ""}]
            elif q_type == QuestionType.NUMERICAL:
                options = [{"label": "Numerical input", "value": ""}]
                
        except Exception as e:
            print(f"Error extracting options: {e}")
        
        return options

    def _extract_radio_options(self, question_element) -> List[Dict[str, str]]:
        """Extract radio button options"""
        options = []
        radios = question_element.locator('input[type="radio"]')
        
        for i in range(radios.count()):
            radio = radios.nth(i)
            try:
                radio_id = radio.get_attribute("id") or ""
                value = radio.get_attribute("value") or ""
                
                label_text = ""
                if radio_id:
                    lbl = question_element.locator(f'label[for="{radio_id}"]')
                    if lbl.count() > 0:
                        label_text = lbl.first.inner_text().strip()
                
                if not label_text:
                    lbl = radio.locator("xpath=following-sibling::label")
                    if lbl.count() > 0:
                        label_text = lbl.first.inner_text().strip()
                
                if label_text or value:
                    options.append({"label": label_text or value, "value": value})
            except Exception as e:
                continue
        
        return options

    def _extract_checkbox_options(self, question_element) -> List[Dict[str, str]]:
        """Extract checkbox options"""
        options = []
        checkboxes = question_element.locator('input[type="checkbox"]')
        
        for i in range(checkboxes.count()):
            checkbox = checkboxes.nth(i)
            try:
                cb_id = checkbox.get_attribute("id") or ""
                value = checkbox.get_attribute("value") or ""
                
                label_text = ""
                if cb_id:
                    lbl = question_element.locator(f'label[for="{cb_id}"]')
                    if lbl.count() > 0:
                        label_text = lbl.first.inner_text().strip()
                
                if not label_text:
                    lbl = checkbox.locator("xpath=following-sibling::label")
                    if lbl.count() > 0:
                        label_text = lbl.first.inner_text().strip()
                
                if label_text or value:
                    options.append({"label": label_text or value, "value": value})
            except Exception as e:
                continue
        
        return options

    def get_question_number(self, question_element) -> Optional[int]:
        """Extract question number"""
        try:
            no_el = question_element.locator(".info .no")
            if no_el.count() > 0:
                text = no_el.inner_text().strip()
                match = re.search(r'\d+', text)
                if match:
                    return int(match.group())
        except Exception as e:
            pass
        
        return None

    def parse_question(self, question_element, question_number: Optional[int] = None) -> Dict:
        """Parse complete question into structured dict"""
        q_type = self.detect_question_type(question_element)
        q_text = self.extract_question_text(question_element)
        q_number = question_number or self.get_question_number(question_element)
        options = self.extract_options(question_element, q_type)
        
        if not q_number:
            q_number = 0
        
        return {
            'number': q_number,
            'text': q_text,
            'type': q_type.value,
            'options': options,
            'metadata': {
                'class': question_element.get_attribute("class") or "",
                'has_feedback': question_element.locator("div.feedback").count() > 0,
                'is_answered': question_element.locator("input:checked").count() > 0
            }
        }

    def batch_parse_questions(self, question_elements) -> List[Dict]:
        """Parse multiple questions efficiently"""
        questions = []
        for i, q_el in enumerate(question_elements):
            try:
                parsed = self.parse_question(q_el, question_number=i+1)
                questions.append(parsed)
            except Exception as e:
                continue
        
        return questions

    def format_for_ai(self, question: Dict) -> str:
        """Format question for AI processing"""
        q_num = question['number']
        q_text = question['text']
        q_type = question['type']
        options = question['options']
        
        formatted = f"[Q{q_num}] {q_text}\n"
        formatted += f"Type: {q_type}\n"
        
        if options and q_type != "essay":
            formatted += "Options:\n"
            for i, opt in enumerate(options, 1):
                formatted += f"  {chr(64+i)}) {opt['label']}\n"
        
        return formatted