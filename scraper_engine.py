import json
import os
import re
import random
import threading
import queue
from time import sleep as wait
from playwright.sync_api import sync_playwright
from question_parser import QuestionParser
from queue_manager import QueueManager
from ai_solver import OllamaSolver, AsyncAISolver

class ScraperEngine:
    def __init__(self, storage_path="storage.json", answers_path="answers.json"):
        self.storage_path = storage_path
        self.answers_path = answers_path
        self.answers = self.load_answers()
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.it_link = "https://itclass.id/course/view.php?id=3"
        
        # Queue-based threading for Playwright operations
        self._operation_queue = queue.Queue()
        self._result_queue = queue.Queue()
        self._worker_thread = None
        self._stop_event = threading.Event()
        self._initialized_event = threading.Event()
        self.question_parser = QuestionParser()
        self.question_queue = QueueManager()
        self.ai_solver = AsyncAISolver(model="shiraTheAgent")
        self.on_progress = None # Callback for progress updates
        
        # Setup submission directory
        self.submission_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "submission")
        if not os.path.exists(self.submission_dir):
            os.makedirs(self.submission_dir)
            print(f"[Worker] Created submission directory: {self.submission_dir}")

        # Warm up AI model in background to avoid first-call latency
        try:
            threading.Thread(target=lambda: getattr(self.ai_solver.solver, "warm_up", lambda: None)(), daemon=True).start()
        except Exception:
            pass

    def load_answers(self):
        if os.path.exists(self.answers_path):
            with open(self.answers_path, "r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return {}
        return {}

    def save_answers(self):
        with open(self.answers_path, "w", encoding="utf-8") as f:
            json.dump(self.answers, f, indent=4, ensure_ascii=False)

    def _update_progress(self, value):
        """Internal helper to call progress callback"""
        if self.on_progress:
            try:
                self.on_progress(value)
            except Exception as e:
                print(f"[Worker] Error in progress callback: {e}")

    def _worker_thread_func(self):
        """Worker thread that runs all Playwright operations"""
        try:
            print("[Worker] Initializing Playwright...")
            self.playwright = sync_playwright().start()
            print("[Worker] Playwright initialized successfully")
            self._initialized_event.set()
            
            while not self._stop_event.is_set():
                try:
                    operation = self._operation_queue.get(timeout=0.1)
                    if operation is None:
                        break
                    
                    op_name, args, kwargs = operation
                    try:
                        print(f"[Worker] Starting operation: {op_name}")
                        if op_name == "start_browser":
                            self._do_start_browser(*args, **kwargs)
                            self._result_queue.put(("success", None))
                        elif op_name == "login":
                            result = self._do_login(*args, **kwargs)
                            self._result_queue.put(("success", result))
                        elif op_name == "get_sections":
                            result = self._do_get_sections(*args, **kwargs)
                            self._result_queue.put(("success", result))
                        elif op_name == "extract_answers":
                            self._do_extract_answers(*args, **kwargs)
                            self._result_queue.put(("success", None))
                        elif op_name == "solve_quiz":
                            self._do_solve_quiz(*args, **kwargs)
                            self._result_queue.put(("success", None))
                        elif op_name == "solve_activity":
                            self._do_solve_activity(*args, **kwargs)
                            self._result_queue.put(("success", None))
                        elif op_name == "solve_assign":
                            self._do_solve_assign(*args, **kwargs)
                            self._result_queue.put(("success", None))
                        elif op_name == "scrap_answers":
                            self._do_scrap_answers(*args, **kwargs)
                            self._result_queue.put(("success", None))
                        elif op_name == "logout":
                            self._do_logout(*args, **kwargs)
                            self._result_queue.put(("success", None))
                        elif op_name == "stop_browser":
                            self._do_stop_browser()
                            self._result_queue.put(("success", None))
                        elif op_name == "chat_with_ai":
                            result = self._do_chat_with_ai(*args, **kwargs)
                            self._result_queue.put(("success", result))
                        else:
                            self._result_queue.put(("error", f"Unknown operation: {op_name}"))
                        print(f"[Worker] Completed operation: {op_name}")
                    except Exception as e:
                        print(f"[Worker] Error in operation {op_name}: {e}")
                        import traceback
                        traceback.print_exc()
                        self._result_queue.put(("error", str(e)))
                except queue.Empty:
                    pass
        except Exception as e:
            print(f"[Worker] Fatal error during initialization: {e}")
            import traceback
            traceback.print_exc()
            # Set the event even on error so main thread doesn't hang
            self._initialized_event.set()
            # Put error in queue for start_browser to pick up
            try:
                self._result_queue.put(("error", f"Worker initialization failed: {str(e)}"))
            except:
                pass
        finally:
            if self.playwright:
                try:
                    self._do_stop_browser()
                except:
                    pass

    def _execute_in_worker(self, op_name, *args, timeout=None, **kwargs):
        """Queue an operation and wait for result"""
        # Check if worker thread is still alive
        if self._worker_thread and not self._worker_thread.is_alive():
            raise RuntimeError("Worker thread has died. Check console for error messages.")
        
        # Set default timeout based on operation type
        if timeout is None:
            if op_name in ("solve_quiz", "solve_activity", "extract_answers", "start_browser", "login", "get_sections", "scrap_answers", "logout"):
                timeout = 180  # 3 minutes for longer browser operations with AI
                print(f"[Worker] Setting timeout {timeout}s for {op_name}")
            elif op_name == "chat_with_ai":
                timeout = 90  # Increased from 30 to 90 for AI inference
                print(f"[Worker] Setting timeout {timeout}s for {op_name}")
            else:
                timeout = 30  # 30 seconds for quick operations
                print(f"[Worker] Setting timeout {timeout}s for {op_name}")
        
        self._operation_queue.put((op_name, args, kwargs))
        try:
            status, result = self._result_queue.get(timeout=timeout)
            if status == "error":
                raise RuntimeError(result)
            return result
        except queue.Empty:
            raise TimeoutError(f"Operation '{op_name}' timed out after {timeout} seconds. Worker thread may be stuck.")

    def _do_start_browser(self, headless=False):
        if not self.browser:
            try:
                # Try to use Microsoft Edge first
                self.browser = self.playwright.chromium.launch(channel="msedge", headless=headless)
                print("[Worker] Using Microsoft Edge browser")
            except Exception as e:
                print(f"[Worker] Microsoft Edge not available ({e}), falling back to Chromium")
                # Fallback to regular Chromium
                self.browser = self.playwright.chromium.launch(headless=headless)
                print("[Worker] Using Chromium browser")
            
            storage_state = None
            if os.path.exists(self.storage_path):
                try:
                    with open(self.storage_path, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                        if content:
                            json.loads(content)
                            storage_state = self.storage_path
                except Exception as e:
                    print(f"[Worker] Warning: Could not load storage state: {e}")
            
            context_kwargs = {
                "viewport": {"width": 1280, "height": 800},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            }
            if storage_state:
                context_kwargs["storage_state"] = storage_state
            
            self.context = self.browser.new_context(**context_kwargs)
            self.page = self.context.new_page()

    def _clear_storage_state(self):
        """Clear the storage state file (for logout operations)"""
        try:
            if os.path.exists(self.storage_path):
                os.remove(self.storage_path)
                print(f"[Worker] Cleared storage state from {self.storage_path}")
        except Exception as e:
            print(f"[Worker] Error clearing storage state: {e}")

    def _do_stop_browser(self):
        if self.context:
            self.context.storage_state(path=self.storage_path)
            self.context.close()
        if self.browser:
            self.browser.close()
        self.context = None
        self.browser = None

    def start_browser(self, headless=False):
        """Start the browser in a dedicated worker thread"""
        if not self._worker_thread:
            self._worker_thread = threading.Thread(target=self._worker_thread_func, daemon=False)
            self._worker_thread.start()
            # Wait for Playwright to initialize with longer timeout
            if not self._initialized_event.wait(timeout=30):
                raise RuntimeError("Worker thread failed to initialize Playwright within 30 seconds")
        
        self._execute_in_worker("start_browser", headless)

    def stop_browser(self):
        """Stop the browser and worker thread"""
        if self._worker_thread:
            self._execute_in_worker("stop_browser")
            self._stop_event.set()
            self._operation_queue.put(None)
            self._worker_thread.join(timeout=5)
            self._worker_thread = None
            self._stop_event.clear()

    def _do_login(self, username, password):
        try:
            self.page.goto(self.it_link, timeout=120000)
        except Exception as e:
            print(f"[Worker] Warning: initial page load timeout: {e}")
            try:
                self.page.wait_for_load_state("networkidle", timeout=60000)
            except Exception:
                pass

        if "Log in" in self.page.content():
            self.page.fill('input[name="username"]', username)
            self.page.fill('input[name="password"]', password)
            self.page.click('button[type="submit"]')
            try:
                self.page.wait_for_load_state("networkidle", timeout=60000)
            except Exception:
                pass
            
            if "Log in" not in self.page.content():
                self.context.storage_state(path=self.storage_path)
                return True
            return False
        return True

    def login(self, username, password):
        """Login - queued to worker thread"""
        if not self._worker_thread:
            self.start_browser()
        return self._execute_in_worker("login", username, password)

    def _do_get_sections(self):
        try:
            self.page.goto(self.it_link, timeout=120000)
            sections_data = []
            
            # Support both old (li.section) and new (div.courseindex-section) Moodle structures
            # Try new courseindex structure first
            sections = self.page.locator("div.courseindex-section")
            count = sections.count()
            
            if count == 0:
                # Fall back to old structure
                sections = self.page.locator("li.section")
                count = sections.count()
                is_old_structure = True
            else:
                is_old_structure = False
            
            for i in range(count):
                section = sections.nth(i)
                
                if is_old_structure:
                    # Old Moodle structure with li.section
                    title_el = section.locator("h3.sectionname")
                    if title_el.count() == 0:
                        continue
                    title = title_el.text_content().strip()
                    if not title or title == "General":
                        continue
                    activity_locs = section.locator("li.activity")
                else:
                    # New courseindex structure with div.courseindex-section
                    # Find the section title (in the courseindex-section-title div)
                    title_el = section.locator("a.courseindex-link")
                    if title_el.count() == 0:
                        continue
                    title = title_el.first.text_content().strip()
                    if not title or title == "General":
                        continue
                    
                    # Activities are inside ul.courseindex-sectioncontent under li.courseindex-item
                    activity_locs = section.locator("ul.courseindex-sectioncontent li.courseindex-item")
                
                activities = []
                
                for j in range(activity_locs.count()):
                    act = activity_locs.nth(j)
                    
                    if is_old_structure:
                        class_attr = act.evaluate("e => e.getAttribute('class')") or ""
                        modtype = "unknown"
                        for c in class_attr.split():
                            if c.startswith("modtype_"):
                                modtype = c.replace("modtype_", "")
                                break
                        
                        name_el = act.locator("span.instancename")
                        name = name_el.inner_text().strip() if name_el.count() > 0 else act.locator(".activity-item").get_attribute("data-activityname")
                        
                        link_el = act.locator("a")
                        link = link_el.first.get_attribute("href") if link_el.count() > 0 else None
                        
                        status_items = act.locator('span[role="listitem"]')
                        info = []
                        for k in range(status_items.count()):
                            itm = status_items.nth(k)
                            text = itm.locator('span.font-weight-normal').inner_text().strip().lower()
                            icon = itm.locator("i")
                            done = False
                            if icon.count() > 0:
                                cls = icon.first.get_attribute("class") or ""
                                if "fa-check" in cls:
                                    done = True
                            info.append({"text": text, "isdone": done})
                    else:
                        # New courseindex structure
                        # Get activity name from courseindex-link or courseindex-name
                        name_el = act.locator("a.courseindex-link")
                        if name_el.count() == 0:
                            name_el = act.locator("span.courseindex-name")
                        name = name_el.first.text_content().strip() if name_el.count() > 0 else "Unknown"
                        
                        # Get activity link
                        link_el = act.locator("a.courseindex-link")
                        link = link_el.first.get_attribute("href") if link_el.count() > 0 else None
                        
                        # Detect module type from link URL (e.g., /mod/quiz/, /mod/lesson/)
                        modtype = "unknown"
                        if link:
                            if "/mod/quiz/" in link:
                                modtype = "quiz"
                            elif "/mod/lesson/" in link:
                                modtype = "lesson"
                            elif "/mod/page/" in link:
                                modtype = "page"
                            elif "/mod/assign/" in link:
                                modtype = "assign"
                            elif "/mod/forum/" in link:
                                modtype = "forum"
                            elif "/mod/scorm/" in link:
                                modtype = "scorm"
                            elif "/mod/url/" in link:
                                modtype = "url"
                        
                        # Get completion status from span.completioninfo
                        info = []
                        completion = act.locator("span.completioninfo")
                        if completion.count() > 0:
                            status_text = "pending"
                            done = False
                            
                            # Check classes on the span itself
                            classes = completion.first.get_attribute("class") or ""
                            if "completion_complete" in classes:
                                status_text = "done"
                                done = True
                            elif "completion_incomplete" in classes:
                                status_text = "incomplete"
                            
                            # Check for nested badges/spans with "To do" or "Done"
                            badges = completion.first.locator("span.badge, span.font-weight-normal")
                            if badges.count() > 0:
                                badge_text = badges.first.inner_text().strip().lower()
                                if "make a submission" in badge_text:
                                    status_text = "make a submission"
                                elif "done" in badge_text:
                                    status_text = "done"
                                    done = True
                            
                            # Check icon
                            icon = completion.first.locator("i")
                            if icon.count() > 0:
                                icon_class = icon.first.get_attribute("class") or ""
                                if "fa-circle" in icon_class and "fa-circle-thin" not in icon_class:
                                    status_text = "done"
                                    done = True
                                elif "fa-circle-thin" in icon_class:
                                    # Already might have more specific text from badges
                                    if status_text == "pending": status_text = "incomplete"
                                elif "fa-check" in icon_class:
                                    status_text = "done"
                                    done = True
                                
                                title_attr = icon.first.get_attribute("title") or ""
                                if title_attr:
                                    status_text = title_attr.lower()
                            
                            info.append({"text": status_text, "isdone": done})
                        
                        # Store full HTML if we're on the assignment page to check requirements later
                        # or just rely on status text
                    
                    if name and link:
                        activities.append({
                            "name": name,
                            "modtype": modtype,
                            "link": link,
                            "status": info
                        })
                
                if activities:  # Only add section if it has activities
                    sections_data.append({
                        "title": title,
                        "activities": activities
                    })
            
            return sections_data
        except Exception as e:
            print(f"[Worker] Error in get_sections: {e}")
            return []  # Return empty list on error

    def get_sections(self):
        """Get sections - queued to worker thread"""
        if not self._worker_thread:
            self.start_browser()
        return self._execute_in_worker("get_sections")

    def norm(self, text):
        return " ".join(text.lower().split())

    def _normalize_answer_text(self, text):
        if not text:
            return ""
        text = text.strip().lower()
        if "the correct answer is" in text:
            text = text.split("the correct answer is", 1)[1]
        text = text.replace("'", "").replace('"', "")
        text = text.strip()
        text = text.rstrip(".?!")
        return " ".join(text.split())

    def _do_extract_answers(self, review_link):
        print(f"Opening review page: {review_link}")
        self.page.goto(review_link, timeout=120000)
        quizzes = self.page.locator("div.que")
        
        new_answers_found = 0
        for i in range(quizzes.count()):
            q = quizzes.nth(i)
            q_type = q.get_attribute("class").lower()
            q_text = q.locator(".qtext").inner_text().strip().lower()
            feedback = q.locator("div.feedback")
            
            if feedback.count() == 0: 
                continue

            # Logic for extracting correct answer from feedback
            right_answer_el = feedback.locator(".rightanswer")
            if right_answer_el.count() > 0:
                raw = right_answer_el.first.inner_text().strip()
                if ":" in raw:
                    correct_answer = raw.split(":", 1)[1].strip()
                else:
                    correct_answer = raw.strip()
                
                # Special cases for True/False
                if "truefalse" in q_type:
                    if "'" in raw:
                        correct_answer = raw.split("'")[1]
                
                # Clean up the answer
                correct_answer = correct_answer.strip()
                
                if q_text not in self.answers:
                    print(f"Found new answer: {q_text} -> {correct_answer}")
                    self.answers[q_text] = {"answers": [correct_answer]}
                    new_answers_found += 1
                else:
                    # Update if different
                    existing_answers = self.answers[q_text]["answers"]
                    if correct_answer not in existing_answers:
                        existing_answers.append(correct_answer)
                        print(f"Updated answer: {q_text} -> {existing_answers}")
                        new_answers_found += 1
        
        if new_answers_found > 0:
            self.save_answers()
            print(f"Extracted {new_answers_found} new answers from review page")
        else:
            print("No new answers found in review page")

    def _get_review_link(self):
        """Find a review link on the current quiz page."""
        review_selectors = [
            'a:has-text("Review")',
            'a:has-text("Review attempt")',
            'a[href*="review.php"]',
            'a[href*="review.php?"]',
            'a:has-text("Review this attempt")',
            'a:has-text("Start review")'
        ]
        for selector in review_selectors:
            review_link_el = self.page.locator(selector)
            if review_link_el.count() > 0:
                href = review_link_el.first.get_attribute("href")
                if href:
                    return href

        # Try to locate a link in a review cell if there is a feedback table
        review_link_el = self.page.locator('td a:has-text("Review")')
        if review_link_el.count() > 0:
            return review_link_el.first.get_attribute("href")

        return None

    def extract_answers_from_review(self, review_link):
        """Extract answers - queued to worker thread"""
        if not self._worker_thread:
            self.start_browser()
        return self._execute_in_worker("extract_answers", review_link)

    def _do_solve_quiz(self, quiz_link):
        self.page.goto(quiz_link, timeout=120000)
        wait(2)
        self.page.wait_for_load_state("networkidle")
        
        # Check if already attempted and score is low
        score_el = self.page.locator("div#feedback, .quizattemptsummary").first
        if score_el.count() > 0:
            try:
                text = score_el.inner_text().strip().lower()
                # Try multiple parsing strategies for score
                import re
                match = re.search(r'([\d\.,]+)\s*/\s*([\d\.,]+)', text)
                if match:
                    curr_score = float(match.group(1).replace(',', '.'))
                    expected = float(match.group(2).replace(',', '.'))
                    
                    if curr_score < expected:
                        print(f"[Worker] Score {curr_score}/{expected} is low, trying to review...")
                        review_el = self.page.locator("td.cell.c3.lastcol a, a:has-text('Review')").first
                        if review_el.count() > 0:
                            self._do_extract_answers(review_el.get_attribute("href"))
                            self.page.goto(quiz_link, timeout=120000)
                else:
                    print(f"[Worker] Could not parse score from: {text[:50]}...")
            except Exception as e:
                print(f"[Worker] Error parsing score: {e}")
        
        # Attempt or Re-attempt or Continue
        attempt_btn = self.page.locator('button[type="submit"], input[type="submit"][value*="Attempt"], input[type="submit"][value*="Continue"]')
        if attempt_btn.count() > 0:
            attempt_btn.first.click()
            start_attempt = self.page.locator('input[type="submit"][value="Start attempt"]')
            if start_attempt.count() > 0:
                start_attempt.click()
            wait(2)
        else:
            print("No attempt button found. Already in quiz?")

        # First pass: Answer all questions on all pages
        print("Starting first pass: answering all questions...")
        self._answer_all_questions()
        
        # Interactive mode: Handle unanswered questions one by one
        print("Starting interactive mode for unanswered questions...")
        self._handle_unanswered_questions_interactive()
        
        # Check final status before finishing
        final_unanswered = self._get_unanswered_questions()
        if final_unanswered:
            print(f"[Worker] ABORTING FINISH: Still {len(final_unanswered)} unanswered questions: {final_unanswered}")
            # Try one more time to solve using AI if answers are missing in DB
            self._handle_unanswered_questions_interactive()
            
            # Re-check after interactive mode
            final_unanswered = self._get_unanswered_questions()
            if final_unanswered:
                print(f"[Worker] CRITICAL: Questions {final_unanswered} are still unanswered. Cannot finish attempt.")
                return # Stop here, do not finish
        
        # Verify we're still on the quiz page
        if not self._is_on_quiz_page():
            print("Not on quiz page anymore, cannot finish attempt")
            return

        # Click "Finish attempt ..." button
        print("Clicking Finish attempt button...")
        finish_btn = self.page.locator('input[type="submit"][value="Finish attempt..."], a:has-text("Finish attempt ...")').first
        if finish_btn.count() > 0:
            finish_btn.click()
            wait(2)
            self.page.wait_for_load_state("networkidle")
        else:
            print("Finish attempt button/link not found - might already be on summary page")

        # Submit all and finish
        submit_all = self.page.locator('button[type="submit"]:has-text("Submit all and finish"), input[type="submit"][value*="Submit all"]').first
        if submit_all.count() > 0:
            submit_all.click()
            wait(2)
        else:
            print("Submit all and finish button not found")
            return
        
        # Handle popup confirmation
        print("Handling confirmation popup...")
        confirm_btn = self.page.locator('button[data-action="save"]:has-text("Submit all and finish"), .moodle-dialogue-base button:has-text("Submit all and finish")').first
        if confirm_btn.count() > 0:
            confirm_btn.click()
            wait(3)
            self.page.wait_for_load_state("networkidle")
        else:
            print("Confirmation button not found")
        # batas kemungkinan kesalahan finish
        # Check final score
        score_el = self.page.locator("td.cell b").first
        if score_el.count() > 0:
            score_text = score_el.inner_text().strip()
            print(f"Final score: {score_text}")
            
            # Extract score numbers
            try:
                if "out of" in score_text:
                    parts = score_text.split("out of")
                    curr_score = float(parts[0].strip())
                    total_score = float(parts[1].split()[0])
                    
                    percentage = (curr_score / total_score) * 100
                    print(f"Score: {curr_score}/{total_score} ({percentage:.1f}%)")
                    
                    # If score is below 95%, try to extract answers from review
                    if percentage < 95:
                        print("Score below 95%, extracting answers from review...")
                        review_link = self._get_review_link()
                        if review_link:
                            self._do_extract_answers(review_link)
            except Exception as e:
                print(f"Could not parse score: {e}")

    def solve_assign(self, assign_link):
        """Solve assignment (upload file) - queued to worker thread"""
        if not self._worker_thread:
            self.start_browser()
        return self._execute_in_worker("solve_assign", assign_link)

    def _do_solve_assign(self, assign_link):
        """Internal worker method to handle assignment submission/upload"""
        try:
            self.page.goto(assign_link, timeout=120000)
            wait(2)
            self.page.wait_for_load_state("networkidle")
            self._update_progress(20)

            # Check if there's a "To do: Make a submission" or "Add submission" button
            submit_btn = self.page.locator('button:has-text("Add submission"), button:has-text("Edit submission"), input[type="submit"][value*="submission"]').first
            if submit_btn.count() > 0:
                submit_btn.click()
                wait(2)
                self.page.wait_for_load_state("networkidle")
                self._update_progress(40)
            
            # Now we should be on the upload page
            file_input = self.page.locator('input[type="file"]').first
            if file_input.count() > 0:
                # Get files from submission directory
                files = os.listdir(self.submission_dir)
                if not files:
                    print(f"[Worker] No files found in {self.submission_dir} to upload.")
                    self._update_progress(0)
                    return
                
                # Pick the first file or a specific one if needed
                file_to_upload = os.path.join(self.submission_dir, files[0])
                print(f"[Worker] Uploading file: {file_to_upload}")
                self._update_progress(60)
                
                # Use set_input_files to upload
                file_input.set_input_files(file_to_upload)
                wait(3)
                self._update_progress(80)
                
                # Click "Save changes"
                save_btn = self.page.locator('input[type="submit"][value="Save changes"], button:has-text("Save changes")').first
                if save_btn.count() > 0:
                    save_btn.click()
                    wait(3)
                    self.page.wait_for_load_state("networkidle")
                    self._update_progress(100)
                    print("[Worker] Assignment submitted successfully")
                else:
                    print("[Worker] Could not find 'Save changes' button")
            else:
                # Maybe drag and drop is required or the file input is hidden
                # Try to find the "Add..." icon button in the filemanager toolbar
                add_icon = self.page.locator('.fp-btn-add a').first
                if add_icon.count() > 0:
                    add_icon.click()
                    wait(2)
                    # This usually opens a "File picker" dialog
                    # Look for "Upload a file" side menu
                    upload_side = self.page.locator('.fp-repo-name:has-text("Upload a file")').first
                    if upload_side.count() > 0:
                        upload_side.click()
                        wait(1)
                    
                    # Look for the actual file input in the dialog
                    dialog_file_input = self.page.locator('input[name="repo_upload_file"]').first
                    if dialog_file_input.count() > 0:
                        files = os.listdir(self.submission_dir)
                        if files:
                            file_to_upload = os.path.join(self.submission_dir, files[0])
                            dialog_file_input.set_input_files(file_to_upload)
                            wait(1)
                            # Click "Upload this file" button
                            upload_btn = self.page.locator('button.fp-upload-btn').first
                            if upload_btn.count() > 0:
                                upload_btn.click()
                                wait(3)
                                # Final save
                                save_btn = self.page.locator('input[type="submit"][value="Save changes"], button:has-text("Save changes")').first
                                if save_btn.count() > 0:
                                    save_btn.click()
                                    wait(3)
                                    print("[Worker] Assignment submitted via file picker")
                else:
                    print("[Worker] Could not find file upload input or add button")
        except Exception as e:
            print(f"[Worker] Error in solve_assign: {e}")

    def _find_navigation_button(self, labels):
        for label in labels:
            btn = self.page.locator(f'button:has-text("{label}")')
            if btn.count() > 0:
                return btn.first
            inp = self.page.locator(f'input[type="submit"][value*="{label}"]')
            if inp.count() > 0:
                return inp.first
        return None

    def _click_navigation_button(self, labels):
        btn = self._find_navigation_button(labels)
        if btn is None or btn.count() == 0:
            return False
        try:
            btn.click()
            wait(2)
            return True
        except Exception as e:
            print(f"Could not click button '{labels}': {e}")
            return False

    def _get_lesson_question_text(self):
        locators = [
            "div#id_pageheadercontainer .contents",
            "div.fcontainer .contents",
            "div.contents",
            "div.questiontext",
            "div#id_pageheader .contents"
        ]
        for selector in locators:
            el = self.page.locator(selector)
            if el.count() > 0:
                text = el.first.inner_text().strip()
                if text:
                    return text.lower()
        return None

    def _force_select_input(self, input_el):
        try:
            if input_el.is_visible():
                input_el.click(force=True)
                wait(0.5)
                if input_el.is_checked():
                    return True
                input_el.check(force=True)
                return True
        except Exception:
            pass

        # Try clicking associated label if input is hidden
        input_id = input_el.get_attribute("id")
        if input_id:
            label = self.page.locator(f'label[for="{input_id}"]')
            if label.count() > 0:
                try:
                    label.first.click(force=True)
                    wait(0.5)
                    return True
                except Exception:
                    pass

        # Fallback: set the input value via JS and dispatch ALL events
        try:
            input_el.evaluate("""el => { 
                el.checked = true; 
                el.dispatchEvent(new Event('input', { bubbles: true })); 
                el.dispatchEvent(new Event('change', { bubbles: true })); 
                el.dispatchEvent(new Event('click', { bubbles: true }));
                // Trigger Moodle's specific auto-save if present
                if (window.M && window.M.core_formchangechecker) {
                    window.M.core_formchangechecker.set_form_changed();
                }
            }""")
            wait(0.5)
            return True
        except Exception as e:
            print(f"Could not force select input: {e}")
            return False

    def _choose_lesson_answer(self, answers):
        answers_norm = [self.norm(a) for a in answers]
        radios = self.page.locator('input[type="radio"]')
        checkboxes = self.page.locator('input[type="checkbox"]')

        def match_option(option):
            label_text = ""
            label_id = option.get_attribute("aria-labelledby")
            if label_id:
                safe_id = label_id.replace(":", "\\:")
                label = self.page.locator(f"#{safe_id}")
                if label.count() > 0:
                    label_text = label.first.inner_text()
            else:
                label = option.locator("xpath=following-sibling::label")
                if label.count() > 0:
                    label_text = label.first.inner_text()
            if not label_text and option.get_attribute("id"):
                label = self.page.locator(f'label[for="{option.get_attribute("id")}"]')
                if label.count() > 0:
                    label_text = label.first.inner_text()
            return self.norm(label_text)

        for i in range(radios.count()):
            radio = radios.nth(i)
            option_text = match_option(radio)
            if any(a in option_text for a in answers_norm):
                return self._force_select_input(radio)
        for i in range(checkboxes.count()):
            cb = checkboxes.nth(i)
            option_text = match_option(cb)
            if any(a in option_text for a in answers_norm):
                return self._force_select_input(cb)
        return False

    def _answer_any_lesson_option(self):
        radios = self.page.locator('input[type="radio"]')
        if radios.count() > 0:
            return self._force_select_input(radios.first)
        checkboxes = self.page.locator('input[type="checkbox"]')
        if checkboxes.count() > 0:
            return self._force_select_input(checkboxes.first)
        return False

    def _handle_lesson_page(self):
        # Detect if current lesson page has a question form
        if self.page.locator('input[type="radio"], input[type="checkbox"]').count() == 0:
            return False

        question_text = self._get_lesson_question_text() or ""
        print(f"Lesson question page detected: {question_text[:80]}")

        matched = None
        for key in self.answers:
            if key in question_text:
                matched = self.answers[key]
                break

        if matched:
            if isinstance(matched, dict) and "answers" in matched:
                answers = matched["answers"]
            elif isinstance(matched, list):
                answers = matched
            elif isinstance(matched, str):
                answers = [matched]
            else:
                answers = []
            if self._choose_lesson_answer(answers):
                print("Selected answer from database")
            else:
                print("Could not match lesson answer from database, selecting first option")
                self._answer_any_lesson_option()
        else:
            print("No lesson answer found in database, selecting first available option")
            self._answer_any_lesson_option()

        submit_btn = self._find_navigation_button(["Submit", "Continue", "Next", "Finish", "Save and continue"])
        if submit_btn:
            submit_btn.click()
            wait(2)
            return True
        return False

    def _lesson_is_complete(self):
        final_text = self.page.locator('text=Congratulations - end of lesson reached')
        if final_text.count() > 0:
            return True
        progress_bar = self.page.locator('.progress-bar.bar')
        if progress_bar.count() > 0:
            try:
                value = int(progress_bar.first.get_attribute('aria-valuenow') or progress_bar.first.inner_text().strip().replace('%',''))
                if value >= 100:
                    return True
            except Exception:
                pass
        completed_badge = self.page.locator('text=Done: Go through the activity to the end')
        if completed_badge.count() > 0 and self.page.locator('text=100%').count() > 0:
            return True
        return False

    def _click_anchor_with_text(self, text):
        anchor = self.page.locator(f'a:has-text("{text}")')
        if anchor.count() > 0:
            try:
                anchor.first.click()
                wait(2)
                return True
            except Exception as e:
                print(f"Could not click anchor '{text}': {e}")
        return False

    def _handle_lesson_resume_prompt(self):
        prompt = self.page.locator('div.box.py-3.generalbox.boxaligncenter')
        if prompt.count() > 0 and "Do you want to start at the last page you saw?" in prompt.first.inner_text():
            print("Lesson resume prompt detected, selecting Yes")
            if self._click_anchor_with_text("Yes"):
                return True
        return False

    def _do_solve_lesson(self, lesson_link):
        self.page.goto(lesson_link)
        wait(2)
        print(f"Starting lesson at {lesson_link}")
        self._update_progress(10) # Start

        # If the lesson start page has a continue button, click it
        self._click_navigation_button(["Continue", "Continue lesson", "Start lesson", "Next"])
        self._handle_lesson_resume_prompt()

        while True:
            # Update progress based on lesson's own progress bar if it exists
            progress_bar = self.page.locator('.progress-bar.bar').first
            if progress_bar.count() > 0:
                try:
                    # Aria-valuenow is 0-100
                    val = progress_bar.get_attribute('aria-valuenow') or progress_bar.inner_text().strip().replace('%','')
                    self._update_progress(float(val))
                except Exception:
                    pass

            if self._lesson_is_complete():
                self._update_progress(100)
                print("Lesson completion detected")
                break

            if self._handle_lesson_page():
                continue

            if self._click_navigation_button(["Evaluation"]):
                continue

            # If there is a progress bar and regular next/evaluation not present, try next
            if self._click_navigation_button(["Next", "Continue"]):
                continue

            # Try any submit button if still not complete
            all_submit = self.page.locator('button[type="submit"], input[type="submit"][value]')
            if all_submit.count() > 0:
                try:
                    all_submit.first.click()
                    wait(2)
                    continue
                except Exception:
                    pass

            print("No further lesson navigation detected")
            break

        # After finishing, save any newly found answers from review pages if available
        if self._lesson_is_complete():
            print("Lesson finished - checking for review links or summary information")
            review_link = self._get_review_link()
            if review_link:
                self._do_extract_answers(review_link)

    def _do_solve_activity(self, activity_link, modtype):
        if modtype == "lesson":
            self._do_solve_lesson(activity_link)
        else:
            self._do_solve_quiz(activity_link)

    def solve_activity(self, activity_link, modtype):
        if not self._worker_thread:
            self.start_browser()
        return self._execute_in_worker("solve_activity", activity_link, modtype)

    def _do_scrap_answers(self, quiz_link):
        """Only go to review page and extract answers, don't attempt quiz"""
        print(f"Scraping answers from {quiz_link}")
        self.page.goto(quiz_link, timeout=120000)
        wait(2)
        
        # Look for review link directly
        review_link = self._get_review_link()
        if review_link:
            print(f"Found review link: {review_link}")
            self._do_extract_answers(review_link)
        else:
            print("No review link found - quiz may not be completed yet")

    def scrap_answers(self, quiz_link):
        """Scrap answers - queued to worker thread"""
        if not self._worker_thread:
            self.start_browser()
        return self._execute_in_worker("scrap_answers", quiz_link)

    def _do_logout(self):
        if self.page is None:
            return

        try:
            logout_el = self.page.locator('a[href*="logout.php"]')
            if logout_el.count() > 0:
                logout_link = logout_el.first.get_attribute("href")
                if logout_link:
                    self.page.goto(logout_link, timeout=120000)
                    wait(2)
                    print(f"[Worker] Logged out via {logout_link}")
                    # Clear storage state after logout
                    self._clear_storage_state()
                    return

            self.page.goto("https://itclass.id/login/logout.php", timeout=120000)
            wait(2)
            print("[Worker] Logged out via fallback logout URL")
            # Clear storage state after logout
            self._clear_storage_state()
        except Exception as e:
            print(f"[Worker] Logout error: {e}")
        finally:
            self._do_stop_browser()

    def logout(self):
        if not self._worker_thread:
            self.start_browser()
        return self._execute_in_worker("logout")

    def chat_with_ai(self, user_prompt: str):
        """Send a chat message to AI and execute any resulting browser commands"""
        if not self._worker_thread:
            self.start_browser()
        return self._execute_in_worker("chat_with_ai", user_prompt)

    def _do_chat_with_ai(self, user_prompt: str):
        """Internal worker method for AI chat and browser command execution"""
        if not self.page:
            return {"response": "Browser belum diinisialisasi. Silakan login atau mulai browser terlebih dahulu.", "js_code": None}

        # Tentukan apakah membutuhkan konteks berat atau cukup ringan
        need_context = any(k in user_prompt.lower() for k in [
            "klik", "click", "scroll", "isi", "fill", "cari", "find", "link", "quiz", "tombol", "button",
            "warna", "background", "buka", "open", "masuk", "navigate", "js", "javascript"
        ])
        try:
            if need_context:
                context = self.page.evaluate("""() => {
                    const getElementInfo = (el) => {
                        const tag = el.tagName.toLowerCase();
                        const id = el.id ? `#${el.id}` : '';
                        const classes = el.className && typeof el.className === 'string' 
                                        ? `.${el.className.split(' ').join('.')}` : '';
                        const text = el.innerText ? el.innerText.trim().substring(0, 50) : '';
                        const value = el.value ? ` [value: ${el.value}]` : '';
                        const placeholder = el.placeholder ? ` [placeholder: ${el.placeholder}]` : '';
                        const type = el.type ? ` [type: ${el.type}]` : '';
                        return `${tag}${id}${classes}${text ? ' ("' + text + '")' : ''}${value}${placeholder}${type}`;
                    };
                    const interactiveElements = Array.from(document.querySelectorAll('button, a, input, select, textarea, [role="button"]'))
                        .filter(el => {
                            const style = window.getComputedStyle(el);
                            return style.display !== 'none' && style.visibility !== 'hidden' && el.offsetWidth > 0;
                        })
                        .slice(0, 50)
                        .map(getElementInfo)
                        .join('\\n');
                    const headings = Array.from(document.querySelectorAll('h1, h2, h3'))
                        .map(el => `${el.tagName.toLowerCase()}: ${el.innerText.trim()}`)
                        .join('\\n');
                    const linksCount = document.querySelectorAll('a[href]').length;
                    return `URL: ${window.location.href}\\nTitle: ${document.title}\\nLinks: ${linksCount}\\n\\nHeadings:\\n${headings}\\n\\nInteractive Elements:\\n${interactiveElements}`.substring(0, 4000);
                }""")
            else:
                context = self.page.evaluate("""() => `URL: ${window.location.href}\\nTitle: ${document.title}`""")
        except Exception as e:
            print(f"[Worker] Error getting page context: {e}")
            context = "Gagal mengambil konteks halaman."

        # Call the AI
        print(f"[Worker] Sending prompt to AI: {user_prompt[:50]}...")
        result = self.ai_solver.solver.chat_with_user(user_prompt, context)
        if not isinstance(result, dict):
            try:
                result = {"response": str(result), "js_code": None}
            except Exception:
                result = {"response": "AI mengembalikan format tidak dikenal.", "js_code": None}
        
        # Execute any JS code provided by the AI
        js_code = result.get("js_code")
        
        # Security/Sanity check: AI sometimes outputs "null" as a string or placeholders
        if js_code and isinstance(js_code, str):
            js_code = js_code.strip()
            # Ignore "null", "None", or placeholder code
            if js_code.lower() in ("null", "none", "") or "..." in js_code:
                print(f"[Worker] AI JS skipped (placeholder or null): {js_code}")
                js_code = None

        if js_code:
            try:
                print(f"[Worker] AI executing JS: {js_code}")
                # Use a more robust execution
                self.page.evaluate(js_code)
                # Wait for any network activity or navigation to settle
                try:
                    self.page.wait_for_load_state("networkidle", timeout=5000)
                except:
                    pass
                wait(1)
                result["execution_status"] = "Success"
            except Exception as e:
                print(f"[Worker] AI JS execution error: {e}")
                result["execution_status"] = f"Failed: {str(e)}"
        
        return result

    def _is_quiz_accessible(self, activity):
        """Check if quiz is accessible based on completion/requirement status."""
        if not activity.get("link"):
            return False

        # If it's already done, definitely accessible
        if any(s["isdone"] for s in activity["status"]):
            return True

        # Check for explicit locked/restricted indicators in status text
        locked_keywords = ["locked", "restricted", "unavailable", "require", "prerequisite", "not available"]
        for s in activity["status"]:
            text = s.get("text", "").lower()
            if any(keyword in text for keyword in locked_keywords):
                return False

        # If there is no explicit lock text, assume the quiz can be accessed.
        return True

    def _handle_unanswered_questions_interactive(self):
        """Handle unanswered questions interactively - improved for persistence"""
        max_attempts = 50  # Prevent infinite loops
        max_attempts_per_question = 5  # Skip question if fails this many times
        attempt_count = 0
        failed_questions = {}  # Track failed attempts per question
        
        while attempt_count < max_attempts:
            attempt_count += 1
            
            # First check if we're still on quiz page
            if not self._is_on_quiz_page():
                print("[Worker] No quiz indicators found - not on quiz page")
                break
                
            unanswered = self._get_unanswered_questions()
            if not unanswered:
                print("[Worker] All questions answered!")
                break
            
            # Filter out questions that have failed too many times
            available_questions = [q for q in unanswered if failed_questions.get(q, 0) < max_attempts_per_question]
            if not available_questions:
                print(f"[Worker] All remaining {len(unanswered)} questions failed too many times. Giving up.")
                break
                
            # Get the first available unanswered question
            q_num = available_questions[0]
            print(f"[Worker] Navigating to unanswered question {q_num} (attempt {attempt_count})")
            
            if not self._go_to_question(q_num):
                print(f"[Worker] Failed to navigate to question {q_num}")
                failed_questions[q_num] = failed_questions.get(q_num, 0) + 1
                continue
                
            wait(1.5)
            
            # Double-check we're still on quiz page after navigation
            if not self._is_on_quiz_page():
                print("[Worker] Navigation took us away from quiz page")
                break
            
            # Try to answer it automatically first (from database)
            # Find the actual question container for THIS question number
            question = self.page.locator(f"div.que:has(.no:has-text('{q_num}'))").first
            if question.count() == 0:
                # Fallback to first .que if specific one not found
                question = self.page.locator(".que").first
                
            answered = self._smart_answer(question)
            
            if not answered:
                # No answer in database - use AI to solve
                print(f"[Worker] Question {q_num} not in database. Using AI to solve...")
                answered = self._solve_with_ai_fallback(question, q_num)
            
            if answered:
                print(f"[Worker] Question {q_num} answered successfully")
                # Force a small wait for Moodle auto-save
                wait(2)
                
                # Verify status
                updated_unanswered = self._get_unanswered_questions()
                if q_num in updated_unanswered:
                    failed_questions[q_num] = failed_questions.get(q_num, 0) + 1
                    print(f"[Worker] Warning: Question {q_num} still shows as unanswered (fail count: {failed_questions[q_num]}/{max_attempts_per_question})")
                else:
                    print(f"[Worker] Confirmed: Question {q_num} is now answered")
                    failed_questions[q_num] = 0
            else:
                failed_questions[q_num] = failed_questions.get(q_num, 0) + 1
                print(f"[Worker] Question {q_num} could not be answered (fail count: {failed_questions[q_num]}/{max_attempts_per_question})")

    def _solve_with_ai_fallback(self, question, q_num):
        """Try to solve a question using AI when not in database"""
        try:
            # Parse the question
            qtext = self._get_question_text(question)
            if not qtext:
                print(f"Could not extract question text for Q{q_num}")
                return False
            
            qtype = self._detect_question_type(question)
            
            # Build question data for AI
            question_data = {
                "number": q_num,
                "text": qtext,
                "type": qtype,
            }
            
            # Add options if available
            if qtype in ["radio", "checkbox", "truefalse"]:
                options = self._extract_question_options(question, qtype)
                question_data["options"] = options
            
            print(f"[AI] Solving Q{q_num} ({qtype})...")
            
            # Ask AI to solve
            ai_answer = self.ai_solver.solver.solve_question(question_data)
            
            if not ai_answer:
                print(f"[AI] No answer from AI for Q{q_num}")
                return False
            
            print(f"[AI] AI answered Q{q_num}: {ai_answer}")
            
            # Now apply the AI answer to the question
            return self._apply_ai_answer(question, qtype, ai_answer, question_data)
            
        except Exception as e:
            print(f"[AI] Error solving Q{q_num}: {e}")
            return False
    
    def _extract_question_options(self, question, qtype):
        """Extract options from question based on type"""
        options = []
        
        try:
            if qtype == "radio" or qtype == "checkbox":
                selector = 'input[type="radio"]' if qtype == "radio" else 'input[type="checkbox"]'
                inputs = question.locator(selector)
                count = inputs.count()
                print(f"[DEBUG] Found {count} {qtype} inputs")
                
                for i in range(count):
                    inp = inputs.nth(i)
                    label_text = ""
                    
                    # Method 1: label[for=id]
                    radio_id = inp.get_attribute("id") or ""
                    if radio_id:
                        lbl = question.locator(f'label[for="{radio_id}"]')
                        if lbl.count() > 0:
                            label_text = lbl.first.inner_text()
                            print(f"  [M1] Option {i}: Found via label[for]: {label_text[:40]}...")
                    
                    # Method 2: following-sibling::label
                    if not label_text:
                        lbl = inp.locator("xpath=following-sibling::label")
                        if lbl.count() > 0:
                            label_text = lbl.first.inner_text()
                            print(f"  [M2] Option {i}: Found via following-sibling: {label_text[:40]}...")
                    
                    # Method 3: following-sibling::span (alternative label container)
                    if not label_text:
                        span = inp.locator("xpath=following-sibling::span")
                        if span.count() > 0:
                            label_text = span.first.inner_text()
                            print(f"  [M3] Option {i}: Found via following-sibling::span: {label_text[:40]}...")
                    
                    # Method 4: sibling div with class containing 'label' or 'text'
                    if not label_text:
                        # Try parent > sibling with label-like class
                        parent = inp.locator("xpath=parent::*")
                        if parent.count() > 0:
                            # Check siblings for text container
                            text_elem = parent.first.locator("xpath=following-sibling::*[1]")
                            if text_elem.count() > 0:
                                label_text = text_elem.first.inner_text()
                                print(f"  [M4] Option {i}: Found via parent sibling: {label_text[:40]}...")
                    
                    # Method 5: Get surrounding text content
                    if not label_text:
                        try:
                            # Get text in same container
                            wrapper = inp.locator("xpath=ancestor::div[1]")
                            if wrapper.count() > 0:
                                all_text = wrapper.first.inner_text()
                                # Try to extract just this option's text
                                lines = all_text.split('\n')
                                if lines:
                                    label_text = lines[0].strip()
                                    print(f"  [M5] Option {i}: Found via ancestor div: {label_text[:40]}...")
                        except:
                            pass
                    
                    if label_text:
                        options.append({
                            "index": i,
                            "label": label_text
                        })
                        print(f"  ✓ Option {chr(65+i)}: {label_text[:50]}...")
                    else:
                        print(f"  ✗ Option {i}: No label found via any method")
            
            elif qtype == "truefalse":
                # True/False options
                options = [
                    {"index": 0, "label": "Benar"},
                    {"index": 1, "label": "Salah"}
                ]
        
        except Exception as e:
            print(f"Error extracting options: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"[DEBUG] Total options extracted: {len(options)}")
        return options
    
    def _apply_ai_answer(self, question, qtype, ai_answer, question_data=None):
        """Apply AI's answer to the question
        AI answer can be in format: 'A' or 'A, B, C' (index format)
        This function converts index to actual label text from question_data options
        """
        ai_answer_clean = str(ai_answer).strip()
        print(f"[DEBUG] _apply_ai_answer: raw answer='{ai_answer_clean}', type={qtype}")
        
        # Convert index-based answers (A, B, C) to label text if options are available
        if question_data and "options" in question_data:
            ai_answer_clean = self._convert_index_to_label(ai_answer_clean, question_data["options"])
            print(f"[DEBUG] After conversion: '{ai_answer_clean}'")
        
        ai_answer_clean = ai_answer_clean.lower()
        
        # Map AI response to actual options
        if qtype == "radio":
            print(f"[DEBUG] Applying as radio: '{ai_answer_clean}'")
            return self._answer_radio(question, ai_answer_clean)
        elif qtype == "checkbox":
            # For checkbox, parse potentially multiple answers
            answers = [a.strip() for a in ai_answer_clean.split(',')]
            print(f"[DEBUG] Applying as checkbox with {len(answers)} answers: {answers}")
            return self._answer_checkbox(question, answers)
        elif qtype == "truefalse":
            print(f"[DEBUG] Applying as truefalse: '{ai_answer_clean}'")
            return self._answer_truefalse(question, ai_answer_clean)
        elif qtype == "essay" or qtype == "shortanswer":
            # Text-based - fill in text area
            print(f"[DEBUG] Applying as essay/short: '{ai_answer_clean}'")
            return self._answer_essay_or_short(question, ai_answer_clean)
        
        return False
    
    def _convert_index_to_label(self, ai_answer: str, options: list) -> str:
        """Convert index-based answers (A, B, C) to label text
        Example: "A, B, C" -> "Option 1 text, Option 2 text, Option 3 text"
        """
        if not options or not ai_answer:
            return ai_answer
        
        # Split if multiple answers (A, B, C or A B C)
        indices = re.findall(r'[A-E]', ai_answer.upper())
        print(f"[DEBUG] Found indices: {indices}")
        if not indices:
            print(f"[DEBUG] No indices found, returning original: {ai_answer}")
            return ai_answer
        
        labels = []
        for idx_char in indices:
            # Convert A->0, B->1, C->2, etc.
            idx = ord(idx_char) - ord('A')
            if 0 <= idx < len(options):
                label = options[idx].get('label', '')
                if label:
                    labels.append(label)
                    print(f"[DEBUG]   {idx_char} (index {idx}) -> '{label[:40]}'")
            else:
                print(f"[DEBUG]   {idx_char} (index {idx}) -> OUT OF RANGE (only {len(options)} options)")
        
        # Return converted labels, or original answer if conversion failed
        if labels:
            result = ', '.join(labels)
            print(f"[DEBUG] Conversion result: '{result[:100]}'")
            return result
        print(f"[DEBUG] No labels converted, returning original")
        return ai_answer
    
    def _answer_essay_or_short(self, question, answer_text):
        """Answer essay or short answer question"""
        try:
            textarea = question.locator("textarea").first
            if textarea.count() > 0:
                textarea.fill(answer_text)
                return True
        except Exception as e:
            print(f"Error filling essay/short answer: {e}")
        return False

    def _answer_all_questions(self):
        """Answer all questions on all pages"""
        # Ensure questions are loaded
        try:
            self.page.wait_for_selector(".que", timeout=10000)
        except:
            print("[Worker] No questions (.que) found on current page")
            return

        nav_buttons = self.page.locator("div.qn_buttons a.qnbutton")
        total_pages = nav_buttons.count()
        
        # Determine current page index if possible
        current_page_idx = 0
        for i in range(total_pages):
            if "thispage" in (nav_buttons.nth(i).get_attribute("class") or ""):
                current_page_idx = i
                break

        for i in range(current_page_idx, total_pages or 1):
            questions = self.page.locator(".que")
            count = questions.count()
            answered_count = 0
            
            if count > 0:
                print(f"[Worker] Page {i+1}: Answering {count} questions...")
                for q_idx in range(count):
                    # Update progress bar
                    if total_pages > 0:
                        progress = ((i / total_pages) + (q_idx / count / total_pages)) * 100
                        self._update_progress(progress)
                    
                    if self._smart_answer(questions.nth(q_idx)):
                        answered_count += 1
                
                print(f"[Worker] Page {i+1}: Finished answering {answered_count}/{count} questions")
                
                # Force save by clicking Next if not on last page
                if i < total_pages - 1:
                    next_page = self.page.locator('input[type="submit"][value="Next page"], button:has-text("Next")').first
                    if next_page.count() > 0:
                        next_page.click()
                        wait(2)
                        self.page.wait_for_load_state("networkidle")
                    else:
                        # Fallback to nav button
                        nav_buttons.nth(i+1).click()
                        wait(2)
            else:
                print(f"[Worker] Page {i+1}: No questions found")
                break

    def _get_unanswered_questions(self):
        """Get list of unanswered question numbers - improved detection"""
        unanswered = []
        
        # Ensure we are on the page and it's loaded
        try:
            self.page.wait_for_load_state("networkidle", timeout=5000)
        except:
            pass

        nav_buttons = self.page.locator("div.qn_buttons a.qnbutton")
        count = nav_buttons.count()
        
        # If no nav buttons found, maybe we're not on a quiz page or it's a different layout
        if count == 0:
            # Check if there are questions on the page at least
            if self.page.locator(".que").count() > 0:
                print("[Worker] Found questions but no nav buttons. Checking page content...")
            else:
                return []

        for i in range(count):
            btn = nav_buttons.nth(i)
            classes = (btn.get_attribute("class") or "").lower()
            title = (btn.get_attribute("title") or "").lower()
            
            # Check various indicators for unanswered questions
            # Modern Moodle classes: 'notyetanswered', 'requires-attention', 'incomplete'
            # We also check if it DOES NOT have 'answered' or 'correct' or 'incorrect' (if review)
            is_unanswered = (
                "notyetanswered" in classes or
                "notanswered" in classes or
                "requires-attention" in classes or
                "incomplete" in classes or
                "unanswered" in title or
                "not answered" in title or
                "requires attention" in title or
                "not yet answered" in title
            )
            
            # If it doesn't have an explicit 'answered' class and isn't 'correct'/'incorrect'
            if not is_unanswered:
                if "answered" not in classes and "correct" not in classes and "incorrect" not in classes:
                    # Check for lack of specific state classes
                    # Some Moodle themes use 'empty' or just don't add 'answered'
                    pass 

            # Also check if button has a specific color or style indicating unanswered
            try:
                style = (btn.get_attribute("style") or "").lower()
                if "color:" in style and ("red" in style or "orange" in style):
                    is_unanswered = True
            except:
                pass
            
            if is_unanswered:
                q_num = i + 1  # Usually 1-based indexing
                unanswered.append(q_num)
        
        # Cross-check with questions on current page
        # If a question is visible on the current page, its real state is more accurate than the nav button
        current_questions = self.page.locator(".que")
        for i in range(current_questions.count()):
            q = current_questions.nth(i)
            q_num_el = q.locator(".info .no")
            if q_num_el.count() > 0:
                try:
                    q_num_text = q_num_el.inner_text().strip()
                    q_num = int(''.join(filter(str.isdigit, q_num_text)))
                    
                    # Check if this specific question is answered in the DOM
                    radios = q.locator('input[type="radio"]:checked')
                    checkboxes = q.locator('input[type="checkbox"]:checked')
                    text_inputs = q.locator('input[type="text"], textarea')
                    
                    has_answer = (radios.count() > 0 or checkboxes.count() > 0)
                    if not has_answer and text_inputs.count() > 0:
                        # For text inputs, check if they have value
                        for j in range(text_inputs.count()):
                            if text_inputs.nth(j).input_value().strip():
                                has_answer = True
                                break
                    
                    if has_answer:
                        # If it's in our unanswered list but we see an answer here, remove it
                        if q_num in unanswered:
                            print(f"[Worker] Question {q_num} shows as answered in DOM, removing from unanswered list")
                            unanswered.remove(q_num)
                    else:
                        # If it's NOT in our list but we see it's empty here, add it
                        if q_num not in unanswered:
                            unanswered.append(q_num)
                except Exception as e:
                    print(f"[Worker] Error checking question state in DOM: {e}")
        
        return sorted(list(set(unanswered)))

    def _go_to_question(self, question_number):
        """Navigate to specific question number with better error handling"""
        try:
            nav_buttons = self.page.locator("div.qn_buttons a.qnbutton")
            if question_number <= nav_buttons.count():
                btn = nav_buttons.nth(question_number - 1)
                btn.click()
                wait(2)  # Wait for page to load
                
                # Verify we're on the correct question
                current_questions = self.page.locator(".que")
                if current_questions.count() > 0:
                    q_num_el = current_questions.first.locator(".info .no")
                    if q_num_el.count() > 0:
                        actual_num = q_num_el.inner_text().strip()
                        try:
                            actual_num = int(''.join(filter(str.isdigit, actual_num)))
                            if actual_num != question_number:
                                print(f"Warning: Expected question {question_number}, got {actual_num}")
                        except:
                            pass
                print(f"Successfully navigated to question {question_number}")
            else:
                print(f"Error: Question {question_number} not found in navigation")
        except Exception as e:
            print(f"Error navigating to question {question_number}: {e}")

    def _is_on_quiz_page(self):
        """Check if we're currently on a quiz attempt page"""
        # Check for quiz-specific elements
        quiz_indicators = [
            'input[type="submit"][value="Finish attempt..."]',
            'button[type="submit"]:has-text("Submit all and finish")',
            'div.qn_buttons',  # Question navigation
            '.que'  # Question elements
        ]
        
        for indicator in quiz_indicators:
            if self.page.locator(indicator).count() > 0:
                print(f"[Worker] Found quiz indicator: {indicator}")
                return True
        
        print("[Worker] No quiz indicators found - not on quiz page")
        return False

    def solve_quiz(self, quiz_link):
        """Solve quiz - queued to worker thread"""
        if not self._worker_thread:
            self.start_browser()
        return self._execute_in_worker("solve_quiz", quiz_link)

    def _smart_answer(self, question):
        """Answer a question and return True if answered, False if not found"""
        qtext = self._get_question_text(question)
        if not qtext: 
            return False

        # 1. Try Database first
        matched = None
        for key in self.answers:
            if key in qtext:
                matched = self.answers[key]
                break
        
        if matched:
            qtype = self._detect_question_type(question)
            print(f"Answering {qtype} from database: {qtext[:50]}...")
            
            if isinstance(matched, dict) and "answers" in matched:
                answers = [self._normalize_answer_text(a) for a in matched["answers"]]
            elif isinstance(matched, list):
                answers = [self._normalize_answer_text(a) for a in matched]
            elif isinstance(matched, str):
                answers = [self._normalize_answer_text(matched)]
            else:
                answers = []

            answers = [a for a in answers if a]
            if answers:
                if qtype == "radio":
                    return self._answer_radio(question, answers[0])
                elif qtype == "checkbox":
                    return self._answer_checkbox(question, answers)
                elif qtype == "truefalse":
                    return self._answer_truefalse(question, answers[0])
        
        # 2. AI Fallback: If not in database, use AI to solve immediately
        q_num_el = question.locator(".info .no")
        q_num = "?"
        if q_num_el.count() > 0:
            q_num_text = q_num_el.inner_text().strip()
            q_num = ''.join(filter(str.isdigit, q_num_text))
            
            print(f"[Worker] No database answer for Q{q_num}: {qtext[:50]}... Using AI fallback.")
            return self._solve_with_ai_fallback(question, q_num)
            return self._answer_checkbox(question, answers)
        elif qtype == "truefalse":
            # Handle True/False questions specifically
            return self._answer_truefalse(question, answers[0])
        
        return False

    def smart_answer(self, question):
        # This is a legacy wrapper - not typically called
        self._smart_answer(question)

    def _get_question_text(self, question):
        qtext = question.locator(".qtext")
        return qtext.inner_text().strip().lower() if qtext.count() > 0 else None

    def get_question_text(self, question):
        # Legacy wrapper
        return self._get_question_text(question)

    def _detect_question_type(self, question):
        # Check for True/False questions first
        q_classes = question.get_attribute("class") or ""
        if "truefalse" in q_classes.lower():
            return "truefalse"
            
        # Check for radio buttons
        if question.locator('input[type="radio"]').count() > 0:
            return "radio"
        # Check for checkboxes
        if question.locator('input[type="checkbox"]').count() > 0:
            return "checkbox"
        return "unknown"

    def detect_question_type(self, question):
        # Legacy wrapper
        return self._detect_question_type(question)

    def _answer_radio(self, question, target_text):
        def clean_text(s):
            return " ".join("".join(ch if ch.isalnum() else " " for ch in s).split()).lower()
        
        target_text = self._normalize_answer_text(target_text)
        target_clean = clean_text(target_text)
        radios = question.locator('input[type="radio"]')
        
        for i in range(radios.count()):
            radio = radios.nth(i)
            label_id = radio.get_attribute("aria-labelledby")
            label_text = ""
            if label_id:
                safe_id = label_id.replace(":", "\\:")
                lbl = question.locator(f"#{safe_id}")
                if lbl.count() > 0:
                    label_text = lbl.first.inner_text()
            else:
                lbl = radio.locator("xpath=following-sibling::label")
                if lbl.count() > 0:
                    label_text = lbl.first.inner_text()
            
            text_clean = clean_text(label_text)
            if target_clean.replace(" ", "") in text_clean.replace(" ", ""):
                try:
                    radio.check(force=True)
                    return True
                except Exception:
                    return self._answer_input_via_js(radio)
        return self._answer_input_via_js(question, target_text)

    def _answer_truefalse(self, question, target_answer):
        """Answer True/False question specifically"""
        target_clean = target_answer.strip().lower().strip("'\"")
        if target_clean in ("t", "f"):
            target_clean = "true" if target_clean == "t" else "false"
        
        # Lookup any likely boolean labels
        radios = question.locator('input[type="radio"]')
        found_labels = []
        radio_count = radios.count()
        
        # Debug: log the HTML of the question div to understand structure
        if radio_count == 0:
            print(f"DEBUG: No radio buttons found. Question HTML snippet:")
            q_html = question.evaluate("el => el.innerHTML.substring(0, 500)")
            print(f"  {q_html[:200]}...")
        
        for i in range(radio_count):
            radio = radios.nth(i)
            
            # Get label text - try multiple methods
            label_text = ""
            
            # Method 0: label[for=id]
            radio_id = radio.get_attribute("id") or ""
            if radio_id:
                lbl = question.locator(f'label[for="{radio_id}"]')
                if lbl.count() > 0:
                    label_text = lbl.first.inner_text()
            
            # Method 1: aria-labelledby
            if not label_text:
                label_id = radio.get_attribute("aria-labelledby")
                if label_id:
                    safe_id = label_id.replace(":", "\\:")
                    lbl = question.locator(f"#{safe_id}")
                    if lbl.count() > 0:
                        label_text = lbl.first.inner_text()
            
            # Method 2: following label
            if not label_text:
                lbl = radio.locator("xpath=following-sibling::label")
                if lbl.count() > 0:
                    label_text = lbl.first.inner_text()
            
            # Method 3: value attribute
            if not label_text:
                value = radio.get_attribute("value") or ""
                if value.lower() in ["true", "false", "benar", "salah", "ya", "tidak"]:
                    label_text = value
            
            normalized_label = self._normalize_answer_text(label_text)
            found_labels.append(normalized_label)
            
            if normalized_label == target_clean or target_clean in normalized_label:
                if self._force_select_input(radio):
                    print(f"Selected {target_clean} for True/False question")
                    return True
                print(f"Failed to force-select {target_clean}, trying JS fallback")
                return self._answer_input_via_js(radio)
        
        print(f"Could not find {target_clean} option in True/False question")
        print(f"DEBUG: target_clean='{target_clean}', found_labels={found_labels}, radio_count={radio_count}")
        # Try fallback: just select any radio and hope it's the right one
        # This might happen with custom HTML structures
        if radio_count == 2:
            # Handle both English and Indonesian True/False labels
            # true/benar = first radio, false/salah = second radio
            is_true_answer = target_clean in ["true", "t", "benar", "ya", "yes", "ya", "betul"]
            idx = 0 if is_true_answer else 1
            if idx < radio_count:
                radio = radios.nth(idx)
                if self._force_select_input(radio):
                    print(f"Selected radio at index {idx} as fallback for {target_clean}")
                    return True
        return False

    def _get_checkbox_label(self, checkbox, question):
        """Extract label text from checkbox using multiple fallback methods"""
        label_text = ""
        
        # Method 1: label[for=id]
        cb_id = checkbox.get_attribute("id") or ""
        if cb_id:
            lbl = question.locator(f'label[for="{cb_id}"]')
            if lbl.count() > 0:
                label_text = lbl.first.inner_text()
        
        # Method 2: aria-labelledby
        if not label_text:
            label_id = checkbox.get_attribute("aria-labelledby")
            if label_id:
                safe_id = label_id.replace(":", "\\:")
                lbl = question.locator(f"#{safe_id}")
                if lbl.count() > 0:
                    label_text = lbl.first.inner_text()
        
        # Method 3: following-sibling::label
        if not label_text:
            lbl = checkbox.locator("xpath=following-sibling::label")
            if lbl.count() > 0:
                label_text = lbl.first.inner_text()
        
        # Method 4: following-sibling::span
        if not label_text:
            span = checkbox.locator("xpath=following-sibling::span")
            if span.count() > 0:
                label_text = span.first.inner_text()
        
        # Method 5: parent > following-sibling
        if not label_text:
            parent = checkbox.locator("xpath=parent::*")
            if parent.count() > 0:
                text_elem = parent.first.locator("xpath=following-sibling::*[1]")
                if text_elem.count() > 0:
                    label_text = text_elem.first.inner_text()
        
        return label_text.strip() if label_text else ""
    
    def _answer_checkbox(self, question, targets):
        """Answer checkbox question - select all matching options"""
        # Improved target processing: AI often returns multiple answers in one string or list
        all_targets = []
        for t in targets:
            if isinstance(t, str):
                # Split by comma if it's a combined string
                if "," in t:
                    all_targets.extend([item.strip() for item in t.split(",")])
                else:
                    all_targets.append(t.strip())
            else:
                all_targets.append(str(t))
        
        targets_norm = [self.norm(self._normalize_answer_text(t)) for t in all_targets if t]
        checkboxes = question.locator('input[type="checkbox"]')
        found = False
        checked_count = 0
        checked_elements = []
        
        print(f"[DEBUG] _answer_checkbox: Looking for {len(targets_norm)} normalized targets in {checkboxes.count()} checkboxes")
        for i in range(checkboxes.count()):
            cb = checkboxes.nth(i)
            label_text = self._get_checkbox_label(cb, question)
            label_norm = self.norm(self._normalize_answer_text(label_text))
            
            # Strict matching: the label should closely match one of the targets
            is_match = False
            for target_norm in targets_norm:
                # Use word-based matching or threshold-based matching to avoid over-matching
                # A match is valid if target is part of label or vice-versa, but avoid very short matches
                if len(target_norm) > 2 and (target_norm in label_norm or label_norm in target_norm):
                    is_match = True
                    print(f"    ✓ Checkbox {i} ('{label_text[:30]}') matches target: '{target_norm[:30]}'")
                    break
                elif target_norm == label_norm:
                    is_match = True
                    print(f"    ✓ Checkbox {i} matches target exactly: '{target_norm[:30]}'")
                    break

            if is_match:
                try:
                    # Check it if not already checked
                    if not cb.is_checked():
                        cb.check(force=True)
                        wait(0.5)
                    
                    if cb.is_checked():
                        checked_count += 1
                        found = True
                        checked_elements.append(cb)
                except Exception as e:
                    print(f"    ✗ Failed to check checkbox {i}: {e}")
        
        print(f"[DEBUG] Total checkboxes checked: {checked_count}")
        
        # Trigger page update by dispatching change events on all checked elements
        if checked_elements:
            try:
                for cb in checked_elements:
                    # Dispatch change and input events
                    cb.evaluate("""el => {
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        el.dispatchEvent(new Event('click', { bubbles: true }));
                    }""")
                print(f"[DEBUG] Dispatched change events for {len(checked_elements)} checkboxes")
                # Wait for UI to update
                wait(1)
            except Exception as e:
                print(f"[DEBUG] Could not dispatch events: {e}")
        
        return found

    def answer_checkbox(self, question, targets):
        # Legacy wrapper
        return self._answer_checkbox(question, targets)

    def _answer_input_via_js(self, element, target_text=None):
        """Fallback to JavaScript evaluation to select radio/checkbox inputs."""
        try:
            if target_text is None:
                # If element is already the input element
                element.evaluate("el => { el.checked = true; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }")
                return True

            script = """
            (el, target) => {
                const normalize = s => s ? s.toString().trim().toLowerCase().replace(/\\s+/g, ' ').replace(/\\s/g, '') : '';
                const target_norm = normalize(target);
                const inputs = Array.from(el.querySelectorAll('input[type="radio"], input[type="checkbox"]'));
                for (const input of inputs) {
                    let labelText = '';
                    if (input.id) {
                        const label = el.querySelector(`label[for="${input.id}"]`);
                        if (label) labelText = label.innerText;
                    }
                    if (!labelText && input.nextElementSibling && input.nextElementSibling.tagName === 'LABEL') {
                        labelText = input.nextElementSibling.innerText;
                    }
                    if (!labelText) {
                        const parentLabel = input.closest('label');
                        if (parentLabel) labelText = parentLabel.innerText;
                    }
                    if (normalize(labelText).includes(target_norm)) {
                        input.checked = true;
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }
                }
                return false;
            }
            """
            return element.evaluate(script, target_text)
        except Exception as e:
            print(f"[Worker] JS answer fallback failed: {e}")
            return False
