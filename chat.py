import tkinter as tk
from tkinter import ttk, scrolledtext
import uuid


class LCPChat:
    def __init__(self):
        user_id = str(uuid.uuid4()).replace("-", "")[:20]
        self.user_id = user_id.encode("utf-8").ljust(20)

    def create_gui(self):
        self.main_window = tk.Tk()
        self.main_window.title(f"Chat - {self.user_id.decode('utf-8').strip('\x00')}")
        self.main_window.geometry("800x600")

        main_frame = ttk.Frame(self.main_window, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(main_frame, width=200)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        users_label = ttk.Label(left_frame, text="Users")
        users_label.pack(anchor=tk.W, pady=(0, 5))

        users_frame = ttk.Frame(left_frame)
        users_frame.pack(fill=tk.BOTH, expand=True)

        self.users_listbox = tk.Listbox(users_frame)
        self.users_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        users_scrollbar = ttk.Scrollbar(
            users_frame, orient=tk.VERTICAL, command=self.users_listbox.yview
        )
        users_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.users_listbox.config(yscrollcommand=users_scrollbar.set)

        self.users_listbox.bind("<<ListboxSelect>>")

        right_frame = ttk.Frame(main_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        chat_frame = ttk.Frame(right_frame)
        chat_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.chat_text = scrolledtext.ScrolledText(chat_frame, state=tk.DISABLED)
        self.chat_text.pack(fill=tk.BOTH, expand=True)

        input_frame = ttk.Frame(right_frame)
        input_frame.pack(fill=tk.X)

        self.entry_message = ttk.Entry(input_frame)
        self.entry_message.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        send_button = ttk.Button(input_frame, text="Send")
        send_button.pack(side=tk.LEFT)

        file_button = ttk.Button(input_frame, text="Send File")
        file_button.pack(side=tk.LEFT, padx=(5, 0))

        self.main_window.protocol("WM_DELETE_WINDOW")

        self.main_window.mainloop()


if __name__ == "__main__":

    app = LCPChat()
    app.create_gui()
