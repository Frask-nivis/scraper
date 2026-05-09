import customtkinter as ctk
import threading
from scraper_engine import ScraperEngine
import json
import os
import time

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

CONFIG_PATH = "config.json"

class ChatPanel(ctk.CTkFrame):
    def __init__(self, master, engine, **kwargs):
        super().__init__(master, **kwargs)
        self.engine = engine
        
        # Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # Header
        self.header_frame = ctk.CTkFrame(self, fg_color="#1f538d", corner_radius=5)
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        self.header_frame.grid_columnconfigure(0, weight=1)
        
        self.header = ctk.CTkLabel(self.header_frame, text="AI BROWSER ASSISTANT", font=("Arial", 14, "bold"), text_color="white")
        self.header.grid(row=0, column=0, padx=10, pady=5, sticky="w")
        
        self.clear_btn = ctk.CTkButton(self.header_frame, text="🗑️", width=30, height=25, fg_color="transparent", hover_color="#c0392b", command=self.clear_chat)
        self.clear_btn.grid(row=0, column=1, padx=5, pady=5)
        
        # Chat history (scrollable)
        self.chat_history = ctk.CTkScrollableFrame(self, fg_color="#2b2b2b")
        self.chat_history.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        
        # Status indicator
        self.status_label = ctk.CTkLabel(self.chat_history, text="", font=("Arial", 11, "italic"), text_color="gray")
        # self.status_label.pack(side="bottom", fill="x", pady=5) # Will be packed when needed
        
        # Input area
        self.input_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.input_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        self.input_frame.grid_columnconfigure(0, weight=1)
        
        self.user_input = ctk.CTkEntry(self.input_frame, placeholder_text="Tanya AI atau suruh AI melakukan sesuatu...", height=40)
        self.user_input.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.user_input.bind("<Return>", lambda e: self.send_message())
        
        self.send_btn = ctk.CTkButton(self.input_frame, text="KIRIM", width=60, height=40, command=self.send_message)
        self.send_btn.grid(row=0, column=1)
        
        # Initial greeting
        self.add_message("AI", "Halo! Saya adalah AI Browser Assistant. Saya bisa membantu Anda mencari informasi, mengklik tombol, mengisi form, atau menjalankan script di halaman ini. Coba suruh saya sesuatu!")

    def clear_chat(self):
        for widget in self.chat_history.winfo_children():
            widget.destroy()
        self.add_message("AI", "Chat telah dibersihkan. Apa yang bisa saya bantu sekarang?")

    def add_message(self, sender, text, color=None):
        if color is None:
            color = "#1f538d" if sender == "AI" else "#3d3d3d"
        
        msg_frame = ctk.CTkFrame(self.chat_history, fg_color=color, corner_radius=10)
        msg_frame.pack(anchor="w" if sender == "AI" else "e", padx=10, pady=5, fill="x")
        
        sender_label = ctk.CTkLabel(msg_frame, text=sender, font=("Arial", 10, "bold"), text_color="#aaaaaa")
        sender_label.pack(anchor="w", padx=10, pady=(5, 0))
        
        content_label = ctk.CTkLabel(msg_frame, text=text, font=("Arial", 12), wraplength=250, justify="left")
        content_label.pack(anchor="w", padx=10, pady=(0, 5))
        
        # Scroll to bottom
        self.chat_history._parent_canvas.yview_moveto(1.0)

    def set_status(self, text):
        if hasattr(self, 'current_status_label') and self.current_status_label:
            self.current_status_label.destroy()
        
        if text:
            self.current_status_label = ctk.CTkLabel(self.chat_history, text=f"⏳ {text}...", font=("Arial", 11, "italic"), text_color="#3498db")
            self.current_status_label.pack(anchor="w", padx=20, pady=2)
            self.chat_history._parent_canvas.yview_moveto(1.0)

    def send_message(self):
        msg = self.user_input.get().strip()
        if not msg:
            return
            
        self.user_input.delete(0, 'end')
        self.add_message("USER", msg)
        self.user_input.configure(state="disabled")
        self.send_btn.configure(state="disabled")
        
        def chat_task():
            try:
                self.after(0, lambda: self.set_status("Menganalisa halaman"))
                # The engine handles context gathering and execution
                result = self.engine.chat_with_ai(msg)
                
                response = result.get("response", "Maaf, terjadi kesalahan.")
                js_code = result.get("js_code")
                exec_status = result.get("execution_status")
                
                self.after(0, lambda: self.set_status(None))
                
                if js_code:
                    self.after(0, lambda: self.add_message("AI", f"🔧 Menjalankan perintah: {js_code[:50]}...", color="#2c3e50"))
                
                self.after(0, lambda: self.add_message("AI", response))
                
                if exec_status and "Failed" in exec_status:
                    self.after(0, lambda: self.add_message("AI", f"❌ Error: {exec_status}", color="#c0392b"))
                
            except Exception as e:
                self.after(0, lambda: self.set_status(None))
                self.after(0, lambda ex=e: self.add_message("AI", f"Terjadi kesalahan: {str(ex)}", color="#c0392b"))
            finally:
                self.after(0, lambda: self.user_input.configure(state="normal"))
                self.after(0, lambda: self.send_btn.configure(state="normal"))
                self.after(0, lambda: self.user_input.focus())

        threading.Thread(target=chat_task, daemon=True).start()

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("ITClass Automation UI")
        self.geometry("1000x800")
        
        self.engine = ScraperEngine()
        self.sections_data = []
        self.config = self.load_config()
        
        # Setup Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        
        # Frames
        self.login_frame = ctk.CTkFrame(self)
        self.setup_login_frame()
        
        self.dashboard_frame = ctk.CTkFrame(self)
        self.setup_dashboard_frame()
        
        # Check initial state
        if self.config.get("username") and self.config.get("password"):
            self.username_entry.insert(0, self.config["username"])
            self.password_entry.insert(0, self.config["password"])
            self.show_login()
        else:
            self.show_login()
            
    def load_config(self):
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        return {}

    def save_config(self, username, password):
        with open(CONFIG_PATH, "w") as f:
            json.dump({"username": username, "password": password}, f)

    def setup_login_frame(self):
        self.login_frame.grid_columnconfigure(0, weight=1)
        self.login_label = ctk.CTkLabel(self.login_frame, text="ITClass Login", font=("Arial", 32, "bold"))
        self.login_label.grid(row=0, column=0, pady=(100, 40))
        
        self.username_entry = ctk.CTkEntry(self.login_frame, placeholder_text="Username", width=300, height=45)
        self.username_entry.grid(row=1, column=0, pady=10)
        
        self.password_entry = ctk.CTkEntry(self.login_frame, placeholder_text="Password", show="*", width=300, height=45)
        self.password_entry.grid(row=2, column=0, pady=10)
        
        self.login_btn = ctk.CTkButton(self.login_frame, text="LOGIN", command=self.handle_login, width=300, height=45, font=("Arial", 16, "bold"))
        self.login_btn.grid(row=3, column=0, pady=30)
        
        self.login_status = ctk.CTkLabel(self.login_frame, text="", font=("Arial", 14))
        self.login_status.grid(row=4, column=0, pady=10)

    def setup_dashboard_frame(self):
        self.dashboard_frame.grid_columnconfigure(0, weight=1)
        self.dashboard_frame.grid_columnconfigure(1, weight=0, minsize=350) # Chat column
        self.dashboard_frame.grid_rowconfigure(1, weight=1)
        
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Left side: Main Content
        self.main_content = ctk.CTkFrame(self.dashboard_frame, fg_color="transparent")
        self.main_content.grid(row=0, column=0, rowspan=3, sticky="nsew")
        self.main_content.grid_columnconfigure(0, weight=1)
        self.main_content.grid_rowconfigure(1, weight=1)

        # Header
        self.header_frame = ctk.CTkFrame(self.main_content, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=10)
        
        self.header_label = ctk.CTkLabel(self.header_frame, text="ITClass Automation Dashboard", font=("Arial", 24, "bold"))
        self.header_label.pack(side="left")
        
        self.search_entry = ctk.CTkEntry(self.header_frame, placeholder_text="Search section/quiz...", width=250)
        self.search_entry.pack(side="left", padx=20)
        self.search_entry.bind("<KeyRelease>", lambda e: self.update_search_visibility())
        
        self.logout_btn = ctk.CTkButton(self.header_frame, text="Logout", width=80, fg_color="red", hover_color="#8B0000", command=self.handle_logout)
        self.logout_btn.pack(side="right")
        
        # Scrollable area
        self.scroll_frame = ctk.CTkScrollableFrame(self.main_content, label_text="Available Sections & Quizzes", label_font=("Arial", 16, "bold"))
        self.scroll_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        
        # Controls / Status
        self.controls_frame = ctk.CTkFrame(self.main_content)
        self.controls_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=20)
        
        self.status_label = ctk.CTkLabel(self.controls_frame, text="Ready", font=("Arial", 14))
        self.status_label.pack(side="left", padx=20)
        
        self.progress_bar = ctk.CTkProgressBar(self.controls_frame, width=300)
        self.progress_bar.pack(side="left", padx=20)
        self.progress_bar.set(0)
        
        self.refresh_btn = ctk.CTkButton(self.controls_frame, text="REFRESH LIST", command=self.handle_refresh)
        self.refresh_btn.pack(side="right", padx=10)
        
        self.bulk_solve_btn = ctk.CTkButton(self.controls_frame, text="SOLVE SELECTED QUIZZES", fg_color="green", hover_color="#006400", command=self.handle_bulk_solve)
        self.bulk_solve_btn.pack(side="right", padx=10)

        # Right side: Chat Panel
        self.chat_panel = ChatPanel(self.dashboard_frame, self.engine, width=350)
        self.chat_panel.grid(row=0, column=1, rowspan=3, sticky="nsew", padx=(0, 10), pady=10)

    def show_login(self):
        self.dashboard_frame.grid_forget()
        self.login_frame.grid(row=0, column=0, sticky="nsew")

    def handle_logout(self):
        def task():
            self.after(0, lambda: self.update_status("Logging out...", "orange"))
            try:
                self.engine.logout()
            except Exception as e:
                print(f"Logout error: {e}")
            self.sections_data = []
            self.after(0, self.show_login)
            self.after(0, lambda: self.update_status("Logged out", "green"))

        threading.Thread(target=task, daemon=True).start()

    def on_close(self):
        try:
            if self.engine:
                self.engine.stop_browser()
        except Exception as e:
            print(f"Error closing engine: {e}")
        self.destroy()

    def show_dashboard(self):
        self.login_frame.grid_forget()
        self.dashboard_frame.grid(row=0, column=0, sticky="nsew")
        if not self.sections_data:
            self.handle_refresh()

    def update_status(self, text, color="white"):
        self.status_label.configure(text=text, text_color=color)

    def handle_login(self):
        user = self.username_entry.get()
        pw = self.password_entry.get()
        
        if not user or not pw:
            self.login_status.configure(text="Please fill both fields", text_color="orange")
            return
            
        def login_task():
            self.after(0, lambda: self.login_btn.configure(state="disabled", text="LOGGING IN..."))
            self.engine.start_browser(headless=False) # Keep browser visible for first login
            if self.engine.login(user, pw):
                self.save_config(user, pw)
                self.after(0, self.show_dashboard)
            else:
                self.after(0, lambda: self.login_status.configure(text="Login failed! Check credentials.", text_color="red"))
            self.after(0, lambda: self.login_btn.configure(state="normal", text="LOGIN"))
            
        threading.Thread(target=login_task, daemon=True).start()

    def handle_refresh(self):
        def refresh_task():
            self.after(0, lambda: self.update_status("Fetching sections..."))
            self.after(0, lambda: self.refresh_btn.configure(state="disabled"))
            
            if not self.engine.page:
                self.engine.start_browser()
                
            try:
                self.sections_data = self.engine.get_sections() or []
            except Exception as e:
                print(f"Refresh error: {e}")
                self.sections_data = []
            self.after(0, self.populate_sections)
            self.after(0, lambda: self.update_status("Ready"))
            self.after(0, lambda: self.refresh_btn.configure(state="normal"))
            
        threading.Thread(target=refresh_task, daemon=True).start()

    def populate_sections(self):
        query = self.search_entry.get().lower() if hasattr(self, 'search_entry') else ""
        
        if not self.sections_data or self.sections_data is None:
            return
        
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
            
        self.section_vars = {}
        self.activity_vars = {}
        self.type_filters = {}  # Store type filter checkboxes per section
        self.type_filter_buttons = {}  # Store actual checkbox widgets per section
        self.visible_activities = {}  # Track which activities are currently visible
        
        display_idx = 0
        for section in self.sections_data:
            # Get all activities in this section (not filtered by type yet)
            all_activities = section['activities']
            
            # Detect unique types in this section
            section_types = set(a['modtype'] for a in all_activities if a['modtype'] != "unknown")
            
            # Filter by search query
            activities_to_show = [a for a in all_activities 
                                 if (query in a['name'].lower() or query in section['title'].lower())]
            
            if not activities_to_show: 
                continue

            # Section Header Frame with title and type filters
            header_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
            header_frame.grid(row=display_idx, column=0, sticky="ew", pady=(15, 5), padx=5)
            display_idx += 1
            
            # Section checkbox - MASTER checkbox to show/hide entire section
            s_var = ctk.BooleanVar(value=True)
            s_cb = ctk.CTkCheckBox(header_frame, text=section['title'].upper(), variable=s_var, 
                                   font=("Arial", 16, "bold"), command=lambda v=s_var, t=section['title']: self.toggle_section(t, v))
            s_cb.pack(side="left")
            self.section_vars[section['title']] = s_var
            
            # Select All / Select Pending buttons
            select_all_btn = ctk.CTkButton(header_frame, text="ALL", width=40, height=20, 
                                         command=lambda t=section['title']: self.select_all_activities(t))
            select_all_btn.pack(side="left", padx=5)
            
            select_pending_btn = ctk.CTkButton(header_frame, text="PENDING", width=60, height=20, fg_color="orange",
                                             command=lambda t=section['title']: self.select_pending_activities(t))
            select_pending_btn.pack(side="left", padx=5)
            
            # Type filter checkboxes
            if section_types:
                type_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
                type_frame.pack(side="left", padx=20)
                
                self.type_filters[section['title']] = {}
                self.type_filter_buttons[section['title']] = {}
                for atype in sorted(section_types):
                    type_var = ctk.BooleanVar(value=True)
                    type_cb = ctk.CTkCheckBox(type_frame, text=atype.upper(), variable=type_var, 
                                             font=("Arial", 11), 
                                             command=lambda t=section['title']: self.update_section_visibility(t))
                    type_cb.pack(side="left", padx=5)
                    self.type_filters[section['title']][atype] = type_var
                    self.type_filter_buttons[section['title']][atype] = type_cb
            
            self.activity_vars[section['title']] = []
            self.visible_activities[section['title']] = []
            
            # Only render activities if section checkbox is checked
            if not s_var.get():
                # Section is unchecked - don't render any activities
                continue
            
            # Get active type filters for this section
            active_types = set()
            if section['title'] in self.type_filters:
                active_types = set(t for t, v in self.type_filters[section['title']].items() if v.get())
            
            # Filter activities by selected types and search query
            filtered_activities = [a for a in activities_to_show 
                                  if a['modtype'] in active_types or a['modtype'] == "unknown"]
            
            for activity in filtered_activities:
                a_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
                a_frame.grid(row=display_idx, column=0, sticky="w", padx=40, pady=2)
                display_idx += 1
                
                a_var = ctk.BooleanVar(value=True)
                
                # Format: [checkbox] - type - name
                display_name = f"{activity['modtype'].upper()} - {activity['name']}"
                a_cb = ctk.CTkCheckBox(a_frame, text=display_name, variable=a_var, font=("Arial", 13),
                                     command=lambda t=section['title']: self.check_master_logic(t))
                a_cb.pack(side="left")
                
                # Status badges
                is_done = any(s['isdone'] for s in activity['status'])
                badge_color = "green" if is_done else "orange"
                badge_text = "DONE" if is_done else "PENDING"
                
                ctk.CTkLabel(a_frame, text=badge_text, text_color=badge_color, font=("Arial", 10, "bold"), width=50).pack(side="left", padx=10)
                
                # Button logic based on activity type and accessibility
                if activity['modtype'] == "quiz":
                    # Check if quiz is accessible
                    quiz_accessible = self.engine._is_quiz_accessible(activity)
                    
                    if quiz_accessible:
                        # SOLVE button for quizzes
                        solve_btn = ctk.CTkButton(a_frame, text="SOLVE", width=60, height=20, 
                                                  command=lambda l=activity['link'], n=activity['name'], m=activity['modtype']: self.handle_solve_single(l, n, m))
                        solve_btn.pack(side="left", padx=5)
                        
                        # SCRAP button only if quiz is done
                        if is_done:
                            scrap_btn = ctk.CTkButton(a_frame, text="SCRAP", width=60, height=20, fg_color="orange", 
                                                      command=lambda l=activity['link'], n=activity['name']: self.handle_scrap_single(l, n))
                            scrap_btn.pack(side="left", padx=5)
                else:
                    # OPEN button for non-quiz activities
                    open_btn = ctk.CTkButton(a_frame, text="OPEN", width=60, height=20, fg_color="blue",
                                             command=lambda l=activity['link'], n=activity['name'], m=activity['modtype']: self.handle_open_single(l, n, m))
                    open_btn.pack(side="left", padx=5)
                
                self.activity_vars[section['title']].append((a_var, activity))
                self.visible_activities[section['title']].append((a_var, activity, a_frame))

    def check_master_logic(self, section_title):
        """Update master checkbox based on activity checkboxes state"""
        if section_title not in self.activity_vars:
            return
            
        vars_list = [v for v, act in self.activity_vars[section_title]]
        if not vars_list:
            return
            
        all_checked = all(v.get() for v in vars_list)
        any_checked = any(v.get() for v in vars_list)
        
        # Update master checkbox
        self.section_vars[section_title].set(all_checked)
        
        # Optional: Visual feedback for partial selection
        # Could change master checkbox color here if needed

    def select_all_activities(self, section_title):
        """Select all visible activities in a section"""
        if section_title not in self.visible_activities:
            return
            
        for a_var, activity, frame in self.visible_activities[section_title]:
            a_var.set(True)
        
        self.check_master_logic(section_title)

    def select_pending_activities(self, section_title):
        """Select only pending (not done) activities in a section"""
        if section_title not in self.visible_activities:
            return
            
        for a_var, activity, frame in self.visible_activities[section_title]:
            is_done = any(s['isdone'] for s in activity['status'])
            a_var.set(not is_done)  # Select if not done
        
        self.check_master_logic(section_title)

    def update_section_visibility(self, section_title):
        """Update visibility of activities in a section based on type filters without full re-render"""
        if section_title not in self.visible_activities or section_title not in self.type_filters:
            return
            
        # Get active type filters
        active_types = set(t for t, v in self.type_filters[section_title].items() if v.get())
        
        # Show/hide activities based on type
        for a_var, activity, frame in self.visible_activities[section_title]:
            should_show = activity['modtype'] in active_types or activity['modtype'] == "unknown"
            if should_show:
                frame.grid()
            else:
                frame.grid_remove()

    def toggle_section(self, section_title, var):
        """
        Handle section checkbox toggling.
        If section is UNchecked: block all activities + disable/uncheck type filters
        If section is checked: show activities based on type filters
        Only affects VISIBLE activities, not hidden ones.
        """
        section_is_checked = var.get()
        
        # Update visible activities in this section
        if section_title in self.visible_activities:
            for a_var, activity, frame in self.visible_activities[section_title]:
                a_var.set(section_is_checked)
                if section_is_checked:
                    frame.grid()  # Show if section is checked
                else:
                    frame.grid_remove()  # Hide if section is unchecked
        
        # Disable/enable and check/uncheck type filters
        if section_title in self.type_filter_buttons:
            for type_name, type_cb in self.type_filter_buttons[section_title].items():
                type_cb.configure(state="normal" if section_is_checked else "disabled")
                if not section_is_checked:
                    # Also uncheck type filters when section is unchecked
                    self.type_filters[section_title][type_name].set(False)
                else:
                    # Re-enable type filters when section is checked
                    self.type_filters[section_title][type_name].set(True)
        
        # Don't call populate_sections() here to avoid flicker
        # Instead, rely on the visibility updates above

    def update_search_visibility(self):
        """Update visibility of activities based on search query without full re-render"""
        query = self.search_entry.get().lower()
        
        for section_title in self.visible_activities:
            for a_var, activity, frame in self.visible_activities[section_title]:
                # Check if activity matches search query
                matches_search = (query in activity['name'].lower() or 
                                query in section_title.lower())
                
                # Also check type filters
                active_types = set()
                if section_title in self.type_filters:
                    active_types = set(t for t, v in self.type_filters[section_title].items() if v.get())
                
                matches_type = (activity['modtype'] in active_types or 
                              activity['modtype'] == "unknown")
                
                # Section must be checked
                section_checked = self.section_vars.get(section_title, ctk.BooleanVar(value=True)).get()
                
                should_show = matches_search and matches_type and section_checked
                
                if should_show:
                    frame.grid()
                else:
                    frame.grid_remove()

    def handle_solve_single(self, link, name, modtype):
        def task():
            self.after(0, lambda: self.update_status(f"Solving {name}..."))
            self.engine.solve_activity(link, modtype)
            self.after(0, lambda: self.update_status(f"Finished {name}!", "green"))
            time.sleep(2)
            self.handle_refresh()
            
        threading.Thread(target=task, daemon=True).start()

    def handle_scrap_single(self, link, name):
        def task():
            self.after(0, lambda: self.update_status(f"Scraping answers from {name}..."))
            self.engine.scrap_answers(link)
            self.after(0, lambda: self.update_status(f"Finished scraping {name}!", "green"))
            time.sleep(2)
            self.handle_refresh()
            
        threading.Thread(target=task, daemon=True).start()

    def handle_open_single(self, link, name, modtype):
        def task():
            self.after(0, lambda: self.update_status(f"Opening {name}..."))
            # For non-quiz activities, just navigate to the link
            if not self.engine.page:
                self.engine.start_browser()
            self.engine.page.goto(link)
            self.after(0, lambda: self.update_status(f"Opened {name} in browser", "blue"))
            
        threading.Thread(target=task, daemon=True).start()

    def handle_bulk_solve(self):
        selected_tasks = []
        for section_title, activities in self.activity_vars.items():
            for a_var, activity in activities:
                if a_var.get():
                    selected_tasks.append(activity)
        
        if not selected_tasks:
            self.update_status("No tasks selected!", "orange")
            return
            
        def bulk_task():
            self.after(0, lambda: self.bulk_solve_btn.configure(state="disabled"))
            total = len(selected_tasks)
            for i, task in enumerate(selected_tasks):
                progress = (i + 1) / total
                task_name = task['name']
                task_type = task.get('modtype', 'activity')
                self.after(0, lambda t=task_name, c=i+1, p=progress: 
                           (self.update_status(f"[{c}/{total}] Solving {t}..."), self.progress_bar.set(p)))
                self.engine.solve_activity(task['link'], task_type)
                
            self.after(0, lambda: (self.update_status("Bulk solve completed!", "green"), self.progress_bar.set(1)))
            self.after(0, lambda: self.bulk_solve_btn.configure(state="normal"))
            self.handle_refresh()
            
        threading.Thread(target=bulk_task, daemon=True).start()

if __name__ == "__main__":
    app = App()
    app.mainloop()
