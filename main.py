
from time import sleep as wait
import os
import json
from playwright.sync_api import sync_playwright

userName = "LMG1998731-232402"
Pass = "MajuIndonesia1!"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    storage_path = "storage.json"
    Answers_path = "answers.json"
    storage_state_arg = None
    with open(Answers_path, "r", encoding="utf-8") as f:
        Answers = json.load(f)
        print(Answers)
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
            target = norm(target_text)

            radios = question.locator('input[type="radio"]')

            for i in range(radios.count()):
                radio = radios.nth(i)

                # ambil label via DOM terdekat
                label = radio.locator("xpath=following-sibling::label")
                if label.count() == 0:
                    continue

                text = norm(label.inner_text())

                if target in text:
                    radio.check(force=True)
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

                # cari label terdekat
                label = checkbox.locator("xpath=following-sibling::label")
                if label.count() == 0:
                    continue

                text = norm(label.inner_text())

                if any(t in text for t in targets_norm):
                    checkbox.check(force=True)

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
                print("No answer found for:", qtext)
                return

            qtype = detectQuestionType(question)
            answers = matched["answers"]

            print("Answering:", qtext)
            print("Type:", qtype, "| Answers:", answers)

            if qtype == "radio":
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
            labels = question.locator(".answer label")

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
                    
                    if modtype != "quiz": 
                        continue

                    # ===== ambil link (jika ada) =====
                    link = None
                    link_el = activity.locator("a")

                    if link_el.count() > 0:
                        link = link_el.first.get_attribute("href")

                    print(f" - [{modtype}] {name} -> {link}")
                    items = activity.locator('span[role="listitem"]')
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

                    if not actInfo[2]["isdone"]:

                        print("quiz not viewed yet. attempting to open...")
                        if not link: print("no link found, skipping...")
                        
                        page.goto(link)
                        wait(2)
                        print(f"quiz of {name} page opened.")
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

                        def saveQuiz(allQuiz:dict, currentQuiz:int, totalQuiz:int):
                            if not Answers:
                                print("No answers provided, extracting the questions...")
                                extracted_data = {}
                                for i in range(question.count()):
                                    q = question.nth(i)
                                    q_data = extract_question_data(q)
                                    if q_data:
                                        extracted_data[q_data["question"]] = {
                                            "type": q_data["type"],
                                            "options": q_data["options"]
                                        }
                                if currentQuiz == totalQuiz - 1:
                                    with open("extracted_questions.json", "w", encoding="utf-8") as f:
                                        json.dump(allQuiz, f, indent=4, ensure_ascii=False)
                                    print("Questions extracted and saved to 'extracted_questions.json'.")
                                else:
                                    allQuiz.update(extracted_data)
                                    print(f"Extracted questions from quiz {currentQuiz+1}/{totalQuiz}, moving")
                                    
                        collectedQuiz = {}
                        totalQuiz = page.locator("div.qn_buttons a.qnbutton")
                        for i in range(totalQuiz.count()):
                            processCurrentPage()
                            saveQuiz(collectedQuiz, i, totalQuiz.count())
                            print(f"Answering question {i+1}/{totalQuiz.count()}")
                            if i == totalQuiz.count() - 1:
                                print("last question, submitting...")
                                wait(20)
                                page.click('button[type="submit"]:has-text("Finish attempt ...")')
                            else:
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