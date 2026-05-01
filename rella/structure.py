import os

def make_file(path):
    # Create parent folders if needed, then create an empty file
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path, 'w', encoding='utf-8'):
            pass

def main():
    base_dir = "RELLA"

    # Folders
    templates_dir = os.path.join(base_dir, "templates")
    static_dir = os.path.join(base_dir, "static")

    os.makedirs(base_dir, exist_ok=True)
    os.makedirs(templates_dir, exist_ok=True)
    os.makedirs(static_dir, exist_ok=True)

    # Top-level files
    make_file(os.path.join(base_dir, "app.py"))
    make_file(os.path.join(base_dir, "requirements.txt"))

    # Template files
    template_files = [
        "base.html",
        "login.html",
        "register.html",
        "forgot_password.html",
        "dashboard.html",
        "products.html",
        "clients.html",
        "sales.html",
        "pos.html",
        "records.html",
        "stores.html",
        "stock_in.html",
        "transfer.html",
        "movements.html",
        "human.html",
        "comms.html",
        "finances.html",
        "tasks.html",
        "permissions.html",
        "logout.html",
    ]

    for filename in template_files:
        make_file(os.path.join(templates_dir, filename))

    # Static files
    static_files = [
        "rella.css",
        "rella.js",
    ]

    for filename in static_files:
        make_file(os.path.join(static_dir, filename))

    print(f"Project structure created under: {os.path.abspath(base_dir)}")

if __name__ == "__main__":
    main()
