"""
Unit Tests for AI Solver System
Tests parsing, queue management, AI communication, and storage.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
from question_parser import QuestionParser, QuestionType
from queue_manager import QueueManager, PendingQuestion
from datetime import datetime


class TestQuestionParser(unittest.TestCase):
    """Test question parsing functionality"""
    
    def setUp(self):
        self.parser = QuestionParser()
    
    def test_detect_truefalse_type(self):
        """Test True/False question detection"""
        mock_element = Mock()
        mock_element.get_attribute.return_value = "que truefalse"
        mock_element.locator.return_value.count.return_value = 0
        
        result = self.parser.detect_question_type(mock_element)
        self.assertEqual(result, QuestionType.TRUEFALSE)
    
    def test_detect_radio_type(self):
        """Test radio button (single choice) detection"""
        mock_element = Mock()
        mock_element.get_attribute.return_value = "que multichoice"
        
        radios_mock = Mock()
        radios_mock.count.return_value = 3
        
        checkboxes_mock = Mock()
        checkboxes_mock.count.return_value = 0
        
        def side_effect(selector):
            if 'radio' in selector:
                return radios_mock
            elif 'checkbox' in selector:
                return checkboxes_mock
            return Mock(count=Mock(return_value=0))
        
        mock_element.locator.side_effect = side_effect
        
        result = self.parser.detect_question_type(mock_element)
        self.assertEqual(result, QuestionType.RADIO)
    
    def test_extract_question_text(self):
        """Test question text extraction"""
        mock_element = Mock()
        mock_qtext = Mock()
        mock_qtext.count.return_value = 1
        mock_qtext.inner_text.return_value = "What is 2+2?"
        
        mock_element.locator.return_value = mock_qtext
        
        result = self.parser.extract_question_text(mock_element)
        self.assertEqual(result, "What is 2+2?")
    
    def test_parse_question_complete(self):
        """Test complete question parsing"""
        mock_element = Mock()
        mock_element.get_attribute.return_value = "que truefalse"
        
        # Setup mocks for question text
        qtext_mock = Mock()
        qtext_mock.count.return_value = 1
        qtext_mock.inner_text.return_value = "The sky is blue"
        
        # Setup mocks for question number
        no_mock = Mock()
        no_mock.count.return_value = 1
        no_mock.inner_text.return_value = "1"
        
        # Setup feedback mock
        feedback_mock = Mock()
        feedback_mock.count.return_value = 0
        
        # Setup locator to return appropriate mocks
        def locator_side_effect(selector):
            if selector == ".qtext":
                return qtext_mock
            elif selector == ".info .no":
                return no_mock
            elif selector == "div.feedback":
                return feedback_mock
            elif selector == "input:checked":
                return Mock(count=Mock(return_value=0))
            else:
                return Mock(count=Mock(return_value=0))
        
        mock_element.locator.side_effect = locator_side_effect
        
        result = self.parser.parse_question(mock_element)
        
        self.assertEqual(result['number'], 1)
        self.assertEqual(result['text'], "The sky is blue")
        self.assertEqual(result['type'], "truefalse")


class TestQueueManager(unittest.TestCase):
    """Test queue management functionality"""
    
    def setUp(self):
        self.manager = QueueManager(max_queue_size=100)
    
    def test_add_question(self):
        """Test adding question to queue"""
        success = self.manager.add_question(
            question_number=1,
            question_text="Test question",
            question_type="radio",
            options=[{"label": "A", "value": "1"}],
            quiz_link="http://test.com"
        )
        
        self.assertTrue(success)
        self.assertEqual(self.manager.get_queue_size(), 1)
    
    def test_get_next_question(self):
        """Test retrieving next question"""
        self.manager.add_question(1, "Q1", "radio", [], "http://test.com")
        self.manager.add_question(2, "Q2", "radio", [], "http://test.com")
        
        next_q = self.manager.get_next_question()
        self.assertEqual(next_q.question_number, 1)
    
    def test_mark_processed(self):
        """Test marking question as processed"""
        self.manager.add_question(1, "Q1", "radio", [], "http://test.com")
        
        success = self.manager.mark_processed(1, "Answer: A")
        self.assertTrue(success)
        self.assertEqual(self.manager.get_processed_count(), 1)
        self.assertEqual(self.manager.get_queue_size(), 0)
    
    def test_queue_size_limit(self):
        """Test queue size limit"""
        small_manager = QueueManager(max_queue_size=5)
        
        for i in range(5):
            success = small_manager.add_question(i, f"Q{i}", "radio", [], "http://test.com")
            self.assertTrue(success)
        
        # 6th question should fail
        success = small_manager.add_question(5, "Q5", "radio", [], "http://test.com")
        self.assertFalse(success)
    
    def test_export_queue(self):
        """Test exporting queue state"""
        self.manager.add_question(1, "Q1", "radio", [{"label": "A", "value": "1"}], "http://test.com")
        self.manager.mark_processed(1, "Answer")
        
        import tempfile
        import os
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_file = f.name
        
        try:
            success = self.manager.export_queue(temp_file)
            self.assertTrue(success)
            
            # Verify file exists and has content
            with open(temp_file, 'r') as f:
                import json
                data = json.load(f)
                self.assertIn('processed', data)
                self.assertEqual(len(data['processed']), 1)
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)
    
    def test_retry_mechanism(self):
        """Test retry counter"""
        pq = PendingQuestion(
            question_number=1,
            question_text="Q1",
            question_type="radio",
            options=[],
            quiz_link="http://test.com",
            timestamp=datetime.now().isoformat(),
            max_retries=3
        )
        
        self.assertEqual(pq.attempt_count, 0)
        pq.attempt_count += 1
        self.assertEqual(pq.attempt_count, 1)


class TestMassProcessing(unittest.TestCase):
    """Test handling of large question batches (100+)"""
    
    def test_queue_100_questions(self):
        """Test queueing 100+ questions without memory issues"""
        manager = QueueManager(max_queue_size=200)
        
        for i in range(100):
            success = manager.add_question(
                question_number=i+1,
                question_text=f"Question {i+1}?",
                question_type="radio",
                options=[
                    {"label": f"Option A", "value": "1"},
                    {"label": f"Option B", "value": "2"}
                ],
                quiz_link="http://test.com"
            )
            self.assertTrue(success)
        
        self.assertEqual(manager.get_queue_size(), 100)
    
    def test_batch_processing_efficiency(self):
        """Test processing batch efficiently"""
        manager = QueueManager()
        
        # Add 100 questions
        for i in range(100):
            manager.add_question(i+1, f"Q{i+1}", "radio", [], "http://test.com")
        
        # Simulate processing
        for i in range(50):
            q = manager.get_next_question()
            manager.mark_processed(q.question_number, f"Answer {i+1}")
        
        self.assertEqual(manager.get_processed_count(), 50)
        self.assertEqual(manager.get_queue_size(), 50)


class TestIntegration(unittest.TestCase):
    """Integration tests for complete workflow"""
    
    def test_question_parsing_and_queueing(self):
        """Test parsing question and adding to queue"""
        parser = QuestionParser()
        manager = QueueManager()
        
        # Create mock question element
        mock_element = Mock()
        mock_element.get_attribute.side_effect = lambda x: {
            "class": "que radio"
        }.get(x, "")
        
        # Setup locators
        def locator_side_effect(selector):
            mock = Mock()
            if selector == ".qtext":
                mock.count.return_value = 1
                mock.inner_text.return_value = "What is 2+2?"
            elif selector == ".info .no":
                mock.count.return_value = 1
                mock.inner_text.return_value = "1"
            else:
                mock.count.return_value = 0
            return mock
        
        mock_element.locator.side_effect = locator_side_effect
        
        # Parse question
        parsed = parser.parse_question(mock_element)
        
        # Add to queue
        success = manager.add_question(
            parsed['number'],
            parsed['text'],
            parsed['type'],
            parsed['options'],
            "http://test.com"
        )
        
        self.assertTrue(success)
        self.assertEqual(manager.get_queue_size(), 1)


if __name__ == '__main__':
    unittest.main()