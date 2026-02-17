
from time import sleep as wait
import os
import json
from playwright.sync_api import sync_playwright

userName = "LMG1998731-232425"
Pass = "MajuIndonesia1!"

unAnswered = {}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    storage_path = "storage.json"
    Answers_path = "answers.json"
    session_path = "extracted_questions.json"
    storage_state_arg = None
    with open(Answers_path, "r", encoding="utf-8") as f:
        Answers = json.load(f)
        print(f"{len(Answers)} jawaban")
    if os.path.exists(storage_path):
        try:
            with open(storage_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    # Validate JSON content before using it
                    json.loads(content)
                    storage_state_arg = storage_path
        except json.JSONDecodeError:
            print("Warning: 'storage.json' is not valid JSON; ignoring it and creating a new one after login.")
    context_kwargs = {
        "viewport": {"width": 1280, "height": 800},
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    }
    if storage_state_arg:
        context_kwargs["storage_state"] = storage_state_arg
    context = browser.new_context(**context_kwargs)
    try:
        page = context.new_page()
        page.goto("https://itclass.id/course/view.php?id=3")
        print(page.title())
        if "Log in" in page.content():
            print("attempting to log in")
            page.fill('input[name="username"]', userName)
            page.fill('input[name="password"]', Pass)
            page.click('button[type="submit"]')
            
        page.goto("https://itclass.id/course/view.php?id=3")
        print(page.title())

        sections = page.locator("li.section")
        section_count = sections.count()
        courses = []

        for i in range(section_count):
            section = sections.nth(i)

            title_el = section.locator("h3.sectionname")

            if title_el.count() == 0 or title_el.inner_text().strip() == "General":
                continue

            title = title_el.inner_text().strip()
            linkEl = section.locator("h3.sectionname a")
            print(title)
            link = linkEl.first.get_attribute("href")
            print(link)
            print(f"Processing {i+1}/{section_count}: {title}, link finded {linkEl.get_attribute('href') is not None}")
            courses.append({
                "title": title,
                "link": link
            })

            # Simpan session untuk login berikutnya
        context.storage_state(path=storage_path)

        def norm(text):
            return " ".join(text.lower().split())


        def getQuestionsText(question):
            qtext = question.locator(".qtext")
            if qtext.count() == 0:
                return None
            return qtext.inner_text().strip().lower()

        def answerRadio(question, target_text):
            def clean_text(s):
                # keep only alphanumerics and spaces, lowercase
                return " ".join("".join(ch if ch.isalnum() else " " for ch in s).split()).lower()

            target_clean = clean_text(target_text)

            radios = question.locator('input[type="radio"]')

            for i in range(radios.count()):
                radio = radios.nth(i)

                # ambil id label dari aria-labelledby
                label_id = radio.get_attribute("aria-labelledby")
                if not label_id:
                    # fallback: try following-sibling <label>
                    lbl = radio.locator("xpath=following-sibling::label")
                    if lbl.count() == 0:
                        continue
                    label_text = lbl.first.inner_text()
                else:
                    # escape ":" untuk CSS selector
                    safe_id = label_id.replace(":", "\\:")
                    label = question.locator(f"#{safe_id}")
                    if label.count() == 0:
                        continue
                    label_text = label.first.inner_text()

                text_clean = clean_text(label_text)

                # match by cleaned substring
                if target_clean.replace(" ", "") in text_clean.replace(" ", ""):
                    radio.check(force=True)
                    print("✅ Radio selected:", label_text)
                    return True

                # try token intersection (for punctuation/dash differences)
                tset = set(target_clean.split())
                sset = set(text_clean.split())
                if tset and (tset <= sset or len(tset & sset) >= max(1, len(tset) // 2)):
                    radio.check(force=True)
                    print("✅ Radio selected by token match:", label_text)
                    return True

                # try acronym/initial matching (e.g., target 'd a c' vs 'Dynamic Active Connect')
                initials = "".join(w[0] for w in text_clean.split() if w)
                target_compact = target_clean.replace(" ", "")
                if target_compact and initials and (target_compact == initials or target_compact == initials[:len(target_compact)]):
                    radio.check(force=True)
                    print("✅ Radio selected by initials:", label_text)
                    return True

                # try common translation normalization (Indonesian <-> English)
                translations = {
                    "benar": "true",
                    "salah": "false",
                    "true": "benar",
                    "false": "salah"
                }
                mapped = translations.get(target_clean)
                if mapped:
                    if mapped in text_clean or mapped in sset:
                        radio.check(force=True)
                        print("✅ Radio selected by translation:", label_text)
                        return True

            print("⚠️ Radio answer not applied:", target_text)
            return False

        def detectQuestionType(question):
            if question.locator('input[type="radio"]').count() > 0:
                return "radio"
            elif question.locator('input[type="checkbox"]').count() > 0:
                return "checkbox"
            else:
                return "unknown"

        def answerCheckbox(question, targets):
            targets_norm = [norm(t) for t in targets]

            checkboxes = question.locator('input[type="checkbox"]')

            for i in range(checkboxes.count()):
                checkbox = checkboxes.nth(i)

                # prefer aria-labelledby reference (Moodle uses this pattern)
                label_id = checkbox.get_attribute("aria-labelledby")
                label_text = None
                if label_id:
                    safe_id = label_id.replace(":", "\\:")
                    lbl = question.locator(f"#{safe_id}")
                    if lbl.count() > 0:
                        label_text = norm(lbl.first.inner_text())

                # fallback: try following-sibling <label>
                if not label_text:
                    lbl = checkbox.locator("xpath=following-sibling::label")
                    if lbl.count() > 0:
                        label_text = norm(lbl.first.inner_text())

                # fallback: try ancestor label
                if not label_text:
                    lbl = checkbox.locator("xpath=ancestor::label")
                    if lbl.count() > 0:
                        label_text = norm(lbl.first.inner_text())

                if not label_text:
                    continue

                if any(t in label_text for t in targets_norm):
                    checkbox.check(force=True)
                    print("✅ Checkbox selected:", label_text)

        def smartAnswer(question, ANSWERS):
            qtext = getQuestionsText(question)
            if not qtext:
                print("No question text found, skipping")
                return

            # cari soal yang cocok (contains)
            matched = None
            for key in ANSWERS:
                if key in qtext:
                    matched = ANSWERS[key]
                    break

            if not matched:
                qType = detectQuestionType(question)
                if qType == "radio":
                    option = extract_radio_options(question)
                elif qType == "checkbox":
                    option = extract_checkbox_options(question)
                else:
                    option = []

                unAnswered[qtext] = {
                    "type": qType,
                    "options": option
                }
                print("No answer found for:", qtext)

                return

            qtype = detectQuestionType(question)

            # support multiple stored formats:
            # - dict with key "answers": {"answers": [..]}
            # - plain list: [..]
            # - plain string: "answer text"
            if isinstance(matched, dict) and "answers" in matched:
                answers = matched["answers"]
            elif isinstance(matched, list):
                answers = matched
            elif isinstance(matched, str):
                answers = [matched]
            else:
                print("Unsupported answer format for:", qtext)
                return

            print("Answering:", qtext)
            print("Type:", qtype, "| Answers:", answers)

            if qtype == "radio":
                if len(answers) > 0:
                    answerRadio(question, answers[0])
            elif qtype == "checkbox":
                answerCheckbox(question, answers)

        def extract_question_text(question):
            qtext = question.locator(".qtext")
            if qtext.count() == 0:
                return None
            return qtext.inner_text().strip().lower()

        def extract_question_type(question):
            if question.locator('input[type="radio"]').count() > 0:
                return "radio"
            if question.locator('input[type="checkbox"]').count() > 0:
                return "checkbox"
            return "unknown"

        def extract_radio_options(question):
            options = []
            labels = question.locator(".answer div[data-region='answer-label']")

            for i in range(labels.count()):
                text = labels.nth(i).inner_text().strip().lower()
                options.append(text)
            return options

        def extract_checkbox_options(question):
            options = []
            checkboxes = question.locator('input[type="checkbox"]')

            for i in range(checkboxes.count()):
                checkbox = checkboxes.nth(i)
                label_id = checkbox.get_attribute("aria-labelledby")

                if label_id:
                    safe_id = label_id.replace(":", "\\:")
                    label_text = question.locator(f'#{safe_id}') \
                                        .inner_text().strip().lower()
                    options.append(label_text)


            return options


        def extract_question_data(question):
            qtext = extract_question_text(question)
            if not qtext:
                return None

            qtype = extract_question_type(question)

            if qtype == "radio":
                options = extract_radio_options(question)
            elif qtype == "checkbox":
                options = extract_checkbox_options(question)
            else:
                return None

            return {
                "question": qtext,
                "type": qtype,
                "options": options
            }
        
        def extractAnswer():
            # trying to review
            print(f"quiz of {name} page opened.")
            review = page.locator('td.cell.c3.lastcol a')

            # if there's a review link or no "no review" message
            if review.count() > 0 or page.locator('.noreviewmessage').count() == 0:
                rLink = review.first.get_attribute("href") if review.count() > 0 else None
                print(f"review page: {rLink}")
                if not rLink:
                    print("skip..")
                    return

                print("quiz already attempted, opening review page...")
                page.goto(rLink)

                incorrectAnswer = page.locator('div.que.incorrect')
                correctAnswerLoc = page.locator('div.que.correct')
                print(incorrectAnswer.count())

                def extract_answer_from_feedback(q):
                    qtext_el = q.locator(".qtext")
                    rightanswer_el = q.locator("div .rightanswer")
                    if qtext_el.count() == 0 or rightanswer_el.count() == 0:
                        return

                    qtext = qtext_el.inner_text().strip().lower()
                    correctAnswer = rightanswer_el.inner_text().strip().lower()

                    if ":" in correctAnswer:
                        parts = correctAnswer.split(":", 1)
                        candidate = parts[1].strip()
                        if candidate:
                            correctAnswer = candidate
                        else:
                            correctAnswer = correctAnswer.replace("the correct answer is:", "").strip()
                    else:
                        correctAnswer = correctAnswer.replace("the correct answer is:", "").strip()

                    if qtext in Answers:
                        if correctAnswer not in Answers[qtext].get("answers", []):
                            print(f"changing the answer {qtext} to: {correctAnswer}...")
                            Answers[qtext]["answers"] = [correctAnswer]
                    else:
                        print(f"no answer key found for {qtext}, saving the answer...")
                        Answers[qtext] = {"answers": [correctAnswer]}

                # handle incorrect answers first
                if incorrectAnswer.count() > 0:
                    print(f"{incorrectAnswer.count()} incorrect answer(s) found, trying to extract correct answers...")
                    for j in range(incorrectAnswer.count()):
                        q = incorrectAnswer.nth(j)
                        extract_answer_from_feedback(q)

                    print(f"saving the answers to {Answers_path}...")
                    with open(Answers_path, "w", encoding="utf-8") as f:
                        json.dump(Answers, f, indent=4, ensure_ascii=False)
                else:
                    print("no incorrect answers found, skipping incorrect-answer extraction...")

                # also process correct answers (to ensure new questions are saved)
                if correctAnswerLoc.count() > 0:
                    for j in range(correctAnswerLoc.count()):
                        q = correctAnswerLoc.nth(j)
                        extract_answer_from_feedback(q)
                    print(f"saving the answers to {Answers_path}...")
                    with open(Answers_path, "w", encoding="utf-8") as f:
                        json.dump(Answers, f, indent=4, ensure_ascii=False)
            else:
                print("no review available for this quiz.")

        for course in courses:
            currLink = course['link']
            print(f"{course['title']}: {course['link']}")
            page.goto(currLink)

            sections = page.locator("li.section")

            for s in range(sections.count()):
                section = sections.nth(s)

                title_el = section.locator("h3.sectionname")
                if title_el.count() == 0:
                    continue

                section_title = title_el.inner_text().strip()
                print(f"\nSection: {section_title}")
                if section_title.lower() == "general":
                    continue

                activities = section.locator("li.activity")

                for i in range(activities.count()):
                    activity = activities.nth(i)

                    # ===== ambil tipe activity =====
                    class_attr = activity.get_attribute("class") or ""
                    modtype = "unknown"
                    for c in class_attr.split():
                        if c.startswith("modtype_"):
                            modtype = c.replace("modtype_", "")
                            break

                    # ===== ambil nama =====
                    name = None

                    name_el = activity.locator("span.instancename")
                    if name_el.count() > 0:
                        name = name_el.first.inner_text().strip()
                    else:
                        item = activity.locator(".activity-item").first
                        name = item.get_attribute("data-activityname")
                    
                    if modtype not in ("quiz", "lesson"): 
                        continue

                    # ===== ambil link (jika ada) =====
                    link = None
                    link_el = activity.locator("a")

                    if link_el.count() > 0:
                        link = link_el.first.get_attribute("href")

                    print(f" - [{modtype}] {name} -> {link}")
                    items = activity.locator('span[role="listitem"]')
                    if items.count() == 0:
                        print("No activity items found.")
                        continue
                    actInfo = []
                    for i in range(items.count()):
                        item = items.nth(i)
                        text = item.locator('span.font-weight-normal').inner_text().strip().lower()
                        icon = item.locator("i")
                        isdone = icon.count() > 0 and icon.get_attribute("aria-hidden") == "true"

                        actInfo.append({
                            "text": text,
                            "isdone": isdone
                        })
                        print(actInfo[i])

                    if not actInfo[len(actInfo)-1]["isdone"]:
                        if actInfo[len(actInfo)-1]["text"] == "go through the activity to the end":
                            print("required activity not done yet, attempting to to do it...")
                            page.goto(link)
                            progress = page.locator('div.progress .progress-bar').inner_text().strip().lower()
                            while progress != "100%":
                                print(progress)
                                wait(1)
                        print("quiz not viewed yet. attempting to open...")
                        if not link: print("no link found, skipping...")
                        
                        page.goto(link)
                        wait(2)
                        page.click('button[type="submit"]')
                        startAttempt = page.locator('input[type="submit"][value="Start attempt"]')
                        if startAttempt.count() > 0:
                            startAttempt.click()
                        wait(4)

                        #kita amsusikan jika sudah di halaman yang menunjukan question
                        question = page.locator(".que")
                        def processCurrentPage():
                            questions = page.locator(".que")

                            for i in range(questions.count()):
                                q = questions.nth(i)
                                smartAnswer(q, Answers)

                        def saveQuiz(allQuiz:dict, currentQuiz:int, totalQuiz:int, nameofQuiz:str):
                            if not Answers:
                                print("No answers provided, extracting the questions...")
                                extracted_data = {}
                                alldata = {}
                                if not os.path.exists(session_path):
                                    alldata = {}
                                else:
                                    with open(session_path, "r", encoding="utf-8") as f:
                                        alldata = json.load(f)

                                for i in range(question.count()):
                                    q = question.nth(i)
                                    q_data = extract_question_data(q)
                                    if q_data:
                                        extracted_data[q_data["question"]] = {
                                            "type": q_data["type"],
                                            "options": q_data["options"]
                                        }
                                if currentQuiz == totalQuiz - 1:
                                    with open(session_path, "w", encoding="utf-8") as f:
                                        json.dump(allQuiz, f, indent=4, ensure_ascii=False)
                                    print(f"Questions extracted and saved to '[{session_path}]'.")
                                else:
                                    if q_data:
                                        quizs = {}
                                        quizs[nameofQuiz] = extracted_data
                                    allQuiz.update(quizs)
                                    print(f"Extracted questions from quiz {currentQuiz+1}/{totalQuiz}, moving")
                        
                        def saveUnsweredQuiz():
                            if unAnswered:
                                print("some Questions were not answered due to missing answer, saving...")
                                alldata = {}
                                if not os.path.exists(session_path):
                                    alldata = {}
                                else:
                                    with open(session_path, "r", encoding="utf-8") as f:
                                        alldata = json.load(f)
                                    with open(session_path, "w", encoding="utf-8") as f:
                                        if name not in alldata:
                                            alldata[name] = {}
                                            alldata[name].update(unAnswered)
                                        json.dump(alldata, f, indent=4, ensure_ascii=False)
                            
                                    
                        collectedQuiz = {}
                        totalQuiz = page.locator("div.qn_buttons a.qnbutton")
                        for i in range(totalQuiz.count()):
                            tombols = totalQuiz.nth(i)
                            tombol = tombols.get_attribute("href")
                            print(tombol)
                            if tombol != None:
                                page.goto(tombols)
                            break
                        for i in range(totalQuiz.count()):
                            #saat attemptting berapapun harus balik ke nomor satu 
                            processCurrentPage()
                            saveQuiz(collectedQuiz, i, totalQuiz.count(), name)
                            print(f"Answering question {i+1}/{totalQuiz.count()}")
                            if i == totalQuiz.count() - 1:
                                buttons = page.locator('a.qnbutton') 
                                notAnswered = 0
                                for b in range(buttons.count()):
                                    btn = buttons.nth(b)
                                    class_attr = btn.get_attribute("class") or ""
                                    if "notyetanswered" in class_attr:
                                        notAnswered += 1
                                if notAnswered < totalQuiz.count() - 1:
                                    if notAnswered > 0:
                                        print(f"{notAnswered}/{buttons.count()}, not answered")
                                        saveUnsweredQuiz()
                                print("last question, submitting...")
                                wait(20)
                                page.click('input[type="submit"][name="next"]')
                                # konfirmasi submit
                                #scope the most better answer...
                                answerKey = page.locator('form .questionflagsaveform .que')
                                if answerKey.count() > 0:
                                    print("scope the most better answer...")
                                    for j in range(answerKey.count()):
                                        q = answerKey.nth(j)
                                        iscorrect = q.locator("div .specificfeedback").inner_text().strip().lower() == "your answer is correct."
                                        if not iscorrect:
                                            qtext = q.locator(".qtext").inner_text().strip().lower()
                                            correctAnswer = q.locator("div .rightanswer").inner_text().strip().lower()
                                            correctAnswer = correctAnswer.replace("the correct answer is:", "").strip() or correctAnswer.split(":", 1)[1].strip() if ":" in correctAnswer else correctAnswer
                                            if qtext in Answers:
                                                print(f"changing the answer {qtext} to: {correctAnswer}...")
                                                Answers[qtext]["answers"] = [correctAnswer]

                            else:
                                wait(10)
                                print("scope next question...")
                                
                                nextpage = page.locator('input[type="submit"][value="Next page"]')
                                if nextpage.count() < 0:
                                    button = totalQuiz.nth(i)
                                    page.click(button)
                                    wait(3)

                                nextpage.click()
                                page.wait_for_load_state("networkidle")

    finally:
        context.close()
        browser.close()